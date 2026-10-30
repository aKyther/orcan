"""Sanitized broker diagnostics and durable communication measurements."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
import redis
from fastapi.testclient import TestClient

from orcan_executor import diagnostics, events, store, web


def test_redis_sample_whitelists_fields_and_reports_pressure(monkeypatch):
    connection = Mock()
    connection.info.return_value = {
        "used_memory": 90,
        "maxmemory": 100,
        "evicted_keys": 2,
        "aof_enabled": 1,
        "aof_last_write_status": "err",
        "config_file": "/private/secret",
        "client_name": "private-token",
    }
    monkeypatch.setattr(events, "client", lambda: connection)
    monkeypatch.setattr(
        diagnostics,
        "lanes",
        lambda: {"heavy": {"configured": True, "ready": False, "last_heartbeat": None}},
    )
    value = diagnostics.sample()
    assert value["status"] == "online"
    assert value["redis"]["memory_percent"] == 90
    assert {"redis_memory_pressure", "aof_write_error", "worker_unavailable"} <= set(
        value["warnings"]
    )
    assert "private" not in json.dumps(value)
    connection.close.assert_called_once()


def test_offline_errors_and_invalid_broker_details_are_not_exposed(monkeypatch):
    def unavailable():
        raise ValueError("redis://secret:password@private-host")

    monkeypatch.setattr(events, "client", unavailable)
    value = diagnostics.sample()
    assert value["status"] == "offline"
    assert "secret" not in json.dumps(value)


def test_health_is_coalesced_and_stale_samples_are_visible(monkeypatch):
    for _ in range(3):
        store.save_health({"sampled_at": "2000-01-01T00:00:00+00:00", "status": "online"})
    assert len(store.unpublished()) == 1
    snapshot = store.diagnostics_snapshot()
    assert snapshot["health_stale"]
    assert snapshot["health_age_seconds"] > 90

    def no_network():
        pytest.fail("Board must read cached health, not poll Redis")

    monkeypatch.setattr(events, "client", no_network)
    board = TestClient(web.app).get("/api/board").json()
    assert board["communication"]["health_stale"]


def test_partial_stream_failure_preserves_unsent_outbox_and_counts_attempts(monkeypatch):
    with store.database() as db:
        store.event(db, {"kind": "fixture", "value": 1})
        store.event(db, {"kind": "fixture", "value": 2})
    connection = Mock()
    connection.xadd.side_effect = ["1-0", ConnectionError("secret transport error")]
    monkeypatch.setattr(events, "client", lambda: connection)
    with pytest.raises(ConnectionError):
        events.publish_pending()
    snapshot = store.diagnostics_snapshot()
    assert snapshot["pending_events"] == 1
    assert snapshot["counters"]["stream_failures"]["count"] == 1
    assert snapshot["counters"]["stream_published"]["count"] == 1
    assert "secret" not in json.dumps(snapshot)
    connection.xadd.side_effect = None
    assert events.publish_pending() == 1
    assert store.diagnostics_snapshot()["counters"]["stream_published"]["count"] == 2


@pytest.mark.skipif(shutil.which("redis-server") is None, reason="Redis binary unavailable")
def test_isolated_redis_aof_restart_preserves_stream_and_health(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="orcan-rd-") as directory:
        socket = Path(directory) / "redis.sock"

        def connect():
            return redis.Redis(
                unix_socket_path=str(socket),
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )

        def start():
            process = subprocess.Popen(
                [
                    "redis-server",
                    "--port",
                    "0",
                    "--unixsocket",
                    str(socket),
                    "--dir",
                    directory,
                    "--appendonly",
                    "yes",
                    "--appendfsync",
                    "everysec",
                    "--save",
                    "",
                    "--maxmemory",
                    "32mb",
                    "--maxmemory-policy",
                    "noeviction",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    with connect() as connection:
                        if connection.ping():
                            return process
                except redis.RedisError:
                    pass
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            process.kill()
            process.wait(timeout=5)
            pytest.fail("Isolated Redis did not start")

        process = start()
        monkeypatch.setattr(events, "client", connect)
        try:
            with store.database() as db:
                store.event(db, {"kind": "fixture"})
            assert events.publish_pending() == 1
            health = diagnostics.sample()
            assert health["status"] == "online"
            assert health["redis"]["aof_enabled"] == 1
            assert health["redis"]["maxmemory_bytes"] == 32 * 1024 * 1024
            process.terminate()  # Graceful restart, not a claim of crash durability.
            process.wait(timeout=5)
            process = start()
            with connect() as connection:
                assert connection.xlen(events.stream_name()) == 1
            assert diagnostics.sample()["status"] == "online"
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
