"""Delayed real PTY output must paint without keyboard, cursor blink or focus."""

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

try:
    from orcan_cockpit.pty_terminal import PtyTerminal
    from textual.app import App, ComposeResult
    from textual.widgets import Button
except ModuleNotFoundError:
    PtyTerminal = None

CHILD = r"""
import os,signal,sys,time,tty,select
from pathlib import Path

tty.setraw(0)
def paint(label):
    cols,rows=os.get_terminal_size(0)
    parts=['\x1b[?25l\x1b[2J']
    for y in range(rows):
        text=(label+':'+str(y)).ljust(cols-1,'.')[:cols-1]+'#'
        parts.append('\x1b['+str(y+1)+';1H'+text)
    os.write(1,''.join(parts).encode())
signal.signal(signal.SIGWINCH,lambda *_:paint('resized'))
paint('initial')
while not Path(sys.argv[1]).exists(): time.sleep(.01)
time.sleep(.25)
paint('late')
os.write(1,b'\x1b[2;3H\x1b[6n')
response=b''
end=time.monotonic()+2
while not response.endswith(b'R') and time.monotonic()<end:
    if select.select([0],[],[],.1)[0]: response+=os.read(0,128)
if response != b'\x1b[2;3R':
    paint('no-reply')
else:
    paint('reply-ok')
    time.sleep(.25)
    paint('idle-final')
time.sleep(60)
"""


@pytest.mark.integration
@unittest.skipIf(PtyTerminal is None, "cockpit dependencies unavailable")
class IdleRenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_output_protocol_reply_and_resize_fill_every_row(self):
        with tempfile.TemporaryDirectory(prefix="orcan-idle-pty-") as root:
            gate = Path(root) / "start"
            await self.exercise([sys.executable, "-u", "-c", CHILD, str(gate)], gate)

    async def test_tmux_idle_output_and_resize_without_keyboard(self):
        if shutil.which("tmux") is None:
            self.skipTest("tmux unavailable")
        with tempfile.TemporaryDirectory(prefix="orcan-idle-tmux-") as root:
            socket = str(Path(root) / "socket")
            gate = Path(root) / "start"

            def tmux(*arguments):
                return subprocess.run(
                    ["tmux", "-S", socket, *arguments],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )

            try:
                tmux(
                    "-f",
                    "/dev/null",
                    "new-session",
                    "-d",
                    "-s",
                    "fixture",
                    "-x",
                    "32",
                    "-y",
                    "9",
                )
                tmux("set-option", "-g", "status", "off")
                tmux(
                    "respawn-pane",
                    "-k",
                    "-t",
                    "fixture:0.0",
                    shlex.join([sys.executable, "-u", "-c", CHILD, str(gate)]),
                )
                await self.exercise(
                    ["tmux", "-S", socket, "attach-session", "-t", "fixture"], gate
                )
            finally:
                subprocess.run(
                    ["tmux", "-S", socket, "kill-server"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )

    async def test_plain_mouse_drag_selects_lines_instead_of_terminal_container(self):
        from orcan_cockpit.pty_links import attach_hyperlink_screen, feed_with_osc8

        class Terminal(PtyTerminal):
            @staticmethod
            def _purge_staged_pastes():
                pass

            def on_mount(self, event):
                event.prevent_default()
                Screen, Stream = attach_hyperlink_screen()
                self._screen = Screen(30, 10)
                self._stream = Stream(self._screen)
                for y in range(10):
                    feed_with_osc8(
                        self._stream,
                        self._screen,
                        f"\x1b[{y + 1};1Hrow{y} abcdefghijkl",
                    )
                self.refresh()

        class Harness(App):
            def compose(self):
                yield Terminal(["true"])

        app = Harness()
        async with app.run_test(size=(30, 10)) as pilot:
            term = app.query_one(Terminal)
            await pilot.pause()
            await pilot.mouse_down(Terminal, offset=(2, 1))
            await pilot.hover(Terminal, offset=(4, 3))
            await pilot.mouse_up(Terminal, offset=(4, 3))
            await pilot.pause()
            selection = term.text_selection
            self.assertIsNotNone(selection)
            self.assertIsNone(selection.get_span(0))
            self.assertIsNone(selection.get_span(4))
            self.assertEqual(
                term.get_selection(selection)[0],
                "w1 abcdefghijkl\nrow2 abcdefghijkl\nrow3 ".rstrip(),
            )
            # Offsets must survive repainting an existing selection/cursor.
            widget, offset = app.screen.get_widget_and_offset_at(4, 3)
            self.assertIs(widget, term)
            self.assertEqual((offset.x, offset.y), (4, 3))

    async def exercise(self, command, gate):
        class Terminal(PtyTerminal):
            def __init__(self):
                super().__init__(
                    command,
                    env={
                        **{
                            key: value
                            for key, value in os.environ.items()
                            if key not in {"TMUX", "TMUX_PANE"}
                        },
                        "TERM": "xterm-256color",
                    },
                    id="terminal",
                )
                self.painted = {}

            @staticmethod
            def _purge_staged_pastes():
                pass  # Fixtures never inspect or expire user paste files.

            def render_line(self, y):
                strip = super().render_line(y)
                self.painted[y] = "".join(segment.text for segment in strip)
                return strip

        class Harness(App):
            CSS = "Button {height:3;} #terminal {height:1fr; width:1fr;}"

            def compose(self) -> ComposeResult:
                yield Button("Other focus", id="other")
                yield Terminal()

        async def until(predicate, timeout=4):
            async with asyncio.timeout(timeout):
                while not predicate():
                    await asyncio.sleep(0.01)

        app = Harness()
        process = None
        try:
            async with app.run_test(size=(32, 12)) as pilot:
                term = app.query_one(Terminal)
                await until(lambda: term._ready)
                process = term._process
                app.set_focus(app.query_one(Button))
                gate.touch()
                try:
                    await until(
                        lambda: term.painted.get(0, "").startswith("idle-final:")
                    )
                except TimeoutError:
                    self.fail(
                        f"idle frame missing: painted={list(term.painted.items())[:3]!r}; screen={term._screen.display[:3]!r}; size={term._term_size()}; child={process.poll() if process is not None else 'closed'}"
                    )
                self.assertFalse(term.has_focus)
                rows, cols = term._term_size()
                await until(
                    lambda: term.painted.get(rows - 1, "").startswith("idle-final:")
                )
                self.assertEqual((cols, rows), (32, 9))
                for y in range(rows):
                    self.assertEqual(len(term.painted[y]), cols)
                    self.assertTrue(term.painted[y].endswith("#"))
                await pilot.resize_terminal(48, 16)
                await until(lambda: term.painted.get(12, "").startswith("resized:"))
                self.assertEqual(term._term_size(), (13, 48))
                for y in range(13):
                    self.assertEqual(len(term.painted[y]), 48)
                    self.assertTrue(term.painted[y].endswith("#"))
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                await asyncio.to_thread(process.wait, 3)
