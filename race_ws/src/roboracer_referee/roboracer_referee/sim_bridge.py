#!/usr/bin/env python3
"""The AutoDRIVE Devkit bridge, with the first-frame deadlock guarded.

    ros2 run roboracer_referee sim_bridge

This is `autodrive_roboracer/autodrive_bridge` - the real devkit node, imported
and run unmodified. All it adds is a guard around one edge case that makes an
automated headless run impossible otherwise.

WHAT GOES WRONG WITHOUT IT
--------------------------
The simulator and the bridge run a strict request/response loop. Every frame,
the simulator emits a `Bridge` event carrying its sensors, and the bridge's
handler replies with a throttle and a steering command. The simulator sends
nothing further until that reply arrives.

On the very first frame the simulator has not yet completed a LiDAR revolution,
so it omits `V1 LIDAR Range Array` from the payload entirely - every other key
is there, that one is not. The devkit reads the key unconditionally:

    autodrive.lidar_range_array = np.fromstring(gzip.decompress(
        base64.b64decode(data["V1 LIDAR Range Array"])) ... )

which raises `KeyError`, which kills the greenlet handling that event *before*
it reaches `sio.emit`. The simulator waits for a reply that is never coming,
the bridge waits for a frame that is never coming, and the whole thing sits
there with an ESTABLISHED socket, a full set of ROS topics and not one message
published on any of them. From the outside it looks exactly like a simulator
that failed to start.

It does not happen when a human drives the setup, which is why it has survived:
the documented workflow is to launch the simulator with a window, let it run,
and then press **Connect** on the Menu Panel. By then the LiDAR has been
spinning for seconds and the first payload the bridge ever sees is complete.
Passing `-ip`/`-port` on the command line - the only way to automate this -
connects on frame zero instead, and loses that race every time.

WHAT THE GUARD DOES
-------------------
If a payload arrives with no LiDAR array, it answers the simulator with the
commands currently in effect and does not run the devkit's handler for that
frame. The loop continues, and frame two - 25 ms later, with a full scan -
is handled by the devkit exactly as written.

The devkit's own source is neither edited nor vendored twice; this imports it
and re-registers its handler behind a wrapper. Rule 29 forbids modifying the
devkit and this does not: no sensor value is altered, no command is
synthesised beyond the neutral one the simulator would have received anyway,
and after the first frame the wrapper is a pass-through.
"""

from __future__ import annotations

import sys

import autodrive_roboracer.autodrive_bridge as devkit

LIDAR_KEY = "V1 LIDAR Range Array"


def install_guard() -> None:
    """Wrap the devkit's `Bridge` handler in place."""
    handlers = devkit.sio.handlers.get("/", {})
    inner = handlers.get("Bridge")
    if inner is None:
        raise RuntimeError(
            "The AutoDRIVE devkit did not register a 'Bridge' event handler. "
            "external/autodrive_devkit may be from a different release - check "
            "its VENDOR.md."
        )

    skipped = {"count": 0}

    def guarded(sid, data):
        if data and LIDAR_KEY not in data:
            skipped["count"] += 1
            if skipped["count"] <= 3:
                print(f"[sim_bridge] frame without {LIDAR_KEY}; replying and "
                      f"waiting for the first full scan.", flush=True)
            elif skipped["count"] == 4:
                print("[sim_bridge] further LiDAR-less frames will not be logged. "
                      "More than a handful is not normal - check the simulator log.",
                      flush=True)
            # Keep the loop turning. These are the values the devkit itself
            # would have sent for this frame: whatever the driver last
            # published, or zero before it has published anything.
            devkit.sio.emit("Bridge", data={
                "V1 Throttle": str(devkit.autodrive.throttle_command),
                "V1 Steering": str(devkit.autodrive.steering_command),
                "V1 Reset": str(devkit.autodrive.reset_command),
            })
            return None
        return inner(sid, data)

    handlers["Bridge"] = guarded
    devkit.sio.handlers["/"] = handlers


def main(args=None) -> int:
    install_guard()
    print("[sim_bridge] AutoDRIVE devkit bridge, first-frame guard installed. "
          "Listening on port 4567.", flush=True)
    try:
        devkit.main()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
