"""Hyperlinks in the embedded tmux PTY.

pyte ignores OSC 8; Textual owns the mouse, so neither bare http(s) URLs nor
Claude-style nested OSC 8 links open in a browser by themselves. This module:

1. Strips OSC 8 from the byte stream (so pyte still draws the visible text)
2. Stores the active href with each character via ``HyperlinkScreen.draw``
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
import unicodedata
import webbrowser
from collections import namedtuple

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


# Enough room for the maximum clipboard payload in base64 plus its header.
# Oversized OSC is discarded through its terminator, never rendered as text.
_OSC_MAX_CHARS = 4 * ((_OSC52_MAX_DECODED + 2) // 3) + 4096
_OSC_START_RE = re.compile(r"\x1b\]|\x9d")
_OSC_END_RE = re.compile(r"\x07|\x1b\\|\x9c|\x18|\x1a")


class _OscFilter:
    """Frame OSC across PTY reads, keeping other terminal input in order."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._length = 0
        self._inside = False
        self._discard = False
        self._escape = ""

    def _append(self, text: str) -> None:
        if self._discard:
            return
        self._length += len(text)
        if self._length > _OSC_MAX_CHARS:
            self._parts.clear()
            self._discard = True
        else:
            self._parts.append(text)

    def feed(self, stream, screen, text: str, on_clipboard) -> None:
        text = self._escape + text
        self._escape = ""
        pos = 0
        while pos < len(text):
            if not self._inside:
                match = _OSC_START_RE.search(text, pos)
                if match is None:
                    end = len(text)
                    if text.endswith("\x1b"):
                        self._escape = "\x1b"
                        end -= 1
                    if pos < end:
                        stream.feed(text[pos:end])
                    return
                if pos < match.start():
                    stream.feed(text[pos : match.start()])
                self._inside = True
                self._discard = False
                self._length = 0
                self._parts = []
                # Normalize C1 OSC to the 7-bit form used by our extractors.
                self._append("\x1b]")
                pos = match.end()
            else:
                match = _OSC_END_RE.search(text, pos)
                if match is None:
                    end = len(text)
                    if text.endswith("\x1b"):
                        self._escape = "\x1b"
                        end -= 1
                    self._append(text[pos:end])
                    return
                self._append(text[pos : match.start()])
                cancelled = match.group() in ("\x18", "\x1a")
                sequence = (
                    None
                    if self._discard or cancelled
                    else "".join(self._parts) + "\x07"
                )
                # Reset framing before dispatch: a failed terminal/clipboard
                # callback must not trap subsequent output inside this OSC.
                self._parts.clear()
                self._length = 0
                self._inside = False
                self._discard = False
                pos = match.end()
                if sequence is not None:
                    if sequence.startswith("\x1b]8;"):
                        osc8 = _OSC8_RE.fullmatch(sequence)
                        if osc8 is not None:
                            screen.active_href = osc8.group(1) or None
                    elif sequence.startswith("\x1b]52;") and on_clipboard is not None:
                        _, clips = extract_osc52(sequence)
                        for clip in clips:
                            on_clipboard(clip)
                    else:
                        stream.feed(sequence)


def normalize_wide_cells(screen, rows=None) -> None:
    """Repair pyte's orphan halves after overwrite, erase or cell shifts."""
    from wcwidth import wcswidth

    for y in tuple(screen.dirty) if rows is None else rows:
        if not 0 <= y < screen.lines:
            continue
        line = screen.buffer[y]
        for x in range(screen.columns):
            char = line[x]
            data = char.data
            if len(data) == 1 and ord(data) < 128:
                continue
            width = wcswidth(data) if data else 0
            if data and width == 2:
                if x + 1 < screen.columns:
                    following = line[x + 1]
                    if not following.data:
                        continue
                    if all(unicodedata.combining(c) for c in following.data):
                        line[x] = char._replace(
                            data=unicodedata.normalize("NFC", data + following.data)
                        )
                        line[x + 1] = following._replace(data="")
                        screen.dirty.add(y)
                        continue
            elif (data and width == 1) or (
                not data and x and wcswidth(line[x - 1].data or " ") == 2
            ):
                continue
            fields = {"data": " "}
            if hasattr(char, "href"):
                fields["href"] = None
            line[x] = char._replace(**fields)
            screen.dirty.add(y)


def feed_with_osc8(stream, screen, text: str, on_clipboard=None) -> None:
    """Feed terminal text with bounded, incremental OSC 8/52 handling."""
    osc_filter = getattr(stream, "_orcan_osc_filter", None)
    if osc_filter is None:
        osc_filter = stream._orcan_osc_filter = _OscFilter()
    osc_filter.feed(stream, screen, text, on_clipboard)
    if hasattr(screen, "buffer") and hasattr(screen, "dirty"):
        normalize_wide_cells(screen)


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
    # Real screens can contain half-overwritten double-width characters.
    if hasattr(screen, "dirty"):
        normalize_wide_cells(screen, (row,))
    buf = screen.buffer[row]
    return "".join(buf[x].data for x in range(screen.columns))


