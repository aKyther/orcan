"""Studio build maintenance stays inside its generated target directory."""

import subprocess
from unittest.mock import Mock

import pytest

from ._scripts_loader import load_script

module = load_script("studio-build-storage.py")


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.delenv("CARGO_TARGET_DIR", raising=False)
    root = tmp_path / "repo"
    (root / "studio/target").mkdir(parents=True)
    (root / "studio/Cargo.toml").write_text("[workspace]\n")
    (root / "studio/target/build-output").write_bytes(b"x" * 2 * 1024**2)
    return root


def test_preview_and_under_budget_preserve_builds(studio, monkeypatch):
    runner = Mock(side_effect=AssertionError("No command should run"))
    monkeypatch.setattr(module.subprocess, "run", runner)
    report = module.maintain(studio)
    assert not report["removed"]
    assert report["allocated_bytes"] >= 2 * 1024**2
    assert not module.maintain(studio, automatic=True)["removed"]
    assert (studio / "studio/target/build-output").exists()


def test_over_budget_uses_cargo_clean_with_canonical_target(studio, monkeypatch):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=""))
    monkeypatch.setattr(module.subprocess, "run", runner)
    assert module.maintain(studio, automatic=True, budget_mb=1)["removed"]
    assert runner.call_args_list[0].args[0] == [
        "git",
        "-C",
        str(studio),
        "ls-files",
        "--",
        "studio/target",
    ]
    assert runner.call_args.args[0] == [
        "cargo",
        "clean",
        "--manifest-path",
        str(studio / "studio/Cargo.toml"),
        "--target-dir",
        str(studio / "studio/target"),
    ]


def test_target_symlink_is_rejected(studio, tmp_path):
    import shutil

    shutil.rmtree(studio / "studio/target")
    (studio / "studio/target").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="non-symlink"):
        module.maintain(studio, apply=True)


def test_external_target_is_preserved(studio, monkeypatch, tmp_path):
    monkeypatch.setenv("CARGO_TARGET_DIR", str(tmp_path / "shared"))
    runner = Mock(side_effect=AssertionError("No command should run"))
    monkeypatch.setattr(module.subprocess, "run", runner)
    assert "preserved" in module.maintain(studio, apply=True)


def test_tracked_target_is_preserved(studio, monkeypatch):
    runner = Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, stdout="studio/target/user-file"
        )
    )
    monkeypatch.setattr(module.subprocess, "run", runner)
    with pytest.raises(ValueError, match="tracked files"):
        module.maintain(studio, apply=True)
    assert runner.call_count == 1
