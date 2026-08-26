"""Single source of truth for every real keybinding this environment exposes.

Deliberately stdlib-only (no Textual import) so it stays directly
unit-testable on the host, same convention as actions.py.

Two independent renderers read SHORTCUTS so the "APP" vs "TMUX" help stays
truthful and can't silently drift from each other: shortcuts_modal.py (the
in-cockpit `?`/F1 overlay) and shortcuts_cli.py (a standalone tmux popup that
works even without the cockpit running — see keybindings.conf's own `bind ?`).

tmux_tokens holds the *literal* `bind ...` substrings each tmux-layer entry
describes, exactly as they appear in
docker/rootfs/etc/tmux/keybindings.conf — not the prettified `keys` display
text (e.g. "Alt+←" vs the file's "M-Left"). tests/host/test_cockpit_shortcuts.py
asserts every token is still present in that file, so an edit to one side
without the other fails a test instead of quietly going stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

Layer = Literal["tmux", "app"]
Context = Literal["terminal", "workspaces", "panel", "rail"]
VALID_CONTEXTS: tuple[Context, ...] = ("terminal", "workspaces", "panel", "rail")

# Shown at the bottom of F1/? overlay (shortcuts_modal) and prefix-? popup
# (shortcuts_cli) — embedded tmux is not a native terminal attach.
EMBED_DISCLAIMER = (
    "Embedded tmux ≠ native attach — Textual translates keys/mouse. "
    "Full attach: orcan enter --tmux"
)

# Browser ttyd (xterm.js) and some desktop terminals (e.g. Windows Terminal /
# WSL) deliver Alt+Arrow as Ctrl+Arrow — Textual never sees distinct Meta, so
# cockpit cannot offer both "Ctrl=split" and "Alt=focus" on the same events.
# Cockpit therefore maps Ctrl/Alt+arrows → pane focus and Ctrl+Shift+arrows →
# split (pty_tmux_nav.py). Raw ``orcan enter --tmux`` still uses
# keybindings.conf (Ctrl=split, Alt=focus) when Meta works.
# Shown in F1 / ? overlay and prefix-? popup footers.
BROWSER_KEY_LIMIT = (
    "Limit: many terminals send Alt+arrows as Ctrl+arrows. "
    "Cockpit: Ctrl/Alt+←/→/↑/↓ = focus pane; Ctrl+Shift+arrows = split "
    "(also prefix - / |). Raw --tmux keeps conf (Ctrl=split, Alt=focus). "
    "ttyd/WT — see Terminal UI docs"
)

# Requested as an IDE-style "Help > About": what is this, what version, where
# are the docs — shown alongside the shortcut list (same F1/? overlay and
# standalone popup) since that's the one place a user already went looking
# for orientation. Version comes from the installed distribution, not a
# hardcoded string or a pyproject.toml parse, so it can't drift from what's
# actually running.
PRODUCT_NAME = "orcan cockpit"
PRODUCT_SUMMARY = (
    "The Textual TUI behind `orcan enter`: a workspace picker with a live "
    "tmux session embedded in its own pty."
)
DOCS_URL = "https://akyther.github.io/orcan/latest/"


def product_version() -> str:
    try:
        return version("orcan-cockpit")
    except PackageNotFoundError:
        return "unknown"


@dataclass(frozen=True)
class Shortcut:
    keys: str
    description: str
    layer: Layer
    category: str
    contexts: tuple[Context, ...] = field(default_factory=tuple)
    tmux_tokens: tuple[str, ...] = field(default_factory=tuple)


SHORTCUTS: list[Shortcut] = [
    # --- app (cockpit) layer, global-navigation subset — listed FIRST,
    # deliberately, not just alphabetically/thematically: hints_for() takes
    # the first `limit` (default 6) matches for a context, and every tmux
    # pane/window/session entry below also matches "terminal" — with these
    # listed after them (as they used to be), they got crowded out of the
    # terminal hint strip entirely (verified: hints_for("terminal") was
    # 6/6 tmux pane hints, no F1/F2/F4 in any form). Global nav should
    # always win that race, even while attached to a live tmux session.
    # (No F3/Git entry — removed on request; lazygit stays reachable via the
    # `lg` shell alias inside the terminal itself.)
    Shortcut("F2", "Toggle assertions panel", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    Shortcut("F4 / ‹›", "Toggle workspaces panel", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    # "?" is a bare letter, not a function key — PtyTerminal swallows it
    # (event.stop() in on_key) whenever the terminal has focus and sends it
    # into the shell/tmux pane as a literal "?" instead; only F1 reliably
    # opens this from there. Kept as ONE entry (not split by context) so the
    # shortcuts modal/CLI still show a single "Open shortcuts" row — the
    # terminal-only trim to bare "F1" happens in hints_for() below, the one
    # place that actually needs the context-accurate distinction. Confirmed
    # via real pty test: typing "?" while attached lands in the pane.
    Shortcut("F1 / ?", "Open shortcuts", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    # --- app: cockpit nav mix (see pty_tmux_nav — differs from raw --tmux) ---
    Shortcut("Ctrl/Alt+←/→/↑/↓", "Focus pane", "app", "panes", ("terminal",)),
    Shortcut("Ctrl+Shift+←/→/↑/↓", "Split pane", "app", "panes", ("terminal",)),
    # --- tmux: panes -------------------------------------------------------
    Shortcut("prefix -", "Split pane (down)", "tmux", "panes", ("terminal",),
              ("bind - split-window -v",)),
    Shortcut("prefix |", "Split pane (right)", "tmux", "panes", ("terminal",),
              ("bind | split-window -h",)),
    # No "terminal" context: cockpit remaps these (hints show APP rows above).
    # Still listed under TMUX in F1 / prefix-? for raw ``orcan enter --tmux``.
    Shortcut("Ctrl+↓/↑/→/←", "Split pane (no prefix; --tmux only)", "tmux", "panes", (), (
        "bind -n C-Down split-window -v",
        "bind -n C-Up split-window -v -b",
        "bind -n C-Right split-window -h",
        "bind -n C-Left split-window -h -b",
    )),
    Shortcut("Alt+←/→/↑/↓", "Focus pane (--tmux when Meta works)", "tmux", "panes", (), (
        "bind -n M-Left select-pane -L",
        "bind -n M-Right select-pane -R",
        "bind -n M-Up select-pane -U",
        "bind -n M-Down select-pane -D",
    )),
    Shortcut("prefix z", "Zoom pane", "tmux", "panes", ("terminal",),
              ("bind z resize-pane -Z",)),
    Shortcut("prefix x", "Kill pane", "tmux", "panes", ("terminal",),
              ("bind x kill-pane",)),
    # --- tmux: windows -------------------------------------------------------
    Shortcut("Ctrl+Alt+←/→", "Previous / next window", "tmux", "windows", ("terminal",), (
        "bind -n C-M-Left previous-window",
        "bind -n C-M-Right next-window",
    )),
    Shortcut("Alt+c", "New window", "tmux", "windows", ("terminal",),
              ("bind -n M-c new-window",)),
    # Cockpit intercepts Ctrl+Shift+arrows for split; swap remains --tmux only.
    Shortcut("Ctrl+Shift+←/→", "Swap window (--tmux only)", "tmux", "windows", (), (
        "bind -n C-S-Left swap-window -t -1",
        "bind -n C-S-Right swap-window -t +1",
    )),
    Shortcut("Alt+1..9", "Select window (left Alt only — right Alt/AltGr on "
              "international Windows layouts won't send it, see prefix 1..9)",
              "tmux", "windows", ("terminal",), ("bind -n M-1 select-window -t 1",)),
    Shortcut("prefix 0..9", "Select window (layout-independent fallback)", "tmux", "windows",
              ("terminal",), ("bind 0 select-window -t :$", "bind 1 select-window -t 1")),
    Shortcut("prefix W", "Choose window", "tmux", "windows", ("terminal",),
              ("bind W choose-window -Z",)),
    # --- tmux: sessions ------------------------------------------------------
    Shortcut("prefix s / w", "Switch session", "tmux", "sessions", ("terminal",), (
        "bind s run-shell '/etc/tmux/scripts/session-switch.sh'",
        "bind w run-shell '/etc/tmux/scripts/session-switch.sh'",
    )),
    Shortcut("prefix I", "Session info", "tmux", "sessions", ("terminal",),
              ("bind I display-message",)),
    # --- tmux: mouse / misc --------------------------------------------------
    Shortcut("Alt+a / Alt+q", "Mouse on / off", "tmux", "misc", ("terminal",), (
        "bind -n M-a set -g mouse on",
        "bind -n M-q set -g mouse off",
    )),
    Shortcut("prefix r", "Reload tmux config", "tmux", "misc", ("terminal",),
              ("bind r source-file /etc/tmux/tmux.conf",)),
    Shortcut("prefix P", "Copy current path", "tmux", "misc", ("terminal",),
              ("bind P run-shell '/etc/tmux/scripts/copy-path.sh'",)),
    Shortcut("prefix u", "Pick URL from pane", "tmux", "misc", ("terminal",),
              ("bind u run-shell '/etc/tmux/scripts/pick-url.sh'",)),
    Shortcut("prefix ?", "Shortcuts (standalone popup)", "tmux", "misc", ("terminal",),
              ("bind ? display-popup",)),
    Shortcut("drag · Ctrl+C", "Copy selection (embedded terminal)", "app", "misc",
              ("terminal",)),
    Shortcut("Ctrl+V", "Paste (embedded terminal)", "app", "misc", ("terminal",)),
    # --- tmux: copy-mode -------------------------------------------------------
    Shortcut("v", "Begin selection", "tmux", "copy-mode", ("terminal",),
              ("bind -T copy-mode-vi v send-keys -X begin-selection",)),
    Shortcut("Ctrl+v", "Toggle rectangle select", "tmux", "copy-mode", ("terminal",),
              ("bind -T copy-mode-vi C-v send-keys -X rectangle-toggle",)),
    Shortcut("y", "Copy selection", "tmux", "copy-mode", ("terminal",),
              ("bind -T copy-mode-vi y send-keys -X copy-selection-and-cancel",)),
    Shortcut("Escape", "Cancel copy mode", "tmux", "copy-mode", ("terminal",),
              ("bind -T copy-mode-vi Escape send-keys -X cancel",)),
    # --- app (cockpit) layer, remainder (the terminal-context subset lives
    # at the top of this list — see the comment there) ----------------------
    Shortcut("Ctrl+P", "Command palette", "app", "cockpit", ("workspaces", "panel", "rail")),
    Shortcut("r", "Run context review", "app", "cockpit", ("panel",)),
    Shortcut("p", "Pause/resume context automation", "app", "cockpit", ("panel",)),
    Shortcut("o", "Turn context automation off/on", "app", "cockpit", ("panel",)),
    Shortcut("↑ / ↓, Enter", "Navigate / attach workspace", "app", "cockpit", ("workspaces",)),
    Shortcut("i", "Expand workspace details (root, repo count)", "app", "cockpit", ("workspaces",)),
]


def grouped_by_layer() -> dict[Layer, list[Shortcut]]:
    groups: dict[Layer, list[Shortcut]] = {"app": [], "tmux": []}
    for shortcut in SHORTCUTS:
        groups[shortcut.layer].append(shortcut)
    return groups


def hints_for(context: Context, limit: int = 6) -> list[str]:
    # Rich markup (bold+cyan key, plain description) — safe here because
    # this only ever feeds the Textual-rendered HintStrip (hints.py), which
    # interprets it; format_row() below stays markup-free since it also
    # feeds shortcuts_cli.py's plain-text standalone tmux popup, where
    # markup tags would show up as literal bracketed text.
    matches = [s for s in SHORTCUTS if context in s.contexts]
    rows = []
    for s in matches[:limit]:
        keys = s.keys
        if context == "terminal" and keys == "F1 / ?":
            # See the "F1 / ?" entry's comment above — "?" doesn't work
            # from here, so the hint strip must not claim it does.
            keys = "F1"
        rows.append(f"[bold #5eead4]{keys}[/] {s.description}")
    return rows


def format_row(shortcut: Shortcut, *, key_width: int = 20) -> str:
    return f"{shortcut.keys:<{key_width}} {shortcut.description}"
