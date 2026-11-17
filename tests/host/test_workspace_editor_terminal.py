"""Exercise the new workspace draft through an actual private terminal."""
import codecs
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import tempfile
import time
from pathlib import Path

import pytest
import pyte

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def executable_bin():
    # /tmp may be mounted noexec; command fixtures need an executable location.
    with tempfile.TemporaryDirectory(prefix='.orcan-test.fork-gh-', dir=ROOT) as directory:
        yield Path(directory)


@pytest.mark.integration
@pytest.mark.parametrize('save', [False, True])
@pytest.mark.parametrize('source,hostname', [('feature/api', 'github.com'), ('alice:fix/login', 'github.com'), ('alice:fix/login', 'github.company.example')])
def test_multi_project_mixed_draft_save_or_discard(tmp_path, tracked_git_repo_factory, save, source, hostname, executable_bin):
    parent = tmp_path / 'projects'
    parent.mkdir()
    tracked_git_repo_factory(parent / 'api')
    (parent / 'assets').mkdir()
    if ':' in source:
        fork = tracked_git_repo_factory(tmp_path / 'renamed-fork')
        subprocess.run(['git', '-C', str(fork), 'checkout', '-b', 'fix/login'], check=True, capture_output=True)
        (fork / 'from-fork').write_text('fork-only content')
        subprocess.run(['git', '-C', str(fork), 'add', 'from-fork'], check=True)
        subprocess.run(['git', '-C', str(fork), 'commit', '-qm', 'fork change'], check=True)
        # Exercise real gh process discovery without contacting GitHub.
        fake_bin = executable_bin
        gh = fake_bin / 'gh'
        gh.write_text('#!/usr/bin/env python3\nimport json, sys\n'
                      f'assert sys.argv[sys.argv.index("--hostname") + 1] == {hostname!r}\n'
                      'base = {"full_name": "upstream/api", "owner": {"login": "upstream"}}\n'
                      'fork = {"full_name": "alice/renamed", "owner": {"login": "alice"}}\n'
                      'print(json.dumps([[fork]] if "--paginate" in sys.argv else base))\n')
        gh.chmod(0o755)
        subprocess.run(['git', '-C', str(parent / 'api'), 'remote', 'add', 'origin', f'https://{hostname}/upstream/api.git'], check=True)
        subprocess.run(['git', '-C', str(parent / 'api'), 'config', f'url.{fork}.insteadOf', f'https://{hostname}/alice/renamed.git'], check=True)

    home = tmp_path / 'home'
    config = home / 'orcan.config.json'
    sandbox = tmp_path / 'sandbox'
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 36, 120, 0, 0))
    env = {**os.environ, 'TERM': 'xterm-256color', 'ORCAN_HOME': str(home),
           'ORCAN_DATA': str(home), 'ORCAN_PROJECTS_ROOT': str(sandbox),
           'ORCAN_NAMED_INSTANCE': '', 'PYTHONPATH': str(ROOT / 'scripts/repository')}
    if ':' in source:
        env['PATH'] = str(fake_bin) + os.pathsep + env['PATH']
    proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/repository/context_tui.py'),
                             '--config', str(config), '--dir', str(parent)],
                            env=env, cwd=ROOT, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    terminal = pyte.Screen(120, 36)
    stream = pyte.Stream(terminal)
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    def until(text):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                stream.feed(decoder.decode(chunk))
                if text.decode() in '\n'.join(terminal.display):
                    return
            if proc.poll() is not None:
                break
        raise AssertionError(f'Missing {text!r} on terminal screen: ' + '\n'.join(terminal.display))
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
        os.write(master, b'\x7f' * len('feature/daily') + source.encode() + b'\n')
        until(b'Branch:')
        os.write(master, b'jjjjjj\n')
        until(b'api')
        assert not config.exists()
        assert not sandbox.exists()
        if save:
            os.write(master, b'jjjj\n')
            until(b'Save all workspace changes')
            os.write(master, b'y\n')
            deadline = time.monotonic() + 15
            while proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        stream.feed(decoder.decode(os.read(master, 65536)))
                    except OSError:
                        break
            assert proc.wait(timeout=2) == 0, '\n'.join(terminal.display)
            projects = json.loads(config.read_text())['workspaces'][0]['projects']
            assert projects[0]['path'] == str(sandbox / '.worktrees/daily/api')
            assert projects[1]['path'] == str(parent / 'assets')
            assert Path(projects[0]['path']).is_dir()
            if ':' in source:
                assert (Path(projects[0]['path']) / 'from-fork').read_text() == 'fork-only content'
                assert not (parent / 'api' / 'from-fork').exists()
        else:
            os.write(master, b'\x1b')
            until(b'Close / discard draft')
            os.write(master, b'\x1b')
            until(b'Discard unsaved changes')
            os.write(master, b'y\n')
            assert proc.wait(timeout=10) == 130
            assert not config.exists()
            assert not sandbox.exists()
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        os.close(master)
