"""Native cache policies use disposable roots; never prune real shared caches."""
import fcntl
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'cache_maintenance', ROOT / 'docker/rootfs/usr/local/lib/orcan/cache_maintenance.py'
)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path))
    monkeypatch.delenv('GRADLE_USER_HOME', raising=False)
    monkeypatch.delenv('UV_CACHE_DIR', raising=False)
    (tmp_path / 'uv').mkdir()
    monkeypatch.setattr(cache.shutil, 'which', lambda name: '/fake/uv')
    command = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(cache.subprocess, 'run', command)
    return tmp_path, command


def test_hourly_native_prune_is_shared_and_preserves_programs_and_custom_policy(isolated):
    root, command = isolated
    program = root / 'cargo/bin/my-program'
    program.parent.mkdir(parents=True)
    program.write_text('keep')
    policy = root / 'gradle/init.d/orcan-cache-retention.gradle'
    policy.parent.mkdir(parents=True)
    policy.write_text('custom policy')
    assert cache.run_once()['uv'] == 'pruned'
    assert cache.run_once()['status'] == 'not_due'
    assert command.call_count == 1
    args = command.call_args.args[0]
    assert args == ['uv', '--no-config', 'cache', 'prune', '--cache-dir', str(root / 'uv')]
    assert command.call_args.kwargs['env']['UV_LOCK_TIMEOUT'] == '1'
    assert policy.read_text() == 'custom policy'
    assert program.read_text() == 'keep'
    os.utime(root / 'orcan-maintenance.last-run', (0, 0))
    assert cache.run_once()['uv'] == 'pruned'
    assert command.call_count == 2


def test_shared_lock_and_disable_marker_prevent_prune(isolated):
    root, command = isolated
    with (root / 'orcan-maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cache.run_once()['status'] == 'busy'
    (root / 'orcan-maintenance.disabled').touch()
    assert cache.run_once()['status'] == 'disabled'
    command.assert_not_called()


def test_busy_uv_is_deferred_without_force_or_short_retry(isolated):
    _root, command = isolated
    command.side_effect = subprocess.TimeoutExpired(['uv'], 60)
    assert cache.run_once()['uv'] == 'deferred'
    assert cache.run_once()['status'] == 'not_due'


def test_custom_and_symlink_cache_paths_are_preserved(isolated, monkeypatch, tmp_path):
    root, command = isolated
    outside = root / 'outside'
    outside.mkdir()
    monkeypatch.setenv('UV_CACHE_DIR', str(outside))
    monkeypatch.setenv('GRADLE_USER_HOME', str(outside))
    result = cache.run_once()
    assert result['uv'] == 'custom_cache'
    assert result['gradle'] == 'custom_home'
    command.assert_not_called()
    assert list(outside.iterdir()) == []


@pytest.mark.integration
def test_native_gradle_accepts_policy_and_uses_retention(tmp_path, monkeypatch):
    gradle = shutil.which('gradle')
    if not gradle:
        pytest.skip('Gradle is not installed')
    root = tmp_path / 'cache'
    monkeypatch.delenv('GRADLE_USER_HOME', raising=False)
    cache.install_gradle_policy(root)
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'settings.gradle').write_text('''
settingsEvaluated { settings ->
    println('ORCAN_RETENTION=' + settings.caches.downloadedResources.removeUnusedEntriesAfterDays.get())
}
''')
    (project / 'build.gradle').write_text('')
    result = subprocess.run(
        [gradle, '--offline', '--no-daemon', '--max-workers=1', '-g', str(root / 'gradle'), 'help'],
        check=False, cwd=project, capture_output=True, text=True, timeout=120,
        env={**os.environ, 'GRADLE_OPTS': '-Dorg.gradle.jvmargs=-Xmx128m'},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert 'ORCAN_RETENTION=14' in result.stdout


@pytest.mark.integration
@pytest.mark.parametrize('disabled,explicit,expected', [
    (False, '', '1 hour'), (True, '', 'never'), (True, '3 days', '3 days'),
])
def test_cargo_frequency_and_opt_out_preserve_explicit_settings(tmp_path, disabled, explicit, expected):
    root = tmp_path / 'cache'
    root.mkdir()
    if disabled:
        (root / 'orcan-maintenance.disabled').touch()
    env = {**os.environ, 'HOME': str(tmp_path), 'XDG_CACHE_HOME': str(root)}
    env.pop('CARGO_CACHE_AUTO_CLEAN_FREQUENCY', None)
    if explicit:
        env['CARGO_CACHE_AUTO_CLEAN_FREQUENCY'] = explicit
    result = subprocess.run(
        ['bash', '--noprofile', '--norc', '-c',
         'source "$1"; printf "%s" "$CARGO_CACHE_AUTO_CLEAN_FREQUENCY"', 'cache-test',
         str(ROOT / 'docker/rootfs/etc/orcan/shell/devtools-env.sh')],
        env=env, check=True, capture_output=True, text=True,
    )
    assert result.stdout == expected
