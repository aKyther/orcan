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


def test_exclusions_prune_before_stat_and_preserve_symlink_targets(
    tmp_path, monkeypatch
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
        str(data), 123, 456, [str(excluded / ".." / excluded.name), str(other)]
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
