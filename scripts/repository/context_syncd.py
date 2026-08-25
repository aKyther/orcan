#!/usr/bin/env python3
"""Host-side Context Assertions sync watcher (spike).

Watches each workspace's ``.orcan/context-inbox/`` and ``context-decisions/``
for file changes, then runs the same ``compile_context`` import+compile path
``orcan sync`` uses — without apply-config or live reconcile.

Why host, not container supervisord: ``$ORCAN_DATA/context`` is intentionally
not mounted in the container; only the host may promote inbox drops into the
git-versioned store / ``CONTEXT-ASSERTIONS.md``.

  orcan sync --context           # one compile pass (via sync.sh)
  orcan sync --context --watch   # this module, poll forever
  orcan sync --context --once    # compile only when fingerprint changed

Human accept/reject stays required — this only imports what a human (or
interactive propose) already stamped, plus undecided proposes as ``proposed``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_REPO_LIB = Path(__file__).resolve().parents[2] / "docker" / "rootfs" / "usr" / "local" / "lib"
if _REPO_LIB.is_dir():
    sys.path.insert(0, str(_REPO_LIB))

import compile_context as cc  # noqa: E402

try:
    from orcan.automation import is_active, is_enabled, is_paused  # noqa: E402
except ImportError:  # pragma: no cover
    def is_active() -> bool:
        return True

    def is_enabled() -> bool:
        return True

    def is_paused() -> bool:
        return False

STATE_NAME = "context-syncd-state.json"
WATCH_DIRS = ("context-inbox", "context-decisions", "context-flags")


def inbox_fingerprint(root: Path) -> str:
    """Fingerprint of every drop that compile_context may import or clear."""
    workspaces = cc.load_enabled_workspaces(root)
    if not workspaces:
        return ""
    parts: list[str] = []
    for ws in workspaces:
        meta = Path(ws.get("meta_path") or "")
        if not meta.is_dir():
            continue
        orcan_dir = meta / ".orcan"
        for dirname in WATCH_DIRS:
            directory = orcan_dir / dirname
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    st = path.stat()
                except OSError:
                    continue
                parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
    return "\n".join(parts)


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def run_compile(root: Path) -> int:
    workspaces = cc.load_enabled_workspaces(root)
    if workspaces is None:
        print(f"context-syncd: no runtime config at {root / 'mounts' / 'runtime-config.json'} — run full: orcan sync")
        return 1
    if not workspaces:
        print("context-syncd: no enabled workspaces")
        return 0
    for ws in workspaces:
        cc.compile_workspace(ws)
    return 0


def sync_if_changed(root: Path, *, force: bool = False) -> int:
    if not is_enabled():
        print("context-syncd: context automation disabled — skip (cockpit [o] to enable)")
        return 0
    if is_paused() and not force:
        print("context-syncd: automation paused — skip (cockpit [p] to resume)")
        return 0
    state_path = root / "mounts" / STATE_NAME
    state = load_state(state_path)
    fp = inbox_fingerprint(root)
    prev = str(state.get("fingerprint") or "")
    if not force and fp == prev:
        print("context-syncd: no inbox/decision changes")
        return 0
    print(f"context-syncd: importing ({'forced' if force else 'fingerprint changed'})")
    rc = run_compile(root)
    if rc == 0:
        # Recompute after import — drops may have been deleted.
        save_state(
            state_path,
            {
                "fingerprint": inbox_fingerprint(root),
                "last_sync_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        print("context-syncd: done")
    return rc


def watch_loop(root: Path, interval: float) -> int:
    print(f"context-syncd: watching {root} every {interval:.0f}s (Ctrl-C to stop)")
    try:
        while True:
            if is_paused():
                print("context-syncd: automation paused — idle")
            elif not is_enabled():
                print("context-syncd: context automation disabled — idle")
            else:
                sync_if_changed(root, force=False)
            time.sleep(max(1.0, interval))
    except KeyboardInterrupt:
        print("\ncontext-syncd: stopped")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("orcan_home", type=Path, help="ORCAN_HOME (contains mounts/runtime-config.json)")
    parser.add_argument("--watch", action="store_true", help="Poll forever")
    parser.add_argument("--once", action="store_true", help="Sync only if fingerprint changed, then exit")
    parser.add_argument("--force", action="store_true", help="Compile even if fingerprint unchanged")
    parser.add_argument("--interval", type=float, default=15.0, help="Seconds between --watch polls")
    args = parser.parse_args()

    root = args.orcan_home.resolve()
    if args.watch and args.once:
        print("context-syncd: use only one of --watch / --once", file=sys.stderr)
        return 2
    if args.watch:
        return watch_loop(root, args.interval)
    if args.once:
        return sync_if_changed(root, force=args.force)
    # Plain one-shot compile (same as orcan sync --context without watch)
    rc = run_compile(root)
    if rc == 0:
        state_path = root / "mounts" / STATE_NAME
        save_state(
            state_path,
            {
                "fingerprint": inbox_fingerprint(root),
                "last_sync_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
