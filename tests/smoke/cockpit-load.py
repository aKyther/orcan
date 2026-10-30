"""Finite, private-tmux responsiveness benchmark; run heavy cases in a capped container."""

import argparse
import asyncio
import json
import math
import os
import re
import select
import shlex
import subprocess
import sys
import tempfile
import time
import tty
from pathlib import Path
from unittest.mock import patch


def producer(flood):
    tty.setraw(0)
    os.write(1, b"\x1b[1;1HACK:00000000\x1b[2;20r\x1b[2;1Hready\r\n")
    number = 0
    output = (b"\x1b[36m" + b"load " * 16 + b"\x1b[0m\r\n") * 32
    while True:
        readable, _, _ = select.select([0], [], [], 0 if flood else 0.05)
        if readable:
            for key in os.read(0, 4096):
                if key == ord("x"):
                    number += 1
                    os.write(1, f"\x1b7\x1b[1;1HACK:{number:08d}\x1b8".encode())
        if flood:
            rows = max(2, os.get_terminal_size(1).lines)
            os.write(
                1,
                f"\x1b[2;{rows}r\x1b[1;1HACK:{number:08d}\x1b[{rows};1H".encode()
                + output,
            )


def percentile(values, q):
    values = sorted(values)
    return (
        round(values[min(len(values) - 1, max(0, math.ceil(len(values) * q) - 1))], 2)
        if values
        else None
    )


