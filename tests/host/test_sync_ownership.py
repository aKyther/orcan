"""Ownership exclusions must prune remote mounts before inspecting them."""

import os
import subprocess
from pathlib import Path

import pytest

from ._scripts_loader import load_script

ROOT = Path(__file__).resolve().parents[2]
ownership = load_script("data-ownership.py")


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


@pytest.mark.integration
def test_saved_policy_survives_project_addition_and_prunes_before_stat(
    tmp_path, monkeypatch
):
    import json

    config = tmp_path / "orcan.config.json"
    project = tmp_path / "project"
    project.mkdir()
    config.write_text(json.dumps({"workspaces": [], "custom": {"keep": True}}))
    data = tmp_path / "data"
    excluded = data / "external mount"
    excluded.mkdir(parents=True)
    ownership.ownership_policy(config, [], ["external*"], save=True)
    # Use the actual scaffold command used by `orcan init PATH`.
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/repository/config-scaffold.py"),
            "--config",
            str(config),
            "--project-dir",
            str(project),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    paths, names = ownership.ownership_policy(
        config, [], []
    )  # Automatic sync has no flags.
    changed = []
    monkeypatch.setattr(
        ownership.os, "chown", lambda path, *a, **k: changed.append(path)
    )
    original = os.scandir

    def scan(path):
        assert path != str(excluded), "automatic sync entered a protected directory"
        return original(path)

    monkeypatch.setattr(ownership.os, "scandir", scan)
    assert ownership.update_ownership(str(data), 1, 1, paths, names)
    assert changed == [str(data)]
    saved = json.loads(config.read_text())
    assert saved["custom"] == {"keep": True}
    assert saved["ownership"]["excluded_names"] == ["external*"]
    assert saved["workspaces"]


def test_policy_merges_flags_without_losing_config_and_can_be_removed(tmp_path):
    import json

    config = tmp_path / "orcan.config.json"
    config.write_text(json.dumps({"workspaces": [], "executor": {"workers": 5}}))
    ownership.ownership_policy(
        config, [str(tmp_path / "remote")], ["external*"], save=True
    )
    ownership.ownership_policy(config, [], ["external*", "archive?"], save=True)
    value = json.loads(config.read_text())
    assert value["executor"] == {"workers": 5}
    assert value["ownership"]["excluded_names"] == ["external*", "archive?"]
    assert value["ownership"]["excluded_paths"] == [str(tmp_path / "remote")]
    value["ownership"] = {"excluded_paths": [], "excluded_names": []}
    config.write_text(json.dumps(value))
    assert ownership.ownership_policy(config, [], []) == ([], [])


