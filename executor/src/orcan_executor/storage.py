"""Storage accounting and bounded copies; accounting never reads file contents."""

import os
import shutil
from pathlib import Path

from .settings import artifact_root, minimum_free_mb, state_dir, storage_limit_mb, worktree_root


def filesystem(path: Path) -> dict:
    path = path.absolute()
    while not path.exists() and path != path.parent:
        path = path.parent
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "minimum_free_bytes": minimum_free_mb() * 1024**2,
        "ready": usage.free >= minimum_free_mb() * 1024**2,
    }


def capacity() -> dict:
    # State and checkouts can be on different filesystems. Both need a reserve.
    disks = [filesystem(state_dir()), filesystem(worktree_root()), filesystem(artifact_root())]
    return {"ready": all(disk["ready"] for disk in disks), "filesystems": disks}


def worktree_capacity() -> dict:
    trees = size(worktree_root())
    budget = storage_limit_mb("worktree_budget_mb") * 1024**2
    return {
        "ready": not trees["incomplete"] and trees["allocated_bytes"] <= budget,
        **trees,
        "budget_bytes": budget,
    }


def size(path: Path, *, limit: int = 100000) -> dict:
    """Bound traversal and memory; hardlinks count once within each category."""
    total = entries = 0
    seen = set()
    pending = [path]
    incomplete = False
    while pending:
        current = pending.pop()
        try:
            stat = current.lstat()
            entries += 1
            if entries > limit:
                incomplete = True
                break
            if current.is_symlink():
                continue
            identity = (stat.st_dev, stat.st_ino)
            if identity in seen:
                continue
            seen.add(identity)
            if current.is_dir():
                with os.scandir(current) as children:
                    for child in children:
                        if entries + len(pending) >= limit:
                            incomplete = True
                            break
                        pending.append(Path(child.path))
            else:
                total += stat.st_blocks * 512
        except FileNotFoundError:
            continue
        except OSError:
            incomplete = True
    return {"allocated_bytes": total, "entries": entries, "incomplete": incomplete}


def report() -> dict:
    root = state_dir()
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    categories = {
        "job_artifacts": artifact_root(),
        "local_job_metadata": root / "jobs",
        "executor_worktrees": worktree_root(),
        "directory_snapshots": root / "snapshots",
        "shared_uv_cache": Path(os.environ.get("UV_CACHE_DIR", str(cache / "uv"))),
        "shared_pip_cache": cache / "pip",
        "shared_gradle_cache": Path(
            os.environ.get("GRADLE_USER_HOME", str(Path.home() / ".gradle"))
        ),
    }
    disks = capacity()
    trees = worktree_capacity()
    return disks | {
        "ready": disks["ready"] and trees["ready"],
        "worktrees": trees,
        "detail_budget_bytes": storage_limit_mb("detail_budget_mb") * 1024**2,
        "categories": [
            {
                "name": name,
                "path": str(path),
                "owner": "shared" if name.startswith("shared_") else "executor",
                **size(path),
            }
            for name, path in categories.items()
        ],
        "notes": [
            "Categories may overlap or share hardlinks; do not sum them as recoverable space.",
            "Shared caches, Docker, user repositories and dirty worktrees are never deleted by storage clean.",
        ],
    }


def bounded_copy(source: Path, target: Path, remaining: int) -> int:
    """Never archive partial/oversized evidence, even when a source grows."""
    written = 0
    created = False
    try:
        with source.open("rb") as reader:
            if os.fstat(reader.fileno()).st_size > remaining:
                raise ValueError("Copied artifacts exceeded artifact_limit_mb")
            with target.open("xb") as writer:
                created = True
                while chunk := reader.read(min(65536, max(1, remaining - written + 1))):
                    if written + len(chunk) > remaining:
                        raise ValueError("Copied artifacts exceeded artifact_limit_mb")
                    writer.write(chunk)
                    written += len(chunk)
    except BaseException:
        # Callers provide a fresh archive destination, never a source-project path.
        if created:
            target.unlink()
        raise
    return written
