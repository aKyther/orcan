#!/usr/bin/env bash
# Run host-side unit tests (no Docker image build required).
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

export PYTHONPATH="${ROOT_DIR}/scripts/repository${PYTHONPATH:+:$PYTHONPATH}"

if ! command -v uv >/dev/null 2>&1; then
    printf 'Host tests require uv. Install uv, then rerun make test-host.\n' >&2
    exit 1
fi

printf '==> host tests (pytest via uv)\n'
uv run --no-project --with-requirements requirements-test.txt python -m pytest tests/host -v

printf '==> release.sh check\n'
./scripts/repository/release.sh check

printf 'Host tests OK\n'
