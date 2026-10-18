# syntax=docker/dockerfile:1
#
# NTU DeepSpeed Recruitment Hackathon 26/27 - Track 2 (RoboRacer Sim Racing)
#
# ROS 2 Humble on Ubuntu 22.04 (Python 3.10), the AutoDRIVE Devkit, and the
# judging environment. The base distribution deliberately matches the official
# AutoDRIVE competition image (`autodriveecosystem/autodrive_roboracer_api`),
# which is `ros:humble`, so anything that runs here runs there.
#
# The AutoDRIVE Simulator is NOT baked into this image. It is a 140 MB Unity
# binary downloaded per platform by scripts/fetch_simulator.sh into
# `simulator/`, which arrives through the bind mount at /hackathon. That keeps
# the image small and lets a macOS or Windows team run the native simulator on
# the host while the devkit stays in the container.
#
# The build context is the REPOSITORY ROOT, not this directory:
#     docker build -f docker/Dockerfile -t roboracer_track2 .
# or just use the setup script for your platform, e.g. install/linux/setup.sh
#
# Portions derived from the AutoDRIVE Ecosystem (BSD-3-Clause, Copyright (c)
# 2026 Tinker Twins). See external/autodrive_devkit/.

ARG ROS_DISTRO=humble
FROM ros:${ROS_DISTRO}

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=humble \
    SIM_WS=/sim_ws \
    RACE_WS=/hackathon/race_ws \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    XDG_RUNTIME_DIR=/tmp/runtime-root \
    AUTODRIVE_SIM_PORT=4567

# XDG_RUNTIME_DIR: Unity writes there on startup and complains loudly when it
#   is unset, which it is in a container.

# ---------------------------------------------------------------------------
# 1. System dependencies
#
# Three groups: build tooling, the ROS packages the devkit and the judging
# environment need, and the graphics/audio libraries the Unity simulator links
# against. The last group is needed even for `-batchmode -nographics`, because
# the player still resolves its shared libraries at load time.
#
# Listed explicitly rather than left to rosdep, so a failure names the package
# that is missing instead of dying inside a resolver.
# ---------------------------------------------------------------------------
RUN set -euxo pipefail; \
    apt-get update -qq; \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        nano \
        net-tools \
        python3-dev \
        python3-numpy \
        python3-opencv \
        python3-pil \
        python3-pip \
        python3-transforms3d \
        tmux \
        unzip \
        vim \
        ros-${ROS_DISTRO}-ackermann-msgs \
        ros-${ROS_DISTRO}-cv-bridge \
        ros-${ROS_DISTRO}-imu-tools \
        ros-${ROS_DISTRO}-rqt-graph \
        ros-${ROS_DISTRO}-rviz2 \
        ros-${ROS_DISTRO}-tf-transformations \
        ros-${ROS_DISTRO}-teleop-twist-keyboard \
        libvulkan1 mesa-vulkan-drivers \
        libgl1 libgl1-mesa-dri libegl1 libgbm1 libdrm2 libglvnd0 libglu1-mesa \
        libgtk-3-0 libnss3 libx11-6 libxcursor1 libxi6 libxinerama1 \
        libxrandr2 libxss1 libxxf86vm1 libsm6 libxext6 \
        libasound2 libpulse0 libc++1 libc++abi1 \
        xvfb ffmpeg; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p "${XDG_RUNTIME_DIR}"; \
    chmod 700 "${XDG_RUNTIME_DIR}"

# ---------------------------------------------------------------------------
# 2. The devkit's Python dependencies
#
# The socket.io pins are load-bearing and are not a mistake. Read the comments
# in devkit-requirements.txt before changing any of them: a newer python-socketio
# gives a bridge that connects and then publishes nothing, for ever, with no
# error anywhere.
# ---------------------------------------------------------------------------
COPY docker/devkit-requirements.txt /opt/devkit-requirements.txt
RUN set -euxo pipefail; \
    python3 -m pip install --no-cache-dir --upgrade pip; \
    python3 -m pip install --no-cache-dir -r /opt/devkit-requirements.txt; \
    python3 -c "import socketio, engineio, gevent, attrdict, numpy, cv2, transforms3d; \
                from importlib.metadata import version as v; \
                assert v('python-engineio').startswith('3.'), \
                    'python-engineio must be 3.x; the simulator speaks Engine.IO v3 framing'; \
                print('socketio', v('python-socketio'), '/ engineio', v('python-engineio'), \
                      '/ numpy', numpy.__version__)"

