"""Hyperlinks in the embedded tmux PTY.

pyte ignores OSC 8; Textual owns the mouse, so neither bare http(s) URLs nor
Claude-style nested OSC 8 links open in a browser by themselves. This module:

1. Strips OSC 8 from the byte stream (so pyte still draws the visible text)
2. Tracks the active href onto a cell grid via ``HyperlinkScreen.draw``
3. Finds a plain http(s) URL under a column as a fallback
4. Opens URLs with ``webbrowser`` (works for local ``orcan enter``; under
   ttyd may fail — callers should still render ``Style(link=…)`` so the
   outer terminal can Ctrl+click OSC 8)
5. Pulls OSC 52 clipboard writes out of the stream so a caller can forward
   them to the real outer terminal (pyte drops OSC 52 entirely)

Stdlib-only — host-testable without Textual.
"""

from __future__ import annotations

import base64
import re
import webbrowser

# OSC 8: ESC ] 8 ; params ; uri BEL  or  ESC ] 8 ; params ; uri ESC \
_OSC8_RE = re.compile(r"\x1b\]8;[^\x07\x1b]*;([^\x07\x1b]*)(?:\x07|\x1b\\)")

# OSC 52: ESC ] 52 ; <targets> ; <base64 | ?> (BEL | ESC \). tmux emits this
# on every yank when ``set -s set-clipboard on`` (copy-mode y, mouse drag,
# prefix-u / prefix-P). pyte has no OSC 52 handler, so unless it is pulled
# out here the child's clipboard writes die inside the emulator.
_OSC52_RE = re.compile(r"\x1b\]52;[^;\x07\x1b]*;([^\x07\x1b]*)(?:\x07|\x1b\\)")

# One yanked selection is small; cap the decode so a pathological payload
# cannot turn a single paint into a multi-MB clipboard write.
_OSC52_MAX_DECODED = 512 * 1024

# Same shape as pick-url.sh — allow trailing punctuation to be trimmed later.
_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
_URL_TRAIL_TRIM = re.compile(r"[.,;:!?\"')\]]+$")


def split_osc8(text: str) -> list[tuple[str, str | None]]:
    """Split *text* into (chunk, href_update) pairs.

    ``href_update`` is None when the chunk is ordinary text (keep current
    href), or a string when an OSC 8 sequence set/cleared the hyperlink
    (empty string means cleared). OSC 8 sequences themselves are omitted
    from chunks so pyte never sees them.
    """
    out: list[tuple[str, str | None]] = []
    pos = 0
    for match in _OSC8_RE.finditer(text):
        if match.start() > pos:
            out.append((text[pos : match.start()], None))
        out.append(("", match.group(1)))
        pos = match.end()
    if pos < len(text):
        out.append((text[pos:], None))
    elif not out:
        out.append((text, None))
    return out


def extract_osc52(text: str) -> tuple[str, list[str]]:
    """Pull OSC 52 clipboard-set sequences out of *text*.

    Returns ``(text_without_osc52, payloads)`` — each payload is the decoded
    UTF-8 string the child asked to place on the clipboard. Query forms
    (``ESC ] 52 ; c ; ?``), oversized and undecodable payloads are dropped.
    """
    if "\x1b]52;" not in text:
        return text, []
    payloads: list[str] = []

    def _take(match: "re.Match[str]") -> str:
        raw = match.group(1)
        if raw and raw != "?":
            try:
                decoded = base64.b64decode(raw, validate=True)
            except ValueError:  # binascii.Error is a ValueError subclass
                return ""
            if len(decoded) <= _OSC52_MAX_DECODED:
                payloads.append(decoded.decode("utf-8", errors="replace"))
        return ""

    return _OSC52_RE.sub(_take, text), payloads


def feed_with_osc8(stream, screen, text: str, on_clipboard=None) -> None:
    """Feed *text* to a pyte Stream, applying OSC 8 to ``screen.active_href``.

    When *on_clipboard* is given, OSC 52 clipboard writes are pulled out of
    *text* first and each decoded payload is handed to it — pyte would
    otherwise silently swallow them.
    """
    if on_clipboard is not None:
        text, clips = extract_osc52(text)
        for clip in clips:
            on_clipboard(clip)
    for chunk, href_update in split_osc8(text):
        if href_update is not None:
            screen.active_href = href_update or None
        if chunk:
            stream.feed(chunk)


