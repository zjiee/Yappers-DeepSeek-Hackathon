#!/usr/bin/env bash
#
# Stop and remove the containers.
#
# Windows, from inside WSL 2.
#
#   ./install/windows/stop.sh           stop
#   ./install/windows/stop.sh --clean   also delete the built image
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
require_wsl
expect_platform wsl
do_stop "$@"
