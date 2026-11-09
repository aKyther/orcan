"""Real PTY flood and stalled browser must leave Textual input responsive."""

import asyncio
import sys
import threading
from unittest.mock import patch

from textual.app import App, ComposeResult

from orcan_cockpit import pty_terminal


async def check():
    class Harness(App):
        ticks = 0
        keys = []

        def compose(self) -> ComposeResult:
            yield pty_terminal.PtyTerminal(
                [sys.executable, "-u", "-c", "import os\nwhile True: os.write(1, b'load\\r\\n' * 1024)"],
                session="fixture",
            )

        def on_mount(self):
            self.set_interval(0.02, self.tick)

        def tick(self):
            self.ticks += 1

    app = Harness()
    started, release = threading.Event(), threading.Event()
    calls = []

    def browser(url):
        calls.append(url)
        started.set()
        assert release.wait(5)
        return True

    try:
        async with app.run_test(size=(80, 24)) as pilot:
            terminal = app.query_one(pty_terminal.PtyTerminal)
            async with asyncio.timeout(4):
                while not terminal._ready:
                    await asyncio.sleep(0.01)
            # The real child keeps the PTY readable throughout these events.
            with patch.object(terminal, "_write_pty", side_effect=app.keys.append):
                await pilot.press("a", "b", "c")
            assert app.keys == [b"a", b"b", b"c"]
            assert app.ticks >= 2
            with patch.object(pty_terminal, "open_url", browser):
                terminal.run_worker(terminal._open_link("https://example.com"), group="pty-link", exclusive=True)
                async with asyncio.timeout(4):
                    while not started.is_set():
                        await asyncio.sleep(0.01)
                before = app.ticks
                # Cancelling a waiter must not launch another browser helper.
                terminal.run_worker(terminal._open_link("https://example.org"), group="pty-link", exclusive=True)
                with patch.object(terminal, "_write_pty", side_effect=app.keys.append):
                    await pilot.press("d")
                    await pilot.pause(0.1)
                assert app.keys[-1] == b"d"
                assert app.ticks > before
                assert calls == ["https://example.com"]
                release.set()
                await app.workers.wait_for_complete()
    finally:
        release.set()


if __name__ == "__main__":
    asyncio.run(check())
    print("Cockpit IO passed: real PTY flood, keyboard, timers, stalled browser, single-flight")
