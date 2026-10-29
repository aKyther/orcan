"""One list format for tools/agents, versioned sources and bounded preview."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from ._scripts_loader import load_script

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker/rootfs/usr/local/lib"))
from orcan import install_agent

profile = load_script("image-profile.py")


def test_uniform_lists_defaults_and_version_selection():
    value = profile.resolve(
        {
            "build": {
                "agents": [{"name": "codex", "version": "0.100.0"}],
                "tools": [{"name": "rust", "version": "1-bookworm"}],
            }
        }
    )
    assert value["agents"][0]["version"] == "0.100.0"
    assert value["agents"][0]["source"]["package"] == "@openai/codex"
    assert value["tools"] == [{"name": "rust", "image": "rust:1-bookworm"}]
    assert profile.resolve({"build": {"agents": ["codex"], "tools": []}})["tools"] == []
    assert profile.resolve({"build": {"agents": ["codex"]}})["tools"] == []
    assert len(profile.resolve({}, "codex")["tools"]) == 2
    assert profile.resolve({"build": value}) == value


def test_exact_native_sources_and_custom_checksums():
    native = profile.resolve(
        {
            "build": {
                "agents": [
                    {"name": "claude", "version": "2.1.0"},
                    {"name": "cursor", "version": "2026.10.22-27dcf5f"},
                ]
            }
        }
    )
    assert native["agents"][0]["version"] == "2.1.0"
    assert native["agents"][1]["source"]["type"] == "archive"
    assert "{arch}" in native["agents"][1]["source"]["url"]
    assert profile.resolve({"build": native}) == native
    custom = {
        "name": "claude",
        "source": {"url": "https://example.invalid/install.sh", "sha256": "0" * 64},
    }
    assert (
        profile.resolve({"build": {"agents": [custom]}})["agents"][0]["source"][
            "sha256"
        ]
        == "0" * 64
    )


@pytest.mark.parametrize(
    "build",
    [
        {"agents": []},
        {"agents": ["unknown"]},
        {"agents": ["codex"], "tools": {"rust": False}},
        {"agents": ["codex"], "tools": ["npm"]},
        {"agents": [{"name": "codex", "version": "latest; echo secret"}]},
        {
            "agents": [
                {"name": "claude", "source": {"url": "https://example.invalid/a"}}
            ]
        },
        {"agents": ["codex"], "tools": [{"name": "rust", "image": "rust:1;id"}]},
        {
            "agents": [
                {
                    "name": "claude",
                    "source": {
                        "url": "https://user:password@example.invalid/install",
                        "sha256": "0" * 64,
                    },
                }
            ]
        },
    ],
)
def test_invalid_profile_rejected(build):
    with pytest.raises(ValueError):
        profile.resolve({"build": build})


def test_checksum_failure_never_executes_source(tmp_path, monkeypatch):
    response = io.BytesIO(b"installer")
    response.url = "https://example.invalid/install"
    monkeypatch.setattr(
        install_agent.urllib.request, "urlopen", lambda *a, **k: response
    )
    execute = Mock()
    monkeypatch.setattr(install_agent.subprocess, "run", execute)
    with pytest.raises(ValueError, match="checksum"):
        install_agent.install(
            profile.resolve(
                {
                    "build": {
                        "agents": [
                            {
                                "name": "claude",
                                "source": {"url": response.url, "sha256": "0" * 64},
                            }
                        ]
                    }
                }
            )["agents"][0],
            tmp_path,
        )
    execute.assert_not_called()


def test_npm_uses_exact_argv_without_shell(tmp_path, monkeypatch):
    command = Mock()
    monkeypatch.setattr(install_agent.subprocess, "run", command)
    entry = profile.resolve(
        {
            "build": {
                "agents": [
                    {
                        "name": "codex",
                        "version": "0.100.0",
                        "source": {
                            "package": "@team/codex",
                            "registry": "https://registry.example.invalid",
                        },
                    }
                ]
            }
        }
    )["agents"][0]
    install_agent.install(entry, tmp_path)
    argv = command.call_args.args[0]
    assert "@team/codex@0.100.0" in argv and "--registry" in argv
    assert "shell" not in command.call_args.kwargs


@pytest.mark.integration
def test_config_flag_preview_and_build_forwarding(tmp_path):
    config = tmp_path / "image.json"
    config.write_text(
        json.dumps(
            {
                "build": {
                    "agents": [{"name": "claude", "version": "stable"}],
                    "tools": [{"name": "rust", "image": "rust:1-bookworm"}],
                }
            }
        )
    )
    result = subprocess.run(
        ["bash", str(ROOT / "bin/orcan"), "build", "--plan", "--config", str(config)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["agents"][0]["version"] == "stable"
    script = """set -Eeuo pipefail
export ORCAN_ROOT="$PWD"
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }
orcan_require_env_for_build() { :; }
orcan_load_env() { :; }
orcan_runtime_warn_if_config_stale() { :; }
orcan_image_build_local() { printf '%s:%s:%s:%s' "$1" "$INSTALL_GO" "$INSTALL_RUST" "$RUST_IMAGE"; }
orcan_cmd_build --agent codex --config "$PROFILE"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={**os.environ, "PROFILE": str(config)},
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "codex:0:1:rust:1-bookworm"


def test_native_archive_installs_expected_version_without_shell(tmp_path, monkeypatch):
    import shutil
    import tarfile

    archive = tmp_path / "package.tar.gz"
    program = tmp_path / "cursor-agent"
    program.write_text("#!/bin/sh\necho fixture\n")
    program.chmod(0o755)
    with tarfile.open(archive, "w:gz") as package:
        package.add(program, arcname="package/cursor-agent")
    monkeypatch.setattr(
        install_agent,
        "download",
        lambda url, target, checksum: shutil.copyfile(archive, target),
    )
    home = tmp_path / "home"
    home.mkdir()
    entry = profile.resolve(
        {
            "build": {
                "agents": [{"name": "cursor", "version": "2026.10.22-27dcf5f"}],
                "tools": [],
            }
        }
    )["agents"][0]
    install_agent.install(entry, home)
    assert (home / ".local/bin/agent").is_symlink()
    assert (home / ".local/bin/agent").read_text() == "#!/bin/sh\necho fixture\n"
