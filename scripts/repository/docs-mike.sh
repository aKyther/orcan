#!/usr/bin/env bash
# Deploy versioned MkDocs docs with mike (Material version selector).
# Host-only — publishes to the gh-pages branch (does not use force_orphan).
#
# Usage:
#   ./scripts/repository/docs-mike.sh release <X.Y.Z>   # version + alias latest + set-default
#   ./scripts/repository/docs-mike.sh dev               # tip-of-tree alias "dev"
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

cmd_list() {
    ensure_mike
    "${MIKE}" list
}

cmd_dev() {
    ensure_mike
    ensure_git_identity
    printf 'Deploying docs alias: dev\n'
    "${MIKE}" deploy "${push_flags[@]}" --update-aliases dev
    printf 'OK: docs alias "dev" updated\n'
    printf 'URL: https://akyther.github.io/orcan/dev/\n'
}

cmd_release() {
    local ver="${1:-}"
    [[ -n "${ver}" ]] || die "usage: docs-mike.sh release <X.Y.Z>"
    [[ "${ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must be SemVer X.Y.Z (got: ${ver})"

    local file_v
    file_v="$(tr -d '[:space:]' < VERSION)"
    if [[ "${file_v}" != "${ver}" ]]; then
        die "VERSION file (${file_v}) != release argument (${ver})"
    fi

    ensure_mike
    ensure_git_identity
    printf 'Deploying docs version %s (alias latest)\n' "${ver}"
    "${MIKE}" deploy "${push_flags[@]}" --update-aliases "${ver}" latest
    "${MIKE}" set-default "${push_flags[@]}" latest
    printf 'OK: docs %s → latest (default)\n' "${ver}"
    printf 'URL: https://akyther.github.io/orcan/latest/\n'
    printf '     https://akyther.github.io/orcan/%s/\n' "${ver}"
}

usage() {
    cat <<'EOF'
Usage: docs-mike.sh <release|dev|list> [version]

  release X.Y.Z  Deploy SemVer docs + alias latest + set-default
  dev            Deploy/update alias "dev" from the current tree
  list           Show mike versions on gh-pages

Set DOCS_MIKE_PUSH=0 to commit locally without pushing.
EOF
}

case "${1:-}" in
    release) cmd_release "${2:-}" ;;
    dev) cmd_dev ;;
    list) cmd_list ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1" ;;
esac
