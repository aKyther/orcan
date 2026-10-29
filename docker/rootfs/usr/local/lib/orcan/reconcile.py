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

    read_first = [
        "1. **This file** — how to behave in this workspace.",
        "2. **`.manifest.json`** — projects, paths, symlinks (source of truth).",
        "3. **`.orcan/session-brief.md`** — **if it exists, read it before coding**",
        "   (shared handoff; create with `orcan-session-brief` / `brief`).",
    ]
    step = 4
    read_first.append(
        f"{step}. After `cd <project>/` — that repo's `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/`"
    )
    read_first.append(
        "   (project SoT — this generated workspace file is not the product guide)."
    )
    step += 1
    read_first.append(
        f"{step}. Respect `.cursorignore` / `.claudeignore` (and Claude `.claude/settings.json` denies)."
    )
    step += 1
    read_first.append(f"{step}. Check pack health anytime: `orcan-context-status`.")

    body = "\n".join(
        [
            "<!-- Generated by orcan reconcile (init-workspace / orcan-runtime-reconcile).",
            "     Repository instructions and custom files are preserved. -->",
            "",
            f"# AGENTS.md — {name}",
            "",
            "You are in a **orcan workspace**: one tmux session, one root directory,",
            "one or more project checkouts as subdirectories.",
            "orcan orchestrates **context** (paths, ignores, instructions); `agent` / `claude`",
            "are tools inside it — their models are not configured by orcan.",
            "",
            "## Context pack (this root)",
            "",
            "| File | Role |",
            "| --- | --- |",
            *context_pack_rows,
            "",
            "## Read first (in order)",
            "",
            *read_first,
            "",
            "## How to work",
            "",
            "- Start in the workspace root; `cd` into a project before repo-specific edits.",
            "- Be concise: short plans, small diffs, no long essays unless asked.",
            "- Do not create `PLAN.md`, `TODO.md`, `SUMMARY.md`, or similar note files.",
            "- For session handoff use `orcan-session-brief` → `.orcan/session-brief.md` only.",
            "- **If `.orcan/session-brief.md` exists, treat it as the current goal** until updated.",
            "  At task start and milestone handoff, run `orcan-compact --check` (host: `orcan compact`).",
            "  If unavailable, keep the brief concise manually. If `needs_compact` is true,",
            "  summarise into `.orcan/session-brief.next.md` within 800 words / 8000 UTF-8 bytes.",
            "  Preserve current goal, constraints, decisions, verified state, open issues and next steps.",
            "  Apply with `orcan-compact --apply .orcan/session-brief.next.md --expected-sha256 HASH`",
            "  using the check's hash; remove the candidate after success. On conflict, reread.",
            "  History in `.orcan/brief-history/` is on-demand only; never read it by default.",
            "- Do not invent tools; use what is in the environment (`rg`, `jq`, `uv`, `make`, …).",
            "- Prefer small, sufficient results; speed alone does not save tokens.",
            "  Use built-in tools when suitable; `cat`/`sed -n`/`grep` suffice for small reads.",
            "  For repository searches, prefer scoped `rg`/`fd`: `rg -q` for existence,",
            "  `-l` for filenames, `-n` for lines. Use `sg` for structure, `jq`/`yq` for fields,",
            "  `difft` for complex diffs. Read enough context to verify changes.",
            "  Prefer plain output for agents; `eza`/`bat`/`delta` suit human terminal review.",
            "  Expand scope when needed; narrow truncated searches. Partial output is not complete.",
            "  Reuse findings until relevant files change.",
            "- Python deps: prefer `uv` / `uvx` — do not `pip install` into system Python.",
            "- Run available checks before claiming success; label what you did not run.",
            "- Git commits you create: no `Co-Authored-By` (or similar AI-attribution)",
            "  trailer. The human is the sole author of record.",
            "",
            "## Secrets",
            "",
            "- Do **not** read, search, or edit `.env`, `.env.*`, keys, or `secrets/`.",
            "- Agent-specific ignore files are seeded only for clients installed in this image.",
            "- After `cd <project>/`, if that repo has no ignore files: run `orcan-init-project`",
            "  (or from the host: `make init-project-all` for every configured project).",
            "- See gaps: `orcan-context-status` (launcher key `s`).",
            "",
            "## Behavioral guidelines",
            "",
            "Bias toward caution on non-trivial work. Inspired by",
            "[andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills).",
            "",
            "1. **Think before coding** — state assumptions; ask when unclear; surface tradeoffs;",
            "   don't pick an interpretation silently.",
            "2. **Simplicity first** — minimum code that solves the ask; nothing speculative;",
            "   rewrite if 200 lines could be 50.",
            "3. **Surgical changes** — touch only what you must; match style; clean up only",
            "   orphans *your* change created; no drive-by refactors.",
            "4. **Goal-driven execution** — define verifiable success criteria and loop until",
            '   checked (tests / make / lint). Prefer "make X pass" over "make it work".',
            "5. **Multi-agent restraint** — spawning subagents (`/code-review`, parallel tasks)",
            "   costs tokens per agent; poll for results on backoff, never a tight loop. If a",
            "   subagent's result looks garbled or unfounded, stop and ask — don't act on it,",
            "   and don't re-poll hoping for a better one.",
            "",
            "## Path parity",
            "",
            "- Canonical host/container path is `projects[].path` in `.manifest.json`.",
            "- Workspace subdirs are **symlinks** for navigation (`cd backend`).",
            "- For Docker bind mounts via the host socket, use the **canonical path**, not the symlink.",
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
            "## Custom rules",
            "",
            *(
                ["- Cross-repo Cursor rules: `.cursor/rules/` in this workspace root."]
                if "cursor" in agents
                else []
            ),
            "- Per-repo rules stay inside each project checkout.",
            "- After `cd <project>/`, that project's `AGENTS.md` / `CLAUDE.md` is SoT for **that** repo.",
            "- Host copy of this tree: `<orcan-repo>/workspaces/<name>/`.",
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
    state = (
        "ENABLED (check readiness before submitting)"
        if enabled
        else "DISABLED; run checks directly as usual"
    )
    return f"""

## Optional Redis background executor

Configured state: **{state}**. This is a configuration snapshot, not a live health check.
The user enables this module with host `orcan up --with-redis`; plain `orcan up` disables it.
Run `orcan-executor doctor` inside Orcan to check current broker and worker readiness.
If disabled or unavailable, use the normal direct workflow and report the limitation.

Commands are installed in the Orcan image: `orcan-executor help` inside the container,
`orcan executor help` on the host, and `orcan executor url` for the dashboard URL.
Users and agents do not need to start uv, Celery, Redis or Uvicorn manually.

Use ready background execution for small or long tests, lint, documentation builds and other
project-approved checks. Small development checks may also run directly. This does not
authorize broader test scope, arbitrary operations, merge, deploy or another AI agent.

1. In the project, inspect `orcan-executor profiles --repo .`. Procedures live in the
   committed `.orcan/checks.json`; never assume a profile exists. To add procedures,
   use `orcan-executor init --repo . --kind python|java|scala|custom` (choose one),
   review the commands and dependencies, then commit. Existing configs are not overwritten.
2. Commit intended changes locally on the task branch. Submit that exact snapshot:
   `orcan-executor submit --repo . --sha HEAD --profile selected --test tests/test_feature.py --task TASK`.
   Python uses pytest paths/node IDs; Gradle uses class/method selectors; sbt uses suite names.
   The executor supports custom argv procedures and documentation/quality profiles.
   Choose a full-suite or coverage profile only when the task calls for that scope.
3. Record returned job ID and SHA; return control to the conversation. The executor
   runs in its own detached worktree. Preserve agent worktrees and the Git common directory.
   New edits require a new committed snapshot and a new job. A locally queued job after
   broker failure is not confirmed execution; recover explicitly with `recover --job JOB`.
4. A separate controller process owns `orcan-executor listen --after STREAM_ID`.
   It emits newline-delimited JSON only for completions, through blocking Redis Stream reads.
   Never block an interactive agent on this listener or repeatedly poll status.
   Persist the cursor and deduplicate event_id; reconnect within the retention window.
   No automatic model invocation occurs. Without a connected controller, report pending
   verification honestly; inspect `orcan-executor result JOB` when returning to the task.
5. Success means no detected errors in the requested scope; report it briefly and continue.
   Skipped tests remain skipped. Final acceptance requires a completed result for the exact SHA.
   Failure summaries contain counters and at most three short errors, never a full log dump.
   Read longer diagnostics only as needed with `orcan-executor logs JOB --offset 0 --limit 4000`;
   follow next_offset to consume further bounded chunks. `artifacts JOB` lists report/XML files;
   use `logs JOB --artifact report.json` or a listed XML name to read long reports. Use the local dashboard for full reports.

The FastAPI/Uvicorn dashboard uses the same host/Tailscale binding as ttyd on its
own port (default 8765). `orcan executor url` prints the URL. Redis has no published port.
Redis carries jobs, procedure lifecycle and compact pytest/JUnit results; SSE updates the page.
Completed communication history and artifacts expire after **1 hour** by default.
Unread results can expire too; collect needed evidence promptly. Active jobs are not TTL-pruned.
The dashboard shows actual use, queue/run time, full-log vs completion-JSON bytes/lines
and measured data reduction, globally and per job. Tiny quiet jobs can show negative savings.
Estimated tokens use a 4-byte heuristic and are not a measured model cost. Executor Python
CPU excludes subprocesses and models; no CPU/GPU saving is claimed. Background execution
lets the agent return control without waiting; it does not promise faster tests.
Dirty executor worktrees are retained for safe manual cleanup. Never force-remove them.
"""
