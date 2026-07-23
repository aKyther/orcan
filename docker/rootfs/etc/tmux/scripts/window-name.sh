#!/usr/bin/env bash
# Optional window rename helper — keeps plain names (no auto icons).
# Usage: window-name.sh [window_id]
# Hook manually in ~/.tmux.conf if desired; orcan does not enable this by default.
set -Eeuo pipefail

wid="${1:-}"
if [[ -z "${wid}" ]]; then
    wid="$(tmux display -p '#{window_id}' 2>/dev/null || true)"
fi
[[ -n "${wid}" ]] || exit 0

current="$(tmux display -p -t "${wid}" '#{window_name}' 2>/dev/null || true)"
[[ -n "${current}" ]] || exit 0

# Leave names as-is; users can rename with prefix ,.
exit 0
