"""Measured history aggregations and local chart assets."""

from fastapi.testclient import TestClient

from orcan_executor import engine, store, web


def test_timeline_and_profile_usage_match_measured_totals(repo):
    job = engine.submit(repo, "HEAD", "build", "quality", [], 30)
    engine.run_job(job["id"])
    store.detail_read(job["id"], 100, 180)
    board = store.board(3)
    bucket = board["timeline"][0]
    stats = board["stats"]
    assert bucket["jobs"] == bucket["passed"] == 1
    assert bucket["log_bytes"] == stats["log_bytes"]
    assert (
        bucket["result_bytes"] + bucket["detail_wire_bytes"] == stats["return_with_details_bytes"]
    )
    assert stats["reduction_with_details_bytes"] == stats["log_bytes"] - stats["result_bytes"] - 180
    assert stats["child_cpu_seconds"] >= 0
    assert board["profile_usage"][0]["profile"] == "quality"
    assert board["timeline_bucket_seconds"] == 300
    assert store.board(720)["timeline_bucket_seconds"] == 86400


def test_chart_assets_are_local_and_have_accessible_data_table():
    client = TestClient(web.app)
    page = client.get("/").text
    asset = client.get("/assets/charts.js")
    assert asset.status_code == 200
    assert "getContext('2d')" in asset.text
    assert 'id="timeline-rows"' in page
    assert 'src="assets/charts.js"' in page
    assert "cdn." not in page
