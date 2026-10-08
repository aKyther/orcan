"""Contract tests for Studio's empty-Enclave configuration plan."""

from __future__ import annotations

import json
import os
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


def test_custom_resources_and_port_are_saved_and_rollback_matches(
    tmp_path: Path,
) -> None:
    config = tmp_path / "orcan.config.json"
    options = (
        "--config",
        str(config),
        "--cpus",
        "1.5",
        "--memory-gb",
        "8",
        "--ttyd-host-port",
        "17682",
    )
    invoke("apply", *options, "--yes")
    assert json.loads(config.read_text()) == {
        "workspaces": [],
        "resources": {"cpus": 1.5, "memory": "8g"},
        "ttyd": {"host_port": 17682},
    }
    invoke("rollback", *options, "--yes")
    assert not config.exists()


def test_invalid_resources_do_not_create_configuration(tmp_path: Path) -> None:
    config = tmp_path / "orcan.config.json"
    for args in [
        ("--cpus", "nan"),
        ("--cpus", "0"),
        ("--memory-gb", "0"),
        ("--ttyd-host-port", "65536"),
    ]:
        result = invoke("apply", "--config", str(config), *args, "--yes", check=False)
        assert result.returncode != 0
        assert not config.exists()


def test_empty_container_first_sync_honors_selected_limits_and_port(
    tmp_path: Path,
) -> None:
    config = tmp_path / "orcan.config.json"
    invoke(
        "apply",
        "--config",
        str(config),
        "--cpus",
        "1.5",
        "--memory-gb",
        "8",
        "--ttyd-host-port",
        "17682",
        "--yes",
    )
    (tmp_path / ".env.example").write_text(
        "CPUS=99\nMEMORY=99g\nTTYD_HOST_PORT=9999\n", encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/repository/apply-config.py"),
            "--root",
            str(tmp_path),
            "--config",
            str(config),
        ],
        env={
            **os.environ,
            "ORCAN_STUDIO_CREATE_RUNTIME": "1",
            "ORCAN_PROJECTS_ROOT": str(tmp_path / "sandbox"),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    runtime = json.loads((tmp_path / "mounts/runtime-config.json").read_text())
    assert runtime["workspaces"] == []
    assert runtime["resources"]["cpus"] == 1.5
    assert runtime["resources"]["memory"] == "8g"
    generated = (tmp_path / ".env").read_text()
    assert "CPUS=1.5\n" in generated
    assert "MEMORY=8g\n" in generated
    assert "TTYD_HOST_PORT=17682\n" in generated
