#!/usr/bin/env bash
# Product version helpers (SemVer). Host-only — not copied into the image.
#
# Source of truth: cockpit/pyproject.toml → [project] version = "X.Y.Z"
# Synced copies (written by bump): root VERSION (CLI/image hot path),
# mkdocs.yml, README, Home docs, cockpit/uv.lock package stanza.
#
# Immutable SemVer tags identify changes. Publishing readiness is a separate
# explicit workflow dispatch for an existing tag and its exact commit SHA.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PYPROJECT="${ROOT_DIR}/cockpit/pyproject.toml"
UV_LOCK="${ROOT_DIR}/cockpit/uv.lock"
VERSION_FILE="${ROOT_DIR}/VERSION"
CHANGELOG="${ROOT_DIR}/CHANGELOG.md"

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

# Read SemVer from cockpit/pyproject.toml (canonical).
read_version() {
    [[ -f "${PYPROJECT}" ]] || die "missing ${PYPROJECT}"
    local v
    v="$(sed -nE 's/^version = "([0-9]+\.[0-9]+\.[0-9]+)"/\1/p' "${PYPROJECT}" | head -n1)"
    [[ "${v}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "cockpit/pyproject.toml version must be SemVer X.Y.Z (got: ${v:-empty})"
    printf '%s' "${v}"
}

# Write SemVer into pyproject + uv.lock package stanza + root VERSION mirror.
write_version() {
    local new="$1"
    [[ "${new}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "refusing non-SemVer write: ${new}"
    [[ -f "${PYPROJECT}" ]] || die "missing ${PYPROJECT}"

    if grep -qE '^version = "[0-9]+\.[0-9]+\.[0-9]+"' "${PYPROJECT}"; then
        sed -i -E "s/^version = \"[0-9]+\.[0-9]+\.[0-9]+\"/version = \"${new}\"/" "${PYPROJECT}"
    else
        die "cockpit/pyproject.toml: missing version = \"X.Y.Z\" line"
    fi

    if [[ -f "${UV_LOCK}" ]]; then
        # Only the local editable package stanza (name = "orcan-cockpit" then version).
        awk -v ver="${new}" '
            $0 == "name = \"orcan-cockpit\"" { print; getline; if ($0 ~ /^version = "/) { print "version = \"" ver "\""; next } }
            { print }
        ' "${UV_LOCK}" >"${UV_LOCK}.tmp" && mv "${UV_LOCK}.tmp" "${UV_LOCK}"
    fi

    printf '%s\n' "${new}" >"${VERSION_FILE}"
}

cmd_show() {
    local v
    v="$(read_version)"
    printf 'pyproject:   cockpit/pyproject.toml → %s\n' "${v}"
    printf 'VERSION:     %s (synced mirror for CLI/image)\n' "$(tr -d '[:space:]' <"${VERSION_FILE}" 2>/dev/null || echo missing)"
    printf 'Git tag:     v%s\n' "${v}"
    printf 'Local tags:  orcan:%s  orcan:latest\n' "${v}"
    printf 'Distribute:  install.sh / git clone + orcan build (images are not published)\n'
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        printf 'Tag exists locally: yes\n'
    else
        printf 'Tag exists locally: no\n'
    fi
}

# Machine-readable: only the SemVer (for Make / docs-mike).
cmd_print() {
    read_version
    printf '\n'
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
    printf 'Bumped (pyproject): %s → %s\n' "${old}" "${new}"
    printf 'Synced: cockpit/uv.lock, VERSION, mkdocs.yml, README.md, docs/en/index.md\n'
    printf '(Low-level — usually you want: make tag)\n'
}

# Keep an empty Unreleased section above each tagged version.

changelog_unreleased_body() {
    [[ -f "${CHANGELOG}" ]] || die "missing ${CHANGELOG}"
    grep -q '^## \[Unreleased\]$' "${CHANGELOG}" || die "${CHANGELOG}: no '## [Unreleased]' heading"
    awk '/^## \[Unreleased\]$/{f=1;next} /^## /{f=0} f' "${CHANGELOG}"
}

changelog_checkpoint() {
    local version="$1" date="$2"
    local body
    body="$(changelog_unreleased_body | sed '/^[[:space:]]*$/d')"
    [[ -n "${body}" ]] || die "${CHANGELOG}: [Unreleased] is empty — nothing to checkpoint"
    awk -v ver="${version}" -v d="${date}" '
        /^## \[Unreleased\]$/ { print; print ""; print "## [" ver "] - " d; next }
        { print }
    ' "${CHANGELOG}" >"${CHANGELOG}.tmp" && mv "${CHANGELOG}.tmp" "${CHANGELOG}"
}

current_branch() {
    git rev-parse --abbrev-ref HEAD
}

cmd_version() {
    local part="${1:-patch}"
    require_clean_tree

    # Validate everything that can fail *before* touching any file —
    # a checkpoint that dies partway must never leave a half-bumped,
    # uncommitted working tree behind.
    local body
    body="$(changelog_unreleased_body | sed '/^[[:space:]]*$/d')"
    [[ -n "${body}" ]] || die "${CHANGELOG}: [Unreleased] is empty — nothing to checkpoint"

    local old new today
    old="$(read_version)"
    new="$(bump_semver "${part}")"
    if git rev-parse "v${new}" >/dev/null 2>&1; then
        die "tag v${new} already exists (released) — bump would reuse a shipped version"
    fi
    if git rev-parse "checkpoint/v${new}" >/dev/null 2>&1; then
        die "tag checkpoint/v${new} already exists"
    fi

    [[ -z "$(git ls-remote --tags origin "refs/tags/v${new}")" ]] || die "origin tag v${new} already exists"
    write_version "${new}"
    sync_version_displays "${old}" "${new}"
    today="$(date +%F)"
    changelog_checkpoint "${new}" "${today}"
    git add cockpit/pyproject.toml cockpit/uv.lock VERSION CHANGELOG.md \
        mkdocs.yml README.md docs/en/index.md
    git commit -m "chore: version v${new}" >/dev/null
    git tag -a "v${new}" -m "orcan v${new}"
    git push origin "$(current_branch)"
    git push origin "v${new}"
    printf 'Version: v%s (commit + tag v%s pushed; release requires an explicit declaration)\n' "${new}" "${new}"
}

# Declare readiness without creating or moving a tag or changing source files.
cmd_release() {
    local tag="${1:-}" sha remote_sha version
    [[ "${tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: release.sh release vX.Y.Z"
    command -v gh >/dev/null 2>&1 || die "gh CLI is required to dispatch the release workflow"
    sha="$(git rev-parse --verify "refs/tags/${tag}^{commit}")" || die "existing local tag required: ${tag}"
    remote_sha="$(git ls-remote --tags origin "refs/tags/${tag}" "refs/tags/${tag}^{}" | awk 'NR==1 {sha=$1} /\^\{\}$/ {sha=$1} END {print sha}')"
    [[ "${sha}" == "${remote_sha}" ]] || die "origin tag missing or differs from local tag: ${tag}"
    version="$(git show "${sha}:VERSION" | tr -d '[:space:]')"
    [[ "${tag}" == "v${version}" ]] || die "tag does not match its committed VERSION"
    gh workflow run release.yml --ref main -f "tag=${tag}" -f "expected_sha=${sha}"
    printf 'Release declaration queued: %s at %s (publication pending validation)\n' "${tag}" "${sha}"
}

# Keep display copies in sync (enforced by tests/host/test_version.py).
sync_version_displays() {
    local old="$1" new="$2"
    local mkdocs="${ROOT_DIR}/mkdocs.yml"
    local readme="${ROOT_DIR}/README.md"
    local en_home="${ROOT_DIR}/docs/en/index.md"

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

}

require_clean_tree() {
    if [[ -n "$(git status --porcelain)" ]]; then
        die "working tree is dirty — commit or stash before release"
    fi
}

cmd_check() {
    local v mirror
    v="$(read_version)"
    printf 'VERSION OK: %s (from cockpit/pyproject.toml)\n' "${v}"
    if [[ -f "${VERSION_FILE}" ]]; then
        mirror="$(tr -d '[:space:]' <"${VERSION_FILE}")"
        if [[ "${mirror}" != "${v}" ]]; then
            die "VERSION file (${mirror}) != pyproject (${v}) — run: make bump-* or sync VERSION"
        fi
    else
        die "VERSION mirror missing — write_version should create it"
    fi
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        printf 'Note: tag v%s already exists locally\n' "${v}"
    fi
}

cmd_retract() {
    die "version tags are immutable; fix forward with a new SemVer tag. Withdraw GitHub Release metadata separately without deleting tags."
}

cmd_tag() {
    local v
    require_clean_tree
    v="$(read_version)"
    if git rev-parse "v${v}" >/dev/null 2>&1; then
        die "tag v${v} already exists"
    fi
    local head_v
    head_v="$(git show HEAD:cockpit/pyproject.toml 2>/dev/null | sed -nE 's/^version = "([0-9]+\.[0-9]+\.[0-9]+)"/\1/p' | head -n1 || true)"
    [[ "${head_v}" == "${v}" ]] || die "HEAD:cockpit/pyproject.toml (${head_v:-missing}) != working tree (${v}); commit version bump first"

    git tag -a "v${v}" -m "orcan v${v}"
    printf 'Created annotated tag v%s\n' "${v}"
}

cmd_push_tag() {
    local v
    v="$(read_version)"
    git rev-parse "v${v}" >/dev/null 2>&1 || die "tag v${v} missing — run: release.sh tag"
    git push origin "v${v}"
    printf 'Pushed v%s → origin\n' "${v}"
    printf 'Tag published; declare readiness separately with make release TAG=vX.Y.Z\n'
    printf 'Users: git checkout v%s && orcan build --all-agents && orcan up\n' "${v}"
}

usage() {
    cat <<'EOF'
Usage: release.sh <show|print|bump|check|version|checkpoint|release|retract|tag|push-tag>

  show               Print version (from cockpit/pyproject.toml) and local image tags
  print              Print SemVer only (scripting)
  bump PART          Low-level: bump SemVer in pyproject (patch|minor|major) + sync copies
  check              Validate pyproject SemVer and VERSION mirror
  version [PART]     make tag: bump + CHANGELOG cut + commit + push immutable vX.Y.Z
  release vX.Y.Z     Declare readiness for an existing remote tag and exact SHA
  retract            Refused: version tags are immutable; fix forward
  tag                Low-level: create annotated git tag vX.Y.Z from current HEAD (clean tree)
  push-tag           Low-level: push tag to origin
EOF
}

case "${1:-}" in
    show) cmd_show ;;
    print) cmd_print ;;
    bump) cmd_bump "${2:-}" ;;
    check) cmd_check ;;
    version|checkpoint) cmd_version "${2:-patch}" ;;
    release) cmd_release "${2:-}" ;;
    retract) cmd_retract "${2:-}" "${3:-}" "${4:-}" ;;
    tag) cmd_tag ;;
    push-tag) cmd_push_tag ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1" ;;
esac
