#!/usr/bin/env bash
#
# Decide whether race_ws/src/team_driver holds a real entry or is still the
# untouched template, and print "submission" or "template".
#
# Automated judging uses this: on the template repository there is nothing to
# score - the template has no driving logic - so CI skips the race rather than
# publishing a result for a car parked against the first barrier.
#
#   ./scripts/detect_submission.sh            # print submission|template
#   ./scripts/detect_submission.sh --explain  # and say why
#   ./scripts/detect_submission.sh --update   # re-record the template (organisers)
#
# Exit code: 0 = submission, 1 = template, 2 = could not tell.
#
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../install" && pwd)/common.sh"

TEMPLATE_DIR="${REPO_ROOT}/race_ws/src/team_driver"
MANIFEST="${REPO_ROOT}/scripts/template_manifest.sha256"

MODE="quiet"
for arg in "$@"; do
    case "${arg}" in
        --explain) MODE="explain" ;;
        --update)  MODE="update" ;;
        -h|--help) print_header_usage "$0"; exit 0 ;;
        *) die "Unknown argument: ${arg}" ;;
    esac
done

command -v sha256sum >/dev/null 2>&1 || die "sha256sum is not available."
[ -d "${TEMPLATE_DIR}" ] || die "${TEMPLATE_DIR} does not exist."

# Build artefacts and caches are not part of the entry.
list_files() {
    find "${TEMPLATE_DIR}" -type f \
        ! -name '*.pyc' ! -path '*/__pycache__/*' -print \
        | sed "s|^${REPO_ROOT}/||" | LC_ALL=C sort
}

if [ "${MODE}" = "update" ]; then
    ( cd "${REPO_ROOT}" && list_files | tr '\n' '\0' | xargs -0 sha256sum ) > "${MANIFEST}"
    ok "Recorded $(wc -l < "${MANIFEST}") template file(s) in ${MANIFEST}"
    exit 0
fi

if [ ! -f "${MANIFEST}" ]; then
    # Without a reference we cannot tell, and guessing would either score a stub
    # or hide a real entry. Say so and let the caller decide.
    [ "${MODE}" = "explain" ] && warn "No template manifest at ${MANIFEST}."
    echo "unknown"
    exit 2
fi

changed=""
if ! ( cd "${REPO_ROOT}" && sha256sum --status --check "${MANIFEST}" ) 2>/dev/null; then
    changed="$( cd "${REPO_ROOT}" && sha256sum --check "${MANIFEST}" 2>/dev/null \
                | grep -v ': OK$' | cut -d: -f1 || true )"
fi

# A file added to the package is an entry just as much as an edited one.
added="$(comm -13 <(cut -d' ' -f3- "${MANIFEST}" | LC_ALL=C sort) \
                  <(cd "${REPO_ROOT}" && list_files) || true)"

if [ -n "${changed}" ] || [ -n "${added}" ]; then
    if [ "${MODE}" = "explain" ]; then
        [ -n "${changed}" ] && info "Modified: $(echo "${changed}" | tr '\n' ' ')"
        [ -n "${added}" ] && info "Added: $(echo "${added}" | tr '\n' ' ')"
    fi
    echo "submission"
    exit 0
fi

[ "${MODE}" = "explain" ] && info "team_driver is byte-identical to the template."
echo "template"
exit 1
