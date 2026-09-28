#!/usr/bin/env bash
# Run host-side unit tests (no Docker image build required).
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

export PYTHONPATH="${ROOT_DIR}/scripts/repository${PYTHONPATH:+:$PYTHONPATH}"

printf '==> host tests (pytest)\n'
python3 -m pytest tests/host -v

printf '==> release.sh check\n'
./scripts/repository/release.sh check

printf 'Host tests OK\n'
