import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "scripts" / "dev" / "terminal-ui-preview"


@unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
class TerminalUiPreviewTests(unittest.TestCase):
    def test_check_loads_ui_on_an_isolated_server(self):
        result = subprocess.run(
            [str(PREVIEW), "tmux", "--check", "--size", "90x24"],
            cwd=ROOT, check=False, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UI preview check OK", result.stdout)
        self.assertIn("status=1", result.stdout)
        self.assertIn("windows=3", result.stdout)

    def test_rejects_invalid_size(self):
        result = subprocess.run(
            [str(PREVIEW), "--check", "--size", "wide"],
            cwd=ROOT, check=False, text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid size", result.stderr)


if __name__ == "__main__":
    unittest.main()
