#!/usr/bin/env bash
# Product version helpers (SemVer). Host-only — not copied into the image.
#
# Usage:
#   ./scripts/repository/release.sh show
#   ./scripts/repository/release.sh bump patch|minor|major
#   ./scripts/repository/release.sh check
#   ./scripts/repository/release.sh tag          # annotated tag vX.Y.Z from VERSION
#   ./scripts/repository/release.sh push-tag    # push tag to origin
#   ./scripts/repository/release.sh release     # tag + push (clean tree required)
#
# Release ritual:
#   1. Edit CHANGELOG.md (move Unreleased → version section)
#   2. make bump-patch   # bumps VERSION + display copies (mkdocs/README/Home)
#   3. git add VERSION CHANGELOG.md mkdocs.yml README.md docs/en/index.md docs/pl/index.md
#   4. git commit -m "release: vX.Y.Z"
#   5. make release      # creates vX.Y.Z and pushes → GitHub Release (no image publish)

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

VERSION_FILE="${ROOT_DIR}/VERSION"

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

read_version() {
    [[ -f "${VERSION_FILE}" ]] || die "VERSION file missing"
    local v
    v="$(tr -d '[:space:]' < "${VERSION_FILE}")"
    [[ "${v}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION must be SemVer X.Y.Z (got: ${v})"
    printf '%s' "${v}"
}

write_version() {
    printf '%s\n' "$1" > "${VERSION_FILE}"
}

cmd_show() {
    local v
    v="$(read_version)"
    printf 'VERSION:     %s\n' "${v}"
    printf 'Git tag:     v%s\n' "${v}"
    printf 'Local tags:  orcan:%s  orcan:latest  orcan:full\n' "${v}"
    printf '             orcan:%s-claude  orcan:claude\n' "${v}"
    printf 'Distribute:  git clone + make build (images are not published)\n'
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        printf 'Tag exists locally: yes\n'
    else
        printf 'Tag exists locally: no\n'
    fi
}

bump_semver() {
    local part="$1" major minor patch
    IFS=. read -r major minor patch <<<"$(read_version)"
    case "${part}" in
        patch) patch=$((patch + 1)) ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        major) major=$((major + 1)); minor=0; patch=0 ;;
        *) die "bump part must be patch|minor|major (got: ${part})" ;;
    esac
    printf '%s.%s.%s' "${major}" "${minor}" "${patch}"
}

cmd_bump() {
    local part="${1:-}"
    [[ -n "${part}" ]] || die "usage: release.sh bump patch|minor|major"
    local old new
    old="$(read_version)"
    new="$(bump_semver "${part}")"
    write_version "${new}"
    sync_version_displays "${old}" "${new}"
    printf 'Bumped VERSION: %s → %s\n' "${old}" "${new}"
    printf 'Synced: mkdocs.yml, README.md, docs/en/index.md, docs/pl/index.md\n'
    printf 'Next:\n'
    printf '  1. Update CHANGELOG.md for %s (move Unreleased → [%s])\n' "${new}" "${new}"
    printf '  2. git add VERSION CHANGELOG.md mkdocs.yml README.md docs/en/index.md docs/pl/index.md\n'
    printf '  3. git commit -m "release: v%s"\n' "${new}"
    printf '  4. make release\n'
}

