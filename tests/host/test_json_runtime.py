"""JSON configuration must work without dotenv files or executable shell state."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def setup_home(tmp_path):
    home = tmp_path / "config"
    home.mkdir()
    config = {
        "workspaces": [],
        "data_root": str(tmp_path / "data"),
        "projects_root": str(tmp_path / "projects"),
        "resources": {"cpus": 3, "memory": "6g"},
        "ttyd": {"host_port": 17681, "renderer": "canvas"},
        "executor": {"workers": 5, "max_running": 5},
        "registry": {"host": "registry.example.test", "repository": "team/orcan"},
    }
    (home / "orcan.config.json").write_text(json.dumps(config))
    env = {
        **os.environ, "ORCAN_HOME": str(home), "ORCAN_ROOT": str(ROOT),
        "ORCAN_CONFIG_FILE": str(home / "orcan.config.json"),
        "ORCAN_RUNTIME_DIR": str(home / "mounts"),
        "ORCAN_DATA": str(tmp_path / "ignored-data"),
        "ORCAN_PROJECTS_ROOT": str(tmp_path / "ignored-projects"),
        "CPUS": "99", "TTYD_HOST_PORT": "9999",
    }
    return home, config, env


def run(script, env):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=ROOT, env=env, text=True, capture_output=True)


def test_sync_generates_json_without_creating_dotenv(tmp_path):
    home, config, env = setup_home(tmp_path)
    result = run('bash scripts/repository/sync-runtime.sh', env)
    assert result.returncode == 0, result.stderr
    assert not (home / ".env").exists()
    assert not (home / ".env.example").exists()
    runtime = json.loads((home / "mounts/runtime-config.json").read_text())
    assert runtime["executor"]["workers"] == 5
    assert runtime["resources"]["cpus"] == 3
    assert (Path(config["projects_root"]) / ".worktrees").is_dir()
    assert Path(config["data_root"]).is_dir()
    assert not Path(env["ORCAN_DATA"]).exists()
    assert (home / "workspaces/index.json").is_file()
    assert run('bash scripts/repository/require-generated.sh', env).returncode == 0


def test_legacy_dotenv_is_neither_executed_nor_overwritten(tmp_path):
    home, config, env = setup_home(tmp_path)
    marker = tmp_path / "executed"
    legacy = f'CPUS=91\ntouch {marker}\n'
    (home / ".env").write_text(legacy)
    result = run('bash scripts/repository/sync-runtime.sh', env)
    assert result.returncode == 0, result.stderr
    assert "legacy .env is ignored" in result.stderr
    assert not marker.exists()
    assert (home / ".env").read_text() == legacy
    result = run('source cli/lib/common.sh; orcan_load_config; printf "%s|%s|%s" "$CPUS" "$TTYD_HOST_PORT" "$ORCAN_EXECUTOR_WORKERS"', env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "3|17681|5"
    assert not marker.exists()


def test_compose_disables_implicit_dotenv_and_receives_json_values(tmp_path):
    home, config, env = setup_home(tmp_path)
    result = run('''
source cli/lib/common.sh
docker() {
    printf '%s|%s|%s|%s|%s\\n' "$CPUS" "$MEMORY" "$TTYD_HOST_PORT" "$ORCAN_EXECUTOR_WORKERS" "$COMPOSE_DISABLE_ENV_FILE"
    printf '%s\\n' "$*"
}
orcan_compose_build config
''', env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("3|6g|17681|5|1\n")
    assert "--env-file /dev/null" in result.stdout
    assert str(home / ".env") not in result.stdout


def test_json_values_cannot_execute_shell_commands(tmp_path):
    home, config, env = setup_home(tmp_path)
    marker = tmp_path / "executed"
    value = f"font ' $(touch {marker}) `touch {marker}` \\\nnext"
    config["ttyd"]["font_family"] = value
    (home / "orcan.config.json").write_text(json.dumps(config))
    result = run('source cli/lib/common.sh; orcan_load_config; printf "%s" "$TTYD_FONT_FAMILY"', env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == value
    assert not marker.exists()


def test_launch_record_round_trip_and_invalid_keys(tmp_path):
    home, config, env = setup_home(tmp_path)
    result = run('''
source cli/lib/common.sh
orcan_write_last_up 1 0 1 0 0 'network with spaces' 0 '' 0 '' 1
saved="$(orcan_last_up_file)"
eval "$(orcan_host_python "$ORCAN_SCRIPTS/runtime-settings.py" --state-read "$saved")"
printf '%s|%s' "$NETWORK_NAME" "$WITH_REDIS"
''', env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "network with spaces|1"
    saved = home / "mounts/last-up.json"
    assert json.loads(saved.read_text())["WITH_DOCKER"] == "1"
    saved.write_text('{"PATH": "/untrusted"}')
    result = run('python3 scripts/repository/runtime-settings.py --state-read "$ORCAN_HOME/mounts/last-up.json"', env)
    assert result.returncode != 0
    assert "invalid launch state" in result.stderr


def test_invalid_json_does_not_start_compose(tmp_path):
    home, config, env = setup_home(tmp_path)
    config["executor"]["workers"] = 99
    (home / "orcan.config.json").write_text(json.dumps(config))
    result = run('source cli/lib/common.sh; docker() { echo STARTED; }; orcan_compose_build config', env)
    assert result.returncode != 0
    assert "STARTED" not in result.stdout
