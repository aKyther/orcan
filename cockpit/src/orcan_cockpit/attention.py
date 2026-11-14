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


def matching_workspaces(job: dict, rows: list[dict]) -> list[dict]:
    """Match canonical project paths, offering every matching workspace."""
    from pathlib import Path

    repo = job.get("repo")
    if not repo:
        return []
    target = Path(repo).resolve()
    return [row for row in rows if any(
        isinstance(project, dict) and project.get("path")
        and Path(project["path"]).resolve() == target
        for project in row.get("projects", [])
    )]


