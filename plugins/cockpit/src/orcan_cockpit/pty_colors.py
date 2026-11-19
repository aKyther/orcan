"""Map pyte cell fg/bg tokens to Rich color strings.

Stdlib-only so host tests can lock the mapping without the cockpit venv.
Rich validation (Color.parse) happens in pty_terminal before Style().
"""

from __future__ import annotations

# pyte.graphics uses classic terminfo names; Rich uses different tokens.
_PYTE_COLOR_TO_RICH: dict[str, str] = {
    "brown": "yellow",
    "brightbrown": "bright_yellow",
    "brightblack": "bright_black",
    "brightred": "bright_red",
    "brightgreen": "bright_green",
    "brightyellow": "bright_yellow",
    "brightblue": "bright_blue",
    "brightmagenta": "bright_magenta",
    "bfightmagenta": "bright_magenta",
    "brightcyan": "bright_cyan",
    "brightwhite": "bright_white",
}

# tmux / pyte tokens that are not Rich color names (drop color, keep attrs).
_UNKNOWN_COLOR_NAMES = frozenset({"norange", "grey", "gray", "lightgray", "lightgrey"})


def pyte_color_to_rich(value: str) -> str | None:
    if not value or value == "default":
        return None
    if value in _UNKNOWN_COLOR_NAMES:
        return None
    mapped = _PYTE_COLOR_TO_RICH.get(value, value)
    if len(mapped) == 6 and all(c in "0123456789abcdefABCDEF" for c in mapped):
        return f"#{mapped}"
    return mapped
