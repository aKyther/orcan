#!/usr/bin/env bash
# Product version helpers (SemVer). Host-only — not copied into the image.
#
# Source of truth: cockpit/pyproject.toml → [project] version = "X.Y.Z"
# Synced copies (written by bump): root VERSION (CLI/image hot path),
# mkdocs.yml, README, Home docs, cockpit/uv.lock package stanza.
#
# Two-tier model — commits are free, tags/releases are deliberate:
#   - Regular dev commits (incl. fixes pushed out just to test somewhere)
#     never touch version/CHANGELOG here — plain `git commit`.
#   - `checkpoint` (make tag): a personal, frequent SemVer stop — bump +
#     move CHANGELOG Unreleased → [X.Y.Z] + commit + tag, fully pushed
#     (nothing local-only). The tag lives under checkpoint/vX.Y.Z, not
#     bare vX.Y.Z — that's what keeps it invisible to orcan
#     update/downgrade (they only match ^v[0-9]+\.[0-9]+\.[0-9]+$) and to
#     release.yml's "v*.*.*" trigger, so a checkpoint can never become an
#     update target or fire a release on its own. The commit is still
#     tested by CI (`checks` runs on every push to main, tag or not).
#   - `release` (make release): the rare, deliberate public stop, labeled
#     CalVer YY.Q (e.g. 26.3). Ensures a real, pushed bare vX.Y.Z tag
#     exists for the commit being released (creating one if `make tag`
#     hasn't already) — that's what CI, `orcan upgrade`/`downgrade`, and
#     GitHub Releases key off, unchanged. On top of it, pushes a second,
#     bare CalVer tag (e.g. "26.3") at the same commit — a human-named
#     "everything from here to here is release 26.3" pointer, plus a
#     CHANGELOG divider and an extra mike docs alias. Pushing vX.Y.Z →
#     triggers .github/workflows/release.yml as before.
#
# Usage:
#   ./scripts/repository/release.sh show
#   ./scripts/repository/release.sh bump patch|minor|major
#   ./scripts/repository/release.sh check
#   ./scripts/repository/release.sh checkpoint [patch|minor|major]  # make tag
#   ./scripts/repository/release.sh release [YY.Q]                  # make release
#   ./scripts/repository/release.sh tag          # low-level: annotated tag vX.Y.Z
#   ./scripts/repository/release.sh push-tag     # low-level: push tag to origin

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
    printf 'Synced: cockpit/uv.lock, VERSION, mkdocs.yml, README.md, docs/en/index.md, docs/pl/index.md\n'
    printf '(Low-level — usually you want: make tag)\n'
}

# --- CHANGELOG.md surgery -----------------------------------------------
# Convention: "## [Unreleased]" stays permanently at the top, empty
# between checkpoints. checkpoint() renames it to "## [X.Y.Z] - DATE" and
# opens a fresh empty one above. cut_release() leaves those version
# sections untouched and just drops a "## YY.Q — DATE" divider above the
# ones accumulated since the previous divider (visual grouping, no
# heading-level surgery needed).

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

changelog_cut_release() {
    local calver="$1" date="$2"
    grep -q '^## \[Unreleased\]$' "${CHANGELOG}" || die "${CHANGELOG}: no '## [Unreleased]' heading"
    awk -v cv="${calver}" -v d="${date}" '
        /^## \[Unreleased\]$/ { print; print ""; print "## " cv " — " d; next }
        { print }
    ' "${CHANGELOG}" >"${CHANGELOG}.tmp" && mv "${CHANGELOG}.tmp" "${CHANGELOG}"
}

# Calver label directly above a version'"'"'s "## [X.Y.Z]" section (empty if
# that version predates this scheme, or has no release divider yet).
changelog_calver_for() {
    local version="$1"
    awk -v target="## [${version}]" '
        /^## [0-9][0-9]\.[0-9]+ /{cv=$2}
        index($0, target) == 1 {print cv; exit}
    ' "${CHANGELOG}"
}

current_branch() {
    git rev-parse --abbrev-ref HEAD
}

