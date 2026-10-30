import fcntl
import json
import os
import resource
import shutil
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from . import profiles, reports, store
from .metrics import log_size
from .settings import default_timeout, state_dir, worktree_root


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def submit(
    repo: Path,
    revision: str,
    task: str,
    profile: str,
    selectors: list[str],
    timeout: int | None,
    reuse: bool = False,
) -> dict:
    repo = Path(git(repo.resolve(), "rev-parse", "--show-toplevel")).resolve()
    sha = git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}")
    selectors = list(dict.fromkeys(value.strip() for value in selectors))
    if (
        len(task) > 160
        or len(selectors) > 100
        or any(item.startswith("-") or len(item) > 300 for item in selectors)
    ):
        raise ValueError("Invalid task label or test selector")
    definitions = profiles.load(git(repo, "show", sha + ":" + profiles.CONFIG))
    if profile not in definitions:
        raise ValueError("Unknown profile; use orcan-executor profiles --repo PATH")
    timeout = (
        timeout
        if timeout is not None
        else definitions[profile].get("timeout_seconds", default_timeout())
    )
    if not 1 <= timeout <= 21600:
        raise ValueError("Timeout must be between 1 and 21600 seconds")
    required = definitions[profile].get("requires_tests", False)
    if required and (not selectors or any(not item for item in selectors)):
        raise ValueError("This profile requires explicit --test selectors")
    if not required and selectors:
        raise ValueError("This profile does not accept test selectors")
    job = dict(
        id=uuid4().hex,
        repo=str(repo),
        git_dir=git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"),
        sha=sha,
        task=task,
        profile=profile,
        lane=definitions[profile].get("lane", "default"),
        selectors=selectors,
        timeout=timeout,
    )
    # Keep the object reachable even if the agent removes its task branch/worktree.
    git(repo, "update-ref", "refs/orcan/executor/jobs/" + job["id"], sha)
    try:
        existing = store.create(job, reuse=reuse)
        if existing != job["id"]:
            git(repo, "update-ref", "-d", "refs/orcan/executor/jobs/" + job["id"])
            return store.get(existing)
    except BaseException:
        git(repo, "update-ref", "-d", "refs/orcan/executor/jobs/" + job["id"])
        raise
    return job


commands = profiles.commands


def execute(command: list[str], cwd: Path, log, timeout: float, lock_fd: int) -> int:
    if timeout <= 0:
        raise subprocess.TimeoutExpired(command, timeout)
    # Gradle and uv output goes straight to disk, never through an agent/model.
    with subprocess.Popen(
        command,
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        pass_fds=(lock_fd,),
    ) as process:
        try:
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                pass
            raise