# ---------------------------------------------------------------------------
# 3. The AutoDRIVE Devkit
#
# Vendored at external/autodrive_devkit (see its VENDOR.md for the upstream
# commit). Built into its own overlay so that a team rebuilding the race
# workspace can never accidentally rebuild - or shadow - the devkit.
#
# The greps turn "upstream moved a topic" into a failed build rather than a
# referee that waits forever for telemetry that is never coming.
# ---------------------------------------------------------------------------
COPY external/autodrive_devkit ${SIM_WS}/src/autodrive_roboracer
RUN set -euxo pipefail; \
    config=${SIM_WS}/src/autodrive_roboracer/autodrive_roboracer/config.py; \
    test -f ${SIM_WS}/src/autodrive_roboracer/package.xml \
      || { echo "ERROR: external/autodrive_devkit is empty." >&2; exit 1; }; \
    for topic in throttle_command steering_command lap_count collision_count last_lap_time; do \
        grep -q "roboracer_1/${topic}" "${config}" \
          || { echo "ERROR: the devkit no longer exposes /autodrive/roboracer_1/${topic}; judging needs it." >&2; exit 1; }; \
    done; \
    echo "Devkit topics verified."; \
    set +u; source /opt/ros/${ROS_DISTRO}/setup.bash; set -u; \
    cd ${SIM_WS}; \
    colcon build --symlink-install; \
    test -f ${SIM_WS}/install/local_setup.bash

# ---------------------------------------------------------------------------
# 4. The circuit
#
# A fallback copy, used when the repository is not bind-mounted. Normally
# /hackathon is mounted and the map is read from there, so what teams edit is
# what runs. Nothing in a scored run depends on the map: lap times and
# collisions come from the simulator itself (docs/04-evaluation.md).
# ---------------------------------------------------------------------------
COPY maps /opt/hackathon_maps
RUN set -euxo pipefail; \
    test -f /opt/hackathon_maps/tracks.yaml; \
    echo "Hackathon circuit installed."

# ---------------------------------------------------------------------------
# 5. Shell environment
# ---------------------------------------------------------------------------
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN set -euxo pipefail; \
    chmod +x /usr/local/bin/entrypoint.sh; \
    printf '%s\n' \
      '# --- roboracer hackathon (track 2) ---' \
      'source /opt/ros/humble/setup.bash' \
      '[ -f /sim_ws/install/local_setup.bash ] && source /sim_ws/install/local_setup.bash' \
      '[ -f /hackathon/race_ws/install/local_setup.bash ] && source /hackathon/race_ws/install/local_setup.bash' \
      'export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}' \
      'export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/tmp/runtime-root}' \
      'cd /hackathon 2>/dev/null || true' \
      >> /root/.bashrc

# ---------------------------------------------------------------------------
# 6. Team-declared dependencies
#
# Extra packages are allowed as long as they are declared (rule 37). These two
# files are the declaration, and this step is what makes them real.
#
# Deliberately LAST: editing either file rebuilds one small layer rather than
# the whole image, so judges can rebuild per submission in seconds.
# ---------------------------------------------------------------------------
COPY race_ws/src/team_driver/apt-packages.txt \
     race_ws/src/team_driver/requirements.txt \
     /opt/team-deps/
RUN set -euxo pipefail; \
    apt_list="$(grep -vE '^[[:space:]]*(#|$)' /opt/team-deps/apt-packages.txt || true)"; \
    if [ -n "${apt_list}" ]; then \
        echo "Installing team-declared apt packages: ${apt_list}"; \
        apt-get update -qq; \
        apt-get install -y --no-install-recommends ${apt_list}; \
        rm -rf /var/lib/apt/lists/*; \
    else \
        echo "No team apt packages declared."; \
    fi; \
    if grep -qvE '^[[:space:]]*(#|$)' /opt/team-deps/requirements.txt; then \
        echo "Installing team-declared Python packages:"; \
        grep -vE '^[[:space:]]*(#|$)' /opt/team-deps/requirements.txt; \
        python3 -m pip install --no-cache-dir -r /opt/team-deps/requirements.txt; \
    else \
        echo "No team Python packages declared."; \
    fi; \
    python3 -c "import socketio, engineio; from engineio import async_drivers" \
      || { echo "ERROR: a declared package broke the devkit's Python environment." >&2; exit 1; }

WORKDIR /hackathon
EXPOSE 4567
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
