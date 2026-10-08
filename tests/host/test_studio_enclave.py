"""Contract tests for Studio's empty-Enclave configuration plan."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repository" / "studio-enclave.py"


def invoke(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=check,
        capture_output=True,
        text=True,
    )


def test_empty_enclave_plan_is_read_only(tmp_path: Path) -> None:
    config = tmp_path / "orcan.config.json"

    report = json.loads(invoke("plan", "--config", str(config)).stdout)

    assert report["ok"] is True
    assert report["plan"]["ready"] is True
    assert not config.exists()
    assert report["plan"]["changes"] == [
        f"create empty configuration {config}",
        "run orcan sync",
        "run orcan up with selected runtime options",
    ]


def test_empty_enclave_apply_requires_confirmation_and_never_overwrites(
    tmp_path: Path,
) -> None:
    config = tmp_path / "orcan.config.json"

    rejected = invoke("apply", "--config", str(config), check=False)
    assert rejected.returncode != 0
    assert not config.exists()

    report = json.loads(invoke("apply", "--config", str(config), "--yes").stdout)
    assert report["ok"] is True
    assert json.loads(config.read_text(encoding="utf-8")) == {"workspaces": []}

    existing = invoke("apply", "--config", str(config), "--yes", check=False)
    assert existing.returncode != 0
    assert json.loads(config.read_text(encoding="utf-8")) == {"workspaces": []}


def test_empty_enclave_rollback_only_removes_the_empty_studio_configuration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "orcan.config.json"
    invoke("apply", "--config", str(config), "--yes")

    report = json.loads(invoke("rollback", "--config", str(config), "--yes").stdout)
    assert report["ok"] is True
    assert not config.exists()

    config.write_text('{"workspaces":[{"name":"keep"}]}\n', encoding="utf-8")
    rejected = invoke("rollback", "--config", str(config), "--yes", check=False)
    assert rejected.returncode != 0
    assert (
        json.loads(config.read_text(encoding="utf-8"))["workspaces"][0]["name"]
        == "keep"
    )


def test_concurrent_apply_creates_configuration_exactly_once(tmp_path: Path) -> None:
    config = tmp_path / "orcan.config.json"
    with ThreadPoolExecutor(max_workers=4) as pool:
        attempts = list(
            pool.map(
                lambda _: invoke(
                    "apply", "--config", str(config), "--yes", check=False
                ),
                range(4),
            )
        )
    assert sum(result.returncode == 0 for result in attempts) == 1
    assert json.loads(config.read_text(encoding="utf-8")) == {"workspaces": []}
