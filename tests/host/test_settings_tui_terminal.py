"""Drive the real curses UI through a private PTY; no live terminal or runtime."""
from __future__ import annotations

import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import termios
import time
from pathlib import Path

import pytest

pytestmark=pytest.mark.integration
ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('save',[False,True])
@pytest.mark.parametrize('section',['plugins','agents'])
def test_settings_terminal_selection_review_save_and_cancel(tmp_path,save,section):
    path=tmp_path/'orcan.config.json'
    path.write_text('{"workspaces":[],"build":{"agents":["codex"],"tools":[]}}')
    before=path.read_bytes()
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',28,120,0,0))
    env={**os.environ,'TERM':'xterm-256color','ORCAN_HOME':str(tmp_path),'ORCAN_CONFIG_FILE':str(path),'ORCAN_RUNTIME_DIR':str(tmp_path/'mounts'),'CONFIG':''}
    proc=subprocess.Popen([str(ROOT/'bin/orcan'),'settings'],cwd=ROOT,env=env,stdin=slave,stdout=slave,stderr=slave,close_fds=True)
    os.close(slave)
    output=bytearray()

    def until(needle):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            ready,_,_=select.select([master],[],[],0.1)
            if ready:
                try:chunk=os.read(master,65536)
                except OSError:break
                if not chunk:break
                output.extend(chunk)
                if needle in output:return
            if proc.poll() is not None:break
        raise AssertionError('Terminal did not show '+repr(needle)+': '+repr(bytes(output[-1800:])))

    try:
        until(b'Orcan settings')
        if section=='plugins':
            os.write(master,b'j\n')
            until(b'background executor')
            os.write(master,b'jjjjj ')  # Redis row; toggle on.
        else:
            os.write(master,b'jj\n')
            until(b'Image contents only')
            os.write(master,b' ')  # Claude row; select it for the image.
        until(b'unsaved')
        if save:
            os.write(master,b'r')
            until(b'plugins.redis.enabled' if section=='plugins' else b'Image agents:')
            os.write(master,b's')
            until(b'Save the reviewed settings?')
            os.write(master,b'y\n')
        else:
            os.write(master,b'q')
            until(b'Discard unsaved changes?')
            os.write(master,b'y\n')
        assert proc.wait(timeout=8)==0
        if save:
            cfg=json.loads(path.read_text())
            if section=='plugins':
                assert cfg['plugins']['redis']['enabled'] is True
                assert cfg['build']['agents']==['codex']
            else:
                assert cfg['build']['agents']==['codex','claude']
                assert 'plugins' not in cfg
        else:assert path.read_bytes()==before
        assert not (tmp_path/'mounts').exists()
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        os.close(master)


def test_opening_ssh_setup_in_real_terminal_does_not_toggle_or_write(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text('{"workspaces":[]}')
    before=path.read_bytes()
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',28,100,0,0))
    env={**os.environ,'TERM':'xterm-256color','ORCAN_HOME':str(tmp_path),'ORCAN_CONFIG_FILE':str(path),'CONFIG':str(path)}
    proc=subprocess.Popen([str(ROOT/'bin/orcan'),'settings'],cwd=ROOT,env=env,stdin=slave,stdout=slave,stderr=slave,close_fds=True)
    os.close(slave)
    output=bytearray()
    def until(needle):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if select.select([master],[],[],0.1)[0]:
                try: chunk=os.read(master,65536)
                except OSError: break
                output.extend(chunk)
                if needle in output:return
            if proc.poll() is not None:break
        raise AssertionError('Missing terminal guidance: '+repr(needle)+': '+repr(bytes(output[-1200:])))
    try:
        until(b'Orcan settings')
        os.write(master,b'j\n')
        until(b'background executor')
        os.write(master,b'jjjjjj\n')
        until(b'SSH_AUTH_SOCK')
        os.write(master,b'q')
        assert proc.wait(timeout=8)==0
        assert path.read_bytes()==before
        assert not (tmp_path/'mounts').exists()
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=5)
        os.close(master)
