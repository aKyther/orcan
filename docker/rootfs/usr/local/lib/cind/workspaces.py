"""Shared workspace helpers for cind container scripts.

Import as: ``from cind.workspaces import …`` (``/usr/local/lib`` on PYTHONPATH
via the ``cind-workspaces`` / ``cind-context-status`` entry points, or
``sys.path.insert(0, "/usr/local/lib")``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator


DEFAULT_CONFIG = "/etc/cind/config.json"

# Files that mark a project as having agent ignore coverage.
PROJECT_IGNORE_MARKERS = (
    ".cursorignore",
    ".claudeignore",
)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path or os.environ.get("CIND_CONFIG") or DEFAULT_CONFIG)
    with cfg_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"config root must be an object: {cfg_path}")
    return data


def iter_workspaces(cfg: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield enabled workspaces with normalized name/root/tmux_session/projects."""
    workspaces = cfg.get("workspaces") or []
    if not workspaces:
        legacy = cfg.get("workspace") or {}
        projects = cfg.get("projects") or []
        if legacy or projects:
            merged = dict(legacy) if isinstance(legacy, dict) else {}
            merged.setdefault("projects", projects)
            workspaces = [merged]

    for ws in workspaces:
        if not isinstance(ws, dict):
            continue
        if ws.get("enabled") is False:
            continue
        name = str(ws.get("name") or "workspace").strip() or "workspace"
        root = str(ws.get("root") or "").strip()
        session = str(ws.get("tmux_session") or ws.get("tmux") or name).strip() or name
        projects = ws.get("projects") if isinstance(ws.get("projects"), list) else []
        yield {
            "name": name,
            "root": root,
            "tmux_session": session,
            "projects": projects,
            "raw": ws,
        }


def project_paths(cfg: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ws in iter_workspaces(cfg):
        for item in ws["projects"]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            out.append(path)
    return out


def repo_names(ws: dict[str, Any]) -> str:
    names: list[str] = []
    for item in ws.get("projects") or []:
        if not isinstance(item, dict):
            continue
        names.append(str(item.get("name") or item.get("alias") or "?").strip() or "?")
    return ", ".join(names)


def project_needs_init(path: str | Path) -> bool:
    root = Path(path)
    if not root.is_dir():
        return False
    return not any((root / name).is_file() for name in PROJECT_IGNORE_MARKERS)


def projects_needing_init(ws: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for item in ws.get("projects") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        name = str(item.get("name") or "?").strip() or "?"
        if path and project_needs_init(path):
            missing.append(name)
    return missing


def pack_flags(root: str | Path) -> dict[str, bool]:
    r = Path(root)
    return {
        "manifest": (r / ".manifest.json").is_file(),
        "agents": (r / "AGENTS.md").is_file(),
        "claude_md": (r / "CLAUDE.md").is_file(),
        "cursorignore": (r / ".cursorignore").is_file(),
        "cursorindexingignore": (r / ".cursorindexingignore").is_file(),
        "claudeignore": (r / ".claudeignore").is_file(),
        "claude_settings": (r / ".claude" / "settings.json").is_file(),
        "brief": (r / ".cind" / "session-brief.md").is_file(),
        "rules": (r / ".cursor" / "rules").is_dir(),
    }


def compact_hints(ws: dict[str, Any]) -> str:
    """Short flags for launcher lines, e.g. 'brief · init:backend'."""
    root = ws.get("root") or ""
    bits: list[str] = []
    if root and Path(root).is_dir():
        flags = pack_flags(root)
        if flags["brief"]:
            bits.append("brief")
        missing = projects_needing_init(ws)
        if missing:
            bits.append("init:" + ",".join(missing[:4]))
            if len(missing) > 4:
                bits.append(f"+{len(missing) - 4}")
        elif not flags["cursorignore"] and not flags["claudeignore"]:
            bits.append("no-ignore")
    else:
        bits.append("missing-root")
    return " · ".join(bits)


def format_status(ws: dict[str, Any]) -> str:
    name = ws["name"]
    root = ws["root"]
    lines = [
        f"workspace: {name}",
        f"root:      {root}",
        f"tmux:      {ws['tmux_session']}",
        "",
        "context pack:",
    ]
    if not root or not Path(root).is_dir():
        lines.append("  (root missing — run make env && recreate container)")
        return "\n".join(lines) + "\n"

    flags = pack_flags(root)
    for key, label in (
        ("manifest", ".manifest.json"),
        ("agents", "AGENTS.md"),
        ("claude_md", "CLAUDE.md"),
        ("cursorignore", ".cursorignore"),
        ("cursorindexingignore", ".cursorindexingignore"),
        ("claudeignore", ".claudeignore"),
        ("claude_settings", ".claude/settings.json"),
        ("rules", ".cursor/rules/"),
        ("brief", ".cind/session-brief.md"),
    ):
        mark = "ok" if flags[key] else "—"
        note = ""
        if key == "brief" and not flags[key]:
            note = "  (create: cind-session-brief)"
        lines.append(f"  [{mark}] {label}{note}")

    missing = projects_needing_init(ws)
    lines.append("")
    lines.append(f"projects: {len(ws.get('projects') or [])}")
    if missing:
        lines.append(
            "  need cursor-init-project (no .cursorignore/.claudeignore): "
            + ", ".join(missing)
        )
        lines.append("  fix: cursor-init-project <path>  or  make init-project-all")
    else:
        lines.append("  project ignores: ok (or no projects)")
    return "\n".join(lines) + "\n"
