"""Workspace metadata and session failures must remain visible to sync callers."""

import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "docker/rootfs/usr/local/bin"


def test_runtime_reconcile_propagates_tmux_failure(monkeypatch, capsys):
    loader = importlib.machinery.SourceFileLoader(
        "runtime_feedback", str(RUNTIME / "orcan-runtime-reconcile")
    )
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader)
    )
    loader.exec_module(module)
    monkeypatch.setattr(module.sys, "argv", ["orcan-runtime-reconcile"])
    monkeypatch.setattr(module, "load_config", lambda _: {})
    report = SimpleNamespace(
        workspaces=[],
        stale_workspace_dirs_removed=[],
        total_repos=lambda: 0,
        changed=lambda: False,
    )
    monkeypatch.setattr(module, "apply_workspaces", lambda *_: report)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=7)
    )
    assert module.main() == 7
    assert "tmux session reconcile failed" in capsys.readouterr().err


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["bootstrap", "attach", "missing-root"])
def test_session_reconcile_aborts_before_pruning_on_incomplete_state(tmp_path, failure):
    config = tmp_path / "config.json"
    config.write_text("{}")
    workspace = tmp_path / "workspace"
    if failure != "missing-root":
        workspace.mkdir()
    calls = tmp_path / "calls"
    script = r"""
orcan-workspaces(){
 if [ "$FAILURE" = bootstrap ]; then echo bootstrap-failed >&2; return 2; fi
 printf 'fixture\t%s\tfixture\n' "$WORKSPACE"
}
cursor-tmux-workspace-attach(){ echo attach-failed >&2; return 7; }
tmux(){ printf '%s\n' "$*" >> "$CALLS"; printf 'fixture\n'; }
set -- --prune-orphans
source "$SCRIPT"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "ORCAN_CONFIG": str(config),
            "WORKSPACE": str(workspace),
            "FAILURE": failure,
            "CALLS": str(calls),
            "SCRIPT": str(RUNTIME / "orcan-tmux-reconcile-sessions"),
        },
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert not calls.exists()
    assert (
        failure.split("-")[0] in result.stderr
        or "workspace root unavailable" in result.stderr
    )
