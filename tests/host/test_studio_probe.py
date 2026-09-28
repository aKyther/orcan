"""Contract tests for the read-only Orcan Studio Sandbox probe."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_probe_emits_only_the_versioned_json_contract(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "ORCAN_HOME": str(tmp_path / "home"),
        "ORCAN_DATA": str(tmp_path / "data"),
        "ORCAN_STUDIO_DOCKER": "definitely-not-docker",
    }
    result = subprocess.run(
        ["./bin/orcan", "studio", "probe", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["protocol"] == {
        "name": "orcan-studio",
        "version": 1,
        "methods": ["probe"],
    }
    assert report["runtime"]["docker"]["container"]["state"] == "unavailable"
    assert report["capabilities"]["managed_projects"]


def test_probe_requires_the_json_protocol_flag() -> None:
    result = subprocess.run(
        ["./bin/orcan", "studio", "probe"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "usage: orcan studio probe --json" in result.stderr
