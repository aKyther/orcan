"""Real curses modal input, including layout, editing, mouse and resize."""

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

import pyte
import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
CHILD = r"""
import curses,json,sys,fcntl,termios
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from pathlib import Path
from context_tui import _init_curses_session, _prompt_line

def run(screen):
    screen.keypad(True)
    _init_curses_session()
    screen.addstr(1, 1, "Workspace editor background")
    screen.refresh()
    value = _prompt_line(screen, sys.argv[2], sys.argv[3])
    assert screen.instr(1, 1, 9).decode() == "Workspace"
    Path(sys.argv[1]).write_text(json.dumps(value))

curses.wrapper(run)
"""


@pytest.fixture
def dialog(tmp_path):
    processes = []

    def start(label="New workspace name", initial="", term="xterm-256color"):
        result = tmp_path / f"result-{len(processes)}.json"
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        process = subprocess.Popen(
            [sys.executable, "-c", CHILD, str(result), label, initial],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env={
                **os.environ,
                "TERM": term,
                "PYTHONPATH": str(ROOT / "scripts/repository"),
            },
        )
        os.close(slave)
        processes.append((process, master))
        screen = pyte.Screen(80, 24)
        stream = pyte.ByteStream(screen)
        output = bytearray()

        def until(predicate):
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.02)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    output.extend(chunk)
                    stream.feed(chunk)
                if predicate():
                    return
                if process.poll() is not None:
                    break
            raise AssertionError(
                f"dialog did not reach expected state: {bytes(output[-1500:])!r}"
            )

        def finish(keys):
            os.write(master, keys)
            until(result.exists)
            assert process.wait(timeout=3) == 0
            return json.loads(result.read_text())

        until(lambda: any(label in line for line in screen.display))
        return master, screen, until, finish

    yield start
    for process, master in processes:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
        os.close(master)


@pytest.mark.parametrize(
    "label",
    [
        "New workspace name",
        "Branch for this project",
        "Parent directory",
        "Filter",
        "Version for codex",
    ],
)
def test_shared_fields_are_centered_with_actions(dialog, label):
    _, screen, _, finish = dialog(label)
    row = next(i for i, line in enumerate(screen.display) if label in line)
    assert row == 8  # 9-row dialog centered in a 24-row terminal.
    assert "[ Confirm ]" in screen.display[14]
    assert "[ Cancel ]" in screen.display[14]
    assert "Workspace editor background" in screen.display[1]
    assert finish("nowy-żółw\n".encode()) == "nowy-żółw"


@pytest.mark.parametrize(
    "keys,expected",
    [
        (b"\x01new-\x05\x7fX\n", "new-featurX"),
        (b"\x1b", None),
        (b"\t\t\n", None),
        (b"\t\n", "feature"),
        (b"\n", "feature"),
    ],
)
def test_edit_confirm_and_cancel(dialog, keys, expected):
    *_, finish = dialog(initial="feature")
    assert finish(keys) == expected


def test_long_wide_text_scrolls_and_resize_preserves_input(dialog):
    initial = "界" * 90 + "/feature"
    master, screen, until, finish = dialog("Branch for this project", initial)
    assert 6 <= screen.cursor.y <= 15
    assert 0 <= screen.cursor.x < 80
    # Resize down: edit is retained, and the modal waits for room to return.
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 7, 25, 0, 0))
    until(lambda: b"Resize" in b"\n".join(line.encode() for line in screen.display))
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    screen.resize(30, 100)
    until(lambda: "Branch for this project" in screen.display[11])
    assert finish(b"X\n") == initial + "X"


@pytest.mark.parametrize("column,expected", [(7, "feature"), (67, None)])
def test_click_dialog_actions(dialog, column, expected):
    *_, finish = dialog(initial="feature")
    # SGR left-button release in the Confirm/Cancel row (terminal coordinates).
    assert finish(f"\x1b[<0;{column};15M\x1b[<0;{column};15m".encode()) == expected


def test_dialog_also_works_without_terminal_colors(dialog):
    *_, finish = dialog(term="vt100")
    assert finish(b"plain-name\n") == "plain-name"
