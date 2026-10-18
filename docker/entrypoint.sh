#!/usr/bin/env bash
# Sources every ROS overlay that exists, then execs whatever was asked for.
# Used for both `docker run ... bash` and `docker exec` style one-shot commands.
set -eo pipefail

source /opt/ros/humble/setup.bash

if [ -f /sim_ws/install/local_setup.bash ]; then
    source /sim_ws/install/local_setup.bash
else
    echo "WARNING: /sim_ws is not built. The AutoDRIVE Devkit will not be available." >&2
fi

# The race workspace lives on the bind mount, so it is only present once the
# team has built it. Missing is normal on a fresh container.
if [ -f /hackathon/race_ws/install/local_setup.bash ]; then
    source /hackathon/race_ws/install/local_setup.bash
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-root}"
mkdir -p "${XDG_RUNTIME_DIR}" 2>/dev/null || true

exec "$@"
