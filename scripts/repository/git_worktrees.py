#!/usr/bin/env python3
"""List / resolve / create / remove git worktrees for orcan context helpers."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str = ""
    branch: str = ""  # short name (no refs/heads/), empty if detached
    bare: bool = False
    detached: bool = False
    locked: bool = False
    prunable: bool = False

    @property
    def label(self) -> str:
        if self.bare:
            return "bare"
        if self.branch:
            return self.branch
        if self.detached:
            return f"detached@{self.head[:7]}" if self.head else "detached"
        return "?"


@dataclass
class ManifestEntry:
    workspace: str
    project: str
    repo: str
    path: str
    branch: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManifestEntry:
        return cls(
            workspace=str(data.get("workspace") or ""),
            project=str(data.get("project") or ""),
            repo=str(data.get("repo") or ""),
            path=str(data.get("path") or ""),
            branch=str(data.get("branch") or ""),
        )


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


class WorktreeCreateError(Exception):
    """Recoverable create failure (wizard can retry / use existing / cancel)."""

    def __init__(
        self,
        message: str,
        *,
        hint: str = "",
        existing: Worktree | None = None,
        code: str = "",
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.existing = existing
        self.code = code


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    r = run_git(path, "rev-parse", "--is-inside-work-tree", check=False)
    if r.returncode == 0 and r.stdout.strip() == "true":
        return True
    r = run_git(path, "rev-parse", "--is-bare-repository", check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def safe_segment(value: str, *, label: str) -> str:
    value = value.strip()
    if not value:
        die(f"{label} is empty")
    # Allow branch-like names for workspace by flattening /
    flat = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    if not flat or not SAFE_SEGMENT.match(flat):
        die(f"invalid {label}: {value}")
    return flat


def orcan_data_root() -> Path:
    raw = os.environ.get("ORCAN_DATA", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".config" / "orcan").resolve()


def projects_root() -> Path:
    """Stable managed-projects mount root (Compose: ORCAN_PROJECTS_ROOT).

    Default ``$ORCAN_DATA/sandbox``. Managed worktrees live under
    ``<projects_root>/.worktrees/`` so they inherit that single bind and do
    not force a container recreate when added.
    """
    raw = os.environ.get("ORCAN_PROJECTS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return orcan_data_root() / "sandbox"


def managed_root(*, ensure: bool = False) -> Path:
    """Host dir for Orcan-managed git worktrees: ``$ORCAN_PROJECTS_ROOT/.worktrees``."""
    root = projects_root() / ".worktrees"
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root


def managed_worktree_path(workspace: str, project: str) -> Path:
    ws = safe_segment(workspace, label="workspace")
    proj = safe_segment(project, label="project")
    root = managed_root(ensure=True)
    return (root / ws / proj).resolve()


def is_under_managed_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(managed_root(ensure=False).resolve())
        return True
    except ValueError:
        return False


def manifest_path() -> Path:
    return managed_root(ensure=True) / "registry.json"


def load_manifest() -> list[ManifestEntry]:
    path = manifest_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid worktree manifest {path}: {exc}")
    if not isinstance(data, dict):
        die(f"worktree manifest root must be an object: {path}")
    items = data.get("worktrees") or []
    if not isinstance(items, list):
        die(f"worktree manifest worktrees[] must be an array: {path}")
    out: list[ManifestEntry] = []
    for item in items:
        if isinstance(item, dict):
            out.append(ManifestEntry.from_dict(item))
    return out


def save_manifest(entries: list[ManifestEntry]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"worktrees": [e.to_dict() for e in entries]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def manifest_upsert(entry: ManifestEntry) -> None:
    entries = [
        e
        for e in load_manifest()
        if not (e.workspace == entry.workspace and e.project == entry.project)
    ]
    entries.append(entry)
    save_manifest(entries)


def manifest_remove(*, workspace: str, project: str | None = None) -> list[ManifestEntry]:
    """Remove matching entries; return removed list."""
    before = load_manifest()
    removed: list[ManifestEntry] = []
    kept: list[ManifestEntry] = []
    for e in before:
        if e.workspace != workspace:
            kept.append(e)
            continue
        if project is not None and e.project != project:
            kept.append(e)
            continue
        removed.append(e)
    save_manifest(kept)
    return removed


def parse_porcelain(text: str) -> list[Worktree]:
    """Parse `git worktree list --porcelain` output."""
    items: list[Worktree] = []
    cur: dict[str, object] = {}

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        path = cur.get("path")
        if not isinstance(path, Path):
            cur = {}
            return
        items.append(
            Worktree(
                path=path,
                head=str(cur.get("head") or ""),
                branch=str(cur.get("branch") or ""),
                bare=bool(cur.get("bare")),
                detached=bool(cur.get("detached")),
                locked=bool(cur.get("locked")),
                prunable=bool(cur.get("prunable")),
            )
        )
        cur = {}

    for line in text.splitlines():
        if line == "":
            flush()
            continue
        if line.startswith("worktree "):
            flush()
            cur = {"path": Path(line[len("worktree ") :]).resolve()}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            ref = line[len("branch ") :]
            prefix = "refs/heads/"
            cur["branch"] = ref[len(prefix) :] if ref.startswith(prefix) else ref
        elif line == "bare":
            cur["bare"] = True
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("locked"):
            cur["locked"] = True
        elif line.startswith("prunable"):
            cur["prunable"] = True
    flush()
    return items


def list_worktrees(repo: Path) -> list[Worktree]:
    if not is_git_repo(repo):
        die(f"not a git repository: {repo}")
    r = run_git(repo, "worktree", "list", "--porcelain")
    return parse_porcelain(r.stdout)


def resolve_worktree(repo: Path, selector: str) -> Worktree:
    """Resolve by index (1-based), branch name, basename, or absolute path."""
    trees = list_worktrees(repo)
    if not trees:
        die(f"no worktrees found for {repo}")

    sel = selector.strip()
    if not sel:
        die("worktree selector is empty")

    if sel.isdigit():
        idx = int(sel)
        if idx < 1 or idx > len(trees):
            die(f"worktree index out of range 1..{len(trees)}: {sel}")
        return trees[idx - 1]

    sel_path = Path(sel)
    if sel_path.is_absolute():
        resolved = sel_path.resolve()
        for wt in trees:
            if wt.path == resolved:
                return wt
        die(f"no worktree at path: {resolved}")

    matches = [
        wt
        for wt in trees
        if wt.branch == sel or wt.path.name == sel or str(wt.path) == sel
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        die(
            f"ambiguous worktree {sel!r}; use index or absolute path:\n"
            + "\n".join(f"  {i + 1}. {w.path} ({w.label})" for i, w in enumerate(trees))
        )
    die(
        f"no worktree matching {sel!r}. Known:\n"
        + "\n".join(f"  {i + 1}. {w.path} ({w.label})" for i, w in enumerate(trees))
    )


def branch_exists(repo: Path, branch: str) -> bool:
    r = run_git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    return r.returncode == 0


def remote_branch_exists(repo: Path, branch: str, remote: str = "origin") -> bool:
    r = run_git(
        repo, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}", check=False
    )
    return r.returncode == 0


def fetch_branch_safely(
    repo: Path, branch: str, remote: str = "origin", timeout: float = 5.0
) -> bool:
    """Best-effort ``git fetch <remote> <branch>`` — never prompts, never hangs.

    Used only so ``create_worktree()`` can start a new local branch from the
    real remote content instead of an empty branch off HEAD when someone
    else already pushed ``branch``. GIT_TERMINAL_PROMPT=0 and SSH BatchMode
    guarantee this can never block on a username/password/passphrase prompt
    — over HTTPS without cached credentials, or SSH without an agent/loaded
    key, it just fails fast (like a network outage would) and the caller
    falls back to the normal new-branch-from-HEAD path.
    """
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=5")
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "fetch", "--quiet", remote, branch],
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def current_branch(repo: Path) -> str:
    """Empty string for detached HEAD (or any other lookup failure)."""
    r = run_git(repo, "branch", "--show-current", check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def pull_current_branch(repo: Path) -> tuple[bool, str]:
    """Fast-forward-only pull of repo's currently checked-out branch — so a
    worktree about to branch from HEAD branches from current code, not a
    stale local master. Best-effort: never raises, returns (ok, message);
    a dirty tree, detached HEAD, or missing upstream is a normal skip, not
    an error — the caller decides whether to warn."""
    status = run_git(repo, "status", "--porcelain", check=False)
    if status.returncode != 0:
        return False, "could not read working tree status"
    if status.stdout.strip():
        return False, "working tree has uncommitted changes"

    branch = current_branch(repo)
    if not branch:
        return False, "detached HEAD (no branch to pull)"

    upstream = run_git(
        repo, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}", check=False
    )
    if upstream.returncode != 0:
        return False, f"branch {branch!r} has no upstream configured"

    pull = run_git(repo, "pull", "--ff-only", check=False)
    if pull.returncode != 0:
        detail = pull.stderr.strip().splitlines()[-1] if pull.stderr.strip() else "pull failed"
        return False, detail[:200]
    out_lines = pull.stdout.strip().splitlines()
    return True, out_lines[-1] if out_lines else "already up to date"


def find_worktree_by_branch(repo: Path, branch: str) -> Worktree | None:
    """Return the worktree that already has this branch checked out, if any."""
    branch = branch.strip()
    if not branch:
        return None
    try:
        trees = list_worktrees(repo)
    except SystemExit:
        return None
    for wt in trees:
        if wt.branch == branch:
            return wt
    return None


def default_worktree_path(repo: Path, branch: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-") or "worktree"
    return (repo.parent / f"{repo.name}-{safe}").resolve()


def create_worktree(
    repo: Path,
    *,
    branch: str,
    path: Path | None = None,
    start_point: str = "HEAD",
    workspace: str = "",
    project: str = "",
    managed: bool = False,
    fatal: bool = True,
    remote: str = "origin",
) -> Worktree:
    """Create a git worktree.

    When ``fatal`` is True (CLI default), conflicts call ``die``.
    When False, raises ``WorktreeCreateError`` so a wizard can retry.
    """

    def fail(
        msg: str,
        *,
        hint: str = "",
        existing: Worktree | None = None,
        code: str = "",
    ) -> None:
        if fatal:
            extra = f"\n{hint}" if hint else ""
            die(f"{msg}{extra}")
        raise WorktreeCreateError(msg, hint=hint, existing=existing, code=code)

    if not is_git_repo(repo):
        fail(f"not a git repository: {repo}", code="not_repo")
    branch = branch.strip()
    if not branch:
        fail("branch name is empty", code="empty_branch")
    if not BRANCH_RE.match(branch):
        fail(
            f"invalid branch name: {branch}",
            hint="Use letters, digits, . _ - / (must start alphanumeric).",
            code="invalid_branch",
        )

    if path is not None:
        dest = path.resolve()
    elif managed or (workspace and project):
        if not workspace or not project:
            fail("managed worktree needs --workspace and --project (or --path)", code="args")
        dest = managed_worktree_path(workspace, project)
    else:
        dest = default_worktree_path(repo, branch)

    if dest.exists():
        existing_here: Worktree | None = None
        if is_git_repo(dest):
            try:
                existing_here = resolve_worktree(repo, str(dest))
            except SystemExit:
                existing_here = None
        fail(
            f"worktree path already exists: {dest}",
            hint="Pick another project name, remove the old worktree, or use the existing path.",
            existing=existing_here,
            code="path_exists",
        )

    in_use = find_worktree_by_branch(repo, branch)
    if in_use is not None:
        fail(
            f"branch {branch!r} is already checked out at {in_use.path}",
            hint="Git allows one checkout per branch. Use that worktree, or choose a new branch name.",
            existing=in_use,
            code="branch_in_use",
        )

    dest.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists(repo, branch):
        # Branch exists but is free — attach a new worktree to it.
        print(f"branch {branch!r} already exists locally — attaching worktree to it", file=sys.stderr)
        args = ["worktree", "add", str(dest), branch]
    elif start_point == "HEAD":
        # No local branch and the caller didn't ask for a specific start
        # point — check whether someone else already pushed this branch
        # before silently creating an empty one off HEAD under the same
        # name. See fetch_branch_safely(): never prompts, never hangs.
        print(f"branch {branch!r} not found locally, checking {remote}...", file=sys.stderr)
        fetched = fetch_branch_safely(repo, branch, remote=remote)
        if not fetched:
            print(
                f"could not fetch {remote}/{branch} (no network / no credentials)",
                file=sys.stderr,
            )
        if remote_branch_exists(repo, branch, remote=remote):
            if fetched:
                print(f"fetched {remote}/{branch} — creating worktree from it", file=sys.stderr)
            else:
                print(
                    f"using existing local copy of {remote}/{branch} (may be stale) — "
                    "creating worktree from it",
                    file=sys.stderr,
                )
            args = ["worktree", "add", "--track", "-b", branch, str(dest), f"{remote}/{branch}"]
        else:
            print(
                f"{remote}/{branch} not available — creating new branch {branch!r} from HEAD",
                file=sys.stderr,
            )
            args = ["worktree", "add", "-b", branch, str(dest), start_point]
    else:
        args = ["worktree", "add", "-b", branch, str(dest), start_point]

    r = run_git(repo, *args, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        hint = "Try a different branch name, or mount the original folder instead."
        low = err.lower()
        if "already used by worktree" in low or "is already checked out" in low:
            hint = "That branch is already checked out elsewhere — pick another name or use the existing worktree."
        elif "already exists" in low:
            hint = "Path or branch already exists — try another branch name."
        fail(f"git worktree add failed: {err}", hint=hint, code="git_failed")

    wt = resolve_worktree(repo, str(dest))
    if is_under_managed_root(dest) and workspace and project:
        manifest_upsert(
            ManifestEntry(
                workspace=safe_segment(workspace, label="workspace"),
                project=safe_segment(project, label="project"),
                repo=str(repo.resolve()),
                path=str(dest),
                branch=branch,
            )
        )
    return wt


def remove_worktree(
    path: Path,
    *,
    force: bool = False,
    allow_unmanaged: bool = False,
) -> None:
    path = path.resolve()
    if not path.exists():
        die(f"worktree path does not exist: {path}")
    if not allow_unmanaged and not is_under_managed_root(path):
        die(
            f"refusing to remove path outside managed root {managed_root()}: {path}\n"
            "Use a path under $ORCAN_PROJECTS_ROOT/.worktrees, or pass --force for unmanaged paths."
        )
    if not is_git_repo(path):
        die(f"not a git worktree: {path}")

    cmd = ["git", "-C", str(path), "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(path))
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        die(f"git worktree remove failed: {(r.stderr or r.stdout or '').strip()}")

    if is_under_managed_root(path):
        parent = path.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass


def find_stale_entries(entries: list[ManifestEntry]) -> list[ManifestEntry]:
    """Registry entries whose path no longer exists on disk."""
    return [e for e in entries if not Path(e.path).exists()]


def find_orphan_dirs(entries: list[ManifestEntry]) -> list[Path]:
    """<workspace>/<project> dirs under managed_root() not in the registry."""
    root = managed_root(ensure=False)
    if not root.is_dir():
        return []
    known = {Path(e.path).resolve() for e in entries}
    orphans: list[Path] = []
    for ws_dir in sorted(root.iterdir()):
        if not ws_dir.is_dir():
            continue
        for proj_dir in sorted(ws_dir.iterdir()):
            if proj_dir.is_dir() and proj_dir.resolve() not in known:
                orphans.append(proj_dir)
    return orphans


def find_config_stale(
    entries: list[ManifestEntry], config_path: Path
) -> list[ManifestEntry]:
    """Registry entries whose workspace/project no longer appears in config."""
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"invalid JSON in {config_path}: {exc}")
    active: set[tuple[str, str]] = set()
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        ws_name = str(ws.get("name") or "")
        for p in ws.get("projects") or []:
            if isinstance(p, dict) and p.get("name"):
                active.add((ws_name, str(p["name"])))
    return [e for e in entries if (e.workspace, e.project) not in active]


def cmd_prune(args: argparse.Namespace) -> None:
    """Reconcile worktrees/registry.json against disk (and optionally config)."""
    entries = load_manifest()

    stale = find_stale_entries(entries)
    if stale:
        print(f"stale registry entries (path missing on disk): {len(stale)}")
        for e in stale:
            print(f"  - {e.workspace}/{e.project}: {e.path}")
        entries = [e for e in entries if e not in stale]
        save_manifest(entries)
        print("  removed from registry.json")

    config_stale: list[ManifestEntry] = []
    if args.config:
        config_path = Path(args.config)
        if not config_path.is_file():
            die(f"config not found: {config_path}")
        config_stale = find_config_stale(entries, config_path)
        if config_stale:
            print(f"registry entries no longer in {config_path}: {len(config_stale)}")
            for e in config_stale:
                print(f"  - {e.workspace}/{e.project}: {e.path}")

    orphans = find_orphan_dirs(entries)
    if orphans:
        print(f"orphan worktree directories (not in registry.json): {len(orphans)}")
        for p in orphans:
            print(f"  - {p}")

    if not stale and not orphans and not config_stale:
        print("nothing to prune")
        return

    if not (orphans or config_stale):
        return
    if not args.force:
        print("\nRe-run with --force to remove orphan directories / config-stale worktrees.")
        return

    for p in orphans:
        if is_git_repo(p):
            remove_worktree(p, force=True, allow_unmanaged=False)
        else:
            shutil.rmtree(p)
        print(f"  removed orphan: {p}")

    for e in config_stale:
        path = Path(e.path)
        if path.exists():
            remove_worktree(path, force=True, allow_unmanaged=False)
        manifest_remove(workspace=e.workspace, project=e.project)
        print(f"  removed (config-stale): {e.workspace}/{e.project}")


def format_table(trees: list[Worktree]) -> str:
    lines = []
    for i, wt in enumerate(trees, 1):
        flags = []
        if wt.bare:
            flags.append("bare")
        if wt.locked:
            flags.append("locked")
        if wt.prunable:
            flags.append("prunable")
        if wt.detached and not wt.branch:
            flags.append("detached")
        extra = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  {i}. {wt.path}  ({wt.label}){extra}")
    return "\n".join(lines)


def cmd_list(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    trees = list_worktrees(repo)
    print(f"worktrees for {repo} ({len(trees)}):")
    print(format_table(trees) if trees else "  (none)")


def cmd_resolve(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    wt = resolve_worktree(repo, args.selector)
    print(str(wt.path))


def cmd_create(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve()
    path = Path(args.path).resolve() if args.path else None
    wt = create_worktree(
        repo,
        branch=args.branch,
        path=path,
        start_point=args.start_point,
        workspace=args.workspace,
        project=args.project,
        managed=bool(args.managed or (args.workspace and args.project)),
    )
    print(f"created: {wt.path} ({wt.label})")
    print(wt.path)


def cmd_remove(args: argparse.Namespace) -> None:
    path = Path(args.path).resolve()
    remove_worktree(path, force=bool(args.force), allow_unmanaged=bool(args.force))
    # Update manifest if present
    entries = load_manifest()
    kept = [e for e in entries if Path(e.path).resolve() != path]
    if len(kept) != len(entries):
        save_manifest(kept)
    print(f"removed: {path}")


def cmd_managed_root(_args: argparse.Namespace) -> None:
    print(managed_root(ensure=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List worktrees for a repo")
    p_list.add_argument("--repo", required=True)
    p_list.set_defaults(func=cmd_list)

    p_res = sub.add_parser("resolve", help="Print absolute path for a selector")
    p_res.add_argument("--repo", required=True)
    p_res.add_argument("selector")
    p_res.set_defaults(func=cmd_resolve)

    p_add = sub.add_parser("create", help="Create a worktree and print its path")
    p_add.add_argument("--repo", required=True)
    p_add.add_argument("--branch", required=True)
    p_add.add_argument("--path", default="")
    p_add.add_argument("--start-point", default="HEAD")
    p_add.add_argument("--workspace", default="")
    p_add.add_argument("--project", default="")
    p_add.add_argument(
        "--managed",
        action="store_true",
        help="Place under $ORCAN_PROJECTS_ROOT/.worktrees/<workspace>/<project>",
    )
    p_add.set_defaults(func=cmd_create)

    p_rm = sub.add_parser("remove", help="Remove a worktree (managed paths by default)")
    p_rm.add_argument("--path", required=True)
    p_rm.add_argument("--force", action="store_true")
    p_rm.set_defaults(func=cmd_remove)

    p_root = sub.add_parser("managed-root", help="Print $ORCAN_PROJECTS_ROOT/.worktrees")
    p_root.set_defaults(func=cmd_managed_root)

    p_prune = sub.add_parser(
        "prune", help="Reconcile worktrees/registry.json against disk (and optionally config)"
    )
    p_prune.add_argument(
        "--config", default="", help="Also flag registry entries missing from this orcan.config.json"
    )
    p_prune.add_argument(
        "--force", action="store_true", help="Remove orphan dirs / config-stale worktrees (default: report only)"
    )
    p_prune.set_defaults(func=cmd_prune)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
