import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "scripts" / "dev" / "orcan-preview"


class OrcanPreviewTests(unittest.TestCase):
    def run_preview(self, *args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "ORCAN_PREVIEW_ROOT": tmp, **overrides}
            return subprocess.run(
                [str(PREVIEW), *args], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=10,
            )

    def test_check_generates_an_isolated_preview_profile(self) -> None:
        result = self.run_preview("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("isolation check OK", result.stdout)

    def test_refuses_production_identifiers(self) -> None:
        cases = (
            {"ORCAN_PREVIEW_PROJECT": "orcan"},
            {"ORCAN_PREVIEW_INSTANCE": "1"},
            {"ORCAN_PREVIEW_IMAGE": "orcan:latest"},
            {"ORCAN_PREVIEW_PORT": "7681"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = self.run_preview("check", **overrides)
                self.assertNotEqual(result.returncode, 0)

    def test_url_uses_the_configured_port(self) -> None:
        result = self.run_preview("url", ORCAN_PREVIEW_PORT="19001")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "http://127.0.0.1:19001")

    def test_check_accepts_isolated_custom_identifiers(self) -> None:
        result = self.run_preview(
            "check",
            ORCAN_PREVIEW_PROJECT="orcan-review-a",
            ORCAN_PREVIEW_INSTANCE="review-a",
            ORCAN_PREVIEW_IMAGE="orcan:review-a",
            ORCAN_PREVIEW_PORT="19001",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_documents_lifecycle_commands(self) -> None:
        result = self.run_preview("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("up", "rebuild", "status", "url", "logs", "shell", "down", "check"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