# Keep display copies of VERSION in sync (enforced by tests/host/test_version.py).
sync_version_displays() {
    local old="$1" new="$2"
    local mkdocs="${ROOT_DIR}/mkdocs.yml"
    local readme="${ROOT_DIR}/README.md"
    local en_home="${ROOT_DIR}/docs/en/index.md"
    local pl_home="${ROOT_DIR}/docs/pl/index.md"

    if grep -qE "orcan_version: \"${old}\"" "${mkdocs}"; then
        sed -i "s/orcan_version: \"${old}\"/orcan_version: \"${new}\"/" "${mkdocs}"
    elif grep -qE 'orcan_version: "' "${mkdocs}"; then
        sed -i -E "s/orcan_version: \"[0-9]+\.[0-9]+\.[0-9]+\"/orcan_version: \"${new}\"/" "${mkdocs}"
    else
        die "mkdocs.yml: missing orcan_version field to sync"
    fi

    if grep -qE "Version \\*\\*${old}\\*\\*" "${readme}"; then
        sed -i "s/Version \\*\\*${old}\\*\\*/Version **${new}**/" "${readme}"
    elif grep -qE 'Version \*\*[0-9]+\.[0-9]+\.[0-9]+\*\*' "${readme}"; then
        sed -i -E "s/Version \\*\\*[0-9]+\\.[0-9]+\\.[0-9]+\\*\\*/Version **${new}**/" "${readme}"
    else
        die "README.md: missing Version **X.Y.Z** to sync"
    fi

    if grep -qE "Version \\*\\*${old}\\*\\*" "${en_home}"; then
        sed -i "s/Version \\*\\*${old}\\*\\*/Version **${new}**/" "${en_home}"
    elif grep -qE 'Version \*\*[0-9]+\.[0-9]+\.[0-9]+\*\*' "${en_home}"; then
        sed -i -E "s/Version \\*\\*[0-9]+\\.[0-9]+\\.[0-9]+\\*\\*/Version **${new}**/" "${en_home}"
    else
        die "docs/en/index.md: missing Version **X.Y.Z** to sync"
    fi

    if grep -qE "Wersja \\*\\*${old}\\*\\*" "${pl_home}"; then
        sed -i "s/Wersja \\*\\*${old}\\*\\*/Wersja **${new}**/" "${pl_home}"
    elif grep -qE 'Wersja \*\*[0-9]+\.[0-9]+\.[0-9]+\*\*' "${pl_home}"; then
        sed -i -E "s/Wersja \\*\\*[0-9]+\\.[0-9]+\\.[0-9]+\\*\\*/Wersja **${new}**/" "${pl_home}"
    else
        die "docs/pl/index.md: missing Wersja **X.Y.Z** to sync"
    fi
}

require_clean_tree() {
    if [[ -n "$(git status --porcelain)" ]]; then
        die "working tree is dirty — commit or stash before release"
    fi
}

cmd_check() {
    local v
    v="$(read_version)"
    printf 'VERSION OK: %s\n' "${v}"
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        printf 'Note: tag v%s already exists locally\n' "${v}"
    fi
}

cmd_tag() {
    local v
    require_clean_tree
    v="$(read_version)"
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        die "tag v${v} already exists"
    fi
    local head_v
    head_v="$(git show HEAD:VERSION 2>/dev/null | tr -d '[:space:]' || true)"
    [[ "${head_v}" == "${v}" ]] || die "HEAD:VERSION (${head_v:-missing}) != VERSION file (${v}); commit VERSION first"

    git tag -a "v${v}" -m "orcan v${v}"
    printf 'Created annotated tag v%s\n' "${v}"
}

cmd_push_tag() {
    local v
    v="$(read_version)"
    git rev-parse "v${v}" >/dev/null 2>&1 || die "tag v${v} missing — run: make release-tag"
    git push origin "v${v}"
    printf 'Pushed v%s → origin\n' "${v}"
    printf 'GitHub Actions: Release workflow validates + creates GitHub Release\n'
    printf 'Users: git checkout v%s && make build && make terminal-docker\n' "${v}"
}

cmd_release() {
    cmd_tag
    cmd_push_tag
}

usage() {
    cat <<'EOF'
Usage: release.sh <show|bump|check|tag|push-tag|release>

  show       Print VERSION and local image tag names
  bump PART  Bump VERSION (patch|minor|major)
  check      Validate VERSION format
  tag        Create annotated git tag vX.Y.Z (clean tree)
  push-tag   Push tag to origin
  release    tag + push-tag (triggers GitHub Release; no image publish)
EOF
}

case "${1:-}" in
    show) cmd_show ;;
    bump) cmd_bump "${2:-}" ;;
    check) cmd_check ;;
    tag) cmd_tag ;;
    push-tag) cmd_push_tag ;;
    release) cmd_release ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1" ;;
esac