# make tag: a personal, frequent stop, fully pushed (commit + tag) —
# nothing hidden on your machine only. Safe because checkpoint tags live
# in their own "checkpoint/vX.Y.Z" namespace, never bare "vX.Y.Z":
#   - orcan upgrade/downgrade (cli/lib/git.sh) only ever look for tags
#     matching ^v[0-9]+\.[0-9]+\.[0-9]+$ — "checkpoint/..." never matches,
#     so a checkpoint can never become an upgrade/downgrade target.
#   - release.yml's trigger glob "v*.*.*" requires the tag to literally
#     start with "v" — "checkpoint/..." doesn't, so pushing one can't
#     fire the release pipeline either.
# CI's `checks` job still tests the commit (triggers on every push to
# main, tag or not). Only a real `vX.Y.Z` tag — created solely by
# `make release` — is ever a release candidate.
cmd_checkpoint() {
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

    write_version "${new}"
    sync_version_displays "${old}" "${new}"
    today="$(date +%F)"
    changelog_checkpoint "${new}" "${today}"
    git add cockpit/pyproject.toml cockpit/uv.lock VERSION CHANGELOG.md \
        mkdocs.yml README.md docs/en/index.md docs/pl/index.md
    git commit -m "chore: checkpoint v${new}" >/dev/null
    git tag -a "checkpoint/v${new}" -m "orcan checkpoint v${new}"
    git push origin "$(current_branch)"
    git push origin "checkpoint/v${new}"
    printf 'Checkpoint: v%s (commit + tag checkpoint/v%s pushed — CI runs tests, no release triggered)\n' "${new}" "${new}"
}

compute_calver() {
    local q
    q=$(( ($(date +%-m) - 1) / 3 + 1 ))
    printf '%s.%s' "$(date +%y)" "${q}"
}

# make release: the rare, deliberate public stop. Auto-checkpoints
# anything still sitting in Unreleased, drops a CalVer divider in the
# CHANGELOG, tags vX.Y.Z if needed, and pushes (CI takes it from there).
cmd_release() {
    local calver="${1:-$(compute_calver)}"
    [[ "${calver}" =~ ^[0-9]{2}\.[0-9]+$ ]] || die "release label must look like YY.Q (got: ${calver})"
    require_clean_tree
    # Validate everything that can fail *before* committing/tagging
    # anything — a reused label must not leave a half-finished release
    # (an extra local commit or tag) behind.
    if git rev-parse "${calver}" >/dev/null 2>&1; then
        die "tag ${calver} already exists — pick a different release label"
    fi

    local unreleased
    unreleased="$(changelog_unreleased_body | sed '/^[[:space:]]*$/d')"
    if [[ -n "${unreleased}" ]]; then
        cmd_checkpoint patch
    fi

    local v today
    v="$(read_version)"
    today="$(date +%F)"
    changelog_cut_release "${calver}" "${today}"
    git add CHANGELOG.md
    git commit -m "release: ${calver} (v${v})" >/dev/null

    # Release always ships from a real, pushed SemVer tag — create it if
    # `make tag` hasn't already (e.g. releasing straight off Unreleased).
    if ! git rev-parse "v${v}" >/dev/null 2>&1; then
        git tag -a "v${v}" -m "orcan v${v} — release ${calver}"
    fi

    # Plus its own CalVer tag — a second, human-named pointer at the same
    # commit ("from here to here is release 26.3"). Bare (no "v" prefix),
    # so it can't collide with vX.Y.Z matching in cli/lib/git.sh or with
    # release.yml's "v*.*.*" tag-push trigger. Already confirmed free above.
    git tag -a "${calver}" -m "orcan release ${calver} (v${v})"

    git push origin "$(current_branch)"
    git push origin "v${v}" "${calver}"
    printf 'Released %s → v%s (both pushed)\n' "${calver}" "${v}"
    printf 'CI: validates, deploys docs %s (+ alias %s), creates GitHub Release\n' "${v}" "${calver}"
}

# Keep display copies in sync (enforced by tests/host/test_version.py).
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

