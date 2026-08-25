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


@dataclass(frozen=True)
class Shortcut:
    keys: str
    description: str
    layer: Layer
    category: str
    contexts: tuple[Context, ...] = field(default_factory=tuple)
    tmux_tokens: tuple[str, ...] = field(default_factory=tuple)


SHORTCUTS: list[Shortcut] = [
    # --- tmux: panes -------------------------------------------------------
    Shortcut("prefix -", "Split pane (down)", "tmux", "panes", ("terminal",),
              ("bind - split-window -v",)),
    Shortcut("prefix |", "Split pane (right)", "tmux", "panes", ("terminal",),
              ("bind | split-window -h",)),
    Shortcut("Ctrl+↓/↑/→/←", "Split pane (no prefix)", "tmux", "panes", ("terminal",), (
        "bind -n C-Down split-window -v",
        "bind -n C-Up split-window -v -b",
        "bind -n C-Right split-window -h",
        "bind -n C-Left split-window -h -b",
    )),
    Shortcut("Alt+←/→/↑/↓", "Focus pane", "tmux", "panes", ("terminal",), (
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
    Shortcut("Ctrl+Shift+←/→", "Swap window", "tmux", "windows", ("terminal",), (
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
    # --- app (cockpit) layer — no tmux_tokens: verified by reading app.py directly
    Shortcut("F2", "Toggle assertions panel", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    Shortcut("F4 / ‹›", "Toggle workspaces panel", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    Shortcut("F3", "Open Git (lazygit)", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    Shortcut("F1 / ?", "Open shortcuts", "app", "cockpit",
              ("terminal", "workspaces", "panel", "rail")),
    Shortcut("Ctrl+P", "Command palette", "app", "cockpit", ("workspaces", "panel", "rail")),
    Shortcut("r", "Run context review", "app", "cockpit", ("panel",)),
    Shortcut("p", "Pause/resume context automation", "app", "cockpit", ("panel",)),
    Shortcut("o", "Turn context automation off/on", "app", "cockpit", ("panel",)),
    Shortcut("↑ / ↓, Enter", "Navigate / attach workspace", "app", "cockpit", ("workspaces",)),
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
    return [f"[bold #5eead4]{s.keys}[/] {s.description}" for s in matches[:limit]]


def format_row(shortcut: Shortcut, *, key_width: int = 20) -> str:
    return f"{shortcut.keys:<{key_width}} {shortcut.description}"
