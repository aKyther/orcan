"""Finite isolated same-container smoke; only compact assertions reach stdout.

Run with: uv run --project executor --locked python executor/smoke/run.py
Full build/runtime logs stay in .orcan-test.executor-smoke/ (Git ignored).
"""

import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".orcan-test.executor-smoke"
NAME = "orcan-executor-smoke"
IMAGE = "orcan:executor-smoke"


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, **kwargs)


def docker(*args):
    return run(["docker", *args], capture_output=True).stdout


def execute(*args):
    return docker("exec", NAME, "orcan-executor", *args)


def main():
    STATE.mkdir(exist_ok=True)
    # Never take over an existing container, even a previous failed fixture.
    if docker("ps", "-aq", "--filter", "name=^/" + NAME + "$").strip():
        raise RuntimeError("Owned smoke container name already exists; inspect it first")
    with (STATE / "build.log").open("w") as log:
        run(
            ["docker", "build", "-t", IMAGE, "-f", "executor/smoke/Dockerfile", "."],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    fixture = STATE / ("repo-" + str(int(time.time())))
    fixture.mkdir()
    run(["git", "init", "-q", str(fixture)])
    for key, value in [("user.name", "Smoke fixture"), ("user.email", "fixture@example.invalid")]:
        run(["git", "-C", str(fixture), "config", key, value])
    (fixture / ".orcan").mkdir()
    (fixture / "check.py").write_text(
        'import sys\nfrom pathlib import Path\nassert Path("marker").read_text() == "snapshot"\nprint("noise" * 100000)\nPath(sys.argv[1]).write_text(\'<testsuite><testcase name="ok"/><testcase name="skip"><skipped/></testcase></testsuite>\')\n'
    )
    (fixture / "test_example.py").write_text(
        'def test_passes():\n    print("successful pytest noise" * 10000)\n    assert 2 + 2 == 4\n\ndef test_fails():\n    assert False, "long failure " * 1000\n'
    )
    (fixture / "marker").write_text("snapshot")
    (fixture / ".orcan/checks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": {
                    "selected": {
                        "requires_tests": True,
                        "steps": [
                            {
                                "argv": [
                                    "/opt/orcan-executor/venv/bin/python",
                                    "check.py",
                                    "{junit}",
                                    "{tests}",
                                ]
                            }
                        ],
                    },
                    "pytest": {
                        "requires_tests": True,
                        "steps": [
                            {
                                "argv": [
                                    "/opt/orcan-executor/venv/bin/python",
                                    "-m",
                                    "pytest",
                                    "-q",
                                    "-s",
                                    "{tests}",
                                    "--junitxml",
                                    "{junit}",
                                ]
                            }
                        ],
                    },
                    "heavy": {"lane": "heavy", "steps": [{"argv": ["true"]}]},
                    "failure": {
                        "steps": [
                            {
                                "argv": [
                                    "/opt/orcan-executor/venv/bin/python",
                                    "-c",
                                    'import sys; print("synthetic failure"); sys.exit(1)',
                                ]
                            }
                        ]
                    },
                },
            }
        )
    )
    run(["git", "-C", str(fixture), "add", "."])
    run(["git", "-C", str(fixture), "commit", "-qm", "Smoke fixture"])
    runtime = STATE / ("runtime-" + uuid4().hex[:12])
    env = [
        "-e",
        "ORCAN_REDIS_ENABLED=1",
        "-e",
        "ORCAN_EXECUTOR_QUEUE=orcan-smoke",
        "-e",
        f"ORCAN_EXECUTOR_STATE_DIR={runtime}",
        "-e",
        "ORCAN_SUPERVISOR_STATE_D=/tmp/orcan-executor-smoke-supervisor",
    ]
    started = False
    try:
        docker(
            "run",
            "-d",
            "--name",
            NAME,
            "--network",
            "none",
            "--mount",
            f"type=bind,source={STATE},target={STATE}",
            *env,
            IMAGE,
        )
        started = True
        # Fixture-only bounded readiness wait, not model/status polling.
        deadline = time.monotonic() + 45
        while True:
            probe = subprocess.run(
                ["docker", "exec", NAME, "orcan-executor", "doctor"],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Fixture readiness deadline exceeded")
            time.sleep(0.5)
        job = json.loads(execute("submit", "--repo", str(fixture), "--test", "Suite"))
        (fixture / "marker").write_text("agent editing")
        # A finite script deliberately awaits one event. Never an agent listener.
        event = json.loads(execute("wait", job["job_id"], "--timeout", "30"))
        assert event["status"] == "passed", event
        assert event["summary"]["passed"] == 1 and event["summary"]["skipped"] == 1
        assert "noise" not in json.dumps(event) and len(json.dumps(event)) < 2000
        assert (fixture / "marker").read_text() == "agent editing"
        bad = json.loads(execute("submit", "--repo", str(fixture), "--profile", "failure"))
        failed = json.loads(execute("wait", bad["job_id"], "--timeout", "30"))
        assert failed["status"] == "failed"
        assert "synthetic failure" in failed["summary"]["log_tail"]
        assert "pytest" in json.loads((fixture / ".orcan/checks.json").read_text())["profiles"]
        for selector, status in [
            ("test_example.py::test_passes", "passed"),
            ("test_example.py::test_fails", "failed"),
        ]:
            submitted = json.loads(
                execute("submit", "--repo", str(fixture), "--profile", "pytest", "--test", selector)
            )
            received = json.loads(execute("wait", submitted["job_id"], "--timeout", "30"))
            assert received["status"] == status and received["summary"]["tests"] == 1
            assert len(json.dumps(received)) < 3000
        # Real broker paths for reuse, cancellation, dedicated lanes and explicit receipts.
        queued = json.loads(
            execute("submit", "--repo", str(fixture), "--profile", "heavy", "--reuse")
        )
        reused = json.loads(
            execute("submit", "--repo", str(fixture), "--profile", "heavy", "--reuse")
        )
        assert reused["job_id"] == queued["job_id"]
        assert json.loads(execute("cancel", queued["job_id"]))["status"] == "cancelled"
        assert (
            json.loads(execute("wait", queued["job_id"], "--timeout", "10"))["status"]
            == "cancelled"
        )
        heavy = json.loads(execute("submit", "--repo", str(fixture), "--profile", "heavy"))
        docker("exec", "-d", NAME, "orcan-executor", "worker", "--lane", "heavy")
        assert json.loads(execute("wait", heavy["job_id"], "--timeout", "30"))["status"] == "passed"
        assert json.loads(execute("ack", job["job_id"]))["acknowledged"]
        execute("logs", bad["job_id"], "--limit", "100")
        plain = fixture / "plain"
        (plain / ".orcan").mkdir(parents=True)
        (plain / ".orcan/checks.json").write_text((fixture / ".orcan/checks.json").read_text())
        (plain / "test_example.py").write_text((fixture / "test_example.py").read_text())
        standalone = json.loads(
            execute(
                "submit",
                "--repo",
                str(plain),
                "--directory",
                "--include",
                "test_example.py",
                "--profile",
                "pytest",
                "--test",
                "test_example.py::test_passes",
            )
        )
        assert (
            json.loads(execute("wait", standalone["job_id"], "--timeout", "30"))["status"]
            == "passed"
        )
        assert not (plain / ".git").exists()
        thread = "019bcf10-1000-7000-8000-000000000001"
        notification_job = json.loads(
            execute(
                "submit",
                "--repo",
                str(fixture),
                "--profile",
                "pytest",
                "--test",
                "test_example.py::test_passes",
                "--notify-codex-thread",
                thread,
            )
        )
        assert (
            json.loads(execute("wait", notification_job["job_id"], "--timeout", "30"))["status"]
            == "passed"
        )
        # Finite fixture-only observation of the fake transport; never contacts a model.
        notification_deadline = time.monotonic() + 20
        while True:
            deliveries = json.loads(execute("deliveries", "--job", notification_job["job_id"]))
            if deliveries and deliveries[0]["status"] not in {"pending", "sending"}:
                break
            if time.monotonic() >= notification_deadline:
                raise RuntimeError("Notification fixture deadline exceeded")
            time.sleep(0.1)
        assert deliveries[0]["status"] == "queued", deliveries
        messages = (runtime / "notification-smoke.jsonl").read_text().splitlines()
        assert len(messages) == 1
        assert json.loads(messages[0])["thread"] == thread
        execute("notify", notification_job["job_id"], "--codex-thread", thread)
        assert json.loads(execute("ack", notification_job["job_id"], "--codex-thread", thread))[
            "acknowledged"
        ]
        assert (
            json.loads(execute("deliveries", "--job", notification_job["job_id"]))[0]["status"]
            == "consumed"
        )
        assert len((runtime / "notification-smoke.jsonl").read_text().splitlines()) == 1
        notify_stats = json.loads(execute("stats"))["notification_stats"]
        assert notify_stats["accepted_bytes"] == len(json.loads(messages[0])["message"].encode())
        assert notify_stats["consumed_bytes"] == notify_stats["accepted_bytes"]
        python = "/opt/orcan-executor/venv/bin/python"
        board = json.loads(
            docker(
                "exec",
                NAME,
                python,
                "-c",
                'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8765/api/board").read().decode())',
            )
        )
        assert board["counts"]["passed"] >= 1 and board["counts"]["failed"] >= 1
        assert board["stats"]["completed_jobs"] >= 4
        assert board["stats"]["acknowledged_jobs"] >= 1
        assert board["stats"]["detail_reads"] >= 1
        assert board["stats"]["log_bytes"] > board["stats"]["result_bytes"]
        assert board["stats"]["reduction_percent"] > 0
        ttl = int(docker("exec", NAME, "redis-cli", "ttl", "orcan-smoke:results").strip())
        assert 0 < ttl <= 3600
        load = json.loads(
            docker("exec", NAME, python, "/opt/orcan-executor-src/smoke/load.py", str(fixture))
        )
        assert load["jobs"] == 50 and load["passed"] == 40 and load["failed"] == 10
        (STATE / "load-report.json").write_text(json.dumps(load, indent=2))
        # Disabled startup installs no module processes, even with old rendered confs.
        docker(
            "exec",
            "-e",
            "ORCAN_REDIS_ENABLED=0",
            "-e",
            "ORCAN_SUPERVISOR_DRY_RUN=1",
            "-e",
            f"ORCAN_SUPERVISOR_STATE_D={STATE}/disabled-supervisor",
            NAME,
            "orcan-supervisord",
        )
        assert not list((STATE / "disabled-supervisor/programs").glob("executor-*.conf"))
        (STATE / "report.json").write_text(
            json.dumps(
                {"success": event, "failure": failed, "stream_ttl": ttl, "same_container": True},
                indent=2,
            )
        )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "checks": [
                        "same-container Redis/Celery/Supervisor",
                        "snapshot isolation",
                        "pytest-compatible JUnit counters",
                        "compact success",
                        "bounded failure",
                        "dashboard",
                        "stream TTL",
                        "disabled module",
                        "50 concurrent submissions + duplicates",
                        "consumer reconnect",
                        "broker outage/recovery",
                        "graceful worker restart",
                        "TTL cleanup",
                    ],
                }
            )
        )
    finally:
        if started:
            (STATE / "container.log").write_text(docker("logs", NAME))
            docker(
                "cp",
                NAME + ":/tmp/orcan-executor-smoke-supervisor",
                str(STATE / ("supervisor-" + str(int(time.time())))),
            )
            docker("stop", "--time", "40", NAME)
            docker("rm", NAME)
        # All executor test worktrees must have been safely cleaned by the worker.
        owned = runtime / "worktrees"
        assert not owned.exists() or not any(p.name == ".git" for p in owned.rglob(".git"))


if __name__ == "__main__":
    main()
