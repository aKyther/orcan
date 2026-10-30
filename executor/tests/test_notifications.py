import json
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest

from orcan_executor import cli, engine, notifications, retention, store

THREAD = "019bcf10-1000-7000-8000-000000000001"


def job(repo, complete=True):
    value = engine.submit(repo, "HEAD", "notification", "selected", ["Test"], 30)
    if complete:
        engine.run_job(value["id"])
    return value


def fake_codex(tmp_path, monkeypatch, *, code=0, delay=0):
    output = tmp_path / "messages.jsonl"
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json,sys,time\n"
        "from pathlib import Path\n"
        f"with Path({str(output)!r}).open('a') as stream: stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"time.sleep({delay})\n"
        "print('do not retain provider diagnostics')\n"
        f"sys.exit({code})\n"
    )
    executable.chmod(0o755)
    # Test temp directories may be mounted noexec. Execute only our fixture via Python.
    original_popen = notifications.subprocess.Popen

    def fixture_process(arguments, **kwargs):
        if arguments[0] == str(executable):
            arguments = [sys.executable, *arguments]
        return original_popen(arguments, **kwargs)

    monkeypatch.setattr(notifications.subprocess, "Popen", fixture_process)
    monkeypatch.setattr(notifications.shutil, "which", lambda name: str(executable))
    return output


def test_explicit_subscription_waits_for_completion_and_never_auto_acks(
    repo, tmp_path, monkeypatch
):
    value = job(repo, complete=False)
    output = fake_codex(tmp_path, monkeypatch)
    notifications.register(value["id"], THREAD)
    assert notifications.deliver(value["id"]) == 0
    assert not output.exists()
    engine.run_job(value["id"])
    assert notifications.deliver(value["id"]) == 1
    arguments = json.loads(output.read_text())
    assert arguments[:4] == ["queue", "--thread", THREAD, "--message"]
    assert value["sha"] in arguments[4]
    assert "success noise" not in arguments[4]
    assert "--codex-thread " + THREAD in arguments[4]
    assert len(arguments[4].encode()) <= notifications.MESSAGE_BYTES
    assert notifications.listing(value["id"])[0]["status"] == "queued"
    stats = store.board()["notification_stats"]
    assert stats["accepted_bytes"] == len(arguments[4].encode())
    assert stats["consumed_bytes"] == 0
    assert stats["adapter_seconds"] > 0
    assert store.get(value["id"])["acknowledged"] is None
    assert notifications.deliver(value["id"]) == 0
    assert notifications.register(value["id"], THREAD)["status"] == "queued"
    notifications.acknowledge(value["id"], THREAD)
    notifications.acknowledge(value["id"], THREAD)
    assert notifications.listing(value["id"])[0]["status"] == "consumed"
    assert store.get(value["id"])["acknowledged"]
    assert store.board()["notification_stats"]["consumed_bytes"] == len(arguments[4].encode())


def test_no_subscription_never_invokes_codex(repo, monkeypatch):
    value = job(repo)
    lookup = Mock()
    monkeypatch.setattr(notifications.shutil, "which", lookup)
    assert notifications.deliver(value["id"]) == 0
    lookup.assert_not_called()


@pytest.mark.parametrize(
    "invalid", ["", "--all", "session name", "../session", "$(command)", "bad\nvalue"]
)
def test_only_canonical_uuid_is_accepted(invalid):
    with pytest.raises(ValueError, match="UUID"):
        notifications.thread_id(invalid)


def test_replayed_events_and_concurrent_controllers_do_not_duplicate(repo, tmp_path, monkeypatch):
    value = job(repo)
    output = fake_codex(tmp_path, monkeypatch, delay=0.1)
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(lambda _: notifications.register(value["id"], THREAD), range(16)))
        list(workers.map(lambda _: notifications.deliver(value["id"]), range(16)))
    assert len(output.read_text().splitlines()) == 1
    assert len(notifications.listing()) == 1


def test_nonzero_exit_is_uncertain_without_silent_retry(repo, tmp_path, monkeypatch):
    value = job(repo)
    output = fake_codex(tmp_path, monkeypatch, code=2)
    notifications.register(value["id"], THREAD)
    notifications.deliver(value["id"])
    record = notifications.listing()[0]
    assert record["status"] == "unknown"
    assert "provider diagnostics" not in json.dumps(record)
    notifications.deliver(value["id"])
    assert len(output.read_text().splitlines()) == 1


def test_timeout_is_bounded_and_does_not_retry(repo, tmp_path, monkeypatch):
    value = job(repo)
    fake_codex(tmp_path, monkeypatch, delay=10)
    monkeypatch.setattr(notifications, "TIMEOUT", 0.05)
    notifications.register(value["id"], THREAD)
    notifications.deliver(value["id"])
    assert notifications.listing()[0]["status"] == "unknown"
    assert notifications.deliver(value["id"]) == 0


def test_missing_codex_is_visible_and_not_reported_as_queued(repo, monkeypatch):
    value = job(repo)
    monkeypatch.setattr(notifications.shutil, "which", lambda _: None)
    notifications.register(value["id"], THREAD)
    notifications.deliver(value["id"])
    assert notifications.listing()[0]["status"] == "unavailable"
    assert store.board()["delivery_counts"] == {"unavailable": 1}


def test_receipt_cannot_claim_an_unregistered_or_unfinished_session(repo):
    value = job(repo, complete=False)
    notifications.register(value["id"], THREAD)
    with pytest.raises(ValueError, match="completed"):
        notifications.acknowledge(value["id"], THREAD)
    engine.run_job(value["id"])
    with pytest.raises(ValueError, match="registered"):
        notifications.acknowledge(value["id"], str(uuid4()))


