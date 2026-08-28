#!/usr/bin/env bash
# Deploy versioned MkDocs docs with mike (Material version selector).
# Host-only — publishes to the gh-pages branch (does not use force_orphan).
#
# "latest" is the rolling tip of main (deployed on every push, default
# landing page) — NOT "most recent release". A real `make release` only
# adds its own pinned snapshot (X.Y.Z + an optional CalVer alias); it
# never touches "latest".
#
# Usage:
#   ./scripts/repository/docs-mike.sh latest               # rolling tip-of-tree, sets default
#   ./scripts/repository/docs-mike.sh release <X.Y.Z> [YY.Q]  # pinned snapshot (+ CalVer alias)
#   ./scripts/repository/docs-mike.sh list
#
# Env:
#   DOCS_MIKE_PUSH=0   skip --push (update local gh-pages only)
#   DOCS_MIKE_REMOTE=origin

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PUSH="${DOCS_MIKE_PUSH:-1}"
REMOTE="${DOCS_MIKE_REMOTE:-origin}"
VENV="${ROOT_DIR}/.venv-docs"
MIKE="${VENV}/bin/mike"
PIP="${VENV}/bin/pip"
MIKE_PUSH_RETRIES="${MIKE_PUSH_RETRIES:-3}"

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

ensure_mike() {
    if [[ ! -x "${MIKE}" ]]; then
        python3 -m venv "${VENV}"
        "${PIP}" install -q -r requirements-docs.txt
    else
        "${PIP}" install -q -r requirements-docs.txt
    fi
    [[ -x "${MIKE}" ]] || die "mike not installed in ${VENV}"
    # mike shells out to `mkdocs`; keep venv binaries first on PATH
    export PATH="${VENV}/bin:${PATH}"
    command -v mkdocs >/dev/null || die "mkdocs not on PATH after activating ${VENV}/bin"
}

push_flags=()
if [[ "${PUSH}" == "1" || "${PUSH}" == "true" ]]; then
    push_flags=(--push)
fi

ensure_git_identity() {
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
        git config user.name "github-actions[bot]"
        git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    fi
    if ! git config user.name >/dev/null && ! git config user.email >/dev/null; then
        die "git user.name / user.email must be set for mike commits"
    fi
}

# mike does not git-fetch for you. Keep local gh-pages aligned with origin
# before every deploy (avoids "rejected (fetch first)" after concurrent CI).
sync_gh_pages() {
    if ! git ls-remote --exit-code --heads "${REMOTE}" gh-pages >/dev/null 2>&1; then
        printf 'Note: remote gh-pages not present yet — mike will create it\n'
        return 0
    fi
    git fetch "${REMOTE}" gh-pages --force
    if git show-ref --verify --quiet refs/heads/gh-pages; then
        git update-ref refs/heads/gh-pages "refs/remotes/${REMOTE}/gh-pages"
    else
        git branch --track gh-pages "${REMOTE}/gh-pages" 2>/dev/null \
            || git branch gh-pages "${REMOTE}/gh-pages"
    fi
}

# Run mike; on gh-pages push rejection, re-sync and retry.
mike_run() {
    local attempt=1
    local max="${MIKE_PUSH_RETRIES}"
    local log status
    log="$(mktemp)"
    # shellcheck disable=SC2064
    trap 'rm -f "'"${log}"'"' RETURN

    while true; do
        sync_gh_pages
        set +e
        "${MIKE}" "$@" 2>&1 | tee "${log}"
        status=${PIPESTATUS[0]}
        set -e
        if [[ "${status}" -eq 0 ]]; then
            return 0
        fi
        if [[ "${PUSH}" != "1" && "${PUSH}" != "true" ]]; then
            return "${status}"
        fi
        if ! grep -Eiq 'rejected|fetch first|non-fast-forward|failed to push' "${log}"; then
            return "${status}"
        fi
        if (( attempt >= max )); then
            die "mike $* failed after ${max} push attempts (gh-pages race?)"
        fi
        printf 'Warning: gh-pages push rejected (attempt %s/%s) — re-syncing and retrying\n' \
            "${attempt}" "${max}" >&2
        : >"${log}"
        attempt=$((attempt + 1))
        sleep $((attempt * 2))
    done
}

cmd_list() {
    ensure_mike
    sync_gh_pages
    "${MIKE}" list
}

cmd_latest() {
    ensure_mike
    ensure_git_identity
    printf 'Deploying docs alias: latest (rolling tip of main)\n'
    mike_run deploy "${push_flags[@]}" --update-aliases latest
    mike_run set-default "${push_flags[@]}" latest
    printf 'OK: docs alias "latest" updated (default)\n'
    printf 'URL: https://akyther.github.io/orcan/latest/\n'
}

cmd_release() {
    local ver="${1:-}" calver="${2:-}"
    [[ -n "${ver}" ]] || die "usage: docs-mike.sh release <X.Y.Z> [YY.Q]"
    [[ "${ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must be SemVer X.Y.Z (got: ${ver})"

    local file_v
    file_v="$(./scripts/repository/release.sh print | tr -d '[:space:]')"
    [[ -n "${file_v}" ]] || die "could not read version from cockpit/pyproject.toml"
    if [[ "${file_v}" != "${ver}" ]]; then
        die "cockpit/pyproject.toml (${file_v}) != release argument (${ver})"
    fi

    local aliases=()
    [[ -n "${calver}" ]] && aliases=("${calver}")

    ensure_mike
    ensure_git_identity
    printf 'Deploying docs version %s%s (does not touch "latest")\n' "${ver}" "${calver:+ + alias ${calver}}"
    mike_run deploy "${push_flags[@]}" --update-aliases "${ver}" "${aliases[@]}"
    printf 'OK: docs %s deployed\n' "${ver}"
    printf 'URL: https://akyther.github.io/orcan/%s/\n' "${ver}"
    [[ -n "${calver}" ]] && printf '     https://akyther.github.io/orcan/%s/\n' "${calver}"
}

usage() {
    cat <<'EOF'
Usage: docs-mike.sh <latest|release|list> [version] [calver]

  latest           Deploy/update rolling alias "latest" from the current tree + set default
  release X.Y.Z [YY.Q]  Deploy a pinned SemVer snapshot (+ optional CalVer alias)
  list             Show mike versions on gh-pages

Set DOCS_MIKE_PUSH=0 to commit locally without pushing.
EOF
}

case "${1:-}" in
    release) cmd_release "${2:-}" "${3:-}" ;;
    latest) cmd_latest ;;
    list) cmd_list ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1" ;;
esac
