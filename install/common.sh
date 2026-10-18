#!/usr/bin/env bash
# Shared helpers for the host-side scripts. Sourced, never executed directly.

set -euo pipefail

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
INSTALL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${INSTALL_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker/docker-compose.yml"
GPU_COMPOSE_FILE="${REPO_ROOT}/docker/docker-compose.gpu.yml"
ENV_FILE="${REPO_ROOT}/docker/.env"

IMAGE_NAME="${IMAGE_NAME:-roboracer_track2}"
CONTAINER_NAME="${CONTAINER_NAME:-roboracer_track2}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-roboracer_track2}"
export IMAGE_NAME CONTAINER_NAME COMPOSE_PROJECT_NAME

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
if [ -t 2 ] && [ -z "${NO_COLOR:-}" ]; then
    _C_RED=$'\033[31m'; _C_YLW=$'\033[33m'; _C_GRN=$'\033[32m'
    _C_BLU=$'\033[34m'; _C_OFF=$'\033[0m'
else
    _C_RED=""; _C_YLW=""; _C_GRN=""; _C_BLU=""; _C_OFF=""
fi

# Print the comment block at the top of a script as its usage text. Reading it
# out of the file keeps --help and the actual header from drifting apart.
print_header_usage() {
    awk 'NR > 1 && /^#/ { sub(/^#[[:space:]]?/, ""); print; next }
         NR > 1         { exit }' "$1"
}

info()  { printf '%s==>%s %s\n'  "${_C_BLU}" "${_C_OFF}" "$*" >&2; }
ok()    { printf '%s OK %s %s\n' "${_C_GRN}" "${_C_OFF}" "$*" >&2; }
warn()  { printf '%swarn%s %s\n' "${_C_YLW}" "${_C_OFF}" "$*" >&2; }
die()   { printf '%serror%s %s\n' "${_C_RED}" "${_C_OFF}" "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
# Environment detection
# --------------------------------------------------------------------------

# True when this script is running inside the hackathon container itself, in
# which case Docker must not be used - the caller is already where it wants
# to be. /sim_ws is only ever present inside the image.
in_container() { [ -d /sim_ws ] && [ -f /opt/ros/humble/setup.bash ]; }

detect_platform() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)
            if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

require_docker() {
    command -v docker >/dev/null 2>&1 \
        || die "docker is not on PATH. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux), then re-run. See docs/01-setup.md"

    if ! docker info >/dev/null 2>&1; then
        case "$(detect_platform)" in
            macos|windows|wsl)
                die "Cannot talk to the Docker daemon. Is Docker Desktop running? (On Windows, also check Settings > Resources > WSL integration has your distro enabled.)" ;;
            *)
                die "Cannot talk to the Docker daemon. Try 'sudo systemctl start docker', and make sure your user is in the 'docker' group (see docs/01-setup.md)." ;;
        esac
    fi
}

# True when an NVIDIA GPU is visible to this shell. Docker may still refuse to
# attach it, which is why the caller retries rather than trusting this.
gpu_available() {
    command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

# Resolve `docker compose` (v2 plugin) or `docker-compose` (v1 standalone), and
# decide whether to merge the GPU overlay.
COMPOSE=()
GPU_MODE="${GPU_MODE:-auto}"          # auto | on | off
GPU_ACTIVE=0
require_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE=(docker-compose)
    else
        die "Neither 'docker compose' nor 'docker-compose' is available. Update Docker Desktop, or install the compose plugin."
    fi
    COMPOSE+=(-p "${COMPOSE_PROJECT_NAME}" -f "${COMPOSE_FILE}")

    GPU_ACTIVE=0
    case "${GPU_MODE}" in
        on)   GPU_ACTIVE=1 ;;
        auto) if gpu_available; then GPU_ACTIVE=1; fi ;;
    esac
    if [ "${GPU_ACTIVE}" = "1" ] && [ -f "${GPU_COMPOSE_FILE}" ]; then
        COMPOSE+=(-f "${GPU_COMPOSE_FILE}")
    else
        GPU_ACTIVE=0
    fi

    if [ -f "${ENV_FILE}" ]; then
        COMPOSE+=(--env-file "${ENV_FILE}")
    fi
    return 0
}

# --------------------------------------------------------------------------
# Repository checks
# --------------------------------------------------------------------------

# The AutoDRIVE Devkit is vendored into this repository rather than pulled in
# as a submodule, so there is nothing to fetch - but a half-copied checkout
# produces a confusing mid-build failure, so check it up front.
require_devkit() {
    local sentinel
    for sentinel in external/autodrive_devkit/package.xml \
                    external/autodrive_devkit/autodrive_roboracer/autodrive_bridge.py; do
        [ -f "${REPO_ROOT}/${sentinel}" ] || die \
"${sentinel} is missing, so the image cannot be built.
The AutoDRIVE Devkit is committed to this repository - it is not a submodule -
so this usually means an incomplete checkout. Try:
    git -C '${REPO_ROOT}' status
    git -C '${REPO_ROOT}' checkout -- external/autodrive_devkit"
    done
    return 0
}

