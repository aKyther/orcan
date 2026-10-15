#!/usr/bin/env bash
set -euo pipefail
# Offline: test dependencies must already be cached by uv.
export UV_OFFLINE=1
make test-host
