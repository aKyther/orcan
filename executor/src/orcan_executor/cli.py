import argparse
import fcntl
import json
import sys
from pathlib import Path

from . import engine, events, profiles, store
from .metrics import model_result, wire
from .settings import integer, queue_name, state_dir


def emit(value):
    print(wire(model_result(value) if isinstance(value, dict) else value), flush=True)


def enqueue(job_id: str):
    from .tasks import verify

    job = store.get(job_id)
    definition = profiles.load(
        engine.git(
            Path(job["repo"]) if Path(job["repo"]).exists() else Path(job["git_dir"]),
            "show",
            job["sha"] + ":" + profiles.CONFIG,
        )
    )[job["profile"]]
    lane = definition.get("lane", "default")
    queue = queue_name() + (":" + lane if lane != "default" else "")
    verify.apply_async(args=[job_id], task_id=job_id, queue=queue)


def parser():
    root = argparse.ArgumentParser(
        description="Local commit verification with compact, event-driven results"
    )
    commands = root.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit", help="Pin a committed revision and enqueue verification")
    submit.add_argument("--repo", type=Path, required=True)
    submit.add_argument("--sha", default="HEAD")
    submit.add_argument(
        "--notify-codex-thread",
        help="Explicit local Codex session UUID to receive the compact result",
    )
    submit.add_argument(
        "--directory",
        action="store_true",
        help="Snapshot explicitly included files without modifying project Git metadata",
    )
    submit.add_argument(
        "--include",
        action="append",
        default=[],
        help="Project-relative regular file to include in a directory snapshot",
    )
    submit.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse identical queued/running verification instead of adding work",
    )
    submit.add_argument("--task", default="")
    submit.add_argument("--profile", default="selected")
    submit.add_argument("--test", action="append", default=[])
    submit.add_argument(
        "--timeout", type=int, default=None, help="Whole verification deadline in seconds"
    )
    init = commands.add_parser(
        "init", help="Create project procedures; review and commit before use"
    )
    init.add_argument("--repo", type=Path, default=Path.cwd())
    init.add_argument("--kind", choices=["python", "java", "scala", "custom"], required=True)
    listing = commands.add_parser("profiles", help="List procedures from a committed snapshot")
    listing.add_argument("--repo", type=Path, default=Path.cwd())
    listing.add_argument("--sha", default="HEAD")
    commands.add_parser(
        "stats",
        help="Bounded measurements, payload bytes and delivery states; token counts are estimates",
    )
    commands.add_parser("maintenance", help="Local TTL cleanup and outbox recovery service")
    notify = commands.add_parser(
        "notify", help="Attach an explicit Codex session to an existing job"
    )
    notify.add_argument("job_id")
    notify.add_argument("--codex-thread", required=True)
    deliveries = commands.add_parser(
        "deliveries", help="Bounded notification states; queued does not mean consumed"
    )
    deliveries.add_argument("--job")
    commands.add_parser(
        "notification-controller",
        help="Event-driven result delivery service; separate process only",
    )
    cancel = commands.add_parser(
        "cancel", help="Cancel queued obsolete work; running processes are preserved"
    )
    cancel.add_argument("job_id")
    ack = commands.add_parser("ack", help="Record that a completed result was consumed")
    ack.add_argument("job_id")
    ack.add_argument("--codex-thread", help="Confirm consumption by a registered Codex session")
    logs = commands.add_parser("logs", help="Read a bounded log chunk; never dump build output")
    artifacts = commands.add_parser(
        "artifacts", help="List a bounded page of full report/XML artifact names"
    )
    artifacts.add_argument("job_id")
    artifacts.add_argument("--after", default="")
    logs.add_argument("job_id")
    logs.add_argument(
        "--artifact",
        default="output.log",
        help="Read report.json or junit/XML instead of output.log",
    )
    logs.add_argument("--offset", type=int, default=0)
    logs.add_argument("--limit", type=int, default=4000)
    commands.add_parser("doctor", help="Bounded readiness check; exit nonzero when unavailable")
    status = commands.add_parser("status")
    status.add_argument("--failures", action="store_true")
    result = commands.add_parser("result")
    result.add_argument("job_id")
    result.add_argument(
        "--full", action="store_true", help="Show full artifact paths; use logs for bounded reading"
    )
    listen = commands.add_parser(
        "listen", help="Block on Redis Streams; JSON per completion, no polling"
    )
    listen.add_argument(
        "--after", default="0-0", help="Resume from stream ID; default replays retained history"
    )
    listen.add_argument("--job")
    listen.add_argument("--once", action="store_true")
    listen.add_argument("--timeout", type=float)
    wait = commands.add_parser(
        "wait", help="Return an existing result, or block until this job completes"
    )
    wait.add_argument("job_id")
    wait.add_argument("--timeout", type=float, default=1800)
    web = commands.add_parser("web", help="Serve the local read-only live dashboard")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    worker = commands.add_parser(
        "worker", help="Run an isolated local Celery worker lane in the foreground"
    )
    worker.add_argument("--lane", choices=["default", "light", "heavy"], default="default")
    recover = commands.add_parser(
        "recover", help="Republish pending events and requeue one interrupted/pending job"
    )
    recover.add_argument("--job")
    recover.add_argument(
        "--replay-events",
        action="store_true",
        help="Republish all SQLite events after Redis data loss; deduplicate by event_id",
    )
    return root


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv == ["help"]:
        parser().print_help()
        return 0
    args = parser().parse_args(argv)
    try:
        if args.command == "notification-controller":
            from .notifications import controller

            controller()
        elif args.command == "notify":
            from .notifications import register

            emit(register(args.job_id, args.codex_thread))
            events.publish_pending()
        elif args.command == "stats":
            board = store.board()
            board["stats"]["measured_model_tokens"] = None
            board["stats"]["measured_model_cost"] = None
            emit(
                {
                    key: board[key]
                    for key in (
                        "stats",
                        "counts",
                        "delivery_counts",
                        "notification_stats",
                        "retention_seconds",
                        "max_pending",
                    )
                }
            )
        elif args.command == "deliveries":
            from .notifications import listing

            emit(listing(args.job))
        elif args.command == "cancel":
            emit(engine.cancel(args.job_id))
            events.publish_pending()
        elif args.command == "ack":
            if args.codex_thread:
                from .notifications import acknowledge

                acknowledge(args.job_id, args.codex_thread)
            else:
                store.acknowledge(args.job_id)
            emit({"job_id": args.job_id, "acknowledged": True})
            events.publish_pending()
        elif args.command == "maintenance":
            from .retention import maintain

            maintain()
        elif args.command == "artifacts":
            job = store.get(args.job_id)
            directory = (
                Path(job["report"]).parent
                if job["report"]
                else state_dir() / "jobs" / job["id"] / str(job["attempts"])
            )
            names = sorted(
                str(path.relative_to(directory))
                for path in directory.rglob("*")
                if path.is_file()
                and path.resolve().is_relative_to(directory.resolve())
                and str(path.relative_to(directory)) > args.after
            )
            selected = names[:50]
            emit(
                {
                    "artifacts": selected,
                    "more": len(names) > 50,
                    "next_after": selected[-1] if selected else None,
                }
            )
        elif args.command == "logs":
            if not 0 <= args.offset or not 1 <= args.limit <= 16000:
                raise ValueError("Use a nonnegative byte offset and limit 1..16000")
            job = store.get(args.job_id)
            directory = (
                Path(job["report"]).parent
                if job["report"]
                else state_dir() / "jobs" / job["id"] / str(job["attempts"])
            )
            path = profiles.inside(directory, args.artifact)
            if not path.resolve().is_relative_to(state_dir()):
                raise ValueError("Artifact outside local state")
            with path.open("rb") as source:
                source.seek(args.offset)
                chunk = source.read(args.limit)
                position = source.tell()
                more = bool(source.read(1))
            payload = {
                "job_id": job["id"],
                "text": chunk.decode("utf-8", errors="replace"),
                "next_offset": position,
                "more": more,
            }
            store.detail_read(job["id"], len(chunk), len(wire(payload).encode()) + 1)
            try:
                events.publish_pending()
            except Exception:
                pass  # Reading local diagnostics remains possible during broker outages.
            emit(payload)
        elif args.command == "init":
            destination = args.repo.resolve() / profiles.CONFIG
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x") as output:
                output.write(json.dumps(profiles.template(args.kind, args.repo), indent=2) + "\n")
            emit(
                {
                    "config": str(destination),
                    "next": "Review procedures and commit the configuration",
                }
            )
        elif args.command == "profiles":
            sha = engine.git(
                args.repo, "rev-parse", "--verify", "--end-of-options", args.sha + "^{commit}"
            )
            definitions = profiles.load(engine.git(args.repo, "show", sha + ":" + profiles.CONFIG))
            emit({"sha": sha, "profiles": list(definitions)})
        elif args.command == "doctor":
            import os

            enabled = os.environ.get("ORCAN_REDIS_ENABLED") == "1"
            broker = False
            if enabled:
                try:
                    broker = bool(events.client().ping())
                except Exception:
                    pass
            worker = False
            if enabled and broker:
                try:
                    worker = store.board()["worker_running"] and bool(
                        any(
                            events.client().get(queue_name() + suffix + ":worker-ready")
                            for suffix in ("", ":light", ":heavy")
                        )
                    )
                except Exception:
                    pass
            ready = enabled and broker and worker
            emit({"enabled": enabled, "broker": broker, "worker": worker, "ready": ready})
            return 0 if ready else 2
        elif args.command == "submit":
            import os

            if os.environ.get("ORCAN_REDIS_ENABLED") != "1":
                raise ValueError(
                    "Executor disabled; start Orcan with --with-redis, or run checks directly"
                )
            from contextlib import nullcontext

            from .snapshots import snapshot

            if args.include and not args.directory:
                raise ValueError("--include requires --directory")
            if args.directory and args.sha != "HEAD":
                raise ValueError("--directory identifies its own snapshot; omit --sha")
            from .notifications import register, thread_id

            target = (
                thread_id(args.notify_codex_thread)
                if args.notify_codex_thread is not None
                else None
            )
            source = snapshot(args.repo, args.include) if args.directory else nullcontext(args.repo)
            with source as repository:
                job = engine.submit(
                    repository,
                    args.sha,
                    args.task,
                    args.profile,
                    args.test,
                    args.timeout
                    if args.timeout is not None
                    else integer("timeout-seconds", 1800, 21600),
                    reuse=args.reuse,
                )
                if target:
                    register(job["id"], target)
            try:
                enqueue(job["id"])
            except Exception:
                emit(
                    {
                        "job_id": job["id"],
                        "sha": job["sha"],
                        "status": "queued_locally",
                        "error": "Broker unavailable; start Redis and run orcan-executor recover --job "
                        + job["id"],
                    }
                )
                return 2
            try:
                events.publish_pending()
            except Exception:
                pass  # The durable outbox can be recovered after an event transport outage.
            emit(
                {"job_id": job["id"], "sha": job["sha"], "task_id": job["task"], "status": "queued"}
            )
        elif args.command == "status":
            emit(store.listing(args.failures))
        elif args.command == "result":
            job = store.get(args.job_id)
            if args.full and job["report"]:
                emit(
                    {
                        "report": job["report"],
                        "log": str(Path(job["report"]).with_name("output.log")),
                        "hint": "Use logs JOB --offset N --limit N for bounded output",
                    }
                )
            else:
                emit(
                    {
                        key: job[key]
                        for key in (
                            "id",
                            "task",
                            "sha",
                            "status",
                            "attempts",
                            "summary",
                            "report",
                            "worktree",
                        )
                    }
                )
        elif args.command == "listen":
            if args.timeout is not None and args.timeout <= 0:
                raise ValueError("timeout must be positive")
            for payload in events.listen(args.after, args.job, args.timeout):
                emit(payload)
                if args.once:
                    break
        elif args.command == "wait":
            if args.timeout <= 0:
                raise ValueError("timeout must be positive")
            # Subscribe from a captured cursor, then check SQLite: completion in between is not lost.
            latest = events.client().xrevrange(events.stream_name(), count=1)
            after = latest[0][0] if latest else "0-0"
            job = store.get(args.job_id)
            if job["status"] in store.TERMINAL:
                emit(
                    {
                        "job_id": job["id"],
                        "sha": job["sha"],
                        "status": job["status"],
                        "summary": job["summary"],
                        "report": job["report"],
                    }
                )
            else:
                payload = next(events.listen(after, args.job_id, args.timeout), None)
                if payload is None:
                    emit({"job_id": args.job_id, "status": "wait_timeout"})
                    return 2
                emit(payload)
        elif args.command == "recover":
            if args.job:
                job = store.get(args.job)
                if job["status"] not in store.TERMINAL:
                    enqueue(job["id"])
            emit(
                {
                    "published_events": events.publish_pending(args.replay_events),
                    "requeued_job": args.job,
                }
            )
        elif args.command == "web":
            import uvicorn

            uvicorn.run(
                "orcan_executor.web:app", host=args.host, port=args.port, log_level="warning"
            )
        elif args.command == "worker":
            from .tasks import app

            state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
            suffix = ":" + args.lane if args.lane != "default" else ""
            worker_queue = queue_name() + suffix
            lock_name = "worker.lock" if args.lane == "default" else "worker-" + args.lane + ".lock"
            app.conf.task_default_queue = worker_queue
            with (state_dir() / lock_name).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                app.worker_main(
                    [
                        "worker",
                        "--pool=solo",
                        "--queues=" + worker_queue,
                        "--hostname=orcan-" + args.lane + "@%h",
                        "--concurrency=1",
                        "--loglevel=WARNING",
                        "--without-gossip",
                        "--without-mingle",
                    ]
                )
    except KeyboardInterrupt:
        return 130
    except ValueError as error:
        emit({"error": "ValueError", "message": str(error)[:500]})
        return 1
    except Exception as error:
        # No raw broker exceptions: connection URLs may contain credentials.
        emit(
            {
                "error": type(error).__name__,
                "message": "Operation failed; verify arguments, local state and Redis availability",
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