def plain_url_at(line: str, column: int) -> str | None:
    """Return the http(s) URL covering *column* on *line*, or None."""
    if column < 0 or column >= len(line):
        # Still allow a click past the last char if the URL ends at EOL.
        if column < 0:
            return None
    for match in _URL_RE.finditer(line):
        start, end = match.start(), match.end()
        url = _URL_TRAIL_TRIM.sub("", match.group(0))
        # Trim may shorten the match; keep clickable span as original match
        # but open the cleaned URL.
        if start <= column < end or (column == len(line) and end == len(line)):
            return url if url.startswith(("http://", "https://")) else None
    return None


def line_from_screen(screen, row: int) -> str:
    """Visible characters on one pyte screen row (no trailing spaces stripped)."""
    if row < 0 or row >= screen.lines:
        return ""
    buf = screen.buffer[row]
    return "".join(buf[x].data or " " for x in range(screen.columns))


def url_at_screen(screen, column: int, row: int) -> str | None:
    """OSC 8 cell href, else plain http(s) under the cursor."""
    href = getattr(screen, "link_at", lambda _c, _r: None)(column, row)
    if href:
        return href
    return plain_url_at(line_from_screen(screen, row), column)


def open_url(url: str) -> bool:
    """Open an http(s) URL in the default browser. False on refusal/failure."""
    if not url.startswith(("http://", "https://")):
        return False
    try:
        if webbrowser.open(url):
            return True
    except (webbrowser.Error, OSError):
        pass
    # Container / WSL often has no usable webbrowser handler — try common
    # openers before giving up (ttyd still may fail; caller can notify).
    import subprocess

    for cmd in (("xdg-open", url), ("sensible-browser", url), ("wslview", url)):
        try:
            result = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def annotate_plain_urls(hrefs: list[str | None], line: str) -> None:
    """Fill *hrefs* in-place with plain http(s) URLs where still empty."""
    limit = len(hrefs)
    for match in _URL_RE.finditer(line):
        url = _URL_TRAIL_TRIM.sub("", match.group(0))
        if not url.startswith(("http://", "https://")):
            continue
        for x in range(match.start(), min(match.end(), limit)):
            if hrefs[x] is None:
                hrefs[x] = url