# The simulator is a separate ~140 MB download (scripts/fetch_simulator.sh).
# Without it the container comes up fine and every ROS node works; there is
# just nothing to race against. Warn rather than refuse - plenty of useful work
# happens without it, and teams on macOS run it on the host instead.
simulator_installed() {
    [ -f "${REPO_ROOT}/simulator/autodrive_simulator/AutoDRIVE Simulator.x86_64" ] \
        || [ -e "${REPO_ROOT}/simulator/autodrive_simulator/AutoDRIVE Simulator.app" ] \
        || [ -f "${REPO_ROOT}/simulator/autodrive_simulator/AutoDRIVE Simulator.exe" ]
}

warn_if_no_simulator() {
    simulator_installed && return 0
    warn "The AutoDRIVE Simulator is not installed in simulator/."
    warn "Fetch it once with:  ./scripts/fetch_simulator.sh"
    return 0
}

image_exists() { docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; }

container_running() {
    [ -n "$(docker ps -q -f "name=^${CONTAINER_NAME}$" -f status=running 2>/dev/null)" ]
}

# --------------------------------------------------------------------------
# Display configuration
#
# Writes docker/.env so that docker-compose.yml, which cannot branch on the
# host platform by itself, gets the right DISPLAY and profile.
# --------------------------------------------------------------------------
write_env_file() {
    local platform display x11_socket profiles
    platform="$(detect_platform)"
    profiles=""
    x11_socket="/tmp/.X11-unix"

    if [ "${FORCE_NOVNC:-0}" = "1" ]; then
        platform="macos"
    fi

    case "${platform}" in
        linux)
            display="${DISPLAY:-:0}"
            if [ ! -d /tmp/.X11-unix ]; then
                warn "No X11 socket at /tmp/.X11-unix - falling back to noVNC."
                platform="macos"
            fi
            ;;
        wsl)
            # WSLg exposes the X server through /tmp/.X11-unix just like native Linux.
            display="${DISPLAY:-:0}"
            if [ ! -d /tmp/.X11-unix ]; then
                warn "WSLg is not available (no /tmp/.X11-unix) - falling back to noVNC."
                platform="macos"
            fi
            ;;
    esac

    if [ "${platform}" = "macos" ] || [ "${platform}" = "windows" ] || [ "${platform}" = "unknown" ]; then
        display="novnc:0.0"
        profiles="novnc"
        # Compose still needs a real path to bind; an unused empty dir is fine.
        x11_socket="${REPO_ROOT}/docker/.x11-placeholder"
        mkdir -p "${x11_socket}"
    fi

    umask 022
    cat > "${ENV_FILE}" <<ENVEOF
# Generated by install/<os>/run.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ') - do not edit by hand.
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}
IMAGE_NAME=${IMAGE_NAME}
CONTAINER_NAME=${CONTAINER_NAME}
DISPLAY=${display}
X11_SOCKET=${x11_socket}
COMPOSE_PROFILES=${profiles}
NOVNC_PORT=${NOVNC_PORT:-8080}
ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
LIBGL_ALWAYS_SOFTWARE=${LIBGL_ALWAYS_SOFTWARE:-0}
ENVEOF

    RESOLVED_DISPLAY="${display}"
    RESOLVED_PROFILES="${profiles}"
}

# Grant the container access to the host X server, and take it back on exit.
x11_allow() {
    command -v xhost >/dev/null 2>&1 || return 0
    xhost +local:root >/dev/null 2>&1 || true
    trap 'xhost -local:root >/dev/null 2>&1 || true' EXIT
}


# --------------------------------------------------------------------------
# Platform guard
#
# The per-OS folders exist so the instructions can name one path per platform.
# Running the wrong folder's script usually still works, so warn, do not refuse.
# --------------------------------------------------------------------------
expect_platform() {
    local wanted actual suggestion
    wanted="$1"
    actual="$(detect_platform)"
    [ "${wanted}" = "${actual}" ] && return 0

    case "${actual}" in
        macos)   suggestion="install/macos" ;;
        wsl)     suggestion="install/windows" ;;
        linux)   suggestion="install/linux" ;;
        windows) suggestion="install/windows, run from inside WSL" ;;
        *)       suggestion="" ;;
    esac
    warn "This is the ${wanted} script but the host looks like ${actual}."
    [ -n "${suggestion}" ] && warn "You probably want ${suggestion}/ instead. Continuing anyway."
    return 0
}

# WSL is a hard requirement on Windows: Docker Desktop on its own cannot run
# these shell scripts or forward the simulator window.
require_wsl() {
    case "$(detect_platform)" in
        windows)
            die "Run this from inside WSL, not PowerShell or Git Bash.
Open a WSL terminal first:
    wsl ~
then run the script again. See docs/01-setup.md." ;;
        *) return 0 ;;
    esac
}

# --------------------------------------------------------------------------
# Actions, shared by every platform's wrappers
# --------------------------------------------------------------------------

