#!/usr/bin/env bash
#
# Build the hackathon Docker image.
#
# Ubuntu / Debian Linux.
#
#   ./install/linux/setup.sh              build (cached)
#   ./install/linux/setup.sh --no-cache   full rebuild
#
# Needs Docker Engine and your user in the 'docker' group - see docs/01-setup.md.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
expect_platform linux
do_build "$@"
