#!/usr/bin/env bash
#
# Start the AutoDRIVE Simulator on its own.
#
# Most of the time you do not need this - `ros2 launch roboracer_referee
# simulator.launch.py` starts the bridge and the simulator together, and
# evaluate.sh does the whole thing. Use this when you want the simulator
# running independently of a run: to look at the circuit, to drive it by hand,
# or to keep it up across several evaluations.
#
#   ./scripts/run_simulator.sh                with a window
#   ./scripts/run_simulator.sh --headless     no graphics device at all
#   ./scripts/run_simulator.sh --host 172.17.0.2 --port 4567
#
# Options
#   --headless        -batchmode -nographics: no window, no GPU, much faster.
#                     The LiDAR, the physics and the lap timing all still work;
#                     the front camera does not.
#   --xvfb            render into a virtual framebuffer instead. Slower than
#                     --headless, but the camera works and there is no window.
#   --host ADDRESS    where the devkit bridge is listening   (default 127.0.0.1)
#   --port PORT       the bridge's port                      (default 4567)
#   --path FILE       simulator executable to run
#
# The simulator is the CLIENT: it dials out to the bridge at --host:--port on
# startup. Start the bridge first, or it has nothing to connect to:
#
#     ros2 launch autodrive_roboracer bringup_headless.launch.py
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../install" && pwd)/common.sh"

HEADLESS=0
XVFB=0
HOST="127.0.0.1"
PORT="4567"
SIM_PATH="${AUTODRIVE_SIM_PATH:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        --headless) HEADLESS=1; shift ;;
        --xvfb)     XVFB=1; shift ;;
        --host)     HOST="${2:?--host needs a value}"; shift 2 ;;
        --port)     PORT="${2:?--port needs a value}"; shift 2 ;;
        --path)     SIM_PATH="${2:?--path needs a value}"; shift 2 ;;
        -h|--help)  print_header_usage "$0"; exit 0 ;;
        *)          die "Unknown argument: $1  (try --help)" ;;
    esac
done

if [ -z "${SIM_PATH}" ]; then
    for candidate in \
        "${REPO_ROOT}/simulator/autodrive_simulator/AutoDRIVE Simulator.x86_64" \
        "/hackathon/simulator/autodrive_simulator/AutoDRIVE Simulator.x86_64" \
        "/opt/autodrive_simulator/AutoDRIVE Simulator.x86_64"
    do
        [ -f "${candidate}" ] && { SIM_PATH="${candidate}"; break; }
    done
fi

[ -n "${SIM_PATH}" ] && [ -f "${SIM_PATH}" ] || die \
"The AutoDRIVE Simulator is not installed.
Fetch it once, on your host:
    ./scripts/fetch_simulator.sh
Or point this script at a copy you already have:
    ./scripts/run_simulator.sh --path '/path/to/AutoDRIVE Simulator.x86_64'"

[ -x "${SIM_PATH}" ] || chmod +x "${SIM_PATH}" 2>/dev/null || true

args=("${SIM_PATH}" -ip "${HOST}" -port "${PORT}")
prefix=()

if [ "${HEADLESS}" = "1" ]; then
    args+=(-batchmode -nographics)
    info "Headless (no graphics device). The front camera will not produce images."
elif [ "${XVFB}" = "1" ] || { [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null 2>&1; }; then
    command -v xvfb-run >/dev/null 2>&1 \
        || die "xvfb-run is not installed, and there is no DISPLAY to render to. Use --headless."
    prefix=(xvfb-run -a)
    info "Rendering into a virtual framebuffer (no window, camera works)."
else
    info "Rendering to DISPLAY=${DISPLAY:-<unset>}."
fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-root}"
mkdir -p "${XDG_RUNTIME_DIR}" 2>/dev/null || true

info "Connecting out to the devkit bridge at ${HOST}:${PORT}."
exec "${prefix[@]}" "${args[@]}"
