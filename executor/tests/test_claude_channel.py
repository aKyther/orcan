"""Claude wire protocol and durable receipts, with fake sessions and isolated Redis only."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
from unittest.mock import Mock
from uuid import uuid4

import pytest

from orcan_executor import cli, engine, notifications, retention, store
from orcan_executor.claude_channel import Channel, binding, session_available

SESSION = "019bcf10-1000-7000-8000-000000000001"
OTHER = "019bcf10-1000-7000-8000-000000000002"


def completed(repo):
    job = engine.submit(repo, "HEAD", "claude-check", "quality", [], 30)
    engine.run_job(job["id"])
    return job


class Transport:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def send_notification(self, payload):
        self.messages.append(payload.model_dump())
        if self.fail:
            raise OSError("private transport credentials must never enter result")


def test_explicit_claude_destination_does_not_invoke_codex_or_auto_ack(repo, monkeypatch):
    job = completed(repo)
    lookup = Mock()
    monkeypatch.setattr(notifications.shutil, "which", lookup)
    with binding(SESSION):
        assert session_available(SESSION)
        notifications.register(job["id"], SESSION, "claude")
        assert notifications.deliver(job["id"]) == 0
        lookup.assert_not_called()
        channel, transport = Channel(SESSION), Transport()
        assert asyncio.run(channel.deliver(job["id"], transport))
        assert not asyncio.run(channel.deliver(job["id"], transport))
        assert len(transport.messages) == 1
        payload = transport.messages[0]
        assert payload["method"] == "notifications/claude/channel"
        text = payload["params"]["content"]
        assert job["sha"] in text and "success noise" not in text
        assert "--claude-session " + SESSION in text
        assert len(text.encode()) <= notifications.MESSAGE_BYTES
        assert notifications.listing(job["id"])[0]["status"] == "queued"
        assert not store.get(job["id"])["acknowledged"]
        notifications.acknowledge(job["id"], SESSION, "claude")
        assert notifications.listing(job["id"])[0]["status"] == "consumed"
        assert store.board()["notification_stats"]["consumed_bytes"] == len(text.encode())
    assert not session_available(SESSION)


def test_binding_is_exclusive_and_registration_requires_live_destination(repo):
    job = completed(repo)
    with pytest.raises(ValueError, match="not connected"):
        notifications.register(job["id"], SESSION, "claude")
    with binding(SESSION):
        with pytest.raises(BlockingIOError), binding(SESSION):
            pytest.fail("duplicate binding acquired")
        notifications.register(job["id"], SESSION, "claude")
    assert not asyncio.run(Channel(OTHER).deliver(job["id"], Transport()))
    with pytest.raises(ValueError, match="No notification"):
        notifications.acknowledge(job["id"], OTHER, "claude")


def test_adapter_identity_is_separate_even_with_same_uuid(repo):
    job = completed(repo)
    notifications.register(job["id"], SESSION)
    with binding(SESSION):
        notifications.register(job["id"], SESSION, "claude")
    rows = notifications.listing(job["id"])
    assert len(rows) == 2
    assert {row["adapter"] for row in rows} == {"codex", "claude"}
    assert len({row["thread_id"] for row in rows}) == 2


def test_uncertain_channel_write_is_never_retried_and_reason_is_sanitized(repo):
    job = completed(repo)
    with binding(SESSION):
        notifications.register(job["id"], SESSION, "claude")
        transport = Transport(fail=True)
        asyncio.run(Channel(SESSION).drain(transport))
        asyncio.run(Channel(SESSION).drain(transport))
    row = notifications.listing(job["id"])[0]
    assert row["status"] == "unknown" and len(transport.messages) == 1
    assert "private" not in json.dumps(row)


def test_interrupted_recovery_only_touches_owned_claude_session(repo):
    job = completed(repo)
    with binding(SESSION), binding(OTHER):
        notifications.register(job["id"], SESSION)
        notifications.register(job["id"], SESSION, "claude")
        notifications.register(job["id"], OTHER, "claude")
        with store.database() as db:
            db.execute("UPDATE deliveries SET status='sending'")
        Channel(SESSION).recover_interrupted()
    states = {row["thread_id"]: row["status"] for row in notifications.listing(job["id"])}
    assert states["claude:" + SESSION] == "unknown"
    assert states[SESSION] == states["claude:" + OTHER] == "sending"


def test_expired_and_running_jobs_cannot_be_sent(repo):
    job = engine.submit(repo, "HEAD", "running", "quality", [], 30)
    with binding(SESSION):
        notifications.register(job["id"], SESSION, "claude")
        transport = Transport()
        assert not asyncio.run(Channel(SESSION).deliver(job["id"], transport))
        engine.run_job(job["id"])
        with store.database() as db:
            db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
        assert retention.prune() == 1
        assert not asyncio.run(Channel(SESSION).deliver(job["id"], transport))
        assert not transport.messages


def test_cli_rejects_missing_claude_channel_before_pinning(repo, capsys):
    assert (
        cli.main(
            [
                "submit",
                "--repo",
                str(repo),
                "--profile",
                "quality",
                "--notify-claude-session",
                SESSION,
            ]
        )
        == 2
    )
    assert "not connected" in capsys.readouterr().out
    assert not store.listing()


def test_cli_exposes_explicit_claude_targets_and_rejects_ambiguous_target():
    args = cli.parser().parse_args(["notify", "job", "--claude-session", SESSION])
    assert args.claude_session == SESSION
    with pytest.raises(SystemExit):
        cli.parser().parse_args(
            ["notify", "job", "--claude-session", SESSION, "--codex-thread", OTHER]
        )


class WireClient:
    def __init__(self, process):
        self.process = process
        self.counter = 0
        self.notifications = []

    async def write(self, message):
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        await self.write({"id": request_id, "method": method, "params": params})
        while True:
            message = await self.read()
            if message.get("id") == request_id:
                return message["result"]
            self.notifications.append(message)

    async def read(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=30)
        assert line, "MCP server exited before responding"
        return json.loads(line)

    async def tool(self, name, **arguments):
        return await self.request("tools/call", {"name": name, "arguments": arguments})

    async def event(self):
        while True:
            message = self.notifications.pop(0) if self.notifications else await self.read()
            if message.get("method") == "notifications/claude/channel":
                return message


@pytest.mark.skipif(shutil.which("redis-server") is None, reason="Redis binary unavailable")
def test_real_stdio_mcp_handshake_two_sessions_push_and_explicit_receipt(
    repo, tmp_path, monkeypatch
):
    import redis

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv("ORCAN_EXECUTOR_BROKER_URL", f"redis://127.0.0.1:{port}/0")
    monkeypatch.setenv("ORCAN_EXECUTOR_QUEUE", "orcan-claude-test-" + uuid4().hex)
    jobs = [completed(repo), completed(repo)]
    log = (tmp_path / "redis.log").open("w")
    broker = subprocess.Popen(
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
        stdout=log,
        stderr=log,
    )

    async def exercise():
        processes = []
        connection = redis.Redis.from_url(os.environ["ORCAN_EXECUTOR_BROKER_URL"])
        try:
            for _ in range(100):
                try:
                    if connection.ping():
                        break
                except redis.exceptions.ConnectionError:
                    await asyncio.sleep(0.05)
            clients, sessions = [], []
            for index in range(2):
                stderr = (tmp_path / f"mcp-{index}.log").open("wb")
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "orcan_executor.cli",
                    "claude-channel",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=stderr,
                    env=dict(os.environ),
                )
                stderr.close()
                processes.append(process)
                client = WireClient(process)
                initialized = await client.request(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "orcan-fixture-no-model", "version": "1"},
                    },
                )
                assert initialized["capabilities"]["experimental"]["claude/channel"] == {}
                await client.write({"method": "notifications/initialized"})
                tool = await client.tool("executor_session")
                session = json.loads(tool["content"][0]["text"])["session_id"]
                clients.append(client)
                sessions.append(session)
            assert sessions[0] != sessions[1]
            for client, job in zip(clients, jobs, strict=True):
                result = await client.tool("executor_subscribe", job_id=job["id"])
                assert not result.get("isError")
            for client, session, job in zip(clients, sessions, jobs, strict=True):
                event = await client.event()
                assert event["params"]["meta"]["job_id"] == job["id"]
                assert job["sha"] in event["params"]["content"]
                assert "success noise" not in event["params"]["content"]
                assert len(event["params"]["content"].encode()) <= notifications.MESSAGE_BYTES
                assert notifications.listing(job["id"])[0]["status"] == "queued"
                assert not store.get(job["id"])["acknowledged"]
            wrong = await clients[0].tool("executor_ack", job_id=jobs[1]["id"])
            assert wrong.get("isError")
            for client, job in zip(clients, jobs, strict=True):
                receipt = await client.tool("executor_ack", job_id=job["id"])
                assert json.loads(receipt["content"][0]["text"])["consumed"]
                assert notifications.listing(job["id"])[0]["status"] == "consumed"
                assert store.get(job["id"])["acknowledged"]
        finally:
            connection.close()
            for process in processes:
                if process.returncode is None:
                    process.stdin.close()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except TimeoutError:
                        process.kill()
                        await process.wait()

    try:
        asyncio.run(exercise())
    finally:
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
            broker.wait()
        log.close()


def test_cancelled_transport_is_uncertain_not_replayed(repo):
    class Cancelled:
        async def send_notification(self, _payload):
            raise asyncio.CancelledError()

    job = completed(repo)
    with binding(SESSION):
        notifications.register(job["id"], SESSION, "claude")
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(Channel(SESSION).deliver(job["id"], Cancelled()))
        assert notifications.listing(job["id"])[0]["status"] == "unknown"
        assert not asyncio.run(Channel(SESSION).deliver(job["id"], Transport()))


def test_empty_claude_submit_destination_is_not_treated_as_no_opt_in(repo, capsys):
    assert (
        cli.main(
            ["submit", "--repo", str(repo), "--profile", "quality", "--notify-claude-session", ""]
        )
        == 2
    )
    assert not store.listing()
    capsys.readouterr()


def test_empty_claude_receipt_cannot_fall_back_to_generic_ack(repo, capsys):
    job = completed(repo)
    assert cli.main(["ack", job["id"], "--claude-session", ""]) == 2
    assert not store.get(job["id"])["acknowledged"]
    capsys.readouterr()


def test_codex_controller_restart_does_not_recover_claude_inflight_delivery(repo, monkeypatch):
    job = completed(repo)
    with binding(SESSION):
        notifications.register(job["id"], SESSION, "claude")
        with store.database() as db:
            db.execute("UPDATE deliveries SET status='sending'")
        connection = Mock()
        connection.xrevrange.return_value = []
        connection.xread.side_effect = KeyboardInterrupt
        monkeypatch.setattr(notifications.events, "stream_client", lambda: connection)
        monkeypatch.setattr(notifications.events, "publish_pending", Mock())
        with pytest.raises(KeyboardInterrupt):
            notifications.controller()
        assert notifications.listing(job["id"])[0]["status"] == "sending"
