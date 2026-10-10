"""Pure context labels and rows shared by the curses views."""

from pathlib import Path
from typing import Any


def selection_outside_scan(
    selected: list[Path] | set[Path],
    repos: list[tuple[Path, bool]],
) -> list[Path]:
    """Paths kept in the selection that are not in the current scan list
    (e.g. picked under a previous parent). Preserves selection order."""
    visible = {p for p, _ in repos}
    return [p for p in selected if p not in visible]


def format_pick_label(path: Path, bits: list[str], *, mark: str = "+") -> str:
    tag = f"  ({' · '.join(bits)})" if bits else ""
    return f"{mark} {path.name}{tag}"


def review_outcome(bits: list[str]) -> str:
    """Translate compact scan tags into an explicit apply outcome."""
    labels = {
        "mount": "plain directory (mount as-is)",
        "elsewhere": "selected in another folder",
        "in ws": "already connected — no change",
        "name taken": "name conflict — will be renamed",
        "other ws": "also used in another workspace",
    }
    return " · ".join(labels.get(bit, bit) for bit in bits) if bits else "new project"


def stack_apply_summary(
    selected: list[Path],
    *,
    paths_in_ws: set[str],
) -> tuple[int, int]:
    """Return (new_count, already_in_ws_count) for the will-add header."""
    already = 0
    for path in selected:
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        if resolved in paths_in_ws:
            already += 1
    return len(selected) - already, already


def _ellipsize(text: str, width: int) -> str:
    """Truncate text to width, marking truncation with an ellipsis instead of
    silently cutting it off — so a long path reads as 'cut here', not as the
    whole path. Pure/curses-free."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def _humanize(seconds: float) -> str:
    """Coarse duration like '5m', '3h', '2d' — used for history age/TTL display."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


def manage_rows(
    workspaces: list[Any], collapsed: set[int] | None = None
) -> list[tuple[str, int, int | None]]:
    """(kind, ws_idx, proj_idx) — kind 'ws' or 'proj'; proj_idx None for 'ws'.
    Pure/curses-free so it's directly unit-testable."""
    out: list[tuple[str, int, int | None]] = []
    collapsed = collapsed or set()
    for wi, ws in enumerate(workspaces):
        if not isinstance(ws, dict):
            continue
        out.append(("ws", wi, None))
        if wi in collapsed:
            continue
        projects = ws.get("projects")
        if isinstance(projects, list):
            for pi, p in enumerate(projects):
                if isinstance(p, dict):
                    out.append(("proj", wi, pi))
    return out
