#!/usr/bin/env python3
"""AGENTS.md and CLAUDE.md must stay identical (Cursor vs Claude Code)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class AgentsClaudeSyncTests(unittest.TestCase):
    def test_agents_and_claude_md_are_identical(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(
            agents,
            claude,
            "AGENTS.md and CLAUDE.md must match; edit one and copy to the other",
        )
        self.assertIn("30-second map", agents)
        self.assertIn("make dev-", agents)

    def test_seed_templates_include_both(self) -> None:
        templates = ROOT / "docker/rootfs/opt/cursor-defaults/templates"
        agents = (templates / "AGENTS.md").read_text(encoding="utf-8")
        claude = (templates / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(agents.startswith("# AGENTS.md\n"))
        self.assertTrue(claude.startswith("# CLAUDE.md\n"))
        self.assertIn("Keep `AGENTS.md` and `CLAUDE.md` identical", agents)
        self.assertIn("Keep `AGENTS.md` and `CLAUDE.md` identical", claude)


if __name__ == "__main__":
    unittest.main()
