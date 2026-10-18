#!/usr/bin/env bash
#
# Download the AutoDRIVE Simulator (compete build) into simulator/.
#
# The simulator is a ~140 MB Unity binary. It is not in this repository and not
# in the Docker image: it is fetched once, here, and picked up through the bind
# mount at /hackathon/simulator.
#
#   ./scripts/fetch_simulator.sh                 the build for this machine
#   ./scripts/fetch_simulator.sh --platform macos
#   ./scripts/fetch_simulator.sh --force         re-download over an existing copy
#   ./scripts/fetch_simulator.sh --check         say what is installed and stop
#
# Options
#   --platform NAME   linux | macos | windows   (default: detected)
#   --force           re-download even if a simulator is already installed
#   --check           report what is installed, download nothing
#   --dest DIR        install somewhere other than <repo>/simulator
#
# On Linux and WSL the Linux build is what you want: it runs inside the
# container, headless, and that is what evaluate.sh drives. On macOS and
# Windows the container cannot run a native simulator window, so the native
# build runs on your host and talks to the bridge in the container over port
# 4567 - see docs/01-setup.md.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../install" && pwd)/common.sh"

RELEASE_TAG="2026-icra"
RELEASE_BASE="https://github.com/AutoDRIVE-Ecosystem/AutoDRIVE-RoboRacer-Sim-Racing/releases/download/${RELEASE_TAG}"

PLATFORM=""
FORCE=0
CHECK=0
DEST=""

while [ $# -gt 0 ]; do
    case "$1" in
        --platform) PLATFORM="${2:?--platform needs a value}"; shift 2 ;;
        --dest)     DEST="${2:?--dest needs a value}"; shift 2 ;;
        --force)    FORCE=1; shift ;;
        --check)    CHECK=1; shift ;;
        -h|--help)  print_header_usage "$0"; exit 0 ;;
        *)          die "Unknown argument: $1  (try --help)" ;;
    esac
done

in_container && die \
"Run this on your host, not inside the container. The download lands in the
repository, which is bind-mounted, so the container sees it either way - and
fetching it from the host means it survives a rebuild."

DEST="${DEST:-${REPO_ROOT}/simulator}"

if [ -z "${PLATFORM}" ]; then
    case "$(detect_platform)" in
        # WSL runs the Linux build inside the container. If you would rather
        # run the simulator natively on Windows for the graphics, fetch the
        # windows build explicitly with --platform windows.
        linux|wsl) PLATFORM="linux" ;;
        macos)     PLATFORM="macos" ;;
        windows)   PLATFORM="windows" ;;
        *)         die "Could not detect your platform. Pass --platform linux|macos|windows." ;;
    esac
fi

case "${PLATFORM}" in
    linux)   EXECUTABLE="autodrive_simulator/AutoDRIVE Simulator.x86_64" ;;
    macos)   EXECUTABLE="autodrive_simulator/AutoDRIVE Simulator.app/Contents/MacOS/AutoDRIVE Simulator" ;;
    windows) EXECUTABLE="autodrive_simulator/AutoDRIVE Simulator.exe" ;;
    *)       die "Unknown platform '${PLATFORM}'. Choose linux, macos or windows." ;;
esac

ARCHIVE_NAME="autodrive_simulator_compete_${PLATFORM}.zip"
URL="${RELEASE_BASE}/${ARCHIVE_NAME}"
STAMP="${DEST}/.installed"

report_installed() {
    if [ -f "${STAMP}" ]; then
        info "Installed: $(cat "${STAMP}")"
    fi
    if [ -e "${DEST}/${EXECUTABLE}" ]; then
        ok "Simulator present at ${DEST}/${EXECUTABLE}"
        return 0
    fi
    warn "No ${PLATFORM} simulator in ${DEST}"
    return 1
}

if [ "${CHECK}" = "1" ]; then
    report_installed && exit 0 || exit 1
fi

if [ -e "${DEST}/${EXECUTABLE}" ] && [ "${FORCE}" = "0" ]; then
    report_installed
    info "Nothing to do. Pass --force to download it again."
    exit 0
fi

command -v curl >/dev/null 2>&1 || die "curl is not installed. Install it and re-run."

mkdir -p "${DEST}"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
archive="${work}/${ARCHIVE_NAME}"

info "Downloading the ${PLATFORM} simulator (${RELEASE_TAG}, about 140 MB)."
info "${URL}"
curl -fL --retry 3 --retry-delay 2 --progress-bar -o "${archive}" "${URL}" \
    || die "Download failed. Check your network, or fetch ${URL} by hand and unzip it into ${DEST}/."

# The release ships no checksum, so the only integrity check available is that
# the archive is a readable zip containing what it should. That catches the
# common failure by far - a captive portal or a rate limit handing back an
# HTML error page with a 200.
size="$(wc -c < "${archive}")"
[ "${size}" -gt 10000000 ] \
    || die "The download is only ${size} bytes, so it is not the simulator. Usually a proxy or a login page. Try again, or download ${URL} in a browser."

info "Extracting into ${DEST}"
rm -rf "${DEST}/autodrive_simulator"
if command -v unzip >/dev/null 2>&1; then
    unzip -q -o "${archive}" -d "${DEST}"
else
    # unzip is not installed by default on a minimal Ubuntu, and Python is
    # everywhere this repository already needs it.
    python3 - "${archive}" "${DEST}" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2])
PY
fi

[ -e "${DEST}/${EXECUTABLE}" ] \
    || die "The archive extracted, but ${EXECUTABLE} is not in it. The release layout may have changed; check ${URL}."

# Zip does not carry the executable bit, so a freshly extracted simulator will
# not run until this is put back.
if [ "${PLATFORM}" != "windows" ]; then
    chmod +x "${DEST}/${EXECUTABLE}" || true
    find "${DEST}/autodrive_simulator" -maxdepth 1 -name '*.so' -exec chmod +r {} + 2>/dev/null || true
fi

printf '%s (%s) fetched %s\n' "${ARCHIVE_NAME}" "${RELEASE_TAG}" \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "${STAMP}"

ok "AutoDRIVE Simulator (${PLATFORM}, ${RELEASE_TAG}) installed in ${DEST}"
case "${PLATFORM}" in
    linux)
        info "It runs inside the container. Nothing else to do:"
        info "    ./scripts/evaluate.sh --team my_team --headless"
        ;;
    *)
        info "Run it on this machine and point it at the bridge in the container:"
        info "    \"${DEST}/${EXECUTABLE}\"   then set IP 127.0.0.1, port 4567, and Connect"
        info "See docs/01-setup.md."
        ;;
esac
