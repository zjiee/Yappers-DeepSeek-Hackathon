#!/usr/bin/env bash
#
# Start the container and open a shell inside it.
#
# Ubuntu / Debian Linux.
#
#   ./install/linux/run.sh                start and attach
#   ./install/linux/run.sh --novnc        force browser rendering
#   ./install/linux/run.sh --rebuild      rebuild the image first
#   ./install/linux/run.sh --gpu          force the NVIDIA GPU to be attached
#   ./install/linux/run.sh --no-gpu       never attach a GPU
#
# Renders straight to your desktop's X server. Add --novnc to use a browser instead.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform linux
do_start "$@"