do_build() {
    case "${1:-}" in -h|--help) print_header_usage "$0"; return 0 ;; esac
    in_container && die "You are already inside the container. Run this on your host machine."

    local extra arg
    extra=()
    for arg in "$@"; do
        case "${arg}" in
            --no-cache|--pull) extra+=("${arg}") ;;
            *) die "Unknown argument: ${arg}  (accepted: --no-cache, --pull)" ;;
        esac
    done

    require_docker
    require_compose
    require_devkit

    info "Building ${IMAGE_NAME}. The first build takes 10-20 minutes."
    if [ ${#extra[@]} -gt 0 ]; then
        "${COMPOSE[@]}" build "${extra[@]}" sim
    else
        "${COMPOSE[@]}" build sim
    fi
    ok "Image ${IMAGE_NAME} is ready. Start it with the run script in this folder."
}

do_start() {
    case "${1:-}" in -h|--help) print_header_usage "$0"; return 0 ;; esac
    in_container && die "You are already inside the container."

    local rebuild arg i up_args
    rebuild=0
    for arg in "$@"; do
        case "${arg}" in
            --novnc)   export FORCE_NOVNC=1 ;;
            --rebuild) rebuild=1 ;;
            --gpu)     GPU_MODE=on ;;
            --no-gpu)  GPU_MODE=off ;;
            *) die "Unknown argument: ${arg}  (accepted: --novnc, --rebuild, --gpu, --no-gpu)" ;;
        esac
    done

    require_docker
    require_devkit
    warn_if_no_simulator
    write_env_file
    require_compose          # after write_env_file, so --env-file is picked up

    if [ "${rebuild}" = "1" ] || ! image_exists; then
        info "Image ${IMAGE_NAME} is missing or a rebuild was requested."
        "${COMPOSE[@]}" build sim
    fi

    case "${RESOLVED_PROFILES}" in
        *novnc*)
            info "Display: noVNC (DISPLAY=${RESOLVED_DISPLAY})"
            up_args=(--profile novnc up -d)
            ;;
        *)
            info "Display: host X server (DISPLAY=${RESOLVED_DISPLAY})"
            x11_allow
            up_args=(up -d sim)
            ;;
    esac

    if [ "${GPU_ACTIVE}" = "1" ]; then
        info "GPU: attaching the NVIDIA device (pass --no-gpu to skip)."
    else
        info "GPU: not attached."
    fi

    # Attaching a GPU fails hard when Docker has no device driver for it, and
    # that is not a reason to leave someone without a simulator. Fall back.
    if ! "${COMPOSE[@]}" "${up_args[@]}"; then
        if [ "${GPU_ACTIVE}" = "1" ]; then
            warn "Startup failed with the GPU attached - Docker may have no NVIDIA device driver configured."
            info "Retrying without it. Use --no-gpu to go straight there next time."
            GPU_MODE=off
            require_compose
            "${COMPOSE[@]}" "${up_args[@]}" \
                || die "Startup failed without the GPU too. See docs/01-setup.md for troubleshooting."
        else
            die "Startup failed. See docs/01-setup.md for troubleshooting."
        fi
    fi

    case "${RESOLVED_PROFILES}" in
        *novnc*)
            ok "The simulator window opens at http://localhost:${NOVNC_PORT:-8080}/vnc.html - click Connect."
            ;;
    esac

    for i in $(seq 1 30); do
        container_running && break
        sleep 1
    done
    if ! container_running; then
        warn "The container did not come up. Recent logs:"
        "${COMPOSE[@]}" logs --tail 50 sim >&2 || true
        die "Startup failed. See docs/01-setup.md for troubleshooting."
    fi

    ok "Container ${CONTAINER_NAME} is running."
    info "Opening a shell. Use shell.sh in this folder for more terminals, stop.sh to shut down."
    exec docker exec -it "${CONTAINER_NAME}" bash
}

do_shell() {
    case "${1:-}" in -h|--help) print_header_usage "$0"; return 0 ;; esac
    in_container && die "You are already inside the container - open a new terminal tab instead."
    require_docker
    container_running \
        || die "Container ${CONTAINER_NAME} is not running. Start it with run.sh in this folder."
    if [ $# -gt 0 ]; then
        exec docker exec -it "${CONTAINER_NAME}" /usr/local/bin/entrypoint.sh bash -lc "$*"
    fi
    exec docker exec -it "${CONTAINER_NAME}" bash
}

do_stop() {
    case "${1:-}" in -h|--help) print_header_usage "$0"; return 0 ;; esac
    in_container && die "You are already inside the container. Run this on your host machine."

    local clean arg
    clean=0
    for arg in "$@"; do
        case "${arg}" in
            --clean) clean=1 ;;
            *) die "Unknown argument: ${arg}  (accepted: --clean)" ;;
        esac
    done

    require_docker
    require_compose

    info "Stopping containers."
    "${COMPOSE[@]}" --profile novnc down --remove-orphans || true

    if [ "${clean}" = "1" ]; then
        info "Removing image ${IMAGE_NAME}."
        docker image rm -f "${IMAGE_NAME}" >/dev/null 2>&1 || true
    fi
    ok "Stopped. Your code lives on the bind mount and is untouched."
}
