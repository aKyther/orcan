"""Configuration is explicit, validated and can be previewed without Docker."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from ._scripts_loader import load_script

profile = load_script("image-profile.py")
ROOT = Path(__file__).resolve().parents[2]


def test_tools_default_on_and_cli_selection_overrides_config():
    value = profile.resolve(
        {"build": {"agents": ["claude"], "tools": {"go": False}}}, "codex"
    )
    assert value == {"agents": ["codex"], "tools": {"go": False, "rust": True}}


@pytest.mark.parametrize(
    "build",
    [
        {"agents": []},
        {"agents": ["unknown"]},
        {"agents": ["codex"], "tools": {"rust": "false"}},
        {"agents": ["codex"], "tools": {"npm": False}},
        {"agents": ["codex"], "other": True},
    ],
)
def test_invalid_profile_is_rejected(build):
    with pytest.raises(ValueError):
        profile.resolve({"build": build})


@pytest.mark.integration
def test_build_plan_needs_no_docker_or_generated_env(tmp_path):
    config = tmp_path / "profile.json"
    config.write_text(
        json.dumps(
            {"build": {"agents": ["claude"], "tools": {"go": False, "rust": False}}}
        )
    )
    result = subprocess.run(
        ["bash", str(ROOT / "bin/orcan"), "build", "--plan"],
        env={**os.environ, "CONFIG": str(config)},
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "agents": ["claude"],
        "tools": {"go": False, "rust": False},
    }


@pytest.mark.integration
def test_profile_values_reach_the_builder(tmp_path):
    config = tmp_path / "profile.json"
    config.write_text(
        json.dumps(
            {"build": {"agents": ["claude"], "tools": {"go": False, "rust": False}}}
        )
    )
    script = """set -Eeuo pipefail
export ORCAN_ROOT="$PWD"
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }
orcan_require_env_for_build() { :; }
orcan_load_env() { :; }
orcan_runtime_warn_if_config_stale() { :; }
orcan_image_build_local() { printf '%s:%s:%s' "$1" "$INSTALL_GO" "$INSTALL_RUST"; }
orcan_cmd_build --agent codex
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={**os.environ, "CONFIG": str(config)},
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "codex:0:0"
