#!/usr/bin/env bash
#
# Open another shell in the running container.
#
# Ubuntu / Debian Linux.
#
# You will want several: one for the simulator, one for your driver, one for
# the referee.
#
#   ./install/linux/shell.sh
#   ./install/linux/shell.sh 'ros2 topic list'
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform linux
do_shell "$@"