def url_at_screen(screen, column: int, row: int) -> str | None:
    """OSC 8 cell href, else plain http(s) under the cursor."""
    if row < 0 or row >= screen.lines or column < 0 or column > screen.columns:
        return None
    if hasattr(screen, "dirty"):
        normalize_wide_cells(screen, (row,))
    if column < screen.columns and column and not screen.buffer[row][column].data:
        column -= 1
    href = getattr(screen, "link_at", lambda _c, _r: None)(column, row)
    if href:
        return href
    offset = sum(len(screen.buffer[row][x].data) for x in range(column))
    return plain_url_at(line_from_screen(screen, row), offset)


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


def attach_hyperlink_screen(on_response=None):
    """Return ``(HyperlinkScreen, Stream)`` factory deps — imported lazily
    so host unit tests for pure helpers need no pyte."""
    import pyte
    from pyte import modes
    from wcwidth import iter_graphemes, wcswidth

    # pyte moves/replaces immutable Char tuples for every screen operation.
    # Carry links in those tuples instead of maintaining a parallel cell grid.
    LinkedChar = namedtuple("LinkedChar", (*pyte.screens.Char._fields, "href"))

    class HyperlinkScreen(pyte.Screen):
        """Screen whose drawn cells carry their own OSC 8 address."""

        def __init__(self, columns: int, lines: int) -> None:
            self.active_href: str | None = None
            super().__init__(columns, lines)

        def link_at(self, column: int, row: int) -> str | None:
            if not (0 <= row < self.lines and 0 <= column < self.columns):
                return None
            return getattr(self.buffer[row][column], "href", None)

        def write_process_input(self, data: str) -> None:
            if on_response is not None:
                on_response(data)

        def reset(self) -> None:
            super().reset()
            self.active_href = None

        def draw(self, data: str) -> None:
            attrs = self.cursor.attrs
            if self.active_href:
                self.cursor.attrs = LinkedChar(*attrs, self.active_href)
            try:
                tail = getattr(self, "_grapheme_tail", None)
                if tail is not None:
                    y, x, cell, end = tail
                    if (self.cursor.y, self.cursor.x) == end and self.buffer[y][
                        x
                    ] == cell:
                        clusters = iter(iter_graphemes(cell.data + data))
                        joined = next(clusters)
                        if len(joined) > len(cell.data):
                            data = data[len(joined) - len(cell.data) :]
                            old_width = wcswidth(cell.data)
                            width = wcswidth(joined)
                            if width > old_width and x + width > self.columns:
                                self.buffer[y][x] = self.default_char
                                self.dirty.add(y)
                                self.cursor.x = (
                                    self.columns
                                    if modes.DECAWM in self.mode
                                    else max(0, self.columns - width)
                                )
                                self._draw_cluster(joined, cell)
                            else:
                                if width > old_width and modes.IRM in self.mode:
                                    self.insert_characters(width - old_width)
                                self.buffer[y][x] = cell._replace(data=joined)
                                if width == 2:
                                    self.buffer[y][x + 1] = cell._replace(data="")
                                self.cursor.x += width - old_width
                                self.dirty.add(y)
                                self._remember_cluster(y, x)
                if data.isascii():
                    super().draw(data)
                    if data:
                        self._remember_cluster(self.cursor.y, self.cursor.x - 1)
                else:
                    for cluster in iter_graphemes(data):
                        self._draw_cluster(cluster, self.cursor.attrs)
            finally:
                # Erasing and filling blank cells must never inherit a link.
                self.cursor.attrs = attrs

        def _remember_cluster(self, y: int, x: int) -> None:
            self._grapheme_tail = (
                y,
                x,
                self.buffer[y][x],
                (self.cursor.y, self.cursor.x),
            )

        def _draw_cluster(self, cluster: str, attrs) -> None:
            width = wcswidth(cluster)
            if width not in (1, 2) or width > self.columns:
                self._grapheme_tail = None
                return
            if (
                width == 2
                and self.cursor.x == self.columns - 1
                and modes.DECAWM in self.mode
            ):
                self.buffer[self.cursor.y][self.cursor.x] = self.default_char
                self.dirty.add(self.cursor.y)
                self.carriage_return()
                self.linefeed()
            if width == 2 and self.cursor.x == self.columns - 1:
                self.cursor.x = self.columns - width
            # Let pyte handle wrapping, insert mode and charset state using a
            # glyph of the right width, then store the complete grapheme.
            super().draw("界" if width == 2 else "a")
            x, y = self.cursor.x - width, self.cursor.y
            self.buffer[y][x] = attrs._replace(data=cluster)
            if width == 2 and x + 1 < self.columns:
                self.buffer[y][x + 1] = attrs._replace(data="")
            self._remember_cluster(y, x)

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

    def invalidate_tail(method):
        def dispatch(self, *args, **kwargs):
            self._grapheme_tail = None
            return method(self, *args, **kwargs)

        return dispatch

    for event in pyte.Stream.events - {"draw", "select_graphic_rendition"}:
        method = getattr(HyperlinkScreen, event, None)
        if method is not None:
            setattr(HyperlinkScreen, event, invalidate_tail(method))

    class ScrollAwareStream(pyte.Stream):
        # Extends, doesn't replace, pyte's own dispatch table — see
        # HyperlinkScreen.scroll_up_region's docstring for why this is
        # needed at all (pyte 0.8.2 doesn't wire CSI S/T to anything).
        csi = {**pyte.Stream.csi, "S": "scroll_up_region", "T": "scroll_down_region"}

    return HyperlinkScreen, ScrollAwareStream
