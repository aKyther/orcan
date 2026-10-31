import fcntl
import hashlib
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from . import profiles, reports, store
from .metrics import log_size
from .settings import default_timeout, execution_lane, state_dir, worktree_root


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
    replace_pending: str | None = None,
    replace_owner: str = "",
) -> dict:
    if replace_pending is not None and (
        reuse or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}", replace_pending)
    ):
        raise ValueError(
            "Replacement requires a group of 1..80 ASCII name characters and cannot combine with --reuse"
        )
    if replace_owner:
        replace_owner = str(UUID(replace_owner))
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
        lane=execution_lane(definitions[profile].get("lane", "default")),
        selectors=selectors,
        timeout=timeout,
        replace_group=replace_pending,
        replace_owner=replace_owner,
    )
    # Keep the object reachable even if the agent removes its task branch/worktree.
    git(repo, "update-ref", "refs/orcan/executor/jobs/" + job["id"], sha)
    try:
        with replacement_guard(job) as candidates:
            existing = store.create(job, reuse=reuse, replacements=candidates)
        if existing != job["id"]:
            git(repo, "update-ref", "-d", "refs/orcan/executor/jobs/" + job["id"])
            return store.get(existing)
    except BaseException:
        git(repo, "update-ref", "-d", "refs/orcan/executor/jobs/" + job["id"])
        raise
    if replace_pending:
        job["superseded_count"] = store.superseded_count(job["id"])
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
    if job["status"] in store.TERMINAL:
        return None  # Late messages must not recreate expired completed-job directories.
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
                definition = profiles.load((worktree / profiles.CONFIG).read_text())[job["profile"]]
                report_inputs = {}
                if definition.get("require_junit"):
                    for pattern in definition.get("junit", []):
                        for source in worktree.glob(pattern):
                            if source.is_file() and source.resolve().is_relative_to(
                                worktree.resolve()
                            ):
                                stat = source.stat()
                                report_inputs[source.resolve()] = (
                                    stat.st_ino,
                                    stat.st_size,
                                    stat.st_mtime_ns,
                                )
                for index, (command, cwd) in enumerate(steps, 1):
                    store.step(job, index, "step_started", total=len(steps))
                    if on_started is not None:
                        on_started()
                    step_start = time.monotonic()
                    step_path = attempt / "steps" / f"step-{index:03d}.log"
                    step_path.parent.mkdir(exist_ok=True)
                    record = dict(
                        step=index,
                        argv=command,
                        exit_code=None,
                        outcome="error",
                        log=str(step_path.relative_to(attempt)),
                    )
                    report["commands"].append(record)
                    try:
                        with step_path.open("wb") as step_log:
                            code = execute(
                                command,
                                cwd,
                                step_log,
                                job["timeout"] - (time.monotonic() - began),
                                lock.fileno(),
                            )
                        record.update(exit_code=code, outcome="passed" if code == 0 else "failed")
                    except subprocess.TimeoutExpired:
                        record["outcome"] = "timed_out"
                        raise
                    finally:
                        with step_path.open("rb") as step_log:
                            shutil.copyfileobj(step_log, log)
                        log.flush()
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
            missing_reports = []
            copied = set()
            for pattern in definition.get("junit", []):
                matched = False
                for source in sorted(worktree.glob(pattern)):
                    if source.is_file() and source.resolve().is_relative_to(worktree.resolve()):
                        stat = source.stat()
                        if report_inputs.get(source.resolve()) == (
                            stat.st_ino,
                            stat.st_size,
                            stat.st_mtime_ns,
                        ):
                            continue  # A report shipped in the snapshot is not execution evidence.
                        matched = True
                        if source.resolve() not in copied:
                            shutil.copyfile(source, junit_dir / f"TEST-{len(copied)}.xml")
                            copied.add(source.resolve())
                if not matched:
                    missing_reports.append(pattern)
            automatic = attempt / "junit.xml"
            if automatic.is_file():
                shutil.copyfile(automatic, junit_dir / "TEST-pytest.xml")
            elif any("{junit}" in step["argv"] for step in definition["steps"]):
                missing_reports.append("{junit}")
            report.update(reports.junit(junit_dir))
            report["status"] = (
                "passed"
                if all(c["exit_code"] == 0 for c in report["commands"])
                and not (report["failed"] or report["errors"])
                else "failed"
            )
            if definition.get("require_junit"):
                if missing_reports or not any(junit_dir.glob("*.xml")):
                    report["error"] = "Required JUnit reports missing or unchanged: " + ", ".join(
                        missing_reports
                    )
                elif report["tests"] < definition.get("minimum_tests", 1):
                    report["error"] = "JUnit report contains fewer tests than the required minimum"
                if report.get("error") and report["status"] == "passed":
                    report["status"] = "error"
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
        if report["status"] != "passed":
            diagnostic = {
                key: report[key]
                for key in (
                    "job_id",
                    "sha",
                    "profile",
                    "status",
                    "tests",
                    "passed",
                    "failed",
                    "errors",
                    "skipped",
                )
            }
            diagnostic["failures"] = report["failures"]
            for key in ("error", "failed_step", "diagnostic_note"):
                if key in summary:
                    diagnostic[key] = summary[key]
            (attempt / "diagnostics.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
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


@contextmanager
def recovery_guard(job_id: str):
    """Hold the execution lock through explicit republish; never restart a live child."""
    job = store.get(job_id)
    if job["status"] in store.TERMINAL or job["details_expired"]:
        raise ValueError("Completed jobs cannot be recovered; submit a new check if needed")
    directory = state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "Execution lock is still held; a worker or child may be active. Recovery refused"
            ) from None
        with store.database() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row["status"] in store.TERMINAL:
                raise ValueError("Job completed while recovery was requested")
            db.execute(
                "UPDATE jobs SET status='queued',publication_state='recovery_pending',recovery_count=recovery_count+1 WHERE id=?",
                (job_id,),
            )
            store.event(db, {"kind": "recovery_requested", "job_id": job_id, "sha": job["sha"]})
        yield store.get(job_id)


@contextmanager
def replacement_guard(job: dict):
    """Serialize bounded replacement scans and hold old execution locks until commit."""
    if not job.get("replace_group"):
        yield []
        return
    scope = json.dumps(
        [
            job[key]
            for key in (
                "git_dir",
                "profile",
                "selectors",
                "timeout",
                "lane",
                "replace_group",
                "replace_owner",
            )
        ]
    )
    stripe = int(hashlib.sha256(scope.encode()).hexdigest(), 16) % 64
    root = state_dir() / "replacement-locks"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        group_lock = stack.enter_context((root / str(stripe)).open("a"))
        fcntl.flock(group_lock, fcntl.LOCK_EX)
        candidates = []
        began = time.monotonic()
        for old in store.replacement_candidates(job):
            if time.monotonic() - began > 10:
                break
            try:
                ancestry = subprocess.run(
                    [
                        "git",
                        "-C",
                        job["repo"],
                        "merge-base",
                        "--is-ancestor",
                        old["sha"],
                        job["sha"],
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                if ancestry.returncode:
                    continue
                directory = state_dir() / "jobs" / old["id"]
                directory.mkdir(parents=True, exist_ok=True)
                lock = stack.enter_context((directory / "run.lock").open("a"))
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, subprocess.TimeoutExpired):
                continue  # Unknown/claimed work is preserved, never force-cancelled.
            candidates.append(old["id"])
        yield candidates