async def scenario(root, name, duration, *, flood, slow_metadata=False, cpu=False):
    from orcan_cockpit import picker
    from orcan_cockpit.pty_terminal import PtyTerminal
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal

    socket = root / (name + ".sock")
    config = root / "tmux.conf"
    config.write_text("set -g default-shell /bin/sh\nset -g status off\n")
    command = shlex.join(
        [sys.executable, str(Path(__file__).resolve()), "--producer"]
        + (["--flood"] if flood else [])
    )
    tmux = ["tmux", "-S", str(socket), "-f", str(config)]
    await asyncio.to_thread(
        subprocess.run,
        [*tmux, "new-session", "-d", "-x", "120", "-y", "36", "-s", "load", command],
        check=True,
        capture_output=True,
    )
    burner = (
        await asyncio.to_thread(
            subprocess.Popen,
            [sys.executable, "-c", "while True: sum(range(50000))"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if cpu
        else None
    )
    lag, reads, keys = [], [], []
    sent = {}
    ready = asyncio.Event()
    key_count = 0
    byte_count = 0
    rows = [
        {
            "name": f"fixture-{i}",
            "root": str(root),
            "session": f"fixture-{i}",
            "live": True,
            "repo_count": 6,
            "projects": [{"name": "fixture", "path": str(root)}] * 6,
        }
        for i in range(20)
    ]

    def list_rows():
        if slow_metadata:
            time.sleep(0.2)
        return rows

    def label(_project):
        if slow_metadata:
            time.sleep(0.03)
        return "fixture-branch"

    def glance(*args, **kwargs):
        if slow_metadata:
            time.sleep(0.2)
        return ["synthetic metadata"]

    class Terminal(PtyTerminal):
        def _note_mouse_modes(self, data):
            nonlocal byte_count
            byte_count += len(data)
            super()._note_mouse_modes(data)

        def _on_readable(self):
            began = time.perf_counter()
            super()._on_readable()
            reads.append((time.perf_counter() - began) * 1000)
            if self._screen:
                row = self._screen.buffer[0]
                text = "".join(
                    row[x].data for x in range(min(self._screen.columns, 20))
                )
                match = re.search(r"ACK:(\d+)", text)
                if match:
                    ready.set()
                    acknowledged = int(match[1])
                    for sequence in list(sent):
                        if sequence <= acknowledged:
                            keys.append(
                                (time.perf_counter() - sent.pop(sequence)) * 1000
                            )

        @staticmethod
        def _purge_staged_pastes():
            pass  # Never inspect or expire a user's staged paste files.

    class Harness(App):
        CSS = "Horizontal {height:1fr;} WorkspaceList {width:38;height:1fr;} PtyTerminal {width:1fr;height:1fr;}"

        def compose(self) -> ComposeResult:
            with Horizontal():
                yield picker.WorkspaceList(id="workspace-list-widget")
                yield Terminal([*tmux, "attach-session", "-t", "load"], id="terminal")

    try:
        with (
            patch.object(picker, "list_workspace_rows", list_rows),
            patch.object(picker, "project_git_label", label),
            patch.object(picker, "glance_lines", glance),
            patch.object(picker, "read_recent_sessions", list),
        ):
            app = Harness()
            async with app.run_test(size=(120, 36)):
                terminal = app.query_one(Terminal)
                listing = app.query_one(picker.WorkspaceList)
                listing._expanded = slow_metadata
                terminal.focus()
                await asyncio.wait_for(ready.wait(), 5)
                deadline = time.perf_counter() + duration

                async def heartbeat():
                    while time.perf_counter() < deadline:
                        target = time.perf_counter() + 0.025
                        await asyncio.sleep(0.025)
                        lag.append(max(0, time.perf_counter() - target) * 1000)

                async def keyboard():
                    nonlocal key_count
                    from textual.events import Key

                    while time.perf_counter() < deadline:
                        key_count += 1
                        sent[key_count] = time.perf_counter()
                        terminal.post_message(Key("x", "x"))
                        await asyncio.sleep(0.25)

                async def metadata():
                    while time.perf_counter() < deadline:
                        if slow_metadata:
                            listing.refresh_rows()
                        await asyncio.sleep(0.5)

                await asyncio.gather(heartbeat(), keyboard(), metadata())
                await asyncio.sleep(0.3)
                if not keys:
                    captured = (
                        await asyncio.to_thread(
                            subprocess.run,
                            [*tmux, "capture-pane", "-pt", "load"],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                    ).stdout
                    screen = terminal._screen.display[:3] if terminal._screen else []
                    raise AssertionError(
                        f"{name}: no ACK; sent={key_count}; pyte={screen}; pane={captured[:700]!r}"
                    )
        return {
            "scenario": name,
            "duration_seconds": duration,
            "input_sent": key_count,
            "input_acknowledged": len(keys),
            "pending_input": len(sent),
            "input_p95_ms": percentile(keys, 0.95),
            "input_max_ms": percentile(keys, 1),
            "loop_p95_ms": percentile(lag, 0.95),
            "loop_max_ms": percentile(lag, 1),
            "read_p95_ms": percentile(reads, 0.95),
            "read_max_ms": percentile(reads, 1),
            "pty_bytes": byte_count,
        }
    finally:
        if burner:
            burner.terminate()
            await asyncio.to_thread(burner.wait, timeout=5)
        await asyncio.to_thread(
            subprocess.run,
            [*tmux, "kill-server"],
            check=False,
            capture_output=True,
            timeout=5,
        )


async def benchmark(args):
    with tempfile.TemporaryDirectory(prefix="orcan-load-") as directory:
        root = Path(directory)
        config = root / "runtime.json"
        config.write_text("{}")
        with patch.dict(
            os.environ,
            {
                "ORCAN_CONFIG": str(config),
                "ORCAN_COCKPIT_STATE_PATH": str(root / "state"),
            },
        ):
            results = []
            for name, options in [
                ("idle", {"flood": False}),
                ("output", {"flood": True}),
                ("slow-metadata", {"flood": True, "slow_metadata": True}),
                ("cpu-contention", {"flood": True, "cpu": True}),
            ]:
                results.append(await scenario(root, name, args.seconds, **options))
            report = {"kind": "headless Textual/private tmux", "results": results}
            if args.report:
                Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", action="store_true")
    parser.add_argument("--flood", action="store_true")
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.producer:
        producer(args.flood)
    elif 1 <= args.seconds <= 30:
        asyncio.run(benchmark(args))
    else:
        parser.error("seconds must be between 1 and 30")
