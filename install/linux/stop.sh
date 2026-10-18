#!/usr/bin/env bash
#
# Stop and remove the containers.
#
# Ubuntu / Debian Linux.
#
#   ./install/linux/stop.sh           stop
#   ./install/linux/stop.sh --clean   also delete the built image
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform linux
do_stop "$@"