# Retract a mistakenly published release without rewriting main history.
# The CalVer tag points at the small release-divider commit, so reverting it
# returns CHANGELOG to a state where the same VERSION / CalVer can be released
# again from a later commit. This intentionally leaves checkpoint tags alone.
cmd_retract() {
    local v="${1:-}" calver="${2:-}" confirm="${3:-}"
    [[ "${v}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "usage: release.sh retract X.Y.Z YY.Q RETRACT-vX.Y.Z"
    [[ "${calver}" =~ ^[0-9]{2}\.[0-9]+$ ]] \
        || die "CalVer label must look like YY.Q (got: ${calver:-empty})"
    [[ "${confirm}" == "RETRACT-v${v}" ]] \
        || die "refusing retraction: set CONFIRM=RETRACT-v${v}"
    require_clean_tree

    local semver_tag="v${v}" release_commit subject semver_commit run_id
    git ls-remote --exit-code --tags origin "refs/tags/${semver_tag}" >/dev/null \
        || die "origin has no ${semver_tag} tag"
    git ls-remote --exit-code --tags origin "refs/tags/${calver}" >/dev/null \
        || die "origin has no ${calver} CalVer tag"
    git fetch origin "refs/tags/${semver_tag}:refs/tags/${semver_tag}" \
        "refs/tags/${calver}:refs/tags/${calver}" >/dev/null
    release_commit="$(git rev-list -n 1 "${calver}")"
    subject="$(git log -1 --format=%s "${release_commit}")"
    [[ "${subject}" == "release: ${calver} (v${v})" ]] \
        || die "${calver} does not point at release: ${calver} (v${v}); refusing to revert ${subject@Q}"
    git merge-base --is-ancestor "${release_commit}" HEAD \
        || die "release commit ${release_commit:0:12} is not an ancestor of HEAD"
    semver_commit="$(git rev-list -n 1 "${semver_tag}")"

    printf 'Retracting release %s / %s:\n' "${semver_tag}" "${calver}"
    printf '  - revert release-divider commit %s (%s)\n' "${release_commit:0:12}" "${subject}"
    printf '  - remove pinned docs %s (and alias %s)\n' "${v}" "${calver}"
    printf '  - remove GitHub Release %s\n' "${semver_tag}"
    printf '  - delete origin tags %s and %s\n' "${semver_tag}" "${calver}"
    printf '  - preserve checkpoint/%s and all ordinary commits\n' "${semver_tag}"

    # Revert first: a docs/GitHub failure leaves the old release public, but
    # main explicitly records the retraction instead of silently moving tags.
    git revert --no-edit "${release_commit}"
    git push origin "$(current_branch)"

    if [[ "${RELEASE_RETRACT_SKIP_DOCS:-0}" != "1" ]]; then
        "${ROOT_DIR}/scripts/repository/docs-mike.sh" delete "${v}"
    else
        printf 'Skip: docs deletion (RELEASE_RETRACT_SKIP_DOCS=1)\n'
    fi

    if [[ "${RELEASE_RETRACT_SKIP_GITHUB:-0}" != "1" ]]; then
        command -v gh >/dev/null 2>&1 || die "gh CLI is required (or set SKIP_GITHUB=1 only when no GitHub Release exists)"
        while IFS= read -r run_id; do
            [[ -n "${run_id}" ]] || continue
            gh run cancel "${run_id}" >/dev/null || true
            printf 'Cancelled active release workflow run %s\n' "${run_id}"
        done < <(gh run list --workflow release.yml --limit 100 \
            --json databaseId,status,headSha --jq \
            ".[] | select(.headSha == \"${semver_commit}\" and (.status == \"queued\" or .status == \"in_progress\" or .status == \"waiting\")) | .databaseId")
        if gh release view "${semver_tag}" >/dev/null 2>&1; then
            gh release delete "${semver_tag}" --yes
            printf 'Deleted GitHub Release %s\n' "${semver_tag}"
        else
            printf 'Note: GitHub Release %s was not present\n' "${semver_tag}"
        fi
    else
        printf 'Skip: GitHub Release deletion (RELEASE_RETRACT_SKIP_GITHUB=1)\n'
    fi

    git push origin --delete "${semver_tag}" "${calver}"
    git tag -d "${semver_tag}" "${calver}" >/dev/null
    printf 'Retracted %s. Fix forward on main, then run: make release Q=%s\n' \
        "${semver_tag}" "${calver}"
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
    printf 'GitHub Actions: Release workflow validates + creates GitHub Release\n'
    printf 'Users: git checkout v%s && orcan build --all-agents && orcan up\n' "${v}"
}

usage() {
    cat <<'EOF'
Usage: release.sh <show|print|bump|check|checkpoint|release|retract|tag|push-tag>

  show               Print version (from cockpit/pyproject.toml) and local image tags
  print              Print SemVer only (scripting)
  bump PART          Low-level: bump SemVer in pyproject (patch|minor|major) + sync copies
  check              Validate pyproject SemVer and VERSION mirror
  checkpoint [PART]  make tag: bump + CHANGELOG cut + commit + push checkpoint/vX.Y.Z
  release [YY.Q]     make release: CalVer divider + push vX.Y.Z + GitHub Release
  retract X.Y.Z YY.Q RETRACT-vX.Y.Z
                     Retract a published release without rewriting main
  tag                Low-level: create annotated git tag vX.Y.Z from current HEAD (clean tree)
  push-tag           Low-level: push tag to origin
EOF
}

case "${1:-}" in
    show) cmd_show ;;
    print) cmd_print ;;
    bump) cmd_bump "${2:-}" ;;
    check) cmd_check ;;
    checkpoint) cmd_checkpoint "${2:-patch}" ;;
    release) cmd_release "${2:-}" ;;
    retract) cmd_retract "${2:-}" "${3:-}" "${4:-}" ;;
    tag) cmd_tag ;;
    push-tag) cmd_push_tag ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1" ;;
esac
