"""Shared-queue routing and independent worker liveness, including real Celery execution."""

import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from unittest.mock import Mock

import pytest
from conftest import commit

from orcan_executor import cli, engine, readiness, settings, store, tasks


@pytest.mark.parametrize("workers", [1, 2, 3, 4, 5])
def test_shared_queue_ignores_profile_lane(repo, monkeypatch, workers):
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKERS", str(workers))
    path = repo / ".orcan/checks.json"
    config = json.loads(path.read_text())
    config["profiles"]["quality"]["lane"] = "heavy"
    path.write_text(json.dumps(config))
    commit(repo)
    job = engine.submit(repo, "HEAD", "shared", "quality", [], 30)
    assert job["lane"] == "default"
    send = Mock()
    monkeypatch.setattr(tasks.verify, "apply_async", send)
    monkeypatch.setattr(readiness, "lanes", lambda: {"default": {"ready": True}})
    cli.enqueue(job["id"])
    assert send.call_args.kwargs["queue"] == settings.queue_name()


def test_each_worker_needs_its_own_lease_and_lock(monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKERS", "5")
    root = settings.state_dir()
    root.mkdir()
    leases = {
        readiness.worker_lease(settings.queue_name(), slot): store.now() for slot in (1, 2, 3, 4, 5)
    }
    monkeypatch.setattr(readiness.events, "client", lambda: Mock(get=leases.get))
    with ExitStack() as stack:
        for slot in (1, 2):
            handle = stack.enter_context((root / readiness.worker_lock("default", slot)).open("a"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert (
            readiness.lanes()["default"]["ready_workers"] == 2
        )  # Slot 3 lease alone is insufficient.
        del leases[readiness.worker_lease(settings.queue_name(), 1)]
        lane = readiness.lanes()["default"]
        assert lane["ready_workers"] == 1 and lane["configured_workers"] == 5
        assert lane["ready"]  # Slot 2 survives slot 1 shutdown.
        assert store.board()["worker_running"]


@pytest.mark.parametrize("value", ["0", "6", "true"])
def test_runtime_rejects_invalid_worker_count(monkeypatch, value):
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKERS", value)
    with pytest.raises(ValueError):
        settings.effective()


def test_runtime_rejects_combined_pool_and_split_lanes(monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKERS", "5")
    monkeypatch.setenv("ORCAN_EXECUTOR_SPLIT_LANES", "1")
    with pytest.raises(ValueError, match="split lanes"):
        settings.effective()


def wait_until(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Isolated worker pool did not reach the expected state")


def test_five_real_workers_share_queue_and_survive_one_shutdown(repo, tmp_path, monkeypatch):
    if not shutil.which("redis-server"):
        pytest.skip("redis-server unavailable")
    import redis

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv("ORCAN_EXECUTOR_BROKER_URL", f"redis://127.0.0.1:{port}/0")
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKERS", "5")
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "5")
    gate = tmp_path / "gate"
    gate.mkdir()
    # Every procedure waits until all five independent workers have started.
    # A single worker (or a global cap below five) cannot pass this barrier.
    (repo / "check.py").write_text(
        "import time\nfrom pathlib import Path\n"
        f"gate=Path({str(gate)!r})\n"
        "(gate/Path.cwd().name).touch()\n"
        "deadline=time.monotonic()+15\n"
        "while len(list(gate.iterdir())) < 5:\n"
        "    assert time.monotonic()<deadline, 'workers did not overlap'\n"
        "    time.sleep(.05)\n"
    )
    commit(repo)
    processes = []
    with ExitStack() as stack:

        def spawn(argv, name):
            log = stack.enter_context((tmp_path / (name + ".log")).open("w"))
            process = subprocess.Popen(argv, env=dict(os.environ), stdout=log, stderr=log)
            processes.append(process)
            return process

        try:
            spawn(
                [
                    "redis-server",
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                    "--dir",
                    str(tmp_path),
                ],
                "redis",
            )
            connection = redis.Redis.from_url(settings.broker_url())

            def redis_ready():
                try:
                    return connection.ping()
                except redis.exceptions.ConnectionError:
                    return False

            wait_until(redis_ready)
            workers = [
                spawn(
                    [sys.executable, "-m", "orcan_executor.cli", "worker", "--slot", str(slot)],
                    f"worker-{slot}",
                )
                for slot in (1, 2, 3, 4, 5)
            ]
            wait_until(lambda: readiness.lanes()["default"]["ready_workers"] == 5)
            jobs = [engine.submit(repo, "HEAD", f"pool-{n}", "quality", [], 30) for n in range(5)]
            for job in jobs:
                cli.enqueue(job["id"])
            wait_until(lambda: all(store.get(job["id"])["status"] == "passed" for job in jobs))
            assert len(list(gate.iterdir())) == 5
            assert all(store.get(job["id"])["attempts"] == 1 for job in jobs)
            workers[0].terminate()
            workers[0].wait(timeout=10)
            lane = readiness.lanes()["default"]
            assert lane["ready_workers"] == 4 and lane["ready"]
            job = engine.submit(repo, "HEAD", "after-stop", "quality", [], 30)
            cli.enqueue(job["id"])
            wait_until(lambda: store.get(job["id"])["status"] == "passed")
            connection.close()
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
