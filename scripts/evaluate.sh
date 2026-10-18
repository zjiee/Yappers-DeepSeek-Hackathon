#!/usr/bin/env bash
#
# Run a scored evaluation and write a result file.
#
# Works from the host (it hops into the container for you) or from inside the
# container directly.
#
#   ./scripts/evaluate.sh --team my_team
#   ./scripts/evaluate.sh --team my_team --runs 3
#   ./scripts/evaluate.sh --team my_team --graphics          # watch it
#   ./scripts/evaluate.sh --team my_team --driver-exec my_other_node
#
# Options
#   --team NAME          team name for the result file      (default: unnamed_team)
#   --track NAME         track from maps/tracks.yaml        (default: the file's default)
#   --driver-pkg PKG     package holding the driver node    (default: team_driver)
#   --driver-exec EXEC   executable name                    (default: driver)
#   --driver-params FILE parameter YAML for the driver
#   --laps N             scored laps                        (default: 10)
#   --warmup N           unscored laps before timing        (default: 2)
#   --runs N             repeat and keep the best           (default: 1)
#   --output DIR         where results land                 (default: <repo>/results)
#   --headless           run the simulator with no graphics device and no RViz.
#                        This is what judging uses.                  (default)
#   --graphics           render the simulator and open RViz, to watch a run
#   --no-simulator       drive a simulator you started yourself, here or on
#                        your host machine (macOS, Windows)
#   --host ADDRESS       where that simulator should find the bridge
#   --no-build           skip the workspace build check
#   --timeout SECONDS    hard limit per run                 (default: 2400)
#   --wall-timeout SEC   referee's own wall-clock watchdog  (default: 1800)
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../install" && pwd)/common.sh"

TEAM="unnamed_team"
TRACK=""
DRIVER_PKG="team_driver"
DRIVER_EXEC="driver"
DRIVER_PARAMS=""
LAPS=10
WARMUP=2
RUNS=1
OUTPUT=""
HEADLESS=1
SIMULATOR=1
HOST="127.0.0.1"
SKIP_BUILD=0
RUN_TIMEOUT=2400
WALL_TIMEOUT=1800

while [ $# -gt 0 ]; do
    case "$1" in
        --team)          TEAM="${2:?--team needs a value}"; shift 2 ;;
        --track)         TRACK="${2:?--track needs a value}"; shift 2 ;;
        --driver-pkg)    DRIVER_PKG="${2:?--driver-pkg needs a value}"; shift 2 ;;
        --driver-exec)   DRIVER_EXEC="${2:?--driver-exec needs a value}"; shift 2 ;;
        --driver-params) DRIVER_PARAMS="${2:?--driver-params needs a value}"; shift 2 ;;
        --laps)          LAPS="${2:?--laps needs a value}"; shift 2 ;;
        --warmup)        WARMUP="${2:?--warmup needs a value}"; shift 2 ;;
        --runs)          RUNS="${2:?--runs needs a value}"; shift 2 ;;
        --output)        OUTPUT="${2:?--output needs a value}"; shift 2 ;;
        --timeout)       RUN_TIMEOUT="${2:?--timeout needs a value}"; shift 2 ;;
        --wall-timeout)  WALL_TIMEOUT="${2:?--wall-timeout needs a value}"; shift 2 ;;
        --headless)      HEADLESS=1; shift ;;
        --graphics)      HEADLESS=0; shift ;;
        --no-simulator)  SIMULATOR=0; shift ;;
        --host)          HOST="${2:?--host needs a value}"; shift 2 ;;
        --no-build)      SKIP_BUILD=1; shift ;;
        -h|--help)       print_header_usage "$0"; exit 0 ;;
        *)               die "Unknown argument: $1  (try --help)" ;;
    esac
done

