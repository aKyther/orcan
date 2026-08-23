#!/usr/bin/env bash
# Compatibility wrapper — use move-worktrees-into-sandbox.sh
set -Eeuo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${here}/move-worktrees-into-sandbox.sh" "$@"
