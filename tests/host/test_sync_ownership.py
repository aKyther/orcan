"""Ownership exclusions must prune remote mounts before inspecting them."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "data_ownership", ROOT / "scripts/repository/data-ownership.py"
)
ownership = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ownership)


@pytest.mark.parametrize("by_name", [False, True])
def test_exclusions_prune_before_stat_and_preserve_symlink_targets(
    tmp_path, monkeypatch, by_name
):
    data = tmp_path / "data"
    data.mkdir()
    excluded = data / "remote [1]"
    excluded.mkdir()
    other = data / "second remote"
    other.mkdir()
    sibling = data / "remote 1"
    sibling.mkdir()
    (sibling / "keep").touch()
    external = tmp_path / "external"
    external.mkdir()
    (data / "link").symlink_to(external, target_is_directory=True)
    changed = []
    scanned = []
    original = os.scandir

    class Entry:
        def __init__(self, entry):
            self.entry = entry
            self.path = entry.path

        def is_dir(self, **kwargs):
            assert self.path not in {str(excluded), str(other)}
            return self.entry.is_dir(**kwargs)

    class Scan:
        def __init__(self, path):
            scanned.append(path)
            self.scan = original(path)

        def __enter__(self):
            return (Entry(entry) for entry in self.scan)

        def __exit__(self, *args):
            self.scan.close()

    def chown(path, uid, gid, *, follow_symlinks):
        assert (uid, gid, follow_symlinks) == (123, 456, False)
        changed.append(path)

    monkeypatch.setattr(ownership.os, "scandir", Scan)
    monkeypatch.setattr(ownership.os, "chown", chown)
    assert ownership.update_ownership(
        str(data),
        123,
        456,
        [] if by_name else [str(excluded / ".." / excluded.name), str(other)],
        ["remote [[]1]", "second*"] if by_name else [],
    )
    assert set(scanned) == {str(data), str(sibling)}
    assert set(changed) == {
        str(data),
        str(sibling),
        str(sibling / "keep"),
        str(data / "link"),
    }


def test_excluded_root_is_never_accessed(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Excluded root was accessed")

    monkeypatch.setattr(ownership.os, "scandir", forbidden)
    monkeypatch.setattr(ownership.os, "chown", forbidden)
    assert ownership.update_ownership(str(tmp_path / "remote"), 1, 1, [str(tmp_path)])


def test_ownership_failure_is_reported(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("fixture")

    monkeypatch.setattr(ownership.os, "chown", denied)
    assert not ownership.update_ownership(str(tmp_path), 1, 1, [])


@pytest.mark.integration
@pytest.mark.parametrize(
    "arguments", ["--chown-exclude", "--chown-exclude relative/path"]
)
def test_sync_rejects_invalid_exclusion_before_changes(arguments):
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source cli/commands/sync.sh; orcan_usage_error() { echo "$*" >&2; }; '
                f"orcan_cmd_sync {arguments}"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "requires an absolute directory path" in result.stderr


@pytest.mark.parametrize("pattern", ["external", "extern*", "externa?"])
def test_name_patterns_match_at_any_depth(tmp_path, monkeypatch, pattern):
    data = tmp_path / "data"
    nested = data / "nested"
    for parent in (data, nested):
        (parent / "external" / "untouched").mkdir(parents=True)
        (parent / "external-backup").mkdir()
    changed = []
    monkeypatch.setattr(
        ownership.os, "chown", lambda path, *args, **kwargs: changed.append(path)
    )
    assert ownership.update_ownership(str(data), 1, 1, [], [pattern])
    assert str(data) in changed and str(nested) in changed
    assert not any("external" in Path(path).parts for path in changed)
    assert (str(nested / "external-backup") in changed) == (pattern != "extern*")


@pytest.mark.integration
@pytest.mark.parametrize(
    "arguments",
    [
        "--no-chown",
        "--no-chown ''",
        "--no-chown --prune-orphans",
        "--no-chown relative/path",
    ],
)
def test_sync_rejects_invalid_name_pattern(arguments):
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source cli/commands/sync.sh; orcan_usage_error() { echo "$*" >&2; }; '
                f"orcan_cmd_sync {arguments}"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "requires a directory name or glob without slashes" in result.stderr
