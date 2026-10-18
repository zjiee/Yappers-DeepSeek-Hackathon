#!/usr/bin/env python3
"""The official Track 2 referee.

Watches a run, records it, applies the collision penalties and writes a result
file. It only ever observes the car - it never sends a throttle or steering
command - so the same node is used for practice and for judging.

    ros2 run roboracer_referee referee --ros-args -p team:=my_team
    ros2 launch roboracer_referee evaluate.launch.py team:=my_team driver_pkg:=team_driver

Where Track 1's referee timed laps itself against a finish line it knew the
coordinates of, this one does not: the AutoDRIVE Simulator owns the
start/finish line and the track boundaries and publishes lap count, lap times
and a collision count through the devkit bridge. The referee reads those,
applies the hackathon's rules to them, and writes the result. That makes a
scored run independent of the map file entirely - which matters, because the
compete circuit is released as a simulator build, not as an occupancy grid.

Timing is the simulator's own. It runs on simulated time, so a run scores the
same on a fast desktop and a tired laptop; see docs/05-evaluation.md.
"""

from __future__ import annotations

import json
import math
import os
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import rclpy
from geometry_msgs.msg import Point
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy)
from std_msgs.msg import Bool, Float32, Int32
from visualization_msgs.msg import Marker

from .session import RaceSession, Rules
from .tracks import TrackError, load_track

REFEREE_VERSION = "2.0.0"
RESULT_SCHEMA_VERSION = 3

# Node exit codes, so a shell harness can branch on the outcome.
EXIT_OK = 0
EXIT_NOT_SCORED = 2       # ran, but DNF or disqualified
EXIT_SETUP_FAILED = 3     # never got as far as racing


def devkit_qos() -> QoSProfile:
    """Match the profile the AutoDRIVE bridge publishes with.

    The bridge uses RELIABLE / KEEP_LAST(1) / VOLATILE. A deeper queue on this
    side would only ever hand the referee stale telemetry after a hiccup, and
    stale telemetry is how a lap gets counted twice.
    """
    return QoSProfile(
        durability=QoSDurabilityPolicy.VOLATILE,
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=1,
    )


class Phase:
    WAIT_TELEMETRY = "waiting for the simulator"
    WAIT_DRIVER = "waiting for the driver node"
    RESETTING = "placing the car on the grid"
    RACING = "racing"
    DONE = "finished"


