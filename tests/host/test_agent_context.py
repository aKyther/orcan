"""Selected clients own only their own generated context and global settings."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker/rootfs/usr/local/lib"))
from orcan import agent_context
from orcan.reconcile import apply_workspaces
from orcan.workspaces import format_status, project_needs_init

TEMPLATES = ROOT / "docker/rootfs/opt/cursor-defaults/templates/workspace"


def apply(tmp_path, selected):
    root = tmp_path / "workspaces/demo"
    cfg = {"workspaces": [{"name": "demo", "root": str(root), "projects": []}]}
    apply_workspaces(cfg, TEMPLATES, tmp_path / "workspaces", agents=set(selected))
    return root


@pytest.mark.parametrize(
    "selected",
    [
        [],
        ["codex"],
        ["claude"],
        ["cursor"],
        ["cursor", "claude"],
        ["gemini", "copilot"],
    ],
)
def test_workspace_matrix(tmp_path, selected):
    root = apply(tmp_path, selected)
    assert (root / "AGENTS.md").is_file()
    for name in ["CLAUDE.md", ".claudeignore", ".claude/settings.json"]:
        assert (root / name).is_file() == ("claude" in selected), name
    for name in [
        ".cursorignore",
        ".cursorindexingignore",
        ".cursor/rules/workspace-context.mdc",
    ]:
        assert (root / name).is_file() == ("cursor" in selected), name
    if "claude" in selected:
        assert (root / "CLAUDE.md").read_text() == (root / "AGENTS.md").read_text()


def test_switch_removes_owned_defaults_but_preserves_custom_rules(tmp_path):
    root = apply(tmp_path, ["cursor", "claude"])
    custom = root / ".cursor/rules/custom.mdc"
    custom.write_text("User rules")
    (root / ".claudeignore").write_text("custom exclusions")
    apply(tmp_path, ["codex"])
    assert not (root / "CLAUDE.md").exists()
    assert not (root / ".cursorignore").exists()
    assert not (root / ".claude/settings.json").exists()
    assert custom.read_text() == "User rules"
    assert (root / ".claudeignore").read_text() == "custom exclusions"
    apply(tmp_path, ["claude"])
    assert (root / "CLAUDE.md").exists()
    assert (root / ".claudeignore").read_text() == "custom exclusions"
    assert not (root / ".cursorignore").exists()


def test_custom_claude_and_symlink_are_preserved(tmp_path):
    root = apply(tmp_path, ["claude"])
    (root / "CLAUDE.md").write_text("Custom instructions")
    apply(tmp_path, ["codex"])
    assert (root / "CLAUDE.md").read_text() == "Custom instructions"
    (root / "CLAUDE.md").unlink()
    external = tmp_path / "external"
    external.write_text("External instructions")
    (root / "CLAUDE.md").symlink_to(external)
    apply(tmp_path, ["claude"])
    assert external.read_text() == "External instructions"


def test_existing_legacy_defaults_can_be_cleaned_without_journal(tmp_path):
    root = apply(tmp_path, ["claude", "cursor"])
    (root / ".orcan/agent-context.json").unlink()
    apply(tmp_path, ["codex"])
    assert not (root / ".claudeignore").exists()
    assert not (root / ".cursorignore").exists()


def test_manifest_is_authoritative_and_accepts_baked_numeric_flags(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "agents.json"
    manifest.write_text(
        json.dumps(
            {"agents": {"cursor": 0, "claude": False, "codex": 1, "gemini": True}}
        )
    )
    monkeypatch.setenv("ORCAN_AGENTS_FILE", str(manifest))
    monkeypatch.setattr(
        agent_context.shutil, "which", lambda _: "/installed/any-client"
    )
    assert agent_context.enabled_agents() == {"codex", "gemini"}
    manifest.write_text("invalid")
    assert agent_context.enabled_agents() == set()


def test_status_does_not_request_disabled_agent_files(tmp_path, monkeypatch):
    manifest = tmp_path / "agents.json"
    manifest.write_text('{"agents":{"codex":true}}')
    monkeypatch.setenv("ORCAN_AGENTS_FILE", str(manifest))
    root = apply(tmp_path, ["codex"])
    assert not project_needs_init(root)
    text = format_status(
        {"name": "demo", "root": str(root), "tmux_session": "demo", "projects": []}
    )
    assert "CLAUDE.md" not in text and ".cursorignore" not in text
