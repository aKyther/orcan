"""Pure attention classification and workspace matching."""

def attention_reason(job: dict) -> str:
    """Only explicit executor state warrants attention; never infer agent readiness."""
    if job.get("status") == "queued" and job.get("publication_state") in {
        "uncertain", "unknown", "recovery_pending",
    }:
        return "Queue delivery needs inspection; run executor diagnostics"
    if job.get("status") in {"passed", "failed", "error", "timed_out", "cancelled"}:
        if "acknowledged" not in job:
            return "Result receipt unknown; executor image needs updating"
        if not job["acknowledged"]:
            return "Result awaiting receipt"
    return ""


def repository_identity(path):
    """Resolve linked worktrees locally without spawning git on the UI thread."""
    from pathlib import Path

    root = Path(path).resolve()
    git = root / ".git"
    try:
        if git.is_file():
            directive = git.read_text()[:4096].strip()
            if not directive.startswith("gitdir: "):
                return root
            git = (root / directive[8:]).resolve()
        common = git / "commondir"
        if common.is_file():
            return (git / common.read_text()[:4096].strip()).resolve()
        if git.is_dir():
            return git.resolve()
    except OSError:
        pass
    return root


def matching_workspaces(job: dict, rows: list[dict]) -> list[dict]:
    """Match canonical project paths, offering every matching workspace."""
    repo = job.get("repo")
    if not repo:
        return []
    target = repository_identity(repo)
    return [row for row in rows if any(
        isinstance(project, dict) and project.get("path")
        and repository_identity(project["path"]) == target
        for project in row.get("projects", [])
    )]


