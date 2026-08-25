"""Keyboard bytes for the embedded tmux PTY.

Maps Textual key names → xterm/tmux bytes expected by
``docker/rootfs/etc/tmux/keybindings.conf`` local binds (``bind -n …``).

Textual is not a terminal emulator: it decomposes xterm CSI modified keys
into ``Escape`` + a second ``Key`` (see ``textual._ansi_sequences``). The
cockpit must recombine those pairs into **one** PTY write — same constraint
as ``Alt+digit`` (two writes break ``escape-time``).

Stdlib-only so host tests can lock behaviour without Textual.
"""

from __future__ import annotations

# Textual's ANSI table maps ESC+digit to macOS Option glyphs (¡™£…).
# On Linux / Windows Terminal, Alt+digit is real Meta (ESC+digit). When those
# bytes reach Textual they become Key(trade_mark_sign, "™") etc. — reverse
# them here so the child tmux still sees M-0..M-9.
_MAC_OPTION_GLYPH_TO_DIGIT: dict[str, str] = {
    "¡": "1",
    "™": "2",
    "£": "3",
    "¢": "4",
    "∞": "5",
    "§": "6",
    "¶": "7",
    "•": "8",
    "ª": "9",
    "º": "0",
}

_MAC_OPTION_KEY_TO_DIGIT: dict[str, str] = {
    "inverted_exclamation_mark": "1",
    "trade_mark_sign": "2",
    "pound_sign": "3",
    "cent_sign": "4",
    "infinity": "5",
    "section_sign": "6",
    "pilcrow_sign": "7",
    "bullet": "8",
    "feminine_ordinal_indicator": "9",
    "masculine_ordinal_indicator": "0",
}

_ARROW_CSI_SUFFIX: dict[str, str] = {
    "up": "A",
    "down": "B",
    "right": "C",
    "left": "D",
    "home": "H",
    "end": "F",
}

_KEY_BYTES: dict[str, bytes] = {
    "enter": b"\r",
    "return": b"\r",
    "escape": b"\x1b",
    "tab": b"\t",
    "shift+tab": b"\x1b[Z",
    "backspace": b"\x7f",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "delete": b"\x1b[3~",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "space": b" ",
    "ctrl+space": b"\x00",  # prefix C-Space (keybindings.conf)
}

# Direct Textual names → bytes for keybindings.conf ``bind -n`` chords.
_MODIFIER_ARROW_BYTES: dict[str, bytes] = {
    # C-Arrow → split (bind -n C-Left … C-Down)
    "ctrl+left": b"\x1b[1;5D",
    "ctrl+right": b"\x1b[1;5C",
    "ctrl+up": b"\x1b[1;5A",
    "ctrl+down": b"\x1b[1;5B",
    # C-S-Arrow → swap window (bind -n C-S-Left / C-S-Right)
    "ctrl+shift+left": b"\x1b[1;6D",
    "ctrl+shift+right": b"\x1b[1;6C",
    # M-Arrow → focus pane — legacy Meta prefix (\x1b\x1b[D), tmux M-Left bind
    "alt+left": b"\x1b\x1b[D",
    "alt+right": b"\x1b\x1b[C",
    "alt+up": b"\x1b\x1b[A",
    "alt+down": b"\x1b\x1b[B",
    # C-M-Arrow → prev/next window (bind -n C-M-Left / C-M-Right)
    "alt+ctrl+left": b"\x1b[1;7D",
    "alt+ctrl+right": b"\x1b[1;7C",
    "ctrl+alt+left": b"\x1b[1;7D",
    "ctrl+alt+right": b"\x1b[1;7C",
}

# M-letter local binds (bind -n M-c, M-a, M-q). Zoom: prefix+z — no wrapper map.
_META_LETTER_BYTES: dict[str, bytes] = {
    "c": b"\x1bc",
    "a": b"\x1ba",
    "q": b"\x1bq",
}


def _csi_arrow(modifier: int, direction: str) -> bytes:
    suffix = _ARROW_CSI_SUFFIX[direction]
    return f"\x1b[1;{modifier}{suffix}".encode("latin-1")


def _meta_arrow_legacy(direction: str) -> bytes:
    return b"\x1b" + _KEY_BYTES[direction]


def _esc_arrow_follow_up(follow_key: str) -> bytes | None:
    if follow_key.startswith(("ctrl+shift+", "shift+ctrl+")):
        direction = follow_key.rsplit("+", 1)[-1]
        if direction in _ARROW_CSI_SUFFIX:
            return _csi_arrow(6, direction)
    # WT/WSL: Alt+arrow often decomposes as Escape + ctrl+arrow — must not
    # forward bare C-arrow (split); treat as Meta+arrow (focus pane).
    if follow_key.startswith("ctrl+"):
        direction = follow_key[5:]
        if direction in _ARROW_CSI_SUFFIX:
            return _meta_arrow_legacy(direction)
    if follow_key.startswith("shift+"):
        direction = follow_key[6:]
        if direction in _ARROW_CSI_SUFFIX:
            return _csi_arrow(4, direction)
    if follow_key in _ARROW_CSI_SUFFIX:
        return _meta_arrow_legacy(follow_key)
    return None


def _esc_meta_follow_up(follow_key: str) -> bytes | None:
    if follow_key in _META_LETTER_BYTES:
        return _META_LETTER_BYTES[follow_key]
    if len(follow_key) == 1 and follow_key.isdigit():
        return b"\x1b" + follow_key.encode("ascii")
    return None


def esc_follow_up_bytes(follow_key: str) -> bytes | None:
    """Recombine Textual's synthetic ``Escape`` + *follow_key* into one write."""
    return _esc_arrow_follow_up(follow_key) or _esc_meta_follow_up(follow_key)


def key_to_bytes(key: str, character: str | None) -> bytes | None:
    if key == "escape":
        # PtyTerminal coalesces every Escape (may prefix arrow / M-letter).
        return None
    if key in _KEY_BYTES:
        return _KEY_BYTES[key]
    if key in _MODIFIER_ARROW_BYTES:
        return _MODIFIER_ARROW_BYTES[key]
    if key.startswith("ctrl+") and len(key) == 6 and key[5].isalpha():
        return bytes([ord(key[5].upper()) & 0x1F])
    if key.startswith("alt+"):
        base_key = key[4:]
        if base_key in _ARROW_CSI_SUFFIX:
            return _meta_arrow_legacy(base_key)
        if base_key in _META_LETTER_BYTES:
            return _META_LETTER_BYTES[base_key]
        base = _KEY_BYTES.get(base_key)
        if base is None and len(base_key) == 1:
            base = base_key.encode("utf-8", errors="ignore")
        if base:
            return b"\x1b" + base
    digit = _MAC_OPTION_KEY_TO_DIGIT.get(key)
    if digit is None and character:
        digit = _MAC_OPTION_GLYPH_TO_DIGIT.get(character)
    if digit is not None:
        return b"\x1b" + digit.encode("ascii")
    if character:
        return character.encode("utf-8", errors="ignore")
    return None
