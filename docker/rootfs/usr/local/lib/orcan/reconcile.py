"""Filesystem reconciliation: workspace symlinks, manifests, agent context.

The single implementation for "make the on-disk workspace trees match
orcan.config.json" — used both at container boot (``init-workspace``, once)
and on demand (``orcan-runtime-reconcile``, any time after a live config
change). Same function, two call sites: startup is just the first
reconcile, not a separate code path.

Idempotent: re-running with an unchanged config produces the same on-disk
state and reports no new creates/removes.

Destructive, by design: a workspace dropped from config is not archived on
the next reconcile — its entire on-disk tree is ``shutil.rmtree``'d, not just
the managed symlinks/manifest this module writes. That includes anything a
human or agent left there directly: ``.orcan/session-brief.md``, agent-inbox
tasks (``.orcan/tasks/``). There is no undo — see ``apply_workspaces()`` below and
docs/en/reference/security.md ("Mount layout tradeoffs").
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DEFAULTS_ROOT = Path("/opt/cursor-defaults/templates/workspace")

# Every workspace root is always "<this>/<name>" (apply-config.py's
# DEFAULT_DEVELOPER_WORKSPACES) — scanning it directly means a workspace
# removed from config still gets pruned even if it was the *only* one that
# used to live there (deriving the scan root purely from the surviving
# workspace list would miss that case).
DEVELOPER_WORKSPACES_ROOT = Path("/home/developer/workspaces")

_KEEP_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.workspace.md",
    ".manifest.json",
}


@dataclass
class WorkspaceReport:
    name: str
    root: str
    repo_count: int
    symlinks_created: list[str] = field(default_factory=list)
    symlinks_removed: list[str] = field(default_factory=list)
    dirs_relocated: list[str] = field(default_factory=list)
    skipped_missing_repos: list[str] = field(default_factory=list)


@dataclass
class ReconcileReport:
    workspaces: list[WorkspaceReport] = field(default_factory=list)
    stale_workspace_dirs_removed: list[str] = field(default_factory=list)

    def total_repos(self) -> int:
        return sum(w.repo_count for w in self.workspaces)

    def changed(self) -> bool:
        return bool(self.stale_workspace_dirs_removed) or any(
            w.symlinks_created or w.symlinks_removed or w.dirs_relocated
            for w in self.workspaces
        )


def iter_enabled_workspaces(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    workspaces = cfg.get("workspaces") or []
    if not workspaces:
        legacy = cfg.get("workspace") or {}
        if legacy.get("enabled") is False:
            return []
        projects = cfg.get("projects") or []
        if legacy or projects:
            merged = dict(legacy)
            merged.setdefault("projects", projects)
            workspaces = [merged]
    return [ws for ws in workspaces if ws.get("enabled") is not False]


def _resolve_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _prepare_symlink_target(target: Path, src: Path) -> tuple[bool, str | None]:
    """Clear *target* so ``symlink_to(src)`` can run.

    Project slots under a workspace root must always be symlinks — a real
    directory there (legacy layout, manual clone, pre-worktree checkout) is
    relocated to ``<name>.orcan-reconcile-bak`` rather than left blocking.

    Returns ``(ready, backup_path)``. *backup_path* is set when a directory
    was moved aside.
    """
    if not target.exists() and not target.is_symlink():
        return True, None

    if target.is_symlink() or target.is_file():
        if target.is_symlink() and _resolve_path(target) == _resolve_path(src):
            return False, None
        target.unlink()
        return True, None

    if target.is_dir():
        if _resolve_path(target) == _resolve_path(src):
            return False, None
        bak = target.with_name(f"{target.name}.orcan-reconcile-bak")
        if bak.exists():
            suffix = 2
            while bak.exists():
                bak = target.with_name(f"{target.name}.orcan-reconcile-bak-{suffix}")
                suffix += 1
        try:
            target.rename(bak)
        except OSError as exc:
            print(
                f"skip: could not relocate blocking directory {target}: {exc}",
                file=sys.stderr,
            )
            return False, None
        print(
            f"replaced real directory with backup: {target} -> {bak}",
            file=sys.stderr,
        )
        return True, str(bak)

    return True, None


def _write_if_changed(path: Path, content: str) -> None:
    """Skip the write (and the mtime bump) when content is already current.

    Called on every reconcile (container boot *and* every `orcan sync` against
    a live container), so an unchanged workspace should cost no disk I/O.
    """
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    path.write_text(content, encoding="utf-8")


def _seed_agent_ignores(root: Path, defaults_root: Path, agents: set[str]) -> None:
    from orcan.agent_context import sync_files

    templates = defaults_root.parent
    sync_files(
        root,
        {
            ".cursorignore": ("cursor", templates / "cursorignore"),
            ".cursorindexingignore": ("cursor", templates / "cursorindexingignore"),
            ".claudeignore": ("claude", templates / "claudeignore"),
            ".claude/settings.json": ("claude", templates / "claude/settings.json"),
            ".cursor/rules/workspace-context.mdc": (
                "cursor",
                defaults_root / ".cursor/rules/workspace-context.mdc",
            ),
        },
        agents,
    )


def _write_agents_md(
    root: Path,
    ws: dict[str, Any],
    projects: list[dict[str, Any]],
    identity: dict | None = None,
    agents: set[str] | None = None,
) -> None:
    agents = agents or set()
    name = ws.get("name") or "workspace"
    session = ws.get("tmux_session") or name
    rows = []
    for item in projects:
        pname = (item.get("name") or "").strip() or "?"
        path = (item.get("path") or "").strip() or "?"
        link = (
            item.get("workspace_path")
            or item.get("container_path")
            or f"{root}/{pname}"
        )
        rows.append(f"| `{pname}` | `{path}` | `{link}` |")
    if not rows:
        rows.append("| — | — | — |")

    if len(rows) > 12:
        rows = rows[:12] + [f"| +{len(rows) - 12} more | See `.manifest.json` | |"]

    context_pack_rows = [
        "| `.manifest.json` | Paths / symlinks (source of truth) |",
        "| `AGENTS.md` | Shared workspace instructions |",
        *(
            ["| `CLAUDE.md` | Claude workspace instructions |"]
            if "claude" in agents
            else []
        ),
        *(
            [
                "| `.cursorignore` / `.cursorindexingignore` | Cursor exclusions |",
                "| `.cursor/rules/` | Lasting Cursor rules |",
            ]
            if "cursor" in agents
            else []
        ),
        *(
            [
                "| `.claudeignore` / `.claude/settings.json` | Claude exclusions + denies |"
            ]
            if "claude" in agents
            else []
        ),
        "| `.orcan/session-brief.md` | Optional handoff (only if created) |",
    ]

    body = "\n".join(
        [
            "<!-- Generated by orcan reconcile (init-workspace / orcan-runtime-reconcile).",
            "     Repository instructions and custom files are preserved. -->",
            "",
            f"# AGENTS.md — {name}",
            "",
            "Orcan manages workspace context and local processes, not models/providers.",
            "Read this file, `.manifest.json`, then the current `.orcan/session-brief.md` if it exists.",
            "After entering a repository, that project's `AGENTS.md` / `CLAUDE.md` is SoT for its work.",
            "User goals and repository instructions take priority over stored notes or tool suggestions.",
            "",
            "## Context pack",
            "",
            "| File | Role |",
            "| --- | --- |",
            *context_pack_rows,
            "",
            "## Working rules",
            "",
            "- Work in the target repository; keep changes surgical and preserve unrelated edits.",
            "- Do not read/search `.env`, keys, credentials or secrets. Respect the installed agents’ ignores.",
            "- Prefer uv-managed Python dependencies; never install into system Python.",
            "- Run checks appropriate to the changed behavior; report pending/skipped checks honestly.",
            "- Preserve agent worktrees. Use canonical project paths for Docker mounts, not workspace symlinks.",
            "- Keep successful logs out of model context; inspect only necessary bounded diagnostics.",
            "- Use `orcan-init-project PATH` explicitly to seed installed agents’ missing project files.",
            "- Do not create PLAN/TODO/SUMMARY note files. Use the brief for handoff and explicit knowledge notes.",
            "- Keep custom repository rules. Do not add AI co-author attribution to human-owned commits.",
            "- Delegate to other AI agents only when the user or repository instructions request it.",
            "",
            "## Handoff and selective memory",
            "",
            "The brief is the current working goal: preserve decisions, exact verification status and next action.",
            "At handoff run `orcan-compact --check`; its hash guards a recap/compaction update.",
            "Use `orcan-memory recap --file FILE --expected-sha256 HASH` for a fresh agent-written recap.",
            "`orcan-compact --apply FILE --expected-sha256 HASH` instead requires a smaller brief.",
            "Both archive previous content. Do not load `.orcan/brief-history/` unless needed.",
            "For stable project knowledge use `orcan-memory --project /canonical/repo search 'TOPIC' --limit 3 --budget 3000`.",
            "Project notes share the Git common directory across worktrees. Search is lexical, not guaranteed truth.",
            "Inspect relevant sources and timestamps; `show ID` reads only the chosen note.",
            "Save verified facts with `remember ID --title TITLE --text TEXT --source PATH`; avoid secrets/log dumps.",
            "Existing notes require their expected SHA to update/forget. `orcan-memory --help` lists operations.",
            "Orcan does not import transcripts, crawl repositories or call models to summarize automatically.",
            "",
            "## Runtime capabilities",
            "",
            "Installed agent clients: "
            + (", ".join(sorted(agents)) or "selection unavailable on this host")
            + ".",
            "`orcan-plugins doctor` checks enabled built-ins; `orcan-plugins list` explains their roles.",
            "Cockpit is an interface over tmux; direct shell/tmux access remains available through the host CLI.",
            "",
            "## Projects",
            "",
            f"- Workspace root: `{root}`",
            f"- tmux session: `{session}`",
            "",
            "| Name | Canonical path | Symlink |",
            "| --- | --- | --- |",
            *rows,
            "",
            "Canonical paths are in `.manifest.json`; project directories under this workspace are navigation symlinks.",
            "Use `orcan-context-status` for installed agents’ context gaps. Custom project files are preserved.",
            "",
        ]
    )
    enabled = os.environ.get("ORCAN_REDIS_ENABLED") == "1"
    body += executor_guidance(enabled)
    if identity:
        body += (
            "\n\n## Container identity\n\n"
            + identity["name"]
            + " (version "
            + str(identity["version"])
            + "; template `"
            + identity["id"]
            + "`).\n\n"
            + "These instructions supplement Orcan base rules and repository instructions.\n\n"
            + identity["instructions"]
            + "\n"
        )
    previous_agents = (
        (root / "AGENTS.md").read_text() if (root / "AGENTS.md").is_file() else ""
    )
    _write_if_changed(root / "AGENTS.md", body + "\n")
    claude = root / "CLAUDE.md"
    generated = (
        claude.is_file()
        and not claude.is_symlink()
        and claude.read_text().startswith("<!-- Generated by orcan reconcile")
        and claude.read_text() == previous_agents
    )
    if (
        "claude" in agents
        and not claude.is_symlink()
        and (not claude.exists() or generated)
    ):
        _write_if_changed(claude, body + "\n")
    elif "claude" not in agents and generated:
        claude.unlink()


def _apply_one_workspace(
    ws: dict[str, Any],
    defaults_root: Path,
    identity: dict | None = None,
    agents: set[str] | None = None,
) -> WorkspaceReport:
    root = Path(ws["root"])
    root.mkdir(parents=True, exist_ok=True)

    projects = ws.get("projects") or []
    manifest = {
        "workspace": {
            "name": ws.get("name"),
            "root": ws.get("root"),
            "tmux_session": ws.get("tmux_session") or ws.get("name"),
        },
        "projects": projects,
    }
    _write_if_changed(root / ".manifest.json", json.dumps(manifest, indent=2) + "\n")

    report = WorkspaceReport(
        name=ws.get("name") or "workspace", root=str(root), repo_count=len(projects)
    )
    desired_names: set[str] = set()
    for item in projects:
        name = (item.get("name") or "").strip()
        host_path = (item.get("path") or "").strip()
        # Symlink location is always under this workspace root — never use
        # container_path (parity path) as the link location.
        workspace_path = (item.get("workspace_path") or "").strip()
        if not name or not host_path:
            continue
        desired_names.add(name)
        target = Path(workspace_path) if workspace_path else root / name
        root_prefix = str(root).rstrip("/") + "/"
        if not str(target).startswith(root_prefix):
            target = root / name
        src = Path(host_path)
        if not src.is_dir():
            print(f"skip missing repo mount: {host_path}", file=sys.stderr)
            report.skipped_missing_repos.append(host_path)
            continue
        ready, backup = _prepare_symlink_target(target, src)
        if not ready:
            continue
        if backup is not None:
            report.dirs_relocated.append(f"{target} -> {backup}")
        target.symlink_to(src, target_is_directory=True)
        report.symlinks_created.append(str(target))

    # Drop leftover project symlinks from older configs / other workspaces.
    for child in root.iterdir():
        if child.name in _KEEP_FILES or child.name.startswith("."):
            continue
        if child.name in desired_names:
            continue
        if child.is_symlink():
            child.unlink()
            print(f"removed orphan symlink: {child}", file=sys.stderr)
            report.symlinks_removed.append(str(child))

    _write_agents_md(root, ws, projects, identity, agents)
    _seed_agent_ignores(root, defaults_root, agents or set())

    project_lines = [
        f"| `{item.get('name')}` | `{item.get('path')}` | `{item.get('workspace_path', item.get('container_path', ''))}` |"
        for item in projects
    ]
    readme = root / "README.workspace.md"
    _write_if_changed(
        readme,
        "\n".join(
            [
                f"# {ws.get('name', 'workspace')}",
                "",
                "Human-oriented workspace map. **Agents: read `AGENTS.md` first.**",
                "",
                "| Name | Host path | Symlink |",
                "| --- | --- | --- |",
                *project_lines,
                "",
                "Context: `.manifest.json`, `AGENTS.md` and files for the installed agent clients.",
                "Optional handoff:",
                "`orcan-session-brief` → `.orcan/session-brief.md`.",
                "Per-repo ignores: `orcan-init-project` or `make init-project-all`.",
                "",
            ]
        ),
    )
    return report


def apply_workspaces(
    cfg: dict[str, Any],
    defaults_root: Path | None = None,
    workspaces_parent: Path | None = None,
    agents: set[str] | None = None,
) -> ReconcileReport:
    """Reconcile every enabled workspace's on-disk tree with `cfg`.

    Idempotent — safe to call at container boot and again any time after a
    live config change (adding/removing a project or workspace).
    """
    if agents is None:
        from orcan.agent_context import enabled_agents

        agents = enabled_agents()
    defaults_root = defaults_root or DEFAULT_DEFAULTS_ROOT

    identity = None
    if cfg.get("identity") is not None:
        from orcan.identity import validate_identity

        identity = validate_identity(cfg["identity"])
    workspaces = iter_enabled_workspaces(cfg)
    report = ReconcileReport()

    for ws in workspaces:
        report.workspaces.append(
            _apply_one_workspace(ws, defaults_root, identity, agents)
        )

    # Remove whole workspace dirs that are no longer in config (visible via
    # the parent mount) — never touches a dir whose name is still active.
    # Scans the fixed workspaces-parent directly (not just parents derived
    # from the surviving list) so a removed workspace is pruned even when it
    # was the only one that used to live there.
    #
    # No quarantine, no --prune-orphans-style opt-in gate (unlike the tmux
    # side — see orcan-tmux-reconcile-sessions): dropping a workspace from
    # config is treated as an explicit decision, and the very next reconcile
    # (container boot, or `orcan-runtime-reconcile` after `orcan sync`) acts
    # on it immediately and irreversibly. This is intentional, not an
    # oversight — but it does mean removing a workspace from config is a
    # deletion of everything under that workspace root, not just the
    # symlinks/manifest this module manages.
    active_names = {
        str(ws.get("name") or "").strip()
        for ws in workspaces
        if str(ws.get("name") or "").strip()
    }
    parents = {Path(ws["root"]).parent for ws in workspaces if ws.get("root")}
    parents.add(workspaces_parent or DEVELOPER_WORKSPACES_ROOT)
    for parent in parents:
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.name in active_names:
                continue
            print(
                f"WARNING: {child} is being permanently deleted (rm -rf) because "
                "its workspace is no longer in config. This removes everything "
                "under it, not only the managed symlinks — including any "
                ".orcan/session-brief.md or agent-inbox tasks. There is no undo.",
                file=sys.stderr,
            )
            shutil.rmtree(child)
            report.stale_workspace_dirs_removed.append(str(child))

    return report


def executor_guidance(enabled: bool) -> str:
    if not enabled:
        return "\n## Background executor\n\nDISABLED: run checks directly. The user can enable it with host `orcan up --with-redis`.\n"
    return """

