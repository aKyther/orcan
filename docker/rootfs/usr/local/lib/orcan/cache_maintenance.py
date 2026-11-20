"""Hourly native cache maintenance, independent of the optional executor."""

import fcntl
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600
GRADLE_POLICY = '''// Orcan: native retention of unused entries; no recursive deletion.
if (!new File(gradle.gradleUserHomeDir, 'orcan-retention.disabled').exists() &&
    !new File(gradle.gradleUserHomeDir.parentFile, 'orcan-maintenance.disabled').exists()) {
    if (org.gradle.util.GradleVersion.current() >= org.gradle.util.GradleVersion.version('8.0')) {
        beforeSettings { settings ->
            settings.caches {
                releasedWrappers.setRemoveUnusedEntriesAfterDays(30)
                snapshotWrappers.setRemoveUnusedEntriesAfterDays(7)
                downloadedResources.setRemoveUnusedEntriesAfterDays(14)
                createdResources.setRemoveUnusedEntriesAfterDays(7)
            }
        }
    }
    if (org.gradle.util.GradleVersion.current() >= org.gradle.util.GradleVersion.version('8.8')) {
        beforeSettings { settings ->
            settings.caches.buildCache.setRemoveUnusedEntriesAfterDays(7)
        }
    }
}
'''


def cache_root() -> Path:
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))


def install_gradle_policy(root: Path) -> str:
    # Custom homes and existing user policies remain user-owned.
    home = Path(os.environ.get('GRADLE_USER_HOME', str(root / 'gradle')))
    if home != root / 'gradle' or home.is_symlink():
        return 'custom_home'
    directory = home / 'init.d'
    if directory.is_symlink():
        return 'custom_home'
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (directory / 'orcan-cache-retention.gradle').open('x') as stream:
            stream.write(GRADLE_POLICY)
    except FileExistsError:
        return 'preserved'
    return 'installed'


def run_once() -> dict:
    root = cache_root()
    if root.is_symlink() or (root / 'orcan-maintenance.disabled').exists():
        return {'status': 'disabled'}
    root.mkdir(parents=True, exist_ok=True)
    # The lock is shared across containers using this cache. Never unlink it.
    fd = os.open(root / 'orcan-maintenance.lock', os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy'}
        stamp = root / 'orcan-maintenance.last-run'
        if stamp.exists() and time.time() - stamp.stat().st_mtime < INTERVAL_SECONDS:
            return {'status': 'not_due'}
        result = {'status': 'completed', 'gradle': install_gradle_policy(root)}
        uv_cache = Path(os.environ.get('UV_CACHE_DIR', str(root / 'uv')))
        if uv_cache != root / 'uv' or uv_cache.is_symlink():
            result['uv'] = 'custom_cache'
        elif not uv_cache.is_dir() or not shutil.which('uv'):
            result['uv'] = 'unavailable'
        else:
            try:
                # uv owns its cache locks. No --force, --ci or direct deletion.
                command = subprocess.run(
                    ['uv', '--no-config', 'cache', 'prune', '--cache-dir', str(uv_cache)],
                    check=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=60,
                    env={**os.environ, 'UV_LOCK_TIMEOUT': '1'},
                )
                result['uv'] = 'pruned' if command.returncode == 0 else 'deferred'
            except (OSError, subprocess.TimeoutExpired):
                result['uv'] = 'deferred'
        # Exclusive creation prevents following a user-supplied marker symlink.
        try:
            stamp_fd = os.open(stamp, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(stamp_fd, 'a'):
                os.utime(stamp, follow_symlinks=False)
        except OSError:
            logger.warning('Cannot record cache maintenance time')
        return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='orcan-cache: %(message)s')
    while True:
        try:
            logger.info('%s', run_once())
        except (OSError, ValueError):
            logger.exception('Maintenance deferred; user files preserved')
        time.sleep(INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