for pair in "laps:${LAPS}" "warmup:${WARMUP}" "runs:${RUNS}" "timeout:${RUN_TIMEOUT}" \
            "wall-timeout:${WALL_TIMEOUT}"; do
    name="${pair%%:*}"; value="${pair#*:}"
    case "${value}" in
        ''|*[!0-9]*) die "--${name} must be a whole number, got '${value}'" ;;
    esac
done
[ "${RUNS}" -ge 1 ] || die "--runs must be at least 1"
[ "${LAPS}" -ge 1 ] || die "--laps must be at least 1"

# --------------------------------------------------------------------------
# From the host: re-run this same script inside the container.
# --------------------------------------------------------------------------
if ! in_container; then
    require_docker
    container_running || die "The container is not running. Start it with install/<your-os>/run.sh"
    info "Handing off to the container."
    args=(--team "${TEAM}" --driver-pkg "${DRIVER_PKG}" --driver-exec "${DRIVER_EXEC}"
          --laps "${LAPS}" --warmup "${WARMUP}" --runs "${RUNS}" --timeout "${RUN_TIMEOUT}"
          --wall-timeout "${WALL_TIMEOUT}")
    [ -n "${TRACK}" ] && args+=(--track "${TRACK}")
    [ -n "${DRIVER_PARAMS}" ] && args+=(--driver-params "${DRIVER_PARAMS}")
    [ -n "${OUTPUT}" ] && args+=(--output "${OUTPUT}")
    args+=(--host "${HOST}")
    [ "${HEADLESS}" = "1" ] && args+=(--headless) || args+=(--graphics)
    [ "${SIMULATOR}" = "0" ] && args+=(--no-simulator)
    [ "${SKIP_BUILD}" = "1" ] && args+=(--no-build)
    exec docker exec -i "${CONTAINER_NAME}" /usr/local/bin/entrypoint.sh \
        /hackathon/scripts/evaluate.sh "${args[@]}"
fi

# --------------------------------------------------------------------------
# Inside the container from here down.
# --------------------------------------------------------------------------
RACE_WS="${RACE_WS:-/hackathon/race_ws}"
OUTPUT="${OUTPUT:-/hackathon/results}"

[ -d "${RACE_WS}/src" ] || die "${RACE_WS}/src is missing. Is the repository mounted at /hackathon?"
mkdir -p "${OUTPUT}" || die "Cannot create the output directory ${OUTPUT}"

if [ "${SKIP_BUILD}" = "0" ]; then
    info "Building the workspace."
    ( cd "${RACE_WS}" && colcon build --symlink-install ) \
        || die "colcon build failed. Fix the build errors above, or pass --no-build to skip this."
fi

# ROS and colcon setup scripts read unset variables, so `set -u` would abort
# the moment we source one. Lift it for the source, then put it back.
# shellcheck disable=SC1091
if [ -f "${RACE_WS}/install/local_setup.bash" ]; then
    set +u
    source "${RACE_WS}/install/local_setup.bash"
    set -u
fi

ros2 pkg executables "${DRIVER_PKG}" 2>/dev/null | grep -q " ${DRIVER_EXEC}$" || die \
"Could not find executable '${DRIVER_EXEC}' in package '${DRIVER_PKG}'.
 Check the console_scripts entry in ${DRIVER_PKG}/setup.py, then rebuild:
     cd ${RACE_WS} && colcon build --symlink-install && source install/local_setup.bash"

RVIZ_ARG="true"
HEADLESS_ARG="false"
if [ "${HEADLESS}" = "1" ]; then
    RVIZ_ARG="false"
    HEADLESS_ARG="true"
fi
SIMULATOR_ARG="true"
[ "${SIMULATOR}" = "0" ] && SIMULATOR_ARG="false"

