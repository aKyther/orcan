"""Docker/Git command boundaries without a daemon or subprocess execution."""

import json
from pathlib import Path

from ._scripts_loader import load_script

probe = load_script("studio-probe.py")
worktree = load_script("studio-worktree.py")


def test_distribution_stage_repeats_agent_arguments_and_labels():
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    distribution = dockerfile.split("FROM scratch", 1)[1]
    for name in ("cursor", "claude", "codex", "gemini", "copilot"):
        assert f"ARG INSTALL_{name.upper()}=1" in distribution
        assert f'io.orcan.agent.{name}="${{INSTALL_{name.upper()}}}"' in distribution


def test_labelled_image_never_starts_a_manifest_container(monkeypatch):
    calls = []
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/docker")

    def output(docker, *args, **kwargs):
        calls.append(args)
        if args[:2] == ("image", "inspect"):
            return json.dumps(
                {
                    f"io.orcan.agent.{name}": "1" if name == "codex" else "false"
                    for name in ("cursor", "claude", "codex", "gemini", "copilot")
                }
            )
        return "running" if args[0] == "inspect" else ""

    monkeypatch.setattr(probe, "docker_output", output)
    report = probe.docker_probe("docker", "orcan:latest", "dev")
    assert report["agents"]["codex"] is True
    assert report["agents"]["claude"] is False
    assert not any(args[0] == "run" for args in calls)


def test_legacy_numeric_agent_manifest_is_supported(monkeypatch):
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/docker")

    def output(docker, *args, **kwargs):
        if args[0] == "run":
            return '{"agents":{"codex":1,"claude":0}}'
        return "{}"

    monkeypatch.setattr(probe, "docker_output", output)
    assert probe.docker_probe("docker", "old", "dev")["agents"] == {
        "codex": True,
        "claude": False,
    }


def test_every_docker_request_has_timeout_and_handles_failure(monkeypatch):
    def run(command, **kwargs):
        assert kwargs["timeout"] == 5
        raise probe.subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(probe.subprocess, "run", run)
    assert probe.docker_output("docker", "inspect", "dev") is None


def test_worktree_git_timeout_is_unknown(monkeypatch, tmp_path):
    def run(command, **kwargs):
        assert kwargs["timeout"] == 3
        raise OSError("unavailable")

    monkeypatch.setattr(worktree.subprocess, "run", run)
    assert worktree.run(tmp_path, "status") is None
