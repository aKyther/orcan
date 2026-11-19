import json
from unittest.mock import Mock

import pytest

from orcan_executor import cli, engine, events, store


def terminal(repo):
    job = engine.submit(repo, "HEAD", "123", "selected", ["Test"], 30)
    return job, engine.run_job(job["id"])


def test_result_and_outbox_are_committed_together(repo):
    job, event = terminal(repo)
    assert store.get(job["id"])["status"] == "passed"
    assert json.loads(store.unpublished()[-1]["payload"]) == event


def test_publish_failure_keeps_durable_outbox_for_recovery(repo, monkeypatch):
    terminal(repo)
    connection = Mock()
    connection.xadd.side_effect = ConnectionError("synthetic broker outage")
    monkeypatch.setattr(events, "client", lambda: connection)
    with pytest.raises(ConnectionError):
        events.publish_pending()
    assert len(store.unpublished()) == 5
    connection.xadd.side_effect = None
    assert events.publish_pending() == 5
    assert store.unpublished() == []
    connection.expire.assert_called_with(events.stream_name(), 3600)
    assert events.publish_pending(replay=True) == 5


def test_subscription_uses_blocking_reads_and_resumes_exact_cursor(monkeypatch):
    connection = Mock()
    payload = {"job_id": "one", "status": "passed", "summary": {"tests": 1}}
    connection.xread.return_value = [("stream", [("10-0", {"payload": json.dumps(payload)})])]
    monkeypatch.setattr(events, "stream_client", lambda: connection)
    received = next(events.listen("9-0"))
    assert received["stream_id"] == "10-0"
    connection.xread.assert_called_once_with({events.stream_name(): "9-0"}, count=50, block=0)


def test_submission_survives_unavailable_broker(repo, monkeypatch, capsys):
    def offline(_):
        raise ConnectionError("broker with secret connection details")

    monkeypatch.setattr(cli, "enqueue", offline)
    assert cli.main(["submit", "--repo", str(repo), "--test", "Test"]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "queued_locally"
    assert "secret" not in json.dumps(response)
    assert store.get(response["job_id"])["status"] == "queued"


def test_wait_handles_completion_between_cursor_capture_and_subscription(repo, monkeypatch, capsys):
    job = engine.submit(repo, "HEAD", "123", "selected", ["Test"], 30)
    connection = Mock()

    def finish_between_reads(*args, **kwargs):
        engine.run_job(job["id"])
        return []

    connection.xrevrange.side_effect = finish_between_reads
    monkeypatch.setattr(events, "client", lambda: connection)
    assert cli.main(["wait", job["id"], "--timeout", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    connection.xread.assert_not_called()


def test_agent_stream_discards_queued_and_running_updates(monkeypatch):
    connection = Mock()
    connection.xread.return_value = [
        (
            "stream",
            [
                ("1-0", {"payload": json.dumps({"job_id": "one", "status": "queued"})}),
                ("2-0", {"payload": json.dumps({"job_id": "one", "status": "running"})}),
                (
                    "3-0",
                    {
                        "payload": json.dumps(
                            {"job_id": "one", "status": "passed", "summary": {"tests": 9}}
                        )
                    },
                ),
            ],
        )
    ]
    monkeypatch.setattr(events, "stream_client", lambda: connection)
    received = next(events.listen())
    assert received["status"] == "passed"
    assert received["stream_id"] == "3-0"
    connection.xread.assert_called_once()


def test_dashboard_instrumentation_is_not_sent_to_agent(monkeypatch):
    connection = Mock()
    payload = {
        "job_id": "one",
        "status": "passed",
        "summary": {"tests": 1, "metrics": {"log_bytes": 1000000}},
    }
    connection.xread.return_value = [("stream", [("10-0", {"payload": json.dumps(payload)})])]
    monkeypatch.setattr(events, "stream_client", lambda: connection)
    result = next(events.listen())
    assert result["summary"] == {"tests": 1}
    assert result["stream_id"] == "10-0"