class Referee(Node):

    def __init__(self):
        super().__init__("referee")

        # -- parameters ----------------------------------------------------
        self.declare_parameter("team", "unnamed_team")
        self.declare_parameter("run_id", "")
        self.declare_parameter("track", "")
        self.declare_parameter("track_config", "")
        self.declare_parameter("output_dir", "/hackathon/results")

        self.declare_parameter("warmup_laps", 2)
        self.declare_parameter("timed_laps", 10)
        self.declare_parameter("collision_penalty_s", 10.0)
        self.declare_parameter("max_collisions", 10)   # negative disables the limit
        self.declare_parameter("min_lap_time_s", 1.0)
        self.declare_parameter("session_timeout_s", 900.0)
        self.declare_parameter("stuck_speed_mps", 0.05)
        self.declare_parameter("stuck_timeout_s", 15.0)

        self.declare_parameter("startup_timeout_s", 120.0)
        self.declare_parameter("driver_timeout_s", 60.0)
        self.declare_parameter("wall_timeout_s", 1800.0)
        self.declare_parameter("reset_car", True)
        self.declare_parameter("reset_hold_s", 0.5)
        self.declare_parameter("reset_settle_s", 1.0)
        self.declare_parameter("lap_settle_s", 0.2)

        self.declare_parameter("vehicle_ns", "/autodrive/roboracer_1")
        self.declare_parameter("reset_topic", "/autodrive/reset_command")

        self.team = str(self.get_parameter("team").value).strip() or "unnamed_team"
        self.run_id = str(self.get_parameter("run_id").value).strip() \
            or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.output_dir = str(self.get_parameter("output_dir").value)
        self.startup_timeout_s = float(self.get_parameter("startup_timeout_s").value)
        self.driver_timeout_s = float(self.get_parameter("driver_timeout_s").value)
        self.wall_timeout_s = float(self.get_parameter("wall_timeout_s").value)
        self.reset_car = bool(self.get_parameter("reset_car").value)
        self.reset_hold_s = float(self.get_parameter("reset_hold_s").value)
        self.reset_settle_s = float(self.get_parameter("reset_settle_s").value)
        self.lap_settle_s = float(self.get_parameter("lap_settle_s").value)

        # -- track ---------------------------------------------------------
        # Metadata only: the name that goes in the result file, and the map a
        # team may have used for planning. Nothing here is used to score.
        track_name = str(self.get_parameter("track").value).strip() or None
        track_config = str(self.get_parameter("track_config").value).strip() or None
        try:
            self.track = load_track(track_name, track_config)
        except TrackError as exc:
            self.get_logger().fatal(str(exc))
            raise SystemExit(EXIT_SETUP_FAILED)

        rules = Rules(
            warmup_laps=int(self.get_parameter("warmup_laps").value),
            timed_laps=int(self.get_parameter("timed_laps").value),
            collision_penalty_s=float(self.get_parameter("collision_penalty_s").value),
            max_collisions=int(self.get_parameter("max_collisions").value),
            min_lap_time_s=float(self.get_parameter("min_lap_time_s").value),
            session_timeout_s=float(self.get_parameter("session_timeout_s").value),
            stuck_speed_mps=float(self.get_parameter("stuck_speed_mps").value),
            stuck_timeout_s=float(self.get_parameter("stuck_timeout_s").value),
        )
        try:
            self.session = RaceSession(rules)
        except ValueError as exc:
            self.get_logger().fatal(str(exc))
            raise SystemExit(EXIT_SETUP_FAILED)

        # -- state ---------------------------------------------------------
        self.phase = Phase.WAIT_TELEMETRY
        self.lap_count: Optional[int] = None
        self.lap_time: float = 0.0
        self.last_lap_time: float = 0.0
        self.best_lap_time: float = 0.0
        self.collision_count: Optional[int] = None
        self.speed: float = 0.0
        self.position: Optional[tuple] = None
        self.last_odom_wall: Optional[float] = None
        self.driver_seen = False
        self.phase_started_wall = time.monotonic()
        self.started_wall = time.monotonic()
        self.result_written = False
        self._racing_started_wall: Optional[float] = None
        self._stable_lap_count: Optional[int] = None
        self._pending_lap_count: Optional[int] = None
        self._pending_lap_since: Optional[float] = None
        self._reset_released = False
        self._callback_errors = 0

        # -- ROS interfaces ------------------------------------------------
        ns = str(self.get_parameter("vehicle_ns").value).rstrip("/")
        qos = devkit_qos()

        self.create_subscription(Int32, f"{ns}/lap_count", self._on_lap_count, qos)
        self.create_subscription(Float32, f"{ns}/lap_time", self._on_lap_time, qos)
        self.create_subscription(Float32, f"{ns}/last_lap_time", self._on_last_lap_time, qos)
        self.create_subscription(Float32, f"{ns}/best_lap_time", self._on_best_lap_time, qos)
        self.create_subscription(Int32, f"{ns}/collision_count", self._on_collisions, qos)
        self.create_subscription(Odometry, f"{ns}/odom", self._on_odom, qos)
        # Either command is proof of life; a driver may legitimately hold one
        # of them at zero for a while (a straight needs no steering input).
        self.create_subscription(Float32, f"{ns}/throttle_command", self._on_driver, qos)
        self.create_subscription(Float32, f"{ns}/steering_command", self._on_driver, qos)

        self.reset_pub = self.create_publisher(
            Bool, str(self.get_parameter("reset_topic").value), qos)
        self.status_pub = self.create_publisher(Marker, "/referee/status", 1)

        self.create_timer(0.05, self._tick)
        self.create_timer(1.0, self._publish_markers)

        self._log_banner()

    # -- logging -----------------------------------------------------------

    def _log_banner(self) -> None:
        rules = self.session.rules
        limit = (f", DQ above {rules.max_collisions}" if rules.max_collisions >= 0
                 else " (no limit)")
        self.get_logger().info(
            "\n"
            "=========================================================\n"
            f" RoboRacer Track 2 referee v{REFEREE_VERSION}\n"
            "=========================================================\n"
            f" team          : {self.team}\n"
            f" run id        : {self.run_id}\n"
            f" track         : {self.track.name}\n"
            f" simulator     : AutoDRIVE (compete build)\n"
            f" format        : {rules.warmup_laps} unscored lap(s) + {rules.timed_laps} timed lap(s)\n"
            f" penalty       : +{rules.collision_penalty_s:.0f}s per collision{limit}\n"
            f" results       : {self.output_dir}\n"
            "========================================================="
        )

    # -- subscriptions -----------------------------------------------------

    def _guard(self, where: str, exc: Exception) -> None:
        """Never let a bad message kill the referee mid-run."""
        self._callback_errors += 1
        if self._callback_errors <= 5:
            self.get_logger().error(f"{where}: {exc}\n{traceback.format_exc()}")
        elif self._callback_errors == 6:
            self.get_logger().error(f"{where}: further callback errors suppressed")

    def _on_lap_count(self, msg: Int32) -> None:
        try:
            self.lap_count = int(msg.data)
        except Exception as exc:                            # noqa: BLE001
            self._guard("lap_count callback", exc)

    def _on_lap_time(self, msg: Float32) -> None:
        try:
            value = float(msg.data)
            if math.isfinite(value):
                self.lap_time = value
        except Exception as exc:                            # noqa: BLE001
            self._guard("lap_time callback", exc)

    def _on_last_lap_time(self, msg: Float32) -> None:
        try:
            self.last_lap_time = float(msg.data)
        except Exception as exc:                            # noqa: BLE001
            self._guard("last_lap_time callback", exc)

    def _on_best_lap_time(self, msg: Float32) -> None:
        try:
            self.best_lap_time = float(msg.data)
        except Exception as exc:                            # noqa: BLE001
            self._guard("best_lap_time callback", exc)

    def _on_collisions(self, msg: Int32) -> None:
        try:
            self.collision_count = int(msg.data)
        except Exception as exc:                            # noqa: BLE001
            self._guard("collision_count callback", exc)

    def _on_odom(self, msg: Odometry) -> None:
        try:
            self.last_odom_wall = time.monotonic()
            self.position = (msg.pose.pose.position.x, msg.pose.pose.position.y)
            self.speed = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
        except Exception as exc:                            # noqa: BLE001
            self._guard("odom callback", exc)

    def _on_driver(self, _msg: Float32) -> None:
        self.driver_seen = True

    # -- phases ------------------------------------------------------------

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self.phase_started_wall = time.monotonic()
        self.get_logger().info(f"[{phase}]")

    def _phase_elapsed(self) -> float:
        return time.monotonic() - self.phase_started_wall

    @property
    def _have_telemetry(self) -> bool:
        return (self.lap_count is not None and self.collision_count is not None
                and self.last_odom_wall is not None)

    def _tick(self) -> None:
        try:
            if self.phase == Phase.DONE:
                return

            if time.monotonic() - self.started_wall > self.wall_timeout_s:
                self.get_logger().error(
                    f"Wall-clock limit of {self.wall_timeout_s:.0f}s reached. Ending the run."
                )
                self.session.abort("wall-clock watchdog expired")
                self._conclude()
                return

            if self.phase == Phase.WAIT_TELEMETRY:
                self._tick_wait_telemetry()
            elif self.phase == Phase.WAIT_DRIVER:
                self._tick_wait_driver()
            elif self.phase == Phase.RESETTING:
                self._tick_resetting()
            elif self.phase == Phase.RACING:
                self._tick_racing()
        except SystemExit:
            raise
        except Exception as exc:                            # noqa: BLE001
            self._guard("referee tick", exc)

    def _tick_wait_telemetry(self) -> None:
        if self._have_telemetry:
            self.get_logger().info(
                f"Simulator connected (lap_count={self.lap_count}, "
                f"collisions={self.collision_count})."
            )
            self._enter(Phase.WAIT_DRIVER)
            return

        if self._phase_elapsed() < self.startup_timeout_s:
            missing = []
            if self.lap_count is None:
                missing.append("lap_count")
            if self.collision_count is None:
                missing.append("collision_count")
            if self.last_odom_wall is None:
                missing.append("odom")
            self.get_logger().info(
                f"Waiting for AutoDRIVE telemetry: {', '.join(missing)}",
                throttle_duration_sec=5,
            )
            return

        self._fail_setup(
            f"No telemetry from the AutoDRIVE bridge after {self.startup_timeout_s:.0f}s.\n"
            "Two things have to be running and talking to each other:\n"
            "  1. the devkit bridge   ros2 launch autodrive_roboracer bringup_headless.launch.py\n"
            "  2. the simulator       ./scripts/run_simulator.sh --headless\n"
            "The simulator connects OUT to the bridge on port 4567, so the bridge has to be\n"
            "up first. Check with:  ros2 topic hz /autodrive/roboracer_1/lap_count\n"
            "Starting both at once is what `ros2 launch roboracer_referee simulator.launch.py`\n"
            "is for."
        )

    def _tick_wait_driver(self) -> None:
        if self.driver_seen:
            self.get_logger().info("Driver is publishing.")
            if self.reset_car:
                self._enter(Phase.RESETTING)
            else:
                self._green_flag()
            return
        if self._phase_elapsed() > self.driver_timeout_s:
            ns = str(self.get_parameter("vehicle_ns").value).rstrip("/")
            self._fail_setup(
                f"Nothing published on {ns}/throttle_command or {ns}/steering_command "
                f"after {self.driver_timeout_s:.0f}s.\n"
                "Start your driver node, e.g.:\n"
                "    ros2 run team_driver driver"
            )
        else:
            self.get_logger().info("Waiting for drive commands", throttle_duration_sec=5)

    def _tick_resetting(self) -> None:
        """Teleport the car to the grid and zero the simulator's race counters.

        /autodrive/reset_command is restricted for publishing (rule 31): the
        referee may use it, an entry may not. It is level-triggered, so it has
        to be released again or the simulator resets forever - which is what
        the devkit's own warning about toggling it back to False is about.
        """
        elapsed = self._phase_elapsed()

        if elapsed < self.reset_hold_s:
            self.reset_pub.publish(Bool(data=True))
            return

        if not self._reset_released:
            self.reset_pub.publish(Bool(data=False))
            self._reset_released = True
            return

        # Keep holding it low while the telemetry catches up, so a dropped
        # message cannot leave the simulator latched in reset.
        self.reset_pub.publish(Bool(data=False))
        if elapsed >= self.reset_hold_s + self.reset_settle_s:
            if self.lap_count not in (0, None) or self.lap_time > 2.0:
                self.get_logger().warn(
                    f"After the reset the simulator still reports lap_count="
                    f"{self.lap_count}, lap_time={self.lap_time:.2f}s. Scoring from "
                    f"here anyway - the referee counts laps and collisions relative "
                    f"to this moment, so the totals stay correct."
                )
            self._green_flag()

    def _green_flag(self) -> None:
        self.session.start(self.lap_count or 0, self.collision_count or 0)
        self._racing_started_wall = time.monotonic()
        self._stable_lap_count = self.lap_count or 0
        self._pending_lap_count = self._stable_lap_count
        self._pending_lap_since = None
        self.get_logger().info("Green flag.")
        self._enter(Phase.RACING)

    def _tick_racing(self) -> None:
        if self.session.finished:
            self._conclude()
            return
        if not self._have_telemetry:
            return

        # The simulator reports the current lap's elapsed time and, at each
        # crossing, the time of the lap that just closed. The session turns
        # those into a race clock on the simulator's own time base, which is
        # what the run limits are measured against.
        for event in self.session.update(
                max(0.0, self.lap_time), self._settled_lap_count(),
                self.last_lap_time, self.collision_count, self.speed):
            self.get_logger().info(event)

        if self.session.finished:
            self._conclude()

    def _settled_lap_count(self) -> int:
        """The lap count, held back until the rest of that frame has landed.

        The bridge publishes one frame of telemetry as a burst of separate
        messages, and it publishes `lap_count` *first* - before `last_lap_time`
        and before `collision_count`. Those arrive on different topics and are
        delivered independently, so a referee that acted on `lap_count` the
        instant it changed would close the lap using the *previous* lap's time,
        and would push a collision from the dying moments of that lap onto the
        next one. Both are silent off-by-ones in the number being scored.

        So a change in the lap count is only acted on once it has been stable
        for `lap_settle_s`. At 40 Hz that is eight frames - the rest of the
        burst has certainly arrived. Nothing is lost by waiting: the lap time
        being recorded is the simulator's own, not a clock running here.
        """
        observed = self.lap_count if self.lap_count is not None else 0
        now = time.monotonic()
        if observed != self._pending_lap_count:
            self._pending_lap_count = observed
            self._pending_lap_since = now
        if (self._pending_lap_since is not None
                and now - self._pending_lap_since >= self.lap_settle_s):
            self._stable_lap_count = self._pending_lap_count
            self._pending_lap_since = None
        return self._stable_lap_count if self._stable_lap_count is not None else observed

    # -- visualisation -----------------------------------------------------

    def _publish_markers(self) -> None:
        try:
            text = Marker()
            text.header.frame_id = "world"
            text.header.stamp = self.get_clock().now().to_msg()
            text.ns = "referee"
            text.id = 1
            text.type = Marker.TEXT_VIEW_FACING
            text.action = Marker.ADD
            text.scale.z = 0.6
            text.color.r = text.color.g = text.color.b = text.color.a = 1.0
            x, y = self.position or (0.0, 0.0)
            text.pose.position = Point(x=x, y=y, z=1.5)
            text.pose.orientation.w = 1.0
            text.text = self._status_line()
            self.status_pub.publish(text)
        except Exception as exc:                            # noqa: BLE001
            self._guard("marker publisher", exc)

    def _status_line(self) -> str:
        rules = self.session.rules
        if self.phase not in (Phase.RACING, Phase.DONE):
            return f"{self.team} | {self.phase}"
        best = self.session.best_lap()
        parts = [
            f"{self.team}",
            f"lap {self.session.timed_laps_done}/{rules.timed_laps}",
            f"collisions {self.session.collision_events}"
            + (f"/{rules.max_collisions}" if rules.max_collisions >= 0 else ""),
        ]
        if best:
            parts.append(f"best {best.net_time:.2f}s")
        if self.session.finished:
            parts.append(self.session.status.value)
        return " | ".join(parts)

    # -- finishing ---------------------------------------------------------

    def _fail_setup(self, message: str) -> None:
        self.get_logger().fatal(message)
        self.session.abort("setup failed: " + message.splitlines()[0])
        self._write_result()
        self._shutdown(EXIT_SETUP_FAILED)

    def _conclude(self) -> None:
        if self.phase == Phase.DONE:
            return
        self._enter(Phase.DONE)
        self._publish_markers()
        result = self._write_result()
        self._print_summary(result)
        self._shutdown(EXIT_OK if self.session.scored else EXIT_NOT_SCORED)

    def real_time_factor(self) -> Optional[float]:
        """Simulated seconds raced per wall-clock second of racing.

        Measured from the green flag, not from node start, so the simulator's
        boot time does not drag it down. Around 1.0 is healthy: AutoDRIVE
        advances in real time when the machine can keep up. Well below it means
        the machine could not, which costs patience rather than lap time - the
        recorded times are the simulator's own.
        """
        if self._racing_started_wall is None:
            return None
        wall = time.monotonic() - self._racing_started_wall
        if wall <= 0:
            return None
        return self.session.race_time / wall

    def _build_result(self) -> dict:
        rtf = self.real_time_factor()
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "referee_version": REFEREE_VERSION,
            "track_variant": "track2",
            "simulator": "autodrive",
            "team": self.team,
            "run_id": self.run_id,
            "track": self.track.name,
            "map_path": self.track.map_path,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "simulator_best_lap_time": (round(self.best_lap_time, 4)
                                        if math.isfinite(self.best_lap_time) else None),
            "environment": {
                "real_time_factor": round(rtf, 3) if rtf else None,
                "wall_duration_s": round(time.monotonic() - self.started_wall, 2),
                "callback_errors": self._callback_errors,
            },
        }
        result.update(self.session.result())
        return result

    def _write_result(self) -> dict:
        result = self._build_result()
        if self.result_written:
            return result
        self.result_written = True

        directory = self.output_dir
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            fallback = os.path.join(tempfile.gettempdir(), "roboracer_results")
            self.get_logger().error(f"Cannot create {directory} ({exc}); using {fallback}")
            directory = fallback
            os.makedirs(directory, exist_ok=True)

        safe_team = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.team)
        path = os.path.join(directory, f"{safe_team}__{self.run_id}.json")
        try:
            # Write to a sibling temp file and rename, so a result file is never
            # left half written if the process is killed at the wrong moment.
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=".referee-", suffix=".json")
            with os.fdopen(fd, "w") as handle:
                json.dump(result, handle, indent=2, sort_keys=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            os.chmod(path, 0o644)
            self.get_logger().info(f"Result written to {path}")
            result["_path"] = path
        except OSError as exc:
            self.get_logger().error(f"Could not write the result file: {exc}")
            self.get_logger().error("Result JSON follows so the run is not lost:\n"
                                    + json.dumps(result, indent=2))
        return result

    def _print_summary(self, result: dict) -> None:
        rules = self.session.rules
        lines = [
            "",
            "=========================================================",
            f" RESULT - {self.team} on {self.track.name}",
            "=========================================================",
            f" status        : {result['status']}",
        ]
        if result.get("reason"):
            lines.append(f" reason        : {result['reason']}")
        lines.append(f" laps          : {result['laps_completed']}/{result['laps_required']}")
        limit = f"/{rules.max_collisions}" if rules.max_collisions >= 0 else ""
        lines.append(f" collisions    : {result['collisions']}{limit}"
                     f"  (penalty {result['total_penalty_s']:.0f}s)")

        if result["laps"]:
            lines.append("")
            lines.append("  lap    raw       pen    net")
            for lap in result["laps"]:
                lines.append(f"  {lap['number']:>3}  {lap['raw_time']:>7.3f}  "
                             f"{lap['penalty_s']:>5.0f}  {lap['net_time']:>7.3f}")

        lines.append("")
        if result.get("fastest_raw_lap_time") is not None:
            lines.append(f" fastest lap as driven: {result['fastest_raw_lap_time']:.3f} s "
                         f"(lap {result['fastest_raw_lap_number']}, before penalties)")
        if result["scored"]:
            lines.append(f" BEST LAP      : {result['best_lap_time']:.3f} s  "
                         f"(lap {result['best_lap_number']})")
            lines.append(f" {rules.timed_laps}-LAP TOTAL  : {result['total_time']:.3f} s")
        else:
            lines.append(" NOT SCORED - this run does not produce leaderboard times.")

        rtf = result["environment"]["real_time_factor"]
        if rtf is not None:
            lines.append(f" real-time factor: {rtf:.2f}x"
                         + ("  (machine could not keep up, but times are unaffected)"
                            if rtf < 0.8 else ""))
        for warning in result.get("warnings", []):
            lines.append(f" note          : {warning}")
        lines.append("=========================================================")
        self.get_logger().info("\n".join(lines))

    def _shutdown(self, code: int) -> None:
        self.exit_code = code
        raise SystemExit(code)


def main(args=None) -> int:
    rclpy.init(args=args)
    node = None
    code = EXIT_SETUP_FAILED
    try:
        node = Referee()

        # Ctrl-C and `ros2 launch` teardown must still leave a result file behind.
        def _on_signal(signum, _frame):
            if node and not node.result_written:
                node.get_logger().warn(f"Signal {signum} received; saving a partial result.")
                node.session.abort(f"interrupted by signal {signum}")
                node._write_result()
            raise KeyboardInterrupt

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _on_signal)

        rclpy.spin(node)
        code = EXIT_OK
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else EXIT_OK
    except KeyboardInterrupt:
        code = EXIT_NOT_SCORED
    except Exception:                                       # noqa: BLE001
        traceback.print_exc()
        code = EXIT_SETUP_FAILED
    finally:
        if node is not None:
            if not node.result_written and node.phase != Phase.WAIT_TELEMETRY:
                node.session.abort("referee stopped before the run finished")
                node._write_result()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
