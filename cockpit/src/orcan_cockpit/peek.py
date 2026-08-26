"""Peek body builder — stdlib-only so host tests need no Textual."""

from __future__ import annotations

import sys
from pathlib import Path

for _lib in (
    Path("/usr/local/lib"),
    Path(__file__).resolve().parents[3] / "docker" / "rootfs" / "usr" / "local" / "lib",
):
    if (_lib / "orcan" / "context_inbox.py").is_file():
        sys.path.insert(0, str(_lib))
        break

from orcan.context_inbox import load_inbox_candidates  # noqa: E402

try:
    from orcan_cockpit.reflection_feedback import last_batch_feedback
except ImportError:  # host file-path load without package install
    import importlib.util

    _rf = Path(__file__).resolve().parent / "reflection_feedback.py"
    _spec = importlib.util.spec_from_file_location("_peek_reflection_feedback", _rf)
    _mod = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_mod)
    last_batch_feedback = _mod.last_batch_feedback


def build_peek_text(workspace_root: Path) -> str:
    """Plain multiline peek body (brief + last batch + first pending note)."""
    sections: list[str] = []
    brief = workspace_root / ".orcan" / "session-brief.md"
    if brief.is_file():
        try:
            text = brief.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            sections.append("SESSION BRIEF\n" + text[:1200])

    sections.append("REFLECTION\n" + last_batch_feedback(workspace_root))

    candidates = load_inbox_candidates(workspace_root)
    queue_path = workspace_root / ".orcan" / "context-review-queue.json"
    if candidates:
        item = candidates[0]
        title = item.get("title") or "(no title)"
        body = item.get("content") or ""
        sections.append(
            "NEXT PENDING NOTE\n"
            f"Title: {title}\n"
            f"Body:  {body}\n"
            "(Full queue: Enter/r → Review — not the same as preview fixtures)"
        )
    elif queue_path.is_file():
        sections.append(
            "NEXT PENDING NOTE\n"
            "(Queued on host — open Review to decide candidates.)"
        )
    else:
        sections.append("NEXT PENDING NOTE\n(none)")

    if not sections:
        return "(nothing to peek)"
    return "\n\n".join(sections)
