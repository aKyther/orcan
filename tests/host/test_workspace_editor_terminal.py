"""Exercise the new workspace draft through an actual private terminal."""
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.parametrize('save', [False, True])
def test_multi_project_mixed_draft_save_or_discard(tmp_path, tracked_git_repo_factory, save):
    parent = tmp_path / 'projects'
    parent.mkdir()
    tracked_git_repo_factory(parent / 'api')
    (parent / 'assets').mkdir()
    home = tmp_path / 'home'
    config = home / 'orcan.config.json'
    sandbox = tmp_path / 'sandbox'
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 120, 0, 0))
    env = {**os.environ, 'TERM': 'xterm-256color', 'ORCAN_HOME': str(home),
           'ORCAN_DATA': str(home), 'ORCAN_PROJECTS_ROOT': str(sandbox),
           'ORCAN_NAMED_INSTANCE': '', 'PYTHONPATH': str(ROOT / 'scripts/repository')}
    proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/repository/context_tui.py'),
                             '--config', str(config), '--dir', str(parent)],
                            env=env, cwd=ROOT, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    def until(text):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                output.extend(chunk)
                if text in output:
                    return
            if proc.poll() is not None:
                break
        raise AssertionError(f'Missing {text!r}: {bytes(output[-1800:])!r}')
    try:
        until(b'Create workspace')
        os.write(master, b'\n')
        until(b'New workspace name')
        os.write(master, b'daily\n')
        until(b'+ Add projects')
        assert not config.exists()
        os.write(master, b'j\n')
        until(b'Select this folder as a project')
        os.write(master, b'\n')  # Enter opens api; it does not select it.
        until(b'Opened api.')
        os.write(master, b'\x1bOD')  # Left in xterm application cursor mode.
        until(b'Returned to parent folder')
        os.write(master, b' j j\n')  # Select api and assets, then Add selected projects.
        until(b'Projects added as mount as-is')
        assert not config.exists()
        os.write(master, b'\n')  # Edit api; assets retains mount as-is.
        until(b'Done')
        os.write(master, b'jj\n')
        until(b'Branch for this project')
        os.write(master, b'\x7f' * len('feature/daily') + b'feature/api\n')
        until(b'Branch:')
        os.write(master, b'jjjjjj\n')
        until(b'api')
        assert not config.exists()
        assert not sandbox.exists()
        if save:
            os.write(master, b'jjjj\n')
            until(b'Save all workspace changes')
            os.write(master, b'y\n')
            assert proc.wait(timeout=15) == 0
            projects = json.loads(config.read_text())['workspaces'][0]['projects']
            assert projects[0]['path'] == str(sandbox / '.worktrees/daily/api')
            assert projects[1]['path'] == str(parent / 'assets')
            assert Path(projects[0]['path']).is_dir()
        else:
            os.write(master, b'\x1b')
            until(b'Close / discard draft')
            os.write(master, b'\x1b')
            until(b'Discard unsaved changes')
            os.write(master, b'y\n')
            assert proc.wait(timeout=10) == 1
            assert not config.exists()
            assert not sandbox.exists()
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        os.close(master)
