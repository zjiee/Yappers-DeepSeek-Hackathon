#!/usr/bin/env bash
#
# Open another shell in the running container.
#
# Windows, from inside WSL 2.
#
# You will want several: one for the simulator, one for your driver, one for
# the referee.
#
#   ./install/windows/shell.sh
#   ./install/windows/shell.sh 'ros2 topic list'
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
require_wsl
expect_platform wsl
do_shell "$@"
