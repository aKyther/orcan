"""Warm Graphite / Amber design tokens for the Textual Cockpit.

Keep all Cockpit colours here. CSS strings use ``$token`` placeholders and
Rich/Textual markup uses the exported uppercase values directly.
"""

from __future__ import annotations

import re

BACKGROUND = "#171512"
SURFACE = "#201d19"
PANEL_ACTIVE = "#2a251f"
BORDER = "#332e28"
BORDER_SUBTLE = "#292420"
TEXT_PRIMARY = "#f0e9e0"
TEXT_MUTED = "#9a8f80"
TEXT_DISABLED = "#5c554c"
ACCENT = "#e8b76c"
ACCENT_BRIGHT = "#f5c988"
ACCENT_DIM = "#a8824f"
RUNNING = "#8fbc6a"
ERROR = "#e06c75"
WARNING = "#e5c07b"
IDLE = "#736a5e"
COMPLETED = "#7a9b8e"

TOKENS = {
    name.lower(): value
    for name, value in {
        "BACKGROUND": BACKGROUND,
        "SURFACE": SURFACE,
        "PANEL_ACTIVE": PANEL_ACTIVE,
        "BORDER": BORDER,
        "BORDER_SUBTLE": BORDER_SUBTLE,
        "TEXT_PRIMARY": TEXT_PRIMARY,
        "TEXT_MUTED": TEXT_MUTED,
        "TEXT_DISABLED": TEXT_DISABLED,
        "ACCENT": ACCENT,
        "ACCENT_BRIGHT": ACCENT_BRIGHT,
        "ACCENT_DIM": ACCENT_DIM,
        "RUNNING": RUNNING,
        "ERROR": ERROR,
        "WARNING": WARNING,
        "IDLE": IDLE,
        "COMPLETED": COMPLETED,
    }.items()
}

# Existing Cockpit styles are normalised here while CSS is rendered. This
# preserves every selector and interaction while making the token file the
# single palette source for the Textual renderer.
_LEGACY_TOKENS = {
    "#0d0b13": BACKGROUND, "#12101a": BACKGROUND, "#17131f": BACKGROUND,
    "#1b1724": SURFACE, "#211c2b": SURFACE, "#241e30": SURFACE,
    "#2a2237": PANEL_ACTIVE, "#2b2420": PANEL_ACTIVE, "#2d2027": PANEL_ACTIVE,
    "#302640": PANEL_ACTIVE, "#342a44": PANEL_ACTIVE, "#3a2e4d": PANEL_ACTIVE,
    "#423452": PANEL_ACTIVE, "#604e72": BORDER, "#7c6694": BORDER,
    "#746a82": TEXT_DISABLED, "#948ba3": TEXT_MUTED, "#b0a6ba": TEXT_MUTED,
    "#cbc4d3": TEXT_PRIMARY, "#d7c7eb": TEXT_PRIMARY, "#ddd2eb": TEXT_PRIMARY,
    "#e2ddea": TEXT_PRIMARY, "#ad91d0": ACCENT, "#9d82bd": ACCENT,
    "#c7b1e2": ACCENT, "#d3a66f": WARNING, "#e0bb8b": WARNING,
    "#c47b91": ERROR, "#dfa1b2": ERROR, "#f87171": ERROR,
}


def css(template: str) -> str:
    """Expand ``$token`` references without treating CSS braces specially."""

    rendered = re.sub(r"\$([a-z_]+)", lambda match: TOKENS[match.group(1)], template)
    for legacy, token in _LEGACY_TOKENS.items():
        rendered = rendered.replace(legacy, token)
    return rendered
