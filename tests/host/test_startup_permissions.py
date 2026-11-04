"""Runtime startup must not bypass the explicit sync ownership policy."""
import os
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.integration


def check(home):
    script='''set -Eeuo pipefail
source docker/rootfs/usr/local/bin/docker-entrypoint
orcan-agent-enabled() { return 1; }
sudo() { echo UNEXPECTED_SUDO >&2; return 99; }
chown() { echo UNEXPECTED_CHOWN >&2; return 99; }
find() { echo UNEXPECTED_SCAN >&2; return 99; }
check_runtime_directory_permissions
'''
    return subprocess.run(['bash','-c',script],cwd=ROOT,env={**os.environ,'HOME':str(home)},capture_output=True,text=True)


def test_startup_checks_writable_roots_without_walking_nested_exclusions(tmp_path):
    cache=tmp_path/'.cache';cache.mkdir()
    nested=cache/'external';nested.mkdir();nested.chmod(0o555)
    before=nested.stat()
    result=check(tmp_path)
    assert result.returncode==0,result.stderr
    after=nested.stat()
    assert (before.st_mode,before.st_uid,before.st_gid)==(after.st_mode,after.st_uid,after.st_gid)
    assert 'UNEXPECTED' not in result.stderr


def test_readonly_runtime_root_fails_without_ownership_repair(tmp_path):
    cache=tmp_path/'.cache';cache.mkdir();cache.chmod(0o555)
    if os.access(cache,os.W_OK):pytest.skip('Root can write despite mode bits')
    result=check(tmp_path)
    assert result.returncode!=0
    assert 'not writable' in result.stderr and 'orcan sync' in result.stderr
    assert 'UNEXPECTED' not in result.stderr
    assert cache.stat().st_mode & 0o777 == 0o555
