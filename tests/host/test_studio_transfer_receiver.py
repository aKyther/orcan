"""Exercise the embedded receiver with real partial files and subprocess stdin."""

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "studio/app/src-tauri/src/transfer_receiver.py"
)
TOKEN = "12345678-1234-1234-1234-123456789abc"


@unittest.skipIf(sys.platform == "win32", "receiver runs on Linux/macOS destinations")
class TransferReceiverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.payload = self.home / ".cache/orcan-studio-transfers" / TOKEN / "payload"
        self.data = b"binary\x00payload\xff" * 100
        self.digest = hashlib.sha256(self.data).hexdigest()

    def run_receiver(self, mode, *args, data=b"", token=TOKEN):
        return subprocess.run(
            [sys.executable, str(SCRIPT), mode, token, *map(str, args)],
            input=data,
            capture_output=True,
            env={**os.environ, "HOME": str(self.home)},
            check=False,
        )

    def test_interruption_resume_and_verified_install(self):
        inspected = self.run_receiver("inspect")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(
            inspected.stdout.strip(), f"0\t{hashlib.sha256(b'').hexdigest()}".encode()
        )
        first = self.run_receiver(
            "append", 0, len(self.data), self.digest, data=self.data[:73]
        )
        self.assertNotEqual(first.returncode, 0)
        self.assertEqual(self.payload.read_bytes(), self.data[:73])
        inspected = self.run_receiver("inspect")
        self.assertEqual(
            inspected.stdout.strip(),
            f"73\t{hashlib.sha256(self.data[:73]).hexdigest()}".encode(),
        )
        marker = self.home / "installed"
        command = f"printf installed > '{marker}'"
        refused = self.run_receiver("install", len(self.data), self.digest, command)
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse(marker.exists())
        resumed = self.run_receiver(
            "append", 73, len(self.data), self.digest, data=self.data[73:]
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(self.payload.read_bytes(), self.data)
        installed = self.run_receiver("install", len(self.data), self.digest, command)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(marker.read_text(), "installed")
        self.assertEqual(self.run_receiver("remove").returncode, 0)
        self.assertFalse(self.payload.parent.exists())

    def test_wrong_offset_and_corrupt_payload_do_not_install(self):
        self.run_receiver("inspect")
        refused = self.run_receiver(
            "append", 1, len(self.data), self.digest, data=self.data
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.payload.stat().st_size, 0)
        corrupt = self.run_receiver(
            "append", 0, len(self.data), self.digest, data=b"x" * len(self.data)
        )
        self.assertNotEqual(corrupt.returncode, 0)
        self.assertNotEqual(
            self.run_receiver(
                "install", len(self.data), self.digest, "true"
            ).returncode,
            0,
        )

    def test_unsafe_token_and_symlink_are_rejected(self):
        self.assertNotEqual(
            self.run_receiver("inspect", token="../outside").returncode, 0
        )
        self.run_receiver("inspect")
        self.payload.unlink()
        outside = self.home / "outside"
        outside.write_bytes(b"preserve")
        self.payload.symlink_to(outside)
        self.assertNotEqual(
            self.run_receiver("append", 0, 1, "bad", data=b"x").returncode, 0
        )
        self.assertEqual(outside.read_bytes(), b"preserve")

    def test_stale_cleanup_skips_active_and_unknown_files(self):
        import fcntl

        self.run_receiver("inspect")
        lease_path = self.payload.parent / ".lease"
        old = time.time() - 90000
        for path in [lease_path, self.payload]:
            os.utime(path, (old, old))
        other = "abcdefab-1234-1234-1234-123456789abc"
        with lease_path.open("r+b") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX)
            self.assertEqual(self.run_receiver("inspect", token=other).returncode, 0)
            self.assertTrue(self.payload.exists())
        unknown = self.payload.parent / "keep.txt"
        unknown.write_text("keep")
        self.run_receiver("inspect", token=other)
        self.assertTrue(unknown.exists())
        unknown.unlink()
        self.run_receiver("inspect", token=other)
        self.assertFalse(self.payload.parent.exists())

    def test_private_permissions(self):
        self.run_receiver("inspect")
        self.assertEqual(self.payload.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.payload.parent.stat().st_mode & 0o777, 0o700)
