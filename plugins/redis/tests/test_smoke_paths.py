"""Docker fixture storage must survive container-only executor worktree locations."""

import importlib.util
import subprocess
from pathlib import Path


def load_smoke():
    path = Path(__file__).resolve().parents[1] / "smoke" / "run.py"
    spec = importlib.util.spec_from_file_location("executor_smoke_paths", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_and_linked_worktrees_use_same_canonical_shared_parent(repo, tmp_path, monkeypatch):
    smoke = load_smoke()
    monkeypatch.setattr(smoke, "ROOT", repo)
    first = smoke.shared_fixture_root()
    linked = tmp_path / "container-only-worktree"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(linked)],
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(smoke, "ROOT", linked)
    second = smoke.shared_fixture_root()
    assert first.parent == second.parent == repo / ".git" / "orcan-executor-smoke"
    assert first != second and first.is_dir() and second.is_dir()
    assert not str(second).startswith(str(linked))