# Fail now, with an explanation, rather than after the referee has spent two
# minutes waiting for telemetry that was never going to arrive.
if [ "${SIMULATOR}" = "1" ]; then
    sim_found=0
    for candidate in \
        "/hackathon/simulator/autodrive_simulator/AutoDRIVE Simulator.x86_64" \
        "/opt/autodrive_simulator/AutoDRIVE Simulator.x86_64" \
        "${AUTODRIVE_SIM_PATH:-}"
    do
        [ -n "${candidate}" ] && [ -f "${candidate}" ] && { sim_found=1; break; }
    done
    [ "${sim_found}" = "1" ] || die \
"The AutoDRIVE Simulator is not installed.

Fetch it once, on your HOST machine (not in here):
    ./scripts/fetch_simulator.sh

Or, if you are running the simulator yourself - natively on macOS or Windows,
or on another machine - tell this script not to start one:
    ./scripts/evaluate.sh --team ${TEAM} --no-simulator"
fi

BASE_RUN_ID="$(date -u '+%Y%m%dT%H%M%SZ')"
declare -a RESULT_FILES=()

cleanup() {
    # `ros2 launch` occasionally leaves these behind when it is killed, and a
    # surviving bridge holds port 4567, so the next run cannot even bind it.
    # Matched on the installed paths rather than on the node names, so this
    # cannot take out an unrelated process that merely mentions them.
    pkill -f 'roboracer_referee/sim_bridge' 2>/dev/null || true
    pkill -f 'roboracer_referee/referee' 2>/dev/null || true
    pkill -f 'autodrive_roboracer/autodrive_bridge' 2>/dev/null || true
    pkill -f 'AutoDRIVE Simulator' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for attempt in $(seq 1 "${RUNS}"); do
    run_id="${BASE_RUN_ID}"
    [ "${RUNS}" -gt 1 ] && run_id="${BASE_RUN_ID}_r${attempt}"

    info "Run ${attempt}/${RUNS}  (team=${TEAM}, laps=${LAPS}, id=${run_id})"

    launch_args=(
        "team:=${TEAM}"
        "run_id:=${run_id}"
        "driver_pkg:=${DRIVER_PKG}"
        "driver_exec:=${DRIVER_EXEC}"
        "output_dir:=${OUTPUT}"
        "timed_laps:=${LAPS}"
        "warmup_laps:=${WARMUP}"
        "wall_timeout_s:=${WALL_TIMEOUT}"
        "rviz:=${RVIZ_ARG}"
        "headless:=${HEADLESS_ARG}"
        "simulator:=${SIMULATOR_ARG}"
        "host:=${HOST}"
    )
    [ -n "${TRACK}" ] && launch_args+=("track:=${TRACK}")
    [ -n "${DRIVER_PARAMS}" ] && launch_args+=("driver_params:=${DRIVER_PARAMS}")

    set +e
    timeout --signal=INT --kill-after=30 "${RUN_TIMEOUT}" \
        ros2 launch roboracer_referee evaluate.launch.py "${launch_args[@]}"
    launch_status=$?
    set -e
    cleanup

    if [ "${launch_status}" = "124" ] || [ "${launch_status}" = "137" ]; then
        warn "Run ${attempt} hit the ${RUN_TIMEOUT}s wall-clock limit."
    fi

    safe_team="$(printf '%s' "${TEAM}" | tr -c 'A-Za-z0-9_-' '_')"
    result="${OUTPUT}/${safe_team}__${run_id}.json"
    if [ -f "${result}" ]; then
        RESULT_FILES+=("${result}")
        ok "Run ${attempt} recorded: ${result}"
    else
        warn "Run ${attempt} produced no result file. The referee log above says why."
    fi

    # Let DDS discovery from the previous run age out, and give the kernel time
    # to release port 4567 before the next bridge tries to bind it.
    [ "${attempt}" -lt "${RUNS}" ] && sleep 8
done

echo
if [ "${#RESULT_FILES[@]}" -eq 0 ]; then
    die "No runs completed. Nothing was scored."
fi

python3 "${REPO_ROOT}/scripts/leaderboard.py" summarise "${RESULT_FILES[@]}"
