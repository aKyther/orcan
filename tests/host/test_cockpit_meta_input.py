"""Exercise Meta input through the outer driver, PtyTerminal and isolated tmux."""

import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHILD = r"""
import os, sys
from pathlib import Path
from orcan_cockpit.cli import main
from orcan_cockpit import app as cockpit_app
from textual.app import App
from textual import constants
from orcan_cockpit.pty_terminal import PtyTerminal
previous = os.environ.get("TEXTUAL_DISABLE_KITTY_KEY")

class Probe(App):
    def compose(self):
        child = 'import os,sys; from pathlib import Path; Path(sys.argv[2]).write_text(os.environ.get("TEXTUAL_DISABLE_KITTY_KEY", "unset")); os.execvp("tmux", ["tmux", "-S", sys.argv[1], "attach", "-t", "fixture"])'
        yield PtyTerminal([sys.executable, "-c", child, sys.argv[2], sys.argv[1] + ".env"], id="terminal")

    def on_mount(self):
        self.query_one(PtyTerminal).focus()
        self.call_after_refresh(Path(sys.argv[1]).touch)

def run():
    assert os.environ.get("TEXTUAL_DISABLE_KITTY_KEY") == previous
    assert constants.DISABLE_KITTY_KEY
    Probe().run()
    return 0

# Replace the workspace picker/layout only. Keep the real app module, CLI,
# terminal widget, input handler, nested PTY and tmux server.
cockpit_app.run_cockpit = run
main()
"""


@pytest.mark.integration
class MetaInputTests(unittest.TestCase):
    def test_meta_creates_and_selects_tmux_windows_without_environment_leak(self):
        import importlib.util

        if importlib.util.find_spec("textual") is None:
            self.skipTest("cockpit dependencies unavailable")
        if shutil.which("tmux") is None:
            self.skipTest("tmux unavailable")
        for previous in (None, "0"):
            with self.subTest(previous=previous):
                self.exercise(previous)

    def exercise(self, previous):
        with tempfile.TemporaryDirectory(prefix="orcan-meta-") as directory:
            ready = Path(directory) / "ready"
            socket = str(Path(directory) / "socket")
            tmux = ["tmux", "-S", socket]

            def command(*args):
                return subprocess.run(
                    [*tmux, *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout.strip()

            master = slave = process = None
            try:
                command("-f", "/dev/null", "new-session", "-d", "-s", "fixture")
                command("set-option", "-g", "base-index", "1")
                command("move-window", "-s", "fixture:0", "-t", "fixture:1")
                command(
                    "source-file", str(ROOT / "docker/rootfs/etc/tmux/keybindings.conf")
                )
                master, slave = pty.openpty()
                env = dict(os.environ, TERM="xterm-256color")
                env.pop("TMUX", None)
                env.pop("TEXTUAL_DISABLE_KITTY_KEY", None)
                if previous is not None:
                    env["TEXTUAL_DISABLE_KITTY_KEY"] = previous
                env["PYTHONPATH"] = os.pathsep.join(
                    [
                        str(ROOT / "cockpit/src"),
                        str(ROOT / "docker/rootfs/usr/local/lib"),
                    ]
                )
                process = subprocess.Popen(
                    [sys.executable, "-c", CHILD, str(ready), socket],
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    env=env,
                    start_new_session=True,
                )
                transcript = bytearray()

                def until(predicate):
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.02)[0]:
                            transcript.extend(os.read(master, 65536))
                        if predicate():
                            return
                        if process.poll() is not None:
                            self.fail("probe exited before receiving input")
                    self.fail("timed out waiting for cockpit/tmux input")

                until(ready.exists)
                until(lambda: bool(command("list-clients", "-F", "#{client_name}")))
                self.assertNotIn(b"\x1b[>25u", transcript)
                os.write(master, b"\x1bc")
                until(
                    lambda: (
                        command(
                            "display-message",
                            "-p",
                            "-t",
                            "fixture",
                            "#{session_windows}",
                        )
                        == "2"
                    )
                )
                self.assertEqual(
                    command(
                        "display-message", "-p", "-t", "fixture", "#{window_index}"
                    ),
                    "2",
                )
                os.write(master, b"\x1b1")
                until(
                    lambda: (
                        command(
                            "display-message", "-p", "-t", "fixture", "#{window_index}"
                        )
                        == "1"
                    )
                )
                os.write(master, b"\x1b2")
                until(
                    lambda: (
                        command(
                            "display-message", "-p", "-t", "fixture", "#{window_index}"
                        )
                        == "2"
                    )
                )
                self.assertEqual(
                    Path(str(ready) + ".env").read_text(),
                    previous if previous is not None else "unset",
                )
            finally:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                subprocess.run(
                    [*tmux, "kill-server"], check=False, capture_output=True, timeout=3
                )
                if master is not None:
                    os.close(master)
                if slave is not None:
                    os.close(slave)
