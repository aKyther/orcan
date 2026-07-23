#!/usr/bin/env bash
# Resolve Python for host repository scripts (prefer project .venv with PyYAML).
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    exec "${ROOT_DIR}/.venv/bin/python" "$@"
fi
exec python3 "$@"
