#!/usr/bin/env python3
"""Apply orcan.config.json into .env, runtime config, workspace artifacts, and Compose mounts."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Host scripts live next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import discover_config, load_config as load_user_config  # noqa: E402
import claude_hook  # noqa: E402
from path_guards import is_sensitive_path  # noqa: E402


DEFAULT_DEVELOPER_WORKSPACES = "/home/developer/workspaces"


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def write_text_replace(path: Path, text: str) -> None:
    """Write text; skip with a warning if the path is a busy/read-only bind mount."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(text, encoding="utf-8")
        return
    except OSError as exc:
        if exc.errno not in (errno.EROFS, errno.EACCES, errno.EBUSY):
            raise
    try:
        path.unlink(missing_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(
            f"Warning: could not update {path} ({exc.strerror}); leaving existing file",
            file=sys.stderr,
        )


def resolve_abs(path: str, label: str) -> Path:
    if "~" in path:
        die(f"{label} must not contain ~ (got: {path})")
    p = Path(path)
    if not p.is_absolute():
        die(f"{label} must be an absolute path (got: {path})")
    if not p.exists():
        die(f"{label} does not exist: {path}")
    if not p.is_dir():
        die(f"{label} is not a directory: {path}")
    resolved = p.resolve()
    if is_sensitive_path(resolved):
        die(f"refusing sensitive path for {label}: {resolved}")
    home = Path.home().resolve()
    if resolved == home:
        die(f"refusing to mount entire home for {label}: {resolved}")
    if not os.access(resolved, os.R_OK):
        die(f"{label} is not readable: {resolved}")
    return resolved


def ensure_dir(path: Path, label: str) -> Path:
    if "~" in str(path):
        die(f"{label} must not contain ~")
    if not path.is_absolute():
        die(f"{label} must be an absolute path (got: {path})")
    resolved = path.resolve()
    if is_sensitive_path(resolved):
        die(f"refusing sensitive path for {label}: {resolved}")
    home = Path.home().resolve()
    if resolved == home:
        die(f"refusing to use entire home for {label}: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def format_env_value(value: str) -> str:
    """Quote .env values that would break shell sourcing (spaces, commas, quotes)."""
    if value == "":
        return '""'
    if re.search(r'[\s#"\'\\$`]|,', value) or value.startswith(("'", '"')):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def ensure_env_key(env_path: Path, key: str, value: str) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    replaced = False
    out: list[str] = []
    rendered = f"{key}={format_env_value(value)}"
    for line in lines:
        if pattern.match(line):
            out.append(rendered)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1] != "":
            out.append("")
        out.append(rendered)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def env_has_key(env_path: Path, key: str) -> bool:
    if not env_path.exists():
        return False
    pattern = re.compile(rf"^{re.escape(key)}=")
    return any(pattern.match(line) for line in env_path.read_text(encoding="utf-8").splitlines())


def ensure_env_key_unless_set(env_path: Path, key: str, value: str) -> None:
    """Set key only when missing — preserves host-specific .env overrides (e.g. CPUS)."""
    if env_has_key(env_path, key):
        return
    ensure_env_key(env_path, key, value)


def remove_env_key(env_path: Path, key: str) -> None:
    if not env_path.exists():
        return
    pattern = re.compile(rf"^{re.escape(key)}=")
    lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not pattern.match(line)
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict:
    return load_user_config(path)


def normalize_workspaces_raw(cfg: dict) -> list[dict]:
    if cfg.get("projects_dir"):
        die(
            "'projects_dir' was removed; use workspaces[] or workspace.projects[] "
            "(see orcan.config.example.json)"
        )

    raw_list = cfg.get("workspaces")
    if raw_list is not None:
        if not isinstance(raw_list, list) or not raw_list:
            die("workspaces must be a non-empty array")
        return raw_list

    ws_raw = cfg.get("workspace")
    if isinstance(ws_raw, dict):
        merged = dict(ws_raw)
        if cfg.get("projects") and not merged.get("projects"):
            merged["projects"] = cfg["projects"]
        if merged.get("projects"):
            return [merged]

    if cfg.get("projects"):
        wrapper: dict = {}
        if isinstance(ws_raw, dict):
            wrapper.update(ws_raw)
        wrapper["projects"] = cfg["projects"]
        return [wrapper]

    die("config requires workspaces[], workspace.projects[], or legacy projects[]")


def default_workspace_root(ws_name: str, explicit: str) -> str:
    if explicit:
        return explicit
    return f"{DEFAULT_DEVELOPER_WORKSPACES.rstrip('/')}/{ws_name}"


def parse_projects(
    projects_raw: list,
    ws_root: str,
    label: str,
) -> list[dict]:
    if not isinstance(projects_raw, list) or not projects_raw:
        die(f"{label} must contain at least one project")

    projects: list[dict] = []
    seen_paths: set[str] = set()
    seen_names: set[str] = set()

    for i, item in enumerate(projects_raw):
        if not isinstance(item, dict):
            die(f"{label}[{i}] must be an object")
        if item.get("alias"):
            die(
                f"{label}[{i}].alias was removed; use name as the subdirectory "
                f"under the workspace root"
            )
        if item.get("mount"):
            die(
                f"{label}[{i}].mount was removed; all projects use path parity "
                f"(host path = container path) with a symlink under the workspace root"
            )
        if item.get("role"):
            die(f"{label}[{i}].role was removed; use name and path only")
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if not name or not path:
            die(f"{label}[{i}] requires name and path")
        if name in seen_names:
            die(f"duplicate project name in {label}: {name}")
        if ".." in Path(name).parts or name.startswith("/"):
            die(f"{label}[{i}].name must be a simple directory name (got: {name})")

        resolved = resolve_abs(path, f"{label}[{i}].path")
        path_key = str(resolved)
        if path_key in seen_paths:
            die(f"duplicate project path in {label}: {path_key}")
        seen_names.add(name)
        seen_paths.add(path_key)

        workspace_path = f"{ws_root.rstrip('/')}/{name}"

        if "windows" in item:
            die(
                f"{label}[{i}].windows is no longer supported; "
                'use root-level "tmux": {{ "initial_windows": … }} and rename tabs in tmux'
            )

        projects.append(
            {
                "name": name,
                "path": path_key,
                "workspace_path": workspace_path,
                "container_path": path_key,
            }
        )

    return projects


def build_workspace_entry(
    cfg: dict,
    ws_raw: dict,
    ws_index: int,
    ws_count: int,
    repo_root: Path,
    seen_names: set[str],
    seen_roots: set[str],
    seen_tmux: set[str],
) -> dict:
    if not isinstance(ws_raw, dict):
        die(f"workspaces[{ws_index}] must be an object")

    projects_raw = ws_raw.get("projects") or []
    label = f"workspaces[{ws_index}].projects"
    ws_name = str(ws_raw.get("name") or "").strip()
    if not ws_name and projects_raw:
        ws_name = str(projects_raw[0].get("name") or f"workspace-{ws_index + 1}").strip()
    if not ws_name:
        die(f"workspaces[{ws_index}] requires name (or projects[].name)")

    if ws_name in seen_names:
        die(f"duplicate workspace name: {ws_name}")
    seen_names.add(ws_name)

    if ws_raw.get("default_project") or cfg.get("default_project"):
        die(
            "default_project was removed; the agent starts in the workspace root. "
            "Agents start in the workspace root."
        )

    if ws_raw.get("mount_mode"):
        die(
            f"workspaces[{ws_index}].mount_mode was removed; all projects use path parity "
            f"with symlinks under {DEFAULT_DEVELOPER_WORKSPACES}/<name>"
        )

    explicit_root = str(ws_raw.get("root") or "").strip()
    if explicit_root:
        die(
            f"workspaces[{ws_index}].root was removed; workspace roots are always "
            f"{DEFAULT_DEVELOPER_WORKSPACES}/<name>"
        )
    ws_root = default_workspace_root(ws_name, "")
    if not ws_root.startswith("/"):
        die(f"workspaces[{ws_index}].root must be an absolute path (got: {ws_root})")
    if is_sensitive_path(ws_root):
        die(f"refusing sensitive workspaces[{ws_index}].root: {ws_root}")
    if ws_root in seen_roots:
        die(f"duplicate workspace root: {ws_root}")
    seen_roots.add(ws_root)

    meta_raw = str(ws_raw.get("meta_path") or "").strip()
    if meta_raw:
        die(
            f"workspaces[{ws_index}].meta_path was removed; workspace roots are always "
            f"{DEFAULT_DEVELOPER_WORKSPACES}/<name> (host meta: workspaces/<name>/)"
        )
    meta_path = ensure_dir(
        repo_root / "workspaces" / ws_name,
        f"workspace meta for {ws_name}",
    )

    if "tmux" in ws_raw:
        die(
            f"workspaces[{ws_index}].tmux was removed; tmux session name is always "
            f"the workspace name ({ws_name!r}). "
            f"Use root-level \"tmux\": {{ \"initial_windows\": … }} for window defaults only."
        )

    tmux_name = ws_name
    if tmux_name in seen_tmux:
        die(f"duplicate tmux session name: {tmux_name}")
    seen_tmux.add(tmux_name)

    projects = parse_projects(projects_raw, ws_root, label)

    for p in projects:
        wp = p["workspace_path"]
        prefix = ws_root.rstrip("/") + "/"
        if not wp.startswith(prefix):
            die(
                f"internal error: project {p['name']!r} workspace_path {wp!r} "
                f"is not under workspace root {ws_root!r}"
            )

    workspace = {
        "name": ws_name,
        "root": ws_root,
        "meta_path": str(meta_path),
        "enabled": ws_raw.get("enabled", True) is not False,
        "tmux_session": tmux_name,
        "project_count": len(projects),
        "projects": projects,
    }
    return workspace


def primary_workspace(workspaces: list[dict]) -> dict:
    for ws in workspaces:
        if ws.get("enabled") is not False:
            return ws
    return workspaces[0]


def prune_stale_workspace_metas(repo_root: Path, active_names: set[str]) -> None:
    """Remove workspaces/<name>/ dirs for workspaces no longer in config."""
    host_workspaces = repo_root / "workspaces"
    if not host_workspaces.is_dir():
        return
    for child in sorted(host_workspaces.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in active_names:
            continue
        print(
            f"warning: removing stale workspace meta (no longer in orcan config): {child}",
            file=sys.stderr,
        )
        shutil.rmtree(child)


def main_repo_git_dir_from_worktree(project_path: Path) -> str | None:
    """Resolve a git worktree's shared `.git` *directory* by reading its pointer.

    A worktree's own `.git` is a plain *file* (not a directory) containing
    `gitdir: <main-repo>/.git/worktrees/<name>`. A normal repo (or a
    non-repo directory) has `.git` as a directory or nothing, so this only
    ever fires for genuine worktrees.

    Deliberately returns `<main-repo>/.git` only — never `<main-repo>`
    itself. Git worktree operations (commit, push, log, branch, fetch) only
    ever need the shared object database, refs, and per-worktree metadata
    under `.git`; they never need the main checkout's actual working-tree
    files. Mounting the whole main repo would let the agent browse and edit
    the main branch's files from inside a feature-branch worktree, which
    defeats the isolation `orcan context worktree create` exists to give —
    "work on this branch" should not silently also mean "and see main".

    Reads the pointer straight off disk instead of shelling out to `git`:
    at `orcan sync` time the whole point is that git doesn't work yet inside
    the worktree (its .git dir isn't mounted), so a git subprocess here
    would be circular. This also means it works for *any* worktree
    regardless of how it was created — a bare `git worktree add`, `orcan
    context worktree create`, or one made by an older Orcan version.
    """
    git_file = project_path / ".git"
    if not git_file.is_file():
        return None
    try:
        first_line = git_file.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return None
    if not first_line.startswith("gitdir:"):
        return None
    gitdir = Path(first_line.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (project_path / gitdir).resolve()
    # Standard worktree layout: <main-repo>/.git/worktrees/<name>
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return str(gitdir.parent.parent)  # <main-repo>/.git — not the working tree
    return None


def worktree_git_dir_paths(project_paths: set[str]) -> set[str]:
    """`<main-repo>/.git` paths for every project path that is itself a git worktree.

    Without that shared .git dir also mounted at the same host path, every
    git command inside the worktree fails with "not a git repository",
    because its `.git` pointer resolves to a path the container can't see.
    Only `.git` is mounted, never the main checkout's working-tree files —
    see main_repo_git_dir_from_worktree() for why that boundary matters.
    """
    extra: set[str] = set()
    for raw in project_paths:
        git_dir = main_repo_git_dir_from_worktree(Path(raw))
        if git_dir:
            extra.add(git_dir)
    return extra


def managed_projects_root(env: dict | None = None) -> Path | None:
    """The stable, always-mounted project root (see docker-compose.yml).

    Set by update-env.sh before apply-config.py runs (`ORCAN_PROJECTS_ROOT`,
    default ``${ORCAN_DATA}/sandbox``). Any project path already living
    under this root needs no bind entry of its own in the generated Compose
    overlay — it's already visible via the one stable base-compose mount —
    which is what lets adding/removing such a project skip the Compose
    recreate that a growing/shrinking bind-mount list would otherwise force.
    """
    raw = (env if env is not None else os.environ).get("ORCAN_PROJECTS_ROOT", "").strip()
    if not raw:
        return None
    return Path(raw)


def _is_under(child: Path, parent: Path) -> bool:
    """True if child is parent or lives under it, symlinks resolved on both sides.

    A project path is typically already fully resolved by the time it lands
    in config, while ``managed_root`` comes straight from
    ``$ORCAN_PROJECTS_ROOT`` as set by the user/environment. Comparing one
    resolved and one unresolved path with plain ``relative_to()`` silently
    fails (and misclassifies a managed project as unmanaged) whenever any
    component on the managed-root side is a symlink — e.g. a symlinked
    ``$HOME``.
    """

    def _resolved(p: Path) -> Path:
        try:
            return p.resolve()
        except OSError:
            return p

    try:
        _resolved(child).relative_to(_resolved(parent))
        return True
    except ValueError:
        return False


def write_compose_projects(
    workspaces: list[dict], repo_root: Path, managed_root: Path | None = None
) -> str:
    """One bind for all workspace metas + parity binds for every project path.

    Paths already under `managed_root` are covered by the stable base-compose
    mount and deliberately excluded here — see managed_projects_root().
    """
    host_workspaces = ensure_dir(
        repo_root / "workspaces", "workspace metas root"
    )
    lines = [
        "# Generated by apply-config.py — do not edit by hand.",
        "services:",
        "  orcan:",
        "    volumes:",
        # Single parent mount — avoids per-workspace bind overlap / cross-visible trees.
        f"      - {host_workspaces}:{DEFAULT_DEVELOPER_WORKSPACES}",
    ]

    parity_paths: set[str] = set()
    for ws in workspaces:
        for project in ws["projects"]:
            parity_paths.add(project["path"])

    parity_paths |= worktree_git_dir_paths(parity_paths)

    if managed_root is not None:
        parity_paths = {p for p in parity_paths if not _is_under(Path(p), managed_root)}

    for path in sorted(parity_paths):
        lines.append(f"      - {path}:{path}")
    return "\n".join(lines) + "\n"


def write_workspace_manifest(runtime: dict) -> dict:
    return {
        "workspaces": [
            {
                "name": ws["name"],
                "root": ws["root"],
                "meta_path": ws["meta_path"],
                "tmux_session": ws["tmux_session"],
                "project_count": ws["project_count"],
                "projects": ws["projects"],
            }
            for ws in runtime["workspaces"]
        ],
    }


def write_code_workspace(
    repo_root: Path,
    workspace: dict,
    projects: list[dict],
    *,
    suffix: str,
    use_container_paths: bool,
) -> Path:
    runtime_dir = repo_root / "mounts"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", workspace["name"]).strip("-") or "workspace"
    out_path = runtime_dir / f"{safe_name}.{suffix}.code-workspace"

    ws_folder = workspace["root"] if use_container_paths else workspace["meta_path"]
    folders = [{"name": workspace["name"], "path": ws_folder}]
    for p in projects:
        folders.append(
            {
                "name": p["name"],
                "path": (
                    p["container_path"]
                    if use_container_paths
                    else p["path"]
                ),
            }
        )

    payload = {
        "folders": folders,
        "settings": {"files.exclude": {"**/.git": True}},
    }
    write_text_replace(out_path, json.dumps(payload, indent=2) + "\n")
    return out_path


def build_from_config(cfg: dict, repo_root: Path) -> dict:
    if cfg.get("default_project"):
        die(
            "default_project was removed; agents start in the workspace root."
        )
    if cfg.get("default_workspace"):
        die("default_workspace was removed; list workspaces[] only (min. one entry)")

    raw_list = normalize_workspaces_raw(cfg)
    ws_count = len(raw_list)
    seen_names: set[str] = set()
    seen_roots: set[str] = set()
    seen_tmux: set[str] = set()

    workspaces: list[dict] = []
    for i, ws_raw in enumerate(raw_list):
        workspaces.append(
            build_workspace_entry(
                cfg, ws_raw, i, ws_count, repo_root, seen_names, seen_roots, seen_tmux
            )
        )

    primary_ws = primary_workspace(workspaces)
    container_project_dir = primary_ws["root"]

    ttyd = cfg.get("ttyd") or {}
    resources = cfg.get("resources") or {}
    if not isinstance(ttyd, dict) or not isinstance(resources, dict):
        die("ttyd and resources must be objects")

    tmux_cfg = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else {}
    initial_windows = int(tmux_cfg.get("initial_windows", 3))
    if initial_windows < 1:
        initial_windows = 1
    if initial_windows > 9:
        initial_windows = 9
    window_prefix = str(tmux_cfg.get("window_prefix") or "tab").strip() or "tab"

    runtime: dict = {
        "workspaces": workspaces,
        "tmux": {
            "initial_windows": initial_windows,
            "window_prefix": window_prefix,
        },
        "ttyd": {
            "port": int(ttyd.get("port", 7681)),
            "host_port": int(ttyd.get("host_port", ttyd.get("port", 7681))),
            # Host publish address — default loopback (security hardening).
            "bind": str(ttyd.get("bind") or "127.0.0.1").strip() or "127.0.0.1",
            "font_size": int(ttyd.get("font_size", 19)),
            "font_family": str(
                ttyd.get("font_family")
                or "Menlo, Monaco, 'Courier New', monospace"
            ),
            "theme": str(ttyd.get("theme") or "dark"),
            "ping_interval": max(1, int(ttyd.get("ping_interval", 20))),
        },
        "resources": {
            "cpus": resources.get("cpus", 2),
            "memory": str(resources.get("memory", "4g")),
            "shm_size": str(resources.get("shm_size", "512m")),
            "tmpfs_size": str(resources.get("tmpfs_size", "512m")),
        },
    }

    project_paths = [p["path"] for ws in workspaces for p in ws["projects"]]

    return {
        "runtime": runtime,
        "project_dir": str(repo_root),
        "container_project_dir": container_project_dir,
        "project_paths": project_paths,
        "primary_workspace": primary_ws,
        "workspaces": workspaces,
    }


def synthesize_from_env(project_dir: str, repo_root: Path) -> dict:
    pd = resolve_abs(project_dir, "PROJECT_DIR")
    ws_name = pd.name
    ws_root = default_workspace_root(ws_name, "")
    meta_path = ensure_dir(repo_root / "workspaces" / ws_name, "workspace meta")
    projects = [
        {
            "name": pd.name,
            "path": str(pd),
            "workspace_path": f"{ws_root}/{pd.name}",
            "container_path": str(pd),
        }
    ]
    workspace = {
        "name": ws_name,
        "root": ws_root,
        "meta_path": str(meta_path),
        "enabled": True,
        "tmux_session": ws_name,
        "project_count": 1,
        "projects": projects,
    }
    runtime = {
        "workspaces": [workspace],
        "tmux": {"initial_windows": 3, "window_prefix": "tab"},
        "ttyd": {
            "port": 7681,
            "host_port": 7681,
            "bind": "127.0.0.1",
            "font_size": 19,
            "font_family": "Menlo, Monaco, 'Courier New', monospace",
            "theme": "dark",
            "ping_interval": 20,
        },
        "resources": {
            "cpus": 2,
            "memory": "4g",
            "shm_size": "512m",
            "tmpfs_size": "512m",
        },
    }
    return {
        "runtime": runtime,
        "project_dir": str(pd),
        "container_project_dir": ws_root,
        "project_paths": [str(pd)],
        "primary_workspace": workspace,
        "workspaces": [workspace],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="",
        help="Path to orcan.config.json (optional)",
    )
    parser.add_argument("--root", default="", help="Repository root")
    parser.add_argument("--project-dir", default="", help="Fallback PROJECT_DIR")
    args = parser.parse_args()

    root = Path(args.root or Path.cwd()).resolve()
    env_path = root / ".env"
    example = root / ".env.example"
    runtime_dir = root / "mounts"
    workspaces_dir = root / "workspaces"
    runtime_path = runtime_dir / "runtime-config.json"
    compose_path = runtime_dir / "compose-projects.generated.yml"
    manifest_path = workspaces_dir / "index.json"

    if not env_path.exists():
        if not example.exists():
            die("missing .env and .env.example")
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    config_path = Path(args.config) if args.config else None
    if config_path is not None and not config_path.is_absolute():
        config_path = (root / config_path).resolve()
    if config_path is None:
        config_path = discover_config(root)

    if config_path and config_path.is_file():
        built = build_from_config(load_config(config_path), root)
        print(f"Applied config: {config_path}")
    else:
        project_dir = args.project_dir or os.environ.get("PROJECT_DIR") or str(root)
        built = synthesize_from_env(project_dir, root)
        print("No CONFIG file; synthesized single-repo workspace from PROJECT_DIR")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    active_names = {ws["name"] for ws in built["workspaces"] if ws.get("enabled") is not False}
    prune_stale_workspace_metas(root, active_names)
    # Drop stale *.code-workspace files for removed workspaces
    for path in runtime_dir.glob("*.container.code-workspace"):
        stem = path.name[: -len(".container.code-workspace")]
        if stem not in active_names and stem != "workspace":
            path.unlink(missing_ok=True)
            print(f"removed stale {path.name}")
    for path in runtime_dir.glob("*.host.code-workspace"):
        stem = path.name[: -len(".host.code-workspace")]
        if stem not in active_names and stem != "workspace":
            path.unlink(missing_ok=True)
            print(f"removed stale {path.name}")

    runtime_path.write_text(
        json.dumps(built["runtime"], indent=2) + "\n", encoding="utf-8"
    )
    compose_path.write_text(
        write_compose_projects(built["workspaces"], root, managed_projects_root()),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(write_workspace_manifest(built["runtime"]), indent=2) + "\n",
        encoding="utf-8",
    )

    code_workspace_paths: list[Path] = []
    for ws in built["workspaces"]:
        code_workspace_paths.append(
            write_code_workspace(
                root, ws, ws["projects"], suffix="container", use_container_paths=True
            )
        )
        write_code_workspace(
            root, ws, ws["projects"], suffix="host", use_container_paths=False
        )

    # Stop hook (orcan-context-reflect) defaults to on for a brand-new
    # workspace meta dir (no .claude/settings.json yet) — opting OUT is what's
    # configurable: `orcan context hook disable <name>` afterwards sticks,
    # since we only ever seed here, never re-enable on top of an existing file.
    for ws in built["workspaces"]:
        if ws.get("enabled") is False:
            continue
        meta_path = Path(ws["meta_path"])
        settings_path = claude_hook.settings_path(meta_path)
        if not settings_path.exists():
            claude_hook.enable(meta_path, dry_run=False)
            print(
                f"context: Stop hook enabled by default for workspace {ws['name']!r} "
                f"(disable: orcan context hook disable {ws['name']})"
            )
        elif not claude_hook.has_hook(claude_hook.load_settings(settings_path)):
            # Either the user ran `orcan context hook disable`, or something
            # else created settings.json before this seed step ever ran for
            # this workspace (e.g. a pre-existing workspace from before this
            # default existed) — either way, say so instead of staying quiet,
            # since the two cases are indistinguishable from here.
            print(
                f"context: Stop hook not active for workspace {ws['name']!r} "
                f"({settings_path} exists without it — enable: orcan context hook enable {ws['name']})"
            )

    primary_ws = built["primary_workspace"]
    ensure_env_key(env_path, "PROJECT_DIR", built["project_dir"])
    ensure_env_key(env_path, "CONTAINER_PROJECT_DIR", built["container_project_dir"])
    remove_env_key(env_path, "PROJECTS_DIR")
    remove_env_key(env_path, "PROJECT_ROOTS")
    remove_env_key(env_path, "DEFAULT_WORKSPACE")
    ensure_env_key(env_path, "ORCAN_CONFIG_HOST", str(runtime_path))
    ensure_env_key(env_path, "ORCAN_CONFIG", "/etc/orcan/config.json")
    ensure_env_key(env_path, "ORCAN_COMPOSE_PROJECTS", str(compose_path))
    ensure_env_key(env_path, "ORCAN_WORKSPACE_MANIFEST", str(manifest_path))
    ensure_env_key(env_path, "WORKSPACE_ROOT", primary_ws["root"])
    ensure_env_key(env_path, "WORKSPACE_NAME", primary_ws["name"])
    ensure_env_key(env_path, "WORKSPACE_META_PATH", primary_ws["meta_path"])

    ttyd = built["runtime"]["ttyd"]
    resources = built["runtime"]["resources"]
    ensure_env_key_unless_set(env_path, "TTYD_PORT", str(ttyd["port"]))
    ensure_env_key_unless_set(env_path, "TTYD_HOST_PORT", str(ttyd["host_port"]))
    ensure_env_key_unless_set(env_path, "TTYD_BIND", str(ttyd.get("bind", "127.0.0.1")))
    ensure_env_key_unless_set(env_path, "TTYD_FONT_SIZE", str(ttyd["font_size"]))
    ensure_env_key_unless_set(env_path, "TTYD_FONT_FAMILY", str(ttyd["font_family"]))
    ensure_env_key_unless_set(env_path, "TTYD_THEME", str(ttyd["theme"]))
    ensure_env_key_unless_set(
        env_path, "TTYD_PING_INTERVAL", str(ttyd.get("ping_interval", 20))
    )
    # Optional basic auth — set only in .env (never commit). Format: user:password
    # ensure_env_key_unless_set is NOT used: leave unset unless the user adds it.
    ensure_env_key_unless_set(env_path, "CPUS", str(resources["cpus"]))
    ensure_env_key_unless_set(env_path, "MEMORY", str(resources["memory"]))
    ensure_env_key_unless_set(env_path, "SHM_SIZE", str(resources["shm_size"]))
    ensure_env_key_unless_set(env_path, "TMPFS_SIZE", str(resources["tmpfs_size"]))

    print(f"PROJECT_DIR={built['project_dir']} (orchestrator home)")
    print(f"WORKSPACE_ROOT={primary_ws['root']} (agent/tmux start directory in container)")
    print(f"workspaces: {len(built['workspaces'])} (one tmux session each)")
    for ws in built["workspaces"]:
        print(
            f"  - {ws['name']} @ {ws['root']} "
            f"(repos={ws['project_count']})"
        )
        print(f"    meta: {ws['meta_path']}")
        for p in ws["projects"]:
            print(
                f"      {p['name']}: {p['path']} (symlink → {p['workspace_path']})"
            )
    print(f"runtime config: {runtime_path}")
    print(f"compose mounts: {compose_path}")
    for path in code_workspace_paths:
        print(f"code-workspace (container): {path}")


if __name__ == "__main__":
    main()