def attach_hyperlink_screen():
    """Return ``(HyperlinkScreen, Stream)`` factory deps — imported lazily
    so host unit tests for pure helpers need no pyte."""
    import pyte

    class HyperlinkScreen(pyte.Screen):
        """pyte Screen that stamps ``active_href`` onto a parallel cell grid."""

        def __init__(self, columns: int, lines: int) -> None:
            super().__init__(columns, lines)
            self.active_href: str | None = None
            self._links: list[list[str | None]] = []
            self._reset_links()

        def _reset_links(self) -> None:
            self._links = [[None] * self.columns for _ in range(self.lines)]

        def link_at(self, column: int, row: int) -> str | None:
            if row < 0 or row >= len(self._links):
                return None
            line = self._links[row]
            if column < 0 or column >= len(line):
                return None
            return line[column]

        def resize(self, lines: int | None = None, columns: int | None = None) -> None:
            super().resize(lines, columns)
            self._reset_links()

        def reset(self) -> None:
            super().reset()
            self.active_href = None
            self._reset_links()

        def draw(self, data: str) -> None:
            href = self.active_href
            if not href:
                super().draw(data)
                return
            for ch in data:
                y, x = self.cursor.y, self.cursor.x
                if 0 <= y < len(self._links) and 0 <= x < len(self._links[y]):
                    self._links[y][x] = href
                super().draw(ch)

        def erase_in_display(self, how: int = 0, private: bool = False) -> None:
            super().erase_in_display(how, private=private)
            if how == 2 or how == 3:
                self._reset_links()
                return
            # 0: cursor to end; 1: start to cursor — clear those cells' links.
            cy, cx = self.cursor.y, self.cursor.x
            if how == 0:
                for x in range(cx, self.columns):
                    self._links[cy][x] = None
                for y in range(cy + 1, self.lines):
                    self._links[y] = [None] * self.columns
            elif how == 1:
                for y in range(0, cy):
                    self._links[y] = [None] * self.columns
                for x in range(0, cx + 1):
                    self._links[cy][x] = None

        def erase_in_line(self, how: int = 0, private: bool = False) -> None:
            super().erase_in_line(how, private=private)
            cy, cx = self.cursor.y, self.cursor.x
            if how == 2:
                self._links[cy] = [None] * self.columns
            elif how == 0:
                for x in range(cx, self.columns):
                    self._links[cy][x] = None
            elif how == 1:
                for x in range(0, cx + 1):
                    self._links[cy][x] = None

        def index(self) -> None:
            at_bottom = self.cursor.y == self.lines - 1
            super().index()
            if at_bottom and self._links:
                self._links.pop(0)
                self._links.append([None] * self.columns)

        def reverse_index(self) -> None:
            at_top = self.cursor.y == 0
            super().reverse_index()
            if at_top and self._links:
                self._links.pop()
                self._links.insert(0, [None] * self.columns)

        def scroll_up_region(self, count: int | None = None) -> None:
            """CSI Ps S (SU) — shift the current scroll region up by
            *count* lines: the top *count* lines are discarded, *count*
            blank lines appear at the bottom, cursor position is
            untouched (unlike ``index``/IND, which is cursor-coupled —
            SU always applies to the whole region regardless of where
            the cursor is).

            pyte 0.8.2 has **no implementation of CSI S/T at all** —
            confirmed no "S"/"T" entry in ``pyte.Stream.csi`` and no
            ``scroll_up``/``scroll_down`` on ``pyte.Screen``; the CSI
            dispatcher silently drops both (no exception, no effect).
            tmux uses exactly this sequence as a redraw optimization —
            e.g. after a shell `clear`, instead of a full erase+repaint
            it sets a scroll region and scrolls it by its own height.
            Without this override, nothing actually moves the buffer
            rows or clears the revealed ones, so the old content stays
            on screen after `clear` (cursor moves, text doesn't — root-
            caused via a real pty+tmux session, not from pyte's docs:
            reproduced with a bare shell child, first ruling out our
            own pty relay, then isolated CSI S in pyte directly).
            Mirrors ``delete_lines``' own buffer-shift loop (same
            pop/reassign idiom, just unconditional on cursor position).
            """
            count = count or 1
            top, bottom = self.margins or (0, self.lines - 1)
            self.dirty.update(range(top, bottom + 1))
            for y in range(top, bottom + 1):
                src = y + count
                if src <= bottom and src in self.buffer:
                    self.buffer[y] = self.buffer.pop(src)
                else:
                    self.buffer.pop(y, None)
                self._links[y] = self._links[src] if src <= bottom else [None] * self.columns

        def scroll_down_region(self, count: int | None = None) -> None:
            """CSI Ps T (SD) — the scroll_up_region counterpart, shifting
            the region's content down instead of up."""
            count = count or 1
            top, bottom = self.margins or (0, self.lines - 1)
            self.dirty.update(range(top, bottom + 1))
            for y in range(bottom, top - 1, -1):
                src = y - count
                if src >= top and src in self.buffer:
                    self.buffer[y] = self.buffer.pop(src)
                else:
                    self.buffer.pop(y, None)
                self._links[y] = self._links[src] if src >= top else [None] * self.columns

    class ScrollAwareStream(pyte.Stream):
        # Extends, doesn't replace, pyte's own dispatch table — see
        # HyperlinkScreen.scroll_up_region's docstring for why this is
        # needed at all (pyte 0.8.2 doesn't wire CSI S/T to anything).
        csi = {**pyte.Stream.csi, "S": "scroll_up_region", "T": "scroll_down_region"}

    return HyperlinkScreen, ScrollAwareStream
