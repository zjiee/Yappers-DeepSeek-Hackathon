#!/usr/bin/env bash
#
# Start the container and open a shell inside it.
#
# Windows, from inside WSL 2.
#
#   ./install/windows/run.sh                start and attach
#   ./install/windows/run.sh --novnc        force browser rendering
#   ./install/windows/run.sh --rebuild      rebuild the image first
#   ./install/windows/run.sh --gpu          force the NVIDIA GPU to be attached
#   ./install/windows/run.sh --no-gpu       never attach a GPU
#
# Uses WSLg for the simulator window. Add --novnc if WSLg is unavailable.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
require_wsl
expect_platform wsl
do_start "$@"
