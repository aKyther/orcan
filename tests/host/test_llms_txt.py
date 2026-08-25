#!/usr/bin/env python3
"""Guard rails for docs/llms.txt — orientation for external agents."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "repository" / "generate-llms-txt.py"
LLMS = ROOT / "docs" / "llms.txt"

# Phrases that encode what matters / what not — keep these if the file is rewritten.
REQUIRED = (
    "## Editing this repository (30 seconds)",
    "## Source priority (highest first)",
    "## Pay attention to (core product)",
    "## Do not invent / out of scope (non-goals)",
    "## Care about when changing the Orcan repo",
    "path parity",
    "orcan.config.json",
    "Model selection",
    "make dev-",
    "cockpit/pyproject.toml",
    "context pack",
    "CLAUDE.md",
)


class LlmsTxtTests(unittest.TestCase):
    def test_generator_writes_opinionated_orientation(self) -> None:
        proc = subprocess.run(
            ["python3", str(GENERATOR)],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = LLMS.read_text(encoding="utf-8")
        for needle in REQUIRED:
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertTrue(text.startswith("# Orcan\n"))
        self.assertIn("Does **not** choose, route, or pin models", text)
        self.assertGreater(len(text), 1500)


if __name__ == "__main__":
    unittest.main()
