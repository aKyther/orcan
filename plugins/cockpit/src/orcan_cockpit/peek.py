"""Peek body builder — stdlib-only so host tests need no Textual."""

from __future__ import annotations

from pathlib import Path


def build_peek_text(workspace_root: Path) -> str:
    """Plain session-brief preview."""
    sections: list[str] = []
    brief = workspace_root / ".orcan" / "session-brief.md"
    if brief.is_file():
        try:
            from orcan_cockpit.runtime_limits import limits

            maximum = limits()["peek_chars"]
            with brief.open(encoding="utf-8") as source:
                text = source.read(maximum).strip()
        except (OSError, UnicodeError):
            text = ""
        if text:
            sections.append("SESSION BRIEF\n" + text[:maximum])

    if not sections:
        return "(nothing to peek)"
    return "\n\n".join(sections)