@pytest.mark.parametrize(
    "policy",
    [
        [],
        {"excluded_names": "external"},
        {"excluded_paths": ["relative"]},
        {"excluded_names": ["remote/path"]},
        {"excluded_names": [True]},
        {"unknown": []},
    ],
)
def test_invalid_persistent_policy_is_rejected_without_changes(tmp_path, policy):
    import json

    config = tmp_path / "orcan.config.json"
    config.write_text(json.dumps({"ownership": policy}))
    before = config.read_bytes()
    with pytest.raises(ValueError):
        ownership.ownership_policy(config, [], [], save=True)
    assert config.read_bytes() == before


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["path", "tui", "cli"])
def test_init_does_not_sync_or_materialize_runtime(tmp_path, mode):
    import shutil

    init = tmp_path / "init.sh"
    shutil.copyfile(ROOT / "cli/commands/init.sh", init)
    # Sourcing sync at all is forbidden, even if no Docker service is available.
    (tmp_path / "sync.sh").write_text('echo "unexpected sync" >&2; exit 91\n')
    shell = """source "$1"
shift
orcan_require_python() { :; }
orcan_host_python() { printf '%s\n' "$1"; }
orcan_info() { printf '%s\n' "$*"; }
orcan_ok() { :; }
orcan_usage_error() { echo "$*" >&2; return 2; }
ORCAN_HOME="$TEST_HOME"
ORCAN_CONFIG_FILE="$TEST_HOME/orcan.config.json"
ORCAN_SCRIPTS="$TEST_HOME"
orcan_cmd_init "$@"
"""
    flags = {"path": [str(tmp_path)], "tui": [], "cli": ["--cli"]}[mode]
    result = subprocess.run(
        ["bash", "-c", shell, "test", str(init), *flags],
        env={**os.environ, "TEST_HOME": str(tmp_path)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    script = {"path": "config-scaffold.py", "tui": "context_tui.py", "cli": "config-wizard.py"}[mode]
    assert script in result.stdout
    assert "next: orcan sync" in result.stdout
    assert not (tmp_path / "mounts").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    "arguments", ["--no-chown", "--no-chown external", "--no-chown relative/path", "--chown-exclude /absolute/path", "--chown-exclude relative"]
)
def test_init_directs_ownership_flags_to_sync_before_wizard(arguments):
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source cli/commands/init.sh; orcan_usage_error() { echo "$*" >&2; }; '
            f"orcan_cmd_init {arguments}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "belongs to orcan sync" in result.stderr


@pytest.mark.integration
def test_update_env_rejects_invalid_saved_policy_before_runtime_materialization(
    tmp_path,
):
    import json

    config = tmp_path / "orcan.config.json"
    config.write_text(json.dumps({"ownership": {"excluded_paths": ["relative"]}}))
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/repository/sync-runtime.sh")],
        env={
            **os.environ,
            "ORCAN_ROOT": str(ROOT),
            "ORCAN_HOME": str(tmp_path),
            "CONFIG": str(config),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "requires absolute directory paths" in result.stderr
    assert not (tmp_path / "mounts").exists()
    assert not (tmp_path / ".env").exists()


def test_absent_configuration_does_not_create_an_empty_workspace_policy(tmp_path):
    config = tmp_path / "orcan.config.json"
    assert ownership.ownership_policy(config, [], [], save=True) == ([], [])
    assert not config.exists()
    with pytest.raises(ValueError, match="orcan init PATH"):
        ownership.ownership_policy(config, [], ["external*"], save=True)
    assert not config.exists()


@pytest.mark.integration
@pytest.mark.parametrize('existing_runtime', [False, True])
def test_real_init_path_saves_config_without_touching_runtime(tmp_path, existing_runtime):
    import json

    home = tmp_path / 'home'
    project = tmp_path / 'project'
    project.mkdir()
    runtime = home / 'mounts'
    marker = runtime / 'runtime-config.json'
    if existing_runtime:
        runtime.mkdir(parents=True)
        marker.write_text('{"untouched":true}')
    config = home / 'orcan.config.json'
    result = subprocess.run(
        [str(ROOT / 'bin/orcan'), 'init', str(project)],
        env={**os.environ, 'ORCAN_HOME': str(home), 'ORCAN_DATA': str(home),
             'ORCAN_CONFIG_FILE': str(config), 'ORCAN_RUNTIME_DIR': str(runtime),
             'CONFIG': ''},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(config.read_text())
    assert any(p['path'] == str(project) for ws in data['workspaces'] for p in ws['projects'])
    assert 'runtime not applied' in result.stdout
    assert 'next: orcan sync' in result.stdout
    if existing_runtime:
        assert marker.read_text() == '{"untouched":true}'
        assert list(runtime.iterdir()) == [marker]
    else:
        assert not runtime.exists()
    assert not (home / 'workspaces').exists()


def test_already_owned_tree_is_scanned_without_repeated_chown(tmp_path, monkeypatch):
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested/file').touch()
    calls = []
    monkeypatch.setattr(ownership.os, 'chown', lambda *a, **kw: calls.append(a))
    uid, gid = tmp_path.stat().st_uid, tmp_path.stat().st_gid
    assert ownership.update_ownership(str(tmp_path), uid, gid, [])
    assert ownership.update_ownership(str(tmp_path), uid, gid, [])
    assert calls == []
