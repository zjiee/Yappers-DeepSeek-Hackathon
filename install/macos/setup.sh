#!/usr/bin/env bash
#
# Build the hackathon Docker image.
#
# macOS (Intel and Apple Silicon).
#
#   ./install/macos/setup.sh              build (cached)
#   ./install/macos/setup.sh --no-cache   full rebuild
#
# Needs Docker Desktop for Mac, running before you start.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform macos
# macOS has no X server by default, so always render through noVNC.
export FORCE_NOVNC=1

do_build "$@"