def test_failure_payload_unicode_control_chars_and_huge_traces_stay_bounded():
    value = {
        "id": "a" * 32,
        "sha": "f" * 40,
        "task": "💥" * 160,
        "profile": "selected",
        "status": "failed",
        "summary": {
            "problems": [{"test": "\x00" * 200, "message": "\x00💥" * 4000}] * 30,
            "log_tail": "\x00" * 20000,
            "error": "💥" * 20000,
            "omitted_failures": 27,
        },
    }
    text = notifications.message(value)
    assert len(text.encode()) <= notifications.MESSAGE_BYTES
    parsed = json.loads(text.split("\n", 1)[1])
    assert parsed["sha"] == value["sha"]
    assert parsed["status"] == "failed"
    assert parsed["diagnostics"]["omitted_failures"] >= 27


def test_controller_startup_recovers_trimmed_events_but_not_uncertain_attempts(
    repo, tmp_path, monkeypatch
):
    value = job(repo)
    output = fake_codex(tmp_path, monkeypatch)
    notifications.register(value["id"], THREAD)
    second = str(uuid4())
    notifications.register(value["id"], second)
    with store.database() as db:
        db.execute("UPDATE deliveries SET status='sending' WHERE thread_id=?", (second,))
    connection = Mock()
    connection.xrevrange.return_value = [("10-0", {})]
    connection.xread.side_effect = KeyboardInterrupt
    monkeypatch.setattr(notifications.events, "stream_client", lambda: connection)
    monkeypatch.setattr(notifications.events, "publish_pending", Mock())
    with pytest.raises(KeyboardInterrupt):
        notifications.controller()
    assert len(output.read_text().splitlines()) == 1
    assert {v["status"] for v in notifications.listing()} == {"queued", "unknown"}
    connection.xread.assert_called_once_with(
        {notifications.stream_name(): "10-0"}, count=50, block=0
    )
    connection.close.assert_called_once()


def test_reused_job_can_notify_multiple_sessions_and_expiry_removes_subscriptions(repo):
    value = job(repo)
    for _ in range(16):
        notifications.register(value["id"], str(uuid4()))
    with pytest.raises(ValueError, match="16"):
        notifications.register(value["id"], str(uuid4()))
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (value["id"],))
    assert retention.prune() == 1
    assert notifications.listing() == []


@pytest.mark.parametrize("destination", ["invalid", ""])
def test_bad_submit_destination_does_not_pin_a_job(repo, monkeypatch, destination):
    monkeypatch.setenv("ORCAN_REDIS_ENABLED", "1")
    assert (
        cli.main(
            ["submit", "--repo", str(repo), "--test", "Test", "--notify-codex-thread", destination]
        )
        == 1
    )
    assert store.listing() == []
    assert engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs") == ""


def test_cli_registers_destination_before_enqueue_and_reuse_adds_subscriber(
    repo, monkeypatch, capsys
):
    monkeypatch.setenv("ORCAN_REDIS_ENABLED", "1")
    observed = []

    def enqueue(job_id):
        observed.append(notifications.listing(job_id))

    monkeypatch.setattr(cli, "enqueue", enqueue)
    monkeypatch.setattr(cli.events, "publish_pending", lambda: None)
    assert (
        cli.main(
            [
                "submit",
                "--repo",
                str(repo),
                "--test",
                "Test",
                "--reuse",
                "--notify-codex-thread",
                THREAD,
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    second_thread = str(uuid4())
    assert (
        cli.main(
            [
                "submit",
                "--repo",
                str(repo),
                "--test",
                "Test",
                "--reuse",
                "--notify-codex-thread",
                second_thread,
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert first["job_id"] == second["job_id"]
    assert len(observed[0]) == 1 and len(observed[1]) == 2


def test_bounded_log_wire_accounting_matches_the_emitted_jsonl(repo, monkeypatch, capsys):
    value = job(repo)
    monkeypatch.setattr(cli.events, "publish_pending", lambda: None)
    assert cli.main(["logs", value["id"], "--limit", "100"]) == 0
    output = capsys.readouterr().out
    stats = store.board()["stats"]
    assert stats["detail_bytes"] == 100
    assert stats["detail_wire_bytes"] == len(output.encode())
    assert stats["detail_wire_bytes"] > stats["detail_bytes"]


def test_broker_reconnect_recovers_pending_jobs_without_resending_accepted_messages(
    repo, tmp_path, monkeypatch
):
    from redis.exceptions import ConnectionError

    value = job(repo)
    output = fake_codex(tmp_path, monkeypatch)
    notifications.register(value["id"], THREAD)
    broken = Mock()
    broken.xrevrange.side_effect = ConnectionError("private broker details")
    live = Mock()
    live.xrevrange.return_value = []
    live.xread.side_effect = KeyboardInterrupt
    connections = iter([broken, live])
    monkeypatch.setattr(notifications.events, "stream_client", lambda: next(connections))
    monkeypatch.setattr(notifications.events, "publish_pending", Mock())
    monkeypatch.setattr(notifications.time, "sleep", Mock())
    with pytest.raises(KeyboardInterrupt):
        notifications.controller()
    assert len(output.read_text().splitlines()) == 1
    assert notifications.listing()[0]["status"] == "queued"
    broken.close.assert_called_once()
    live.close.assert_called_once()
