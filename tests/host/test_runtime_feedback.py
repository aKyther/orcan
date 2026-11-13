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


@pytest.mark.integration
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("list-error", 6),
        ("kill-error", 7),
        ("marker-error", 8),
        ("permission", 1),
        ("no-server", 0),
        ("missing-socket", 0),
        ("success", 0),
        ("server-lost", 1),
    ],
)
def test_orphan_phase_propagates_errors_and_distinguishes_absent_server(
    tmp_path, mode, expected
):
    config = tmp_path / "config.json"
    config.write_text("{}")
    killed = tmp_path / "killed"
    script = r"""
orcan-workspaces(){ if [ "$MODE" = server-lost ]; then printf 'fixture\t%s\tfixture\n' "$WORKSPACE";fi;return 0; }
cursor-tmux-workspace-attach(){ return 0; }
tmux(){
 case "$3" in
  list-sessions)
   case "$MODE" in
    list-error) echo fixture-list-error >&2; return 6;;
    permission) echo 'error connecting to /fixture/socket (Permission denied)' >&2; return 1;;
    no-server|server-lost) echo 'no server running on /fixture/socket' >&2; return 1;;
    missing-socket) echo 'error connecting to /fixture/socket (No such file or directory)' >&2; return 1;;
   esac
   printf 'orphan\nunmanaged\n';;
  show-environment)
   if [ "$MODE" = marker-error ]; then echo fixture-marker-error >&2; return 8;fi
   if [ "$5" = '=unmanaged' ]; then echo 'unknown variable: ORCAN_WORKSPACE_NAME' >&2; return 1;fi;;
  kill-session)
   printf '%s\n' "$5" >> "$KILLED"
   if [ "$MODE" = kill-error ]; then echo fixture-kill-error >&2; return 7;fi;;
 esac
}
set -- --prune-orphans
source "$SCRIPT"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "ORCAN_CONFIG": str(config),
            "MODE": mode,
            "KILLED": str(killed),
            "WORKSPACE": str(tmp_path),
            "SCRIPT": str(RUNTIME / "orcan-tmux-reconcile-sessions"),
        },
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == expected, result.stderr
    if mode == "list-error":
        assert "fixture-list-error" in result.stderr
    if mode == "kill-error":
        assert "fixture-kill-error" in result.stderr
    if mode in {
        "list-error",
        "marker-error",
        "permission",
        "no-server",
        "missing-socket",
        "server-lost",
    }:
        assert not killed.exists()
    else:
        assert killed.read_text().splitlines() == ["=orphan"]
    assert ("removed orphaned" in result.stderr) == (mode == "success")


@pytest.mark.integration
def test_real_missing_tmux_server_is_a_clean_noop(tmp_path):
    import shutil

    executable = shutil.which("tmux")
    if executable is None:
        pytest.skip("tmux unavailable")
    config, socket = tmp_path / "config.json", tmp_path / "private.sock"
    config.write_text("{}")
    script = r"""
orcan-workspaces(){ return 0; }
tmux(){ "$TMUX_BINARY" -S "$SOCKET" "$@"; }
set -- --prune-orphans
source "$SCRIPT"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env={
            **os.environ,
            "ORCAN_CONFIG": str(config),
            "TMUX_BINARY": executable,
            "SOCKET": str(socket),
            "SCRIPT": str(RUNTIME / "orcan-tmux-reconcile-sessions"),
        },
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert not socket.exists()


@pytest.mark.integration
def test_real_private_tmux_prunes_only_managed_orphans(tmp_path):
    import shutil

    executable = shutil.which("tmux")
    if executable is None:
        pytest.skip("tmux unavailable")
    socket, config = tmp_path / "private.sock", tmp_path / "config.json"
    config.write_text("{}")
    prefix = [executable, "-S", str(socket), "-f", "/dev/null"]

    def tmux(*arguments, check=True):
        return subprocess.run(
            [*prefix, *arguments],
            capture_output=True,
            text=True,
            timeout=5,
            check=check,
        )

    script = r"""
orcan-workspaces(){ return 0; }
tmux(){ "$TMUX_BINARY" -S "$SOCKET" "$@"; }
if [ "$PRUNE" = 1 ]; then set -- --prune-orphans; else set --; fi
source "$SCRIPT"
"""
    try:
        tmux("new-session", "-d", "-s", "managed", "sleep 60")
        tmux("new-session", "-d", "-s", "unmanaged", "sleep 60")
        tmux(
            "set-environment", "-t", "=managed", "ORCAN_WORKSPACE_NAME", "old-workspace"
        )
        for prune in ("0", "1"):
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=ROOT,
                env={
                    **os.environ,
                    "ORCAN_CONFIG": str(config),
                    "TMUX_CONF": "/dev/null",
                    "TMUX_BINARY": executable,
                    "SOCKET": str(socket),
                    "PRUNE": prune,
                    "SCRIPT": str(RUNTIME / "orcan-tmux-reconcile-sessions"),
                },
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, result.stderr
            assert tmux("has-session", "-t", "=unmanaged").returncode == 0
            assert (
                tmux("has-session", "-t", "=managed", check=False).returncode == 0
            ) == (prune == "0")
    finally:
        tmux("kill-server", check=False)
