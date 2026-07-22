#!/usr/bin/env bash
# Print workspace manifest summary for make path-check (host-only).
set -Eeuo pipefail

manifest="${1:-.cind/workspace.manifest.json}"
[[ -f "${manifest}" ]] || exit 0

python3 - "${manifest}" <<'PY'
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"workspaces: {len(m.get('workspaces', []))}")
for ws in m.get("workspaces", []):
    print(f"{ws['name']}: tmux={ws.get('tmux_session')} root={ws.get('root')}")
    for p in ws.get("projects", []):
        print(f"  {p['name']}: {p['path']} -> {p.get('workspace_path')}")
PY
