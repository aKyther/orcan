#!/usr/bin/env bash
# Resolve Python for host repository scripts (stdlib only — no venv required).
set -Eeuo pipefail
exec python3 "$@"
