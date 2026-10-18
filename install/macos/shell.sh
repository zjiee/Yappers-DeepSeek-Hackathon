#!/usr/bin/env bash
#
# Open another shell in the running container.
#
# macOS (Intel and Apple Silicon).
#
# You will want several: one for the simulator, one for your driver, one for
# the referee.
#
#   ./install/macos/shell.sh
#   ./install/macos/shell.sh 'ros2 topic list'
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform macos
# macOS has no X server by default, so always render through noVNC.
export FORCE_NOVNC=1

do_shell "$@"
