#!/usr/bin/env python3
"""Interactive wizard to edit tool-level settings (tmux / ttyd) in
orcan.config.json — separate from `orcan init`'s workspace/project editing
(config-wizard.py / context_tui.py). Only touches the top-level "tmux", "ttyd" and "executor" keys; never reads or writes "workspaces".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "docker/rootfs/usr/local/lib")
)
from config_io import (
    discover_config,
    dump_config,
    load_config,
)
from defaults import TMUX_DEFAULTS as DEFAULT_TMUX
from defaults import TTYD_DEFAULTS as DEFAULT_TTYD
from orcan.executor_config import resolve as resolve_executor
from wizard_ui import (
    ask,
    ask_yes_no,
    die,
    heading,
    info,
    success,
    warn,
)


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
    executor = resolve_executor(cfg.get("executor", {}))
    info(
        f"  executor: split lanes={executor['split_lanes']}, max running={executor['max_running']}, "
        f"pending={executor['max_pending']}, timeout={executor['timeout_seconds']}s, "
        f"log retention={executor['retention_seconds']}s, Redis={executor['redis_memory_mb']} MiB, "
        f"visibility={executor['visibility_timeout_seconds']}s"
    )


def edit_tmux(cfg: dict[str, Any]) -> None:
    current = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else DEFAULT_TMUX
    windows = ask(
        "Initial tmux windows per workspace", str(current.get("initial_windows", 3))
    )
    try:
        n = int(windows)
        n = max(1, min(9, n))
    except ValueError:
        n = 3
        warn("invalid number — using 3")
    prefix = (
        ask("Window name prefix", str(current.get("window_prefix", "tab"))) or "tab"
    )
    cfg["tmux"] = {"initial_windows": n, "window_prefix": prefix}


def edit_ttyd(cfg: dict[str, Any]) -> None:
    current = cfg.get("ttyd") if isinstance(cfg.get("ttyd"), dict) else DEFAULT_TTYD
    port = ask("ttyd container port", str(current.get("port", 7681)))
    host_port = ask("ttyd host port", str(current.get("host_port", port)))
    bind = (
        ask(
            "ttyd host bind (0.0.0.0=all interfaces; 127.0.0.1=local only)",
            str(current.get("bind", "0.0.0.0")),
        ).strip()
        or "0.0.0.0"
    )
    if bind not in ("127.0.0.1", "0.0.0.0", "localhost") and ":" not in bind:
        # Allow IPv4 literals; reject empty garbage.
        parts = bind.split(".")
        if not (
            len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
        ):
            warn("unusual bind address — keeping it; prefer 127.0.0.1 or 0.0.0.0")
    if bind in ("0.0.0.0", "::"):
        warn(
            "binding all interfaces — set TTYD_CREDENTIAL=user:pass in .env for basic auth"
        )
    font = ask("ttyd font size", str(current.get("font_size", 14)))
    renderer = (
        ask(
            "ttyd renderer (webgl=fast; canvas=fallback)",
            str(current.get("renderer", DEFAULT_TTYD["renderer"])),
        )
        .strip()
        .lower()
    )
    if renderer not in ("webgl", "canvas"):
        warn("renderer must be webgl or canvas — settings unchanged")
        return
    try:
        cfg["ttyd"] = {
            "port": int(port),
            "host_port": int(host_port),
            "bind": bind,
            "font_size": int(font),
            "font_family": current.get("font_family", DEFAULT_TTYD["font_family"]),
            "renderer": renderer,
            "theme": current.get("theme", DEFAULT_TTYD["theme"]),
            "ping_interval": current.get(
                "ping_interval", DEFAULT_TTYD["ping_interval"]
            ),
        }
    except ValueError:
        warn("invalid ttyd numbers — settings unchanged")


def edit_executor(cfg: dict[str, Any]) -> None:
    current = resolve_executor(cfg.get("executor", {}))
    proposed = dict(current)
    proposed["split_lanes"] = ask_yes_no(
        "Enable default/light/heavy workers?", default=current["split_lanes"]
    )
    try:
        for key, label in [
            ("max_running", "Maximum simultaneous jobs across workers (1..3)"),
            ("max_pending", "Maximum queued plus running jobs (1..10000)"),
            ("timeout_seconds", "Default job timeout in seconds (1..21600)"),
            ("retention_seconds", "Detailed log retention in seconds (60..86400)"),
            ("redis_memory_mb", "Redis memory budget in MiB (32..4096)"),
            (
                "visibility_timeout_seconds",
                "Redis visibility timeout in seconds (22200..86400)",
            ),
        ]:
            proposed[key] = int(ask(label, str(current[key])))
        cfg["executor"] = current | resolve_executor(proposed)
    except ValueError as error:
        warn(f"{error} — executor settings unchanged")
    info(
        "Requires --with-redis. The parallel job cap is enforced; CPU/RAM remain container-wide limits."
    )


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

    if ask_yes_no(
        "Change executor (queues / parallel jobs / timeout / retention)?", default=False
    ):
        heading("executor")
        edit_executor(cfg)

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
    info(
        "Next: orcan sync, then recreate with your runtime flags (including --with-redis); settings are not applied to a running process automatically"
    )


if __name__ == "__main__":
    main()
