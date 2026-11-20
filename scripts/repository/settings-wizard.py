#!/usr/bin/env python3
"""Edit tool settings and bundled plugins without changing workspace definitions."""

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
from orcan.plugin_registry import catalog, validate_field, validate_selection
from orcan.plugin_registry import resolve as resolve_plugins
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
    info()
    info("── Current settings ──")
    info(f"  tmux: {tmux.get('initial_windows', '?')} windows, prefix {tmux.get('window_prefix', '?')!r}")
    current = resolve_plugins(cfg)
    for group in ("access", "services", "interface"):
        info("  " + group.capitalize() + ":")
        for entry in catalog():
            if entry["group"] == group and entry.get("configurable", True):
                mark = "on" if current[entry["id"]]["enabled"] else "off"
                info(f"    [{mark}] {entry['id']}: {entry['title']}")


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


def edit_plugins(cfg: dict[str, Any]) -> bool:
    """One package-driven list controls activation and each package's own fields."""
    proposed = resolve_plugins(cfg)
    entries = catalog()
    for group in ("access", "services", "interface"):
        heading(group.capitalize() + " plugins")
        for entry in entries:
            if entry["group"] != group or not entry.get("configurable", True):
                continue
            name = entry["id"]
            current = proposed[name]
            for hint in entry['help']: info(hint)
            for example in entry['examples']: info('Example JSON: '+example)
            current["enabled"] = ask_yes_no(f"Enable {entry['title']} ({name})?", default=current["enabled"])
            if not current["enabled"] or not entry["fields"]:
                continue
            configure = name == "network" and not current.get("name")
            if not configure and not ask_yes_no(f"Configure {entry['title']} settings?", default=False):
                continue
            for key, rule in entry["fields"].items():
                if rule.get("hidden"):
                    continue
                try:
                    if rule.get("help"): info(rule["help"])
                    if rule["type"] == "boolean":
                        value = ask_yes_no(rule["label"], default=current[key])
                    else:
                        value = ask(rule["label"], str(current[key]))
                        if rule["type"] == "integer": value = int(value)
                    current[key] = validate_field(name, key, value, rule)
                except ValueError as error:
                    warn(f"{error} — keeping the previous field value")
    try:
        validate_selection(proposed, entries)
    except ValueError as error:
        warn(f"{error} — plugin changes were not applied")
        return False
    cfg["plugins"] = {entry["id"]:proposed[entry["id"]] for entry in entries if entry.get("configurable", True)}
    # Move compatibility sections only in this explicit, user-reviewed save flow.
    for key in ("executor", "executor_port", "ttyd"):
        cfg.pop(key, None)
    return True


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
    if ask_yes_no("Configure an artifact storage host path (for example SSHFS)?", default=False):
        from orcan.storage_config import resolve as resolve_storage
        current=resolve_storage(cfg.get('storage'))
        path=ask("Existing absolute host storage path ('-' disables external storage)", current['path'])
        path='' if path=='-' else path
        mount=ask("Expected host mountpoint ('-' means storage path itself)",current['mount_path'])
        mount='' if mount=='-' else mount
        require=ask_yes_no('Require this mountpoint before startup?',default=current['require_mount'])
        cfg['storage']=resolve_storage({'path':path,'mount_path':mount,'require_mount':require})
    if ask_yes_no("Choose startup plugins and their settings?", default=False):
        edit_plugins(cfg)

    cfg.setdefault("tmux", dict(DEFAULT_TMUX))

    summarize(cfg)
    info()
    if not ask_yes_no("Save these settings?", default=True):
        info("Cancelled — nothing written.")
        return

    dump_config(config_path, cfg)
    success(f"saved {config_path}")
    info()
    info(
        "Next: orcan sync, then orcan up. Enabled plugins are selected automatically; running processes are not changed until recreation."
    )


if __name__ == "__main__":
    main()
