#!/usr/bin/env bash
#
# Stop and remove the containers.
#
# macOS (Intel and Apple Silicon).
#
#   ./install/macos/stop.sh           stop
#   ./install/macos/stop.sh --clean   also delete the built image
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform macos
# macOS has no X server by default, so always render through noVNC.
export FORCE_NOVNC=1

do_stop "$@"
