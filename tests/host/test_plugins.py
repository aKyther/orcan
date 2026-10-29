import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker/rootfs/usr/local/lib"))
from orcan import plugins


def test_catalog_includes_ui_access_and_executor():
    values = plugins.catalog(ROOT / "plugins")
    assert {v["id"] for v in values} == {"ssh", "docker", "ttyd", "executor", "cockpit"}
    assert "--with-ssh" in next(v for v in values if v["id"] == "ssh")["flags"]


def test_disabled_executor_does_not_run_checks(monkeypatch):
    monkeypatch.setenv("ORCAN_REDIS_ENABLED", "0")
    execute = Mock()
    monkeypatch.setattr(plugins.subprocess, "run", execute)
    assert plugins.check("redis")["enabled"] is False
    execute.assert_not_called()


def test_cgroup_diagnostics_are_numeric_and_missing_metrics_are_safe(tmp_path):
    (tmp_path / "memory.current").write_text("75")
    (tmp_path / "memory.max").write_text("100")
    (tmp_path / "memory.events").write_text("max 3\noom_kill 0\n")
    result = plugins.resources(tmp_path, tmp_path)
    assert result["memory_percent"] == 75
    assert result["memory_events"] == {"max": 3, "oom_kill": 0}
    assert isinstance(result["disk_free_bytes"], int)
    assert plugins.resources(tmp_path / "missing", tmp_path)["disk_free_bytes"] >= 0


def test_declared_plugin_flags_have_real_handlers(monkeypatch, capsys):
    monkeypatch.setenv("ORCAN_ROOT", str(ROOT))
    assert plugins.main(["validate"]) == 0
    assert '"valid": true' in capsys.readouterr().out


def test_cockpit_check_contains_container_resource_diagnostics(monkeypatch):
    monkeypatch.setattr(plugins, "resources", lambda: {"memory_percent": 90.0})
    assert plugins.check("cockpit")["resources"] == {"memory_percent": 90.0}


@pytest.mark.integration
def test_tmux_history_limit_uses_configured_value_without_user_server(tmp_path):
    import os
    import subprocess
    from uuid import uuid4

    name = "orcan-history-fixture-" + uuid4().hex[:12]
    command = [
        "tmux",
        "-L",
        name,
        "-f",
        str(ROOT / "docker/rootfs/etc/tmux/options.conf"),
    ]
    try:
        subprocess.run(
            [*command, "new-session", "-d", "-s", "fixture", "sleep", "30"],
            env={**os.environ, "ORCAN_TMUX_HISTORY_LIMIT": "5000"},
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            [*command, "show-option", "-gv", "history-limit"],
            check=True,
            text=True,
            capture_output=True,
        )
        assert result.stdout.strip() == "5000"
    finally:
        subprocess.run([*command, "kill-server"], check=False, capture_output=True)
