#!/usr/bin/env python3
"""Interactive wizard to edit tool-level settings (tmux / ttyd) in
orcan.config.json — separate from `orcan init`'s workspace/project editing
(config-wizard.py / context_tui.py). Only touches the top-level "tmux" and
"ttyd" keys; never reads or writes "workspaces".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import (  # noqa: E402
    discover_config,
    dump_config,
    load_config,
)
from wizard_ui import (  # noqa: E402
    ask,
    ask_yes_no,
    die,
    heading,
    info,
    success,
    warn,
)

DEFAULT_TMUX = {"initial_windows": 3, "window_prefix": "tab"}
DEFAULT_TTYD = {
    "port": 7681,
    "host_port": 7681,
    "bind": "0.0.0.0",
    "font_size": 19,
    "font_family": "Menlo, Monaco, 'Courier New', monospace",
    "theme": "dark",
    "ping_interval": 20,
}


def summarize(cfg: dict[str, Any]) -> None:
    tmux = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else DEFAULT_TMUX
    ttyd = cfg.get("ttyd") if isinstance(cfg.get("ttyd"), dict) else DEFAULT_TTYD
    info()
    info("── Current settings ──")
    info(
        f"  tmux: {tmux.get('initial_windows', '?')} windows, "
        f"prefix {tmux.get('window_prefix', '?')!r}"
    )
    info(
        f"  ttyd: host {ttyd.get('bind', '0.0.0.0')}:{ttyd.get('host_port', '?')}, "
        f"font {ttyd.get('font_size', '?')}"
    )


def edit_tmux(cfg: dict[str, Any]) -> None:
    current = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else DEFAULT_TMUX
    windows = ask("Initial tmux windows per workspace", str(current.get("initial_windows", 3)))
    try:
        n = int(windows)
        n = max(1, min(9, n))
    except ValueError:
        n = 3
        warn("invalid number — using 3")
    prefix = ask("Window name prefix", str(current.get("window_prefix", "tab"))) or "tab"
    cfg["tmux"] = {"initial_windows": n, "window_prefix": prefix}


def edit_ttyd(cfg: dict[str, Any]) -> None:
    current = cfg.get("ttyd") if isinstance(cfg.get("ttyd"), dict) else DEFAULT_TTYD
    port = ask("ttyd container port", str(current.get("port", 7681)))
    host_port = ask("ttyd host port", str(current.get("host_port", port)))
    bind = ask(
        "ttyd host bind (0.0.0.0=all interfaces; 127.0.0.1=local only)",
        str(current.get("bind", "0.0.0.0")),
    ).strip() or "0.0.0.0"
    if bind not in ("127.0.0.1", "0.0.0.0", "localhost") and ":" not in bind:
        # Allow IPv4 literals; reject empty garbage.
        parts = bind.split(".")
        if not (len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)):
            warn("unusual bind address — keeping it; prefer 127.0.0.1 or 0.0.0.0")
    if bind in ("0.0.0.0", "::"):
        warn("binding all interfaces — set TTYD_CREDENTIAL=user:pass in .env for basic auth")
    font = ask("ttyd font size", str(current.get("font_size", 19)))
    try:
        cfg["ttyd"] = {
            "port": int(port),
            "host_port": int(host_port),
            "bind": bind,
            "font_size": int(font),
            "font_family": current.get("font_family", DEFAULT_TTYD["font_family"]),
            "theme": current.get("theme", DEFAULT_TTYD["theme"]),
            "ping_interval": current.get("ping_interval", DEFAULT_TTYD["ping_interval"]),
        }
    except ValueError:
        warn("invalid ttyd numbers — settings unchanged")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="ORCAN_HOME / repo root (default: ORCAN_HOME or orcan repo)",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Config path (default: discover orcan.config.json)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not sys.stdin.isatty():
        die("settings wizard needs an interactive TTY (run in a terminal)")

    if args.config:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = (root / config_path).resolve()
        if not config_path.is_file():
            die(f"config not found: {config_path}")
    else:
        config_path = discover_config(root)
        if config_path is None:
            die("no orcan.config.json found — run 'orcan init' first")

    cfg = load_config(config_path)

    info("orcan settings")
    info("──────────────")
    info(f"Config file: {config_path}")
    summarize(cfg)

    if ask_yes_no("Change tmux (windows / prefix)?", default=False):
        heading("tmux")
        edit_tmux(cfg)
    if ask_yes_no("Change ttyd (port / bind / font)?", default=False):
        heading("ttyd")
        edit_ttyd(cfg)

    cfg.setdefault("tmux", dict(DEFAULT_TMUX))
    cfg.setdefault("ttyd", dict(DEFAULT_TTYD))

    summarize(cfg)
    info()
    if not ask_yes_no("Save these settings?", default=True):
        info("Cancelled — nothing written.")
        return

    dump_config(config_path, cfg)
    success(f"saved {config_path}")
    info()
    info("Next: orcan down && orcan up (tmux/ttyd changes need a container restart)")


if __name__ == "__main__":
    main()
