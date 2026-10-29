"""Brief compaction preserves history and rejects stale or unsafe writes."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "orcan_compact", ROOT / "docker/rootfs/usr/local/lib/orcan/compact.py"
)
compact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".manifest.json").write_text("{}")
    (tmp_path / ".orcan").mkdir()
    return tmp_path


def seed(root, text="Old goal and decisions. " * 500):
    path = root / ".orcan/session-brief.md"
    path.write_text(text)
    return path


def test_check_missing_and_small_brief_does_not_write(workspace):
    assert compact.check(workspace) == {"exists": False, "needs_compact": False}
    assert list((workspace / ".orcan").iterdir()) == []
    seed(workspace, "Short goal")
    stats = compact.check(workspace)
    assert stats["words"] == 2
    assert not stats["needs_compact"]


def test_budget_checks_words_and_utf8_bytes(workspace):
    seed(workspace, "a " * 801)
    assert compact.check(workspace)["needs_compact"]
    seed(workspace, "ą" * 4001)
    assert compact.check(workspace)["needs_compact"]
    seed(workspace, "a " * 800)
    assert not compact.check(workspace)["needs_compact"]


def test_apply_preserves_exact_original_and_candidate(workspace):
    brief = seed(workspace)
    original = brief.read_bytes()
    candidate = workspace / ".orcan/session-brief.next.md"
    candidate.write_text("# Goal\nCurrent goal\n# Next\nRun tests\n")
    result = compact.apply(workspace, candidate, compact.check(workspace)["sha256"])
    assert brief.read_bytes() == candidate.read_bytes()
    assert Path(result["archive"]).read_bytes() == original
    assert not result["needs_compact"]
    # A second pass preserves the first archive, too.
    candidate.write_text("# Goal\nRun tests\n")
    compact.apply(workspace, candidate, result["sha256"])
    assert len(list((workspace / ".orcan/brief-history").glob("*.md"))) == 2


def test_stale_hash_cannot_replace_newer_work(workspace):
    brief = seed(workspace)
    old_hash = compact.check(workspace)["sha256"]
    brief.write_text("Another session's current goal")
    candidate = workspace / "next.md"
    candidate.write_text("Short summary")
    with pytest.raises(ValueError, match="Brief changed"):
        compact.apply(workspace, candidate, old_hash)
    assert brief.read_text() == "Another session's current goal"
    assert not (workspace / ".orcan/brief-history").exists()


@pytest.mark.parametrize("text", ["", "  ", "x " * 801, "ą" * 4001])
def test_invalid_summary_keeps_original(workspace, text):
    brief = seed(workspace)
    original = brief.read_bytes()
    candidate = workspace / "next.md"
    candidate.write_text(text)
    with pytest.raises(ValueError, match="non-empty"):
        compact.apply(workspace, candidate, compact.check(workspace)["sha256"])
    assert brief.read_bytes() == original


def test_rejects_nonshrinking_summary_and_source_as_candidate(workspace):
    brief = seed(workspace, "Small goal")
    digest = compact.check(workspace)["sha256"]
    with pytest.raises(ValueError, match="separate"):
        compact.apply(workspace, brief, digest)
    candidate = workspace / "next.md"
    candidate.write_text("A much longer candidate goal")
    with pytest.raises(ValueError, match="smaller"):
        compact.apply(workspace, candidate, digest)
    assert brief.read_text() == "Small goal"


@pytest.mark.parametrize(
    "target", ["session-brief.md", "brief-history", "compact.lock"]
)
def test_rejects_symlinked_output(workspace, target):
    seed(workspace)
    digest = compact.check(workspace)["sha256"]
    candidate = workspace / "next.md"
    candidate.write_text("Summary")
    external = workspace / "outside"
    external.write_text("Untouched")
    link = workspace / ".orcan" / target
    link.unlink(missing_ok=True)
    link.symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        compact.apply(workspace, candidate, digest)
    assert external.read_text() == "Untouched"


def test_archive_failure_never_replaces_brief(workspace):
    brief = seed(workspace)
    original = brief.read_bytes()
    candidate = workspace / "next.md"
    candidate.write_text("Summary")
    (workspace / ".orcan/brief-history").write_text("Not a directory")
    with pytest.raises(OSError):
        compact.apply(workspace, candidate, compact.check(workspace)["sha256"])
    assert brief.read_bytes() == original


def test_workspace_resolution_and_json_cli(workspace, monkeypatch, capsys):
    monkeypatch.delenv("ORCAN_WORKSPACE_ROOT", raising=False)
    child = workspace / "project"
    child.mkdir()
    monkeypatch.chdir(child)
    assert compact.workspace_root() == workspace
    assert compact.main(["--check"]) == 0
    assert json.loads(capsys.readouterr().out)["exists"] is False
    with pytest.raises(SystemExit) as error:
        compact.main(["--apply", "next.md"])
    assert error.value.code == 2
    monkeypatch.setenv("ORCAN_WORKSPACE_ROOT", str(child))
    with pytest.raises(ValueError, match="manifest"):
        compact.workspace_root()


def test_change_during_archive_keeps_newer_brief(workspace, monkeypatch):
    brief = seed(workspace)
    original = brief.read_bytes()
    digest = compact.check(workspace)["sha256"]
    candidate = workspace / "next.md"
    candidate.write_text("Summary")
    fsync = compact.os.fsync

    def concurrent_edit(fd):
        fsync(fd)
        brief.write_text("Newer work from another editor")

    monkeypatch.setattr(compact.os, "fsync", concurrent_edit)
    with pytest.raises(ValueError, match="during compaction"):
        compact.apply(workspace, candidate, digest)
    assert brief.read_text() == "Newer work from another editor"
    backups = list((workspace / ".orcan/brief-history").glob("*.md"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert not list((workspace / ".orcan").glob("tmp*"))


@pytest.mark.integration
def test_host_and_container_entry_points(workspace):
    import os
    import shutil
    import subprocess

    seed(workspace)
    env = {"HOME": str(workspace), "PATH": os.environ["PATH"]}
    for entry in (
        ROOT / "bin/orcan",
        ROOT / "docker/rootfs/usr/local/bin/orcan-compact",
    ):
        command = [str(entry)]
        if entry.name == "orcan":
            command.append("compact")
        result = subprocess.run(
            [*command, "--check", "--workspace", str(workspace)],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        assert json.loads(result.stdout)["needs_compact"] is True
    candidate = workspace / "next.md"
    candidate.write_text("Current goal")
    compact.apply(workspace, candidate, compact.check(workspace)["sha256"])
    if shutil.which("rg"):
        files = subprocess.run(
            ["rg", "--files", "--hidden", str(workspace)],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout
        assert "session-brief.md" in files
        assert "brief-history" not in files


def test_large_legacy_brief_is_streamed_and_candidate_is_bounded(
    workspace, monkeypatch
):
    brief = seed(workspace, "legacy goal " * 100000)
    candidate = workspace / "candidate.md"
    candidate.write_text("New goal")
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda *a: (_ for _ in ()).throw(AssertionError("unbounded read")),
    )
    checked = compact.check(workspace)
    assert checked["words"] == 200000
    result = compact.apply(workspace, candidate, checked["sha256"])
    assert result["bytes"] == len("New goal")
    candidate.write_text("x" * (compact.MAX_BYTES + 10000))
    with pytest.raises(ValueError, match="non-empty"):
        compact.apply(workspace, candidate, result["sha256"])
