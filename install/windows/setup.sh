#!/usr/bin/env bash
#
# Build the hackathon Docker image.
#
# Windows, from inside WSL 2.
#
#   ./install/windows/setup.sh              build (cached)
#   ./install/windows/setup.sh --no-cache   full rebuild
#
# Run this from a WSL terminal ('wsl ~'), not PowerShell. Docker Desktop must be
# running with WSL integration enabled for your distro - see docs/01-setup.md.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
require_wsl
expect_platform wsl
do_build "$@"
