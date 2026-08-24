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
tasks (``.orcan/tasks/``), unsynced Context Assertions drops
(``.orcan/context-inbox/``, ``context-decisions/``), and CONTEXT-ASSERTIONS.md
itself. There is no undo — see ``apply_workspaces()`` below and
docs/en/reference/security.md ("Mount layout tradeoffs").
"""

from __future__ import annotations

import json
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
    skipped_missing_repos: list[str] = field(default_factory=list)


@dataclass
class ReconcileReport:
    workspaces: list[WorkspaceReport] = field(default_factory=list)
    stale_workspace_dirs_removed: list[str] = field(default_factory=list)

    def total_repos(self) -> int:
        return sum(w.repo_count for w in self.workspaces)

    def changed(self) -> bool:
        return bool(self.stale_workspace_dirs_removed) or any(
            w.symlinks_created or w.symlinks_removed for w in self.workspaces
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


def _copy_missing(src: Path, dst: Path) -> None:
    if not src.is_file() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


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


def _seed_agent_ignores(root: Path, templates_root: Path) -> None:
    """Cursor + Claude ignore files at workspace root (missing-only).

    Protects discovery when the agent cwd is the workspace. Per-repo
    coverage still needs cursor-init-project inside each checkout.
    """
    _copy_missing(templates_root / "cursorignore", root / ".cursorignore")
    _copy_missing(
        templates_root / "cursorindexingignore", root / ".cursorindexingignore"
    )
    _copy_missing(templates_root / "claudeignore", root / ".claudeignore")
    _copy_missing(
        templates_root / "claude" / "settings.json",
        root / ".claude" / "settings.json",
    )


def _write_agents_md(root: Path, ws: dict[str, Any], projects: list[dict[str, Any]]) -> None:
    name = ws.get("name") or "workspace"
    session = ws.get("tmux_session") or name
    has_context_assertions = (root / "CONTEXT-ASSERTIONS.md").is_file()
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
        "| `AGENTS.md` / `CLAUDE.md` | This file (behaviour) |",
        "| `.cursorignore` / `.cursorindexingignore` | Cursor exclusions |",
        "| `.claudeignore` / `.claude/settings.json` | Claude exclusions + denies |",
        "| `.cursor/rules/` | Lasting Cursor rules |",
        "| `.orcan/session-brief.md` | Optional handoff (only if created) |",
    ]
    if has_context_assertions:
        context_pack_rows.append(
            "| `CONTEXT-ASSERTIONS.md` | Compiled, human-approved context (if any matched) |"
        )

    read_first = [
        "1. **This file** — how to behave in this workspace.",
        "2. **`.manifest.json`** — projects, paths, symlinks (source of truth).",
        "3. **`.orcan/session-brief.md`** — **if it exists, read it before coding**",
        "   (shared handoff; create with `orcan-session-brief` / `brief`).",
    ]
    step = 4
    if has_context_assertions:
        read_first.append(
            f"{step}. **`CONTEXT-ASSERTIONS.md`** — human-approved context selected for this"
        )
        read_first.append(
            "   workspace's current repos/branches; each item states why it was selected."
        )
        step += 1
    read_first.append(
        f"{step}. After `cd <project>/` — that repo's `AGENTS.md` / `.cursor/rules/` if present."
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
            "     Lasting custom rules: put them in .cursor/rules/ (not here). -->",
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
            "- Do not invent tools; use what is in the environment (`rg`, `jq`, `uv`, `make`, …).",
            "- Prefer the faster replacement over the classic tool for shell commands you run",
            "  yourself: `rg` not `grep -r`, `fd` not `find -name`, `eza` not `ls`, `bat` not",
            "  `cat` (only when showing a human a file — skip it for piping/parsing), `delta`",
            "  as the git pager, `sg`/`ast-grep` for structural code search, `shfmt` to format",
            "  shell scripts, `difft` (difftastic) for a structural diff on a large refactor.",
            "  A built-in editor/search tool still comes first when one is available.",
            "- Python deps: prefer `uv` / `uvx` — do not `pip install` into system Python.",
            "- Run available checks before claiming success; label what you did not run.",
            "- Learned something durably true about a project? Draft it with",
            "  `orcan-context-propose --project NAME --text \"...\" --justification \"...\"`",
            "  (ask before running it). It only ever proposes — a human still decides",
            "  with `orcan-context-review`; nothing is accepted automatically.",
            "",
            "## Secrets",
            "",
            "- Do **not** read, search, or edit `.env`, `.env.*`, keys, or `secrets/`.",
            "- Workspace root has `.cursorignore`, `.cursorindexingignore`, `.claudeignore`.",
            "- After `cd <project>/`, if that repo has no ignore files: run `cursor-init-project`",
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
            "   checked (tests / make / lint). Prefer \"make X pass\" over \"make it work\".",
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
            "- Cross-repo Cursor rules: `.cursor/rules/` in this workspace root.",
            "- Per-repo rules stay inside each project checkout.",
            "- Host copy of this tree: `<orcan-repo>/workspaces/<name>/`.",
            "",
        ]
    )
    _write_if_changed(root / "AGENTS.md", body + "\n")
    # Claude Code looks for CLAUDE.md; keep in sync with AGENTS.md.
    _write_if_changed(root / "CLAUDE.md", body + "\n")


def _apply_one_workspace(
    ws: dict[str, Any], defaults_root: Path, templates_root: Path
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
    _write_if_changed(
        root / ".manifest.json", json.dumps(manifest, indent=2) + "\n"
    )

    report = WorkspaceReport(name=ws.get("name") or "workspace", root=str(root), repo_count=len(projects))
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
        already_ok = target.is_symlink() and target.resolve() == src.resolve()
        if target.exists() or target.is_symlink():
            if already_ok:
                continue
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                print(f"skip non-symlink in the way: {target}", file=sys.stderr)
                continue
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

    _write_agents_md(root, ws, projects)
    _seed_agent_ignores(root, templates_root)

    rule_template = defaults_root / ".cursor" / "rules" / "workspace-context.mdc"
    rules_dst = root / ".cursor" / "rules"
    dest = rules_dst / "workspace-context.mdc"
    if rule_template.is_file() and not dest.exists():
        rules_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rule_template, dest)

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
                "Also: context pack — `.manifest.json`, `CLAUDE.md`, ignores,",
                "`.claude/settings.json`, `.cursor/rules/`. Optional handoff:",
                "`orcan-session-brief` → `.orcan/session-brief.md`.",
                "Per-repo ignores: `cursor-init-project` or `make init-project-all`.",
                "",
            ]
        ),
    )
    return report


def apply_workspaces(
    cfg: dict[str, Any],
    defaults_root: Path | None = None,
    workspaces_parent: Path | None = None,
) -> ReconcileReport:
    """Reconcile every enabled workspace's on-disk tree with `cfg`.

    Idempotent — safe to call at container boot and again any time after a
    live config change (adding/removing a project or workspace).
    """
    defaults_root = defaults_root or DEFAULT_DEFAULTS_ROOT
    templates_root = defaults_root.parent

    workspaces = iter_enabled_workspaces(cfg)
    report = ReconcileReport()

    for ws in workspaces:
        report.workspaces.append(_apply_one_workspace(ws, defaults_root, templates_root))

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
    active_names = {str(ws.get("name") or "").strip() for ws in workspaces if str(ws.get("name") or "").strip()}
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
                ".orcan/session-brief.md, agent-inbox tasks, or Context "
                "Assertions drops not yet synced. There is no undo.",
                file=sys.stderr,
            )
            shutil.rmtree(child)
            report.stale_workspace_dirs_removed.append(str(child))

    return report
