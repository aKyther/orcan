"""Optional module lifecycle and generated agent contract; no live Docker changes."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_generated_guidance_enabled_and_disabled():
    # Load through the normal stdlib-only library namespace.
    import sys

    sys.path.insert(0, str(ROOT / "docker/rootfs/usr/local/lib"))
    from orcan.reconcile import executor_guidance

    assert "DISABLED" in executor_guidance(False)
    enabled = executor_guidance(True)
    for text in [
        "ENABLED",
        "doctor",
        "submit --repo",
        "listen --after",
        "next_offset",
        "1 hour",
        "exact SHA",
        "pytest",
        "sbt",
        "Gradle",
    ]:
        assert text in enabled


@pytest.mark.integration
@pytest.mark.parametrize("enabled", ["0", "1"])
@pytest.mark.parametrize("split", ["0", "1"])
def test_supervisor_only_installs_module_when_enabled(tmp_path, enabled, split):
    result = subprocess.run(
        ["bash", str(ROOT / "docker/rootfs/usr/local/bin/orcan-supervisord")],
        env={
            **os.environ,
            "ORCAN_REDIS_ENABLED": enabled,
            "ORCAN_EXECUTOR_SPLIT_LANES": split,
            "ORCAN_SUPERVISOR_DRY_RUN": "1",
            "ORCAN_SUPERVISOR_STATE_D": str(tmp_path),
            "ORCAN_SUPERVISOR_CONF_D": str(
                ROOT / "docker/rootfs/etc/orcan/supervisor.d"
            ),
            "ORCAN_SUPERVISOR_CONF_TEMPLATE": str(
                ROOT / "docker/rootfs/etc/orcan/supervisord.conf"
            ),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    programs = {p.stem for p in (tmp_path / "programs").glob("*.conf")}
    assert ("executor-worker" in programs) == (enabled == "1")
    assert ("executor-redis" in programs) == (enabled == "1")
    assert ("executor-web" in programs) == (enabled == "1")
    assert ("executor-notifications" in programs) == (enabled == "1")
    assert ("executor-worker-heavy" in programs) == (enabled == "1" and split == "1")
    assert ("executor-worker-light" in programs) == (enabled == "1" and split == "1")
    assert "keepalive" in programs


@pytest.mark.integration
def test_public_help_is_available_without_docker():
    result = subprocess.run(
        ["bash", str(ROOT / "bin/orcan"), "executor", "help"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    for text in [
        "submit",
        "doctor",
        "artifacts",
        "logs",
        "--with-redis",
        "No manual uv",
        "--notify-codex-thread",
        "deliveries",
        "stats",
    ]:
        assert text in result.stdout


@pytest.mark.integration
def test_dashboard_url_inherits_ttyd_host_and_has_own_port():
    script = 'source cli/lib/runtime.sh\norcan_ttyd_bind() { printf "100.64.0.9"; }\nORCAN_EXECUTOR_PORT=8877\norcan_executor_url\n'
    result = subprocess.run(
        ["bash", "-c", script], cwd=ROOT, check=False, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "http://100.64.0.9:8877"
