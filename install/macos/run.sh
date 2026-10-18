#!/usr/bin/env bash
#
# Start the container and open a shell inside it.
#
# macOS (Intel and Apple Silicon).
#
#   ./install/macos/run.sh                start and attach
#   ./install/macos/run.sh --novnc        force browser rendering
#   ./install/macos/run.sh --rebuild      rebuild the image first
#   ./install/macos/run.sh --gpu          force the NVIDIA GPU to be attached
#   ./install/macos/run.sh --no-gpu       never attach a GPU
#
# On macOS the simulator does NOT run in the container - the container is Linux
# and the simulator you fetched is a native Mac build. Start the bridge in here,
# then run the simulator on your Mac and point it at 127.0.0.1:4567. The port is
# published for exactly that. See docs/01-setup.md section 1.6.
#
# RViz and other ROS windows open in your browser at http://localhost:8080/vnc.html
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform macos
# macOS has no X server by default, so always render through noVNC.
export FORCE_NOVNC=1

do_start "$@"
