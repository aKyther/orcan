"""Peek body builder — stdlib-only so host tests need no Textual."""

from __future__ import annotations

from pathlib import Path


def build_peek_text(workspace_root: Path) -> str:
    """Plain session-brief preview."""
    sections: list[str] = []
    brief = workspace_root / ".orcan" / "session-brief.md"
    if brief.is_file():
        try:
            text = brief.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            sections.append("SESSION BRIEF\n" + text[:1200])

    if not sections:
        return "(nothing to peek)"
    return "\n\n".join(sections)