## Background executor: ENABLED configuration

Check `orcan-executor doctor` before use; the flag alone does not mean services are ready.
Host help: `orcan executor help`; inside Orcan: `orcan-executor help`.

1. Inspect committed project procedures with `orcan-executor profiles --repo .`.
   Explicit `init --kind python|java|scala|custom` scaffolds them; review and commit.
   Without Git, use submit --directory with explicit --include FILE entries; the SHA identifies an executor snapshot.
   Selected tests may use pytest node IDs, Gradle selectors or sbt suites; full scope is explicit.
2. Commit intended changes, then `orcan-executor submit --repo . --sha HEAD --profile selected --test SELECTOR --task TASK`.
   Small or long approved checks run in a separate detached worktree. Record job ID and SHA; return control.
   New edits require a new committed snapshot. A queued_locally response needs explicit recovery.
   Use --reuse for identical active checks; cancel JOB stops queued obsolete work.
   Codex may opt in with --notify-codex-thread UUID (its own CODEX_THREAD_ID when available).
   Never guess the target session. The supervised notification controller queues a compact result;
   queued is not consumed. After reading it use ack JOB --codex-thread UUID. No tmux typing is used.
3. A separate controller owns `orcan-executor listen --after STREAM_ID` (blocking JSONL).
   Never block the interactive agent on this listener or repeatedly poll status. Save cursor; deduplicate event_id.
   Without a connected controller, report verification pending. Acceptance requires a completed result for the exact SHA.
4. Success contains counters, never stdout; report it briefly. Skips did not run.
   Failures contain at most three short errors. Use `logs JOB --offset 0 --limit 4000` only as needed;
   follow next_offset. `artifacts JOB` lists full JSON/XML for bounded `logs --artifact NAME` reading.
5. Completed results/artifacts expire after 1 hour by default, even unread. Active jobs do not expire.
   Dirty executor worktrees are retained; never force-remove them. Keep the Git common directory available.

Dashboard: same host/Tailscale as ttyd, separate default port 8765 (`orcan executor url`).
It shows usage and measured log/result reduction; token estimates are approximate. Metrics stay out of agent results.
After consuming a terminal result, run `orcan-executor ack JOB`; this records use, not test acceptance.
Redis/Celery are local processes in Orcan. No automatic AI invocation occurs without explicit notification opt-in; no automatic merge, push or deployment occurs.
"""
