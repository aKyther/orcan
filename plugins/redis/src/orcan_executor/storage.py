"""Storage accounting and bounded copies; accounting never reads file contents."""

import os
import shutil
import stat as stat_mode
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
    """Bounded informational accounting; never used to admit or reject work."""
    return size(worktree_root())


def require_capacity() -> None:
    """Check actual free space without scanning checkouts or reading file contents."""
    result = capacity()
    if result["ready"]:
        return
    for disk in result["filesystems"]:
        if not disk["ready"]:
            free = disk["free_bytes"] // 1024**2
            reserve = disk["minimum_free_bytes"] // 1024**2
            raise OSError(
                f"Disk reserve reached at {disk['path']}: {free} MiB free; "
                f"{reserve} MiB required. Free disk space or review executor storage clean. "
                "Active or modified worktrees are preserved; no automatic procedure retry."
            )


def size(path: Path, *, limit: int | None = 150000, stop_after_bytes: int | None = None) -> dict:
    """Stream metadata without following links; hardlinked files count once.

    Reports bound their entry count. Neither report completeness nor checkout
    size controls admission; admission uses actual filesystem free space.
    Open directory iterators and pending paths scale with depth, not file count.
    """
    total = entries = 0
    seen = set()
    pending = iter((path,))
    parents = []
    incomplete = False
    try:
        while True:
            current = next(pending, None)
            if current is None:
                if hasattr(pending, "close"):
                    pending.close()
                if not parents:
                    break
                pending = parents.pop()
                continue
            if limit is not None and entries >= limit:
                incomplete = True
                break
            try:
                metadata = current.lstat() if isinstance(current, Path) else current.stat(
                    follow_symlinks=False
                )
                entries += 1
                if stat_mode.S_ISLNK(metadata.st_mode):
                    continue
                if stat_mode.S_ISDIR(metadata.st_mode):
                    children = os.scandir(current)
                    parents.append(pending)
                    pending = children
                else:
                    if metadata.st_nlink > 1:
                        identity = (metadata.st_dev, metadata.st_ino)
                        if identity in seen:
                            continue
                        seen.add(identity)
                    total += metadata.st_blocks * 512
                    if stop_after_bytes is not None and total > stop_after_bytes:
                        incomplete = True
                        break
            except FileNotFoundError:
                continue
            except OSError:
                incomplete = True
    finally:
        for iterator in [pending, *parents]:
            if hasattr(iterator, "close"):
                iterator.close()
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
        "ready": disks["ready"],
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
            "Worktree sizes are informational; incomplete accounting does not block jobs.",
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