def run_job(job_id: str, on_started=None) -> dict | None:
    # Validate the ID by DB lookup before using it as a path component.
    job = store.get(job_id)
    directory = state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        job = store.get(job_id)
        if job["status"] in store.TERMINAL:
            return None
        if job["attempts"] >= 3:
            report = directory / "report.json"
            report.write_text(json.dumps({"error": "Interrupted attempt limit reached"}) + "\n")
            return store.finish(
                job_id,
                "error",
                {
                    "error": "Three interrupted attempts; inspect executor infrastructure before resubmitting"
                },
                report,
            )
        worktree = worktree_root() / job_id / str(job["attempts"] + 1)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        if not store.start(job_id, worktree):
            return None
        if on_started is not None:
            on_started()
        job = store.get(job_id)
        attempt = directory / str(job["attempts"])
        attempt.mkdir()
        log_path = attempt / "output.log"
        began = time.monotonic()
        cpu_start = resource.getrusage(resource.RUSAGE_SELF)
        child_cpu_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        report = dict(
            job_id=job_id,
            sha=job["sha"],
            profile=job["profile"],
            status="error",
            tests=0,
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            failures=[],
            commands=[],
            worktree=str(worktree),
        )
        repo = Path(job["repo"])
        common = job["git_dir"] or git(
            repo, "rev-parse", "--path-format=absolute", "--git-common-dir"
        )
        added = False
        try:
            with log_path.open("wb") as log:
                subprocess.run(
                    [
                        "git",
                        "--git-dir",
                        common,
                        "worktree",
                        "add",
                        "--detach",
                        str(worktree),
                        job["sha"],
                    ],
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                added = True
                job["artifact_dir"] = str(attempt)
                steps = commands(worktree, job)
                for index, (command, cwd) in enumerate(steps, 1):
                    store.step(job, index, "step_started", total=len(steps))
                    if on_started is not None:
                        on_started()
                    step_start = time.monotonic()
                    code = execute(
                        command,
                        cwd,
                        log,
                        job["timeout"] - (time.monotonic() - began),
                        lock.fileno(),
                    )
                    report["commands"].append(dict(argv=command, exit_code=code))
                    store.step(
                        job,
                        index,
                        "step_passed" if code == 0 else "step_failed",
                        round(time.monotonic() - step_start, 3),
                        total=len(steps),
                    )
                    if on_started is not None:
                        on_started()
                    if code:
                        break
            junit_dir = attempt / "junit"
            junit_dir.mkdir()
            definition = profiles.load((worktree / profiles.CONFIG).read_text())[job["profile"]]
            for pattern in definition.get("junit", []):
                for source in sorted(worktree.glob(pattern)):
                    if source.is_file() and source.resolve().is_relative_to(worktree.resolve()):
                        shutil.copyfile(
                            source, junit_dir / f"TEST-{len(list(junit_dir.iterdir()))}.xml"
                        )
            if (attempt / "junit.xml").is_file():
                shutil.copyfile(attempt / "junit.xml", junit_dir / "TEST-pytest.xml")
            report.update(reports.junit(junit_dir))
            report["status"] = (
                "passed"
                if all(c["exit_code"] == 0 for c in report["commands"])
                and not (report["failed"] or report["errors"])
                else "failed"
            )
        except subprocess.TimeoutExpired:
            report.update(status="timed_out", error="Verification exceeded its configured timeout")
        except Exception as error:
            report.update(status="error", error=f"{type(error).__name__}: {str(error)[:500]}")
        finally:
            if added:
                try:
                    definition = profiles.load((worktree / profiles.CONFIG).read_text())[
                        job["profile"]
                    ]
                    for pattern in definition.get("artifacts", []):
                        for source in sorted(worktree.glob(pattern)):
                            if source.is_file() and source.resolve().is_relative_to(
                                worktree.resolve()
                            ):
                                target = attempt / "artifacts" / source.relative_to(worktree)
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(source, target)
                except Exception:
                    report["artifact_error"] = "Some project artifacts could not be archived"
            # Never force-remove a dirty checkout. Keep it and report the path if cleanup is blocked.
            if added:
                try:
                    # Only disposable outputs of the allowed commands in our own checkout.
                    for name in ("site", ".build"):
                        output = worktree / name
                        if (
                            output.is_dir()
                            and not output.is_symlink()
                            and not git(worktree, "ls-files", "--", name)
                        ):
                            shutil.rmtree(output)
                    cleanup = subprocess.run(
                        ["git", "--git-dir", common, "worktree", "remove", str(worktree)],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if cleanup.returncode:
                        report["cleanup"] = {
                            "retained_worktree": str(worktree),
                            "reason": cleanup.stderr[-500:],
                        }
                except (OSError, subprocess.SubprocessError) as error:
                    report["cleanup"] = {
                        "retained_worktree": str(worktree),
                        "reason": str(error)[:500],
                    }
        report["seconds"] = round(time.monotonic() - began, 3)
        log_bytes, log_lines = log_size(log_path)
        cpu_end = resource.getrusage(resource.RUSAGE_SELF)
        child_cpu_end = resource.getrusage(resource.RUSAGE_CHILDREN)
        report["metrics"] = {
            "log_bytes": log_bytes,
            "log_lines": log_lines,
            "queue_seconds": round(
                max(
                    0,
                    (
                        datetime.fromisoformat(job["started"])
                        - datetime.fromisoformat(job["created"])
                    ).total_seconds(),
                ),
                3,
            ),
            "child_cpu_seconds": round(
                child_cpu_end.ru_utime
                + child_cpu_end.ru_stime
                - child_cpu_start.ru_utime
                - child_cpu_start.ru_stime,
                6,
            ),
            "executor_cpu_seconds": round(
                cpu_end.ru_utime + cpu_end.ru_stime - cpu_start.ru_utime - cpu_start.ru_stime, 6
            ),
        }
        report_path = attempt / "report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        summary = reports.compact(report, log_path)
        summary["seconds"] = report["seconds"]
        summary["metrics"] = report["metrics"].copy()
        if report.get("artifact_error"):
            summary["artifact_warning"] = report["artifact_error"]
        if report.get("cleanup"):
            summary["retained_worktree"] = report["cleanup"]["retained_worktree"]
        result = store.finish(job_id, report["status"], summary, report_path)
        report["metrics"] = result["summary"]["metrics"].copy()
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        return result


def cancel(job_id: str) -> dict:
    """Cancel only queued work, serialized with the execution lock; never kill agent processes."""
    job = store.get(job_id)
    directory = state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Job already running; queued cancellation cannot stop it") from None
        job = store.get(job_id)
        if job["status"] != "queued":
            raise ValueError("Only queued jobs can be cancelled")
        report = directory / "report.json"
        report.write_text(
            json.dumps({"job_id": job_id, "sha": job["sha"], "status": "cancelled"}) + "\n"
        )
        return store.finish(
            job_id,
            "cancelled",
            {"message": "Queued verification cancelled; no checks executed"},
            report,
        )
