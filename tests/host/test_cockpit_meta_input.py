"""Exercise CLI keyboard negotiation and Meta events through a real outer PTY."""

import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHILD = r"""
import json, sys, types
from pathlib import Path
from orcan_cockpit.cli import main

def run():
    from textual.app import App
    from orcan_cockpit.pty_keys import key_to_bytes

    class Probe(App):
        def on_mount(self):
            self.call_after_refresh(Path(sys.argv[1]).touch)

        def on_key(self, event):
            data = key_to_bytes(event.key, event.character)
            with open(sys.argv[2], "a") as output:
                output.write(json.dumps([event.key, list(data or b"")]) + "\n")

    Probe().run()
    return 0

module = types.ModuleType("orcan_cockpit.app")
module.run_cockpit = run
sys.modules[module.__name__] = module
main()
"""


class MetaInputTests(unittest.TestCase):
    def test_cli_keeps_meta_in_legacy_input_without_kitty_negotiation(self):
        import importlib.util
        import json

        if importlib.util.find_spec("textual") is None:
            self.skipTest("cockpit dependencies unavailable")
        with tempfile.TemporaryDirectory(prefix="orcan-meta-") as directory:
            ready = Path(directory) / "ready"
            keys = Path(directory) / "keys"
            master, slave = pty.openpty()
            env = dict(os.environ, TERM="xterm-256color")
            env.pop("TEXTUAL_DISABLE_KITTY_KEY", None)
            env["PYTHONPATH"] = str(ROOT / "cockpit" / "src")
            process = subprocess.Popen(
                [sys.executable, "-c", CHILD, str(ready), str(keys)],
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
                self.fail("timed out waiting for cockpit keyboard input")

            try:
                until(ready.exists)
                # A Kitty-capable terminal would switch protocol when this is
                # requested, then send associated text which loses Alt.
                self.assertNotIn(b"\x1b[>25u", transcript)
                os.write(master, b"\x1bc")
                until(lambda: keys.exists() and len(keys.read_text().splitlines()) >= 1)
                os.write(master, b"\x1b1")
                until(lambda: len(keys.read_text().splitlines()) >= 2)
                received = [json.loads(line) for line in keys.read_text().splitlines()]
                self.assertEqual([entry[1] for entry in received], [[27, 99], [27, 49]])
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                os.close(master)
                os.close(slave)
