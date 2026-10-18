# Vendored: AutoDRIVE Devkit

This directory is a verbatim copy of the `autodrive_devkit` package that ships
with the AutoDRIVE competition release. **Do not modify anything in it** —
rule 29.

| | |
| --- | --- |
| Upstream | <https://github.com/AutoDRIVE-Ecosystem/AutoDRIVE-RoboRacer-Sim-Racing> |
| Release | `2026-icra` |
| Asset | `autodrive_devkit.zip` (24 146 bytes) |
| SHA-256 | `ac2c3bb49bb32b7c84e000ddc7fecf07e191d3d03d00113d60dc4da693941ee0` |
| Licence | BSD-3-Clause, Copyright (c) 2026 Tinker Twins — see `LICENSE` |
| ROS 2 package | `autodrive_roboracer` |

It is vendored rather than added as a git submodule because the upstream
repository carries the Unity simulator binary in its history and is about
660 MB to clone, against roughly 100 KB for the package we actually need.

**Take it from the release, not from `main`.** The devkit is versioned with the
simulator build it talks to: the two have to agree on the websocket payload,
and `main` tracks whichever event is most recent. The `2026-icra` asset is the
one that matches the `2026-icra` compete simulator this track races on.

Only `test/` is removed, because those are upstream's lint tests and they run
against upstream's own CI configuration, not ours.

## Two things that are not used as shipped

**1. The dependency pins are installed from elsewhere.**
`requirements_python_3.*.txt` are kept here for reference; the image installs
[`docker/devkit-requirements.txt`](../../docker/devkit-requirements.txt)
instead. It is the same dependency set minus the four packages ROS 2 Humble
already provides from apt — numpy, Pillow, OpenCV and transforms3d — which pip
must not replace. The socket.io versions are identical to upstream's and are
load-bearing; that file explains why at length.

**2. The bridge node is launched through a guard.**
`roboracer_referee/sim_bridge.py` imports this package's `autodrive_bridge`
unmodified and wraps its `Bridge` event handler. On the very first frame the
simulator sends no LiDAR array — it has not completed a revolution yet — and
the devkit reads that key unconditionally, raising `KeyError` before it can
reply. Since the protocol is a strict request/response loop, the simulator then
waits for ever and the whole run deadlocks with a full topic list and no
messages on any of it.

This never shows up in the documented manual workflow, where a human presses
**Connect** seconds after the simulator has started and the first payload is
complete. It happens every single time when `-ip`/`-port` are passed on the
command line, which is the only way to automate a run. The guard replies for
that one frame and hands everything afterwards to the devkit untouched. No
sensor value is altered. See the docstring in `sim_bridge.py`.

## Regenerating it

```sh
curl -fL -o /tmp/autodrive_devkit.zip \
  https://github.com/AutoDRIVE-Ecosystem/AutoDRIVE-RoboRacer-Sim-Racing/releases/download/2026-icra/autodrive_devkit.zip
sha256sum /tmp/autodrive_devkit.zip     # compare against the table above
rm -rf external/autodrive_devkit && mkdir -p external/autodrive_devkit
unzip -q /tmp/autodrive_devkit.zip -d /tmp/devkit
cp -r /tmp/devkit/autodrive_devkit/. external/autodrive_devkit/
rm -rf external/autodrive_devkit/test
# keep the licence and this file
git checkout -- external/autodrive_devkit/LICENSE external/autodrive_devkit/VENDOR.md
# then re-record the hashes the integrity check compares against:
./scripts/verify_judging_env.sh --update
```
