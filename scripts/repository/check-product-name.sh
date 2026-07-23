#!/usr/bin/env bash
# Fail if historical product names reappear as branding in user-facing docs.
# Allows: Cursor (editor/CLI), cursor-* binaries, cind migration notes,
# and meta lines that *forbid* old names.
# Host-only.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

fail=0

scan_list="$(mktemp)"
trap 'rm -f "${scan_list}"' EXIT

{
    printf '%s\n' README.md AGENTS.md CONTRIBUTING.md CHANGELOG.md LICENSE mkdocs.yml
    find docs/en docs/pl docs/assets .cursor/rules -type f \( -name '*.md' -o -name '*.mdc' -o -name '*.yml' -o -name '*.svg' \) 2>/dev/null || true
} > "${scan_list}"

mapfile -t files < "${scan_list}"

# Meta / allowlist lines may mention forbidden names on purpose.
allow_re='old product|do not (reintroduce|use)|Forbidden|except migration|migration notes|cind-as-product|historical'

if raw="$(grep -nEiw 'Sint|Orkan' "${files[@]}" 2>/dev/null || true)" && [[ -n "${raw}" ]]; then
    hits="$(printf '%s\n' "${raw}" | grep -Ev "${allow_re}" || true)"
    if [[ -n "${hits}" ]]; then
        printf 'Forbidden old product name (Sint|Orkan):\n%s\n' "${hits}" >&2
        fail=1
    fi
fi

if hits="$(grep -nF 'Cursor CLI Dev Container' "${files[@]}" 2>/dev/null || true)" && [[ -n "${hits}" ]]; then
    printf 'Forbidden old project title:\n%s\n' "${hits}" >&2
    fail=1
fi

if grep -nE '^# orcan[[:space:]]*$' README.md docs/en/index.md docs/pl/index.md 2>/dev/null; then
    printf 'Use display name "# Orcan" in README/docs index titles\n' >&2
    fail=1
fi

if [[ "${fail}" -ne 0 ]]; then
    printf 'Product-name check failed\n' >&2
    exit 1
fi

printf 'Product-name check OK\n'
