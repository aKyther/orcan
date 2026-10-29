import asyncio
import json
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from orcan_executor import engine, store, web


def test_empty_dashboard_and_read_only_api():
    client = TestClient(web.app)
    assert client.get("/").status_code == 200
    assert "EventSource" in client.get("/").text
    board = client.get("/api/board").json()
    assert board["counts"]["queued"] == 0
    assert board["jobs"] == []
    assert client.post("/api/board").status_code == 405
    assert client.get("/api/jobs/missing/report").status_code == 404


def test_dashboard_counts_and_report_access(repo):
    client = TestClient(web.app)
    queued = engine.submit(repo, "HEAD", "queued", "selected", ["Test"], 30)
    finished = engine.submit(repo, "HEAD", "done", "selected", ["Test"], 30)
    engine.run_job(finished["id"])
    board = client.get("/api/board").json()
    assert board["counts"]["queued"] == 1
    assert board["counts"]["passed"] == 1
    assert len(board["jobs"]) == 2
    assert client.get("/api/jobs/" + queued["id"] + "/report").status_code == 404
    response = client.get("/api/jobs/" + finished["id"] + "/report")
    assert response.status_code == 200
    assert response.json()["sha"] == finished["sha"]
    assert client.get("/api/jobs/" + finished["id"] + "/log").status_code == 200


def test_sse_snapshot_and_blocking_stream_refresh(monkeypatch):
    async def check():
        connection = AsyncMock()
        connection.xrevrange.return_value = [("1-0", {})]
        connection.xread.return_value = [("stream", [("2-0", {"payload": "{}"})])]
        monkeypatch.setattr(
            web.redis,
            "Redis",
            type("Fake", (), {"from_url": staticmethod(lambda *a, **k: connection)}),
        )
        request = AsyncMock()
        request.headers = {}
        request.is_disconnected.return_value = False
        stream = web.frames(request)
        first = await anext(stream)
        second = await anext(stream)
        assert "id: 1-0" in first
        assert "id: 2-0" in second
        connection.xread.assert_awaited_once_with({web.stream_name(): "1-0"}, count=50, block=15000)
        payload = json.loads(first.split("data: ", 1)[1])
        assert payload["redis_online"]
        await stream.aclose()
        connection.aclose.assert_awaited_once()

    asyncio.run(check())


def test_snapshot_has_lifecycle_events(repo):
    job = engine.submit(repo, "HEAD", "lifecycle", "selected", ["Test"], 30)
    engine.run_job(job["id"])
    assert [json.loads(e["payload"])["kind"] for e in store.unpublished()] == [
        "queued",
        "running",
        "step",
        "step",
        "finished",
    ]


def test_dashboard_uses_same_optional_auth_as_terminal(monkeypatch):
    monkeypatch.setenv("TTYD_CREDENTIAL", "fixture:fixture-password")
    client = TestClient(web.app)
    assert client.get("/").status_code == 401
    assert client.get("/api/board").status_code == 401
    assert client.get("/api/board", auth=("fixture", "wrong")).status_code == 401
    assert client.get("/api/board", auth=("fixture", "fixture-password")).status_code == 200
    assert client.get("/api/board", headers={"Authorization": "Basic invalid"}).status_code == 401


def test_dashboard_exposes_measurements_and_contextual_hints():
    client = TestClient(web.app)
    html = client.get("/").text
    for text in [
        "Czy ten flow pomaga?",
        "reduction",
        "Tokeny",
        "orcan-executor help",
        "CPU Pythona",
    ]:
        assert text in html
    board = client.get("/api/board").json()
    assert board["stats"]["completed_jobs"] == 0
    assert board["stats"]["reduction_percent"] is None
    assert board["retention_seconds"] == 3600
