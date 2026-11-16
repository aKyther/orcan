"""Shared centered text entry for the curses setup screens (stdlib only)."""

from __future__ import annotations

import curses
import unicodedata
from typing import Any


def _width(text: str) -> int:
    return sum(
        0
        if unicodedata.combining(char)
        else 2
        if unicodedata.east_asian_width(char) in ("W", "F")
        else 1
        for char in text
    )


def _clip(text: str, cells: int) -> str:
    result = ""
    for char in text:
        if _width(result + char) > cells:
            break
        result += char
    return result


def prompt_line(screen: Any, label: str, initial: str, *, attr: int = 0) -> str | None:
    """Modal line editor. Empty confirmation keeps initial; cancellation returns None."""
    buf = list(initial)
    pos = len(buf)
    offset = 0
    focus = 0  # input, confirm, cancel
    old_mouse = None

    def cursor(visible: bool) -> None:
        try:
            curses.curs_set(int(visible))
        except curses.error:
            pass

    try:
        _, old_mouse = curses.mousemask(curses.ALL_MOUSE_EVENTS)
        while True:
            height, width = screen.getmaxyx()
            # The underlying screen is never erased: redraw it before placing
            # a fresh modal, including after a resize, and restore it on exit.
            screen.touchwin()
            screen.noutrefresh()
            if height < 9 or width < 32:
                cursor(False)
                notice = _clip("Resize terminal / Esc cancels", max(0, width - 2))
                window = curses.newwin(max(1, height), max(1, width), 0, 0)
                window.keypad(True)
                try:
                    window.addnstr(
                        height // 2,
                        max(0, (width - _width(notice)) // 2),
                        notice,
                        max(0, width - 1),
                    )
                    window.noutrefresh()
                    curses.doupdate()
                except curses.error:
                    pass
                field_width = 0
            else:
                dialog_width = min(72, width - 4)
                top, left = (height - 9) // 2, (width - dialog_width) // 2
                window = curses.newwin(9, dialog_width, top, left)
                window.keypad(True)
                accent = attr or (curses.color_pair(2) if curses.has_colors() else 0)
                window.attron(accent)
                window.box()
                window.attroff(accent)
                window.addstr(
                    1, 2, _clip(label, dialog_width - 4), accent | curses.A_BOLD
                )
                field_width = dialog_width - 4
                offset = min(offset, pos)
                while _width("".join(buf[offset:pos])) >= field_width:
                    offset += 1
                text = _clip("".join(buf[offset:]), field_width)
                window.addstr(
                    3,
                    2,
                    text + " " * (field_width - _width(text)),
                    attr | curses.A_REVERSE,
                )
                window.addstr(
                    5,
                    2,
                    _clip("Enter: confirm  Esc: cancel  Tab: move", field_width),
                    curses.A_DIM,
                )
                buttons = [(2, "[ Confirm ]"), (dialog_width - 12, "[ Cancel ]")]
                for index, (col, title) in enumerate(buttons, 1):
                    style = accent | curses.A_BOLD
                    if focus == index:
                        style |= curses.A_REVERSE
                    window.addstr(7, col, title, style)
                cursor(focus == 0)
                if focus == 0:
                    window.move(3, 2 + _width("".join(buf[offset:pos])))
                window.noutrefresh()
                curses.doupdate()
            try:
                key = window.get_wch()
            except curses.error:
                continue
            if key == curses.KEY_RESIZE:
                continue
            if key in ("\x1b", 27, "\x03", 3):
                return None
            if not field_width:
                continue
            if key == curses.KEY_MOUSE:
                try:
                    _, x, y, _, state = curses.getmouse()
                except curses.error:
                    continue
                if not state & (curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED):
                    continue
                row, col = y - top, x - left
                if row == 7:
                    for index, (start, title) in enumerate(buttons, 1):
                        if start <= col < start + len(title):
                            return (
                                ("".join(buf).strip() or initial)
                                if index == 1
                                else None
                            )
                elif row == 3 and 2 <= col < dialog_width - 2:
                    focus = 0
                    pos = offset
                    while (
                        pos < len(buf)
                        and _width("".join(buf[offset : pos + 1])) <= col - 2
                    ):
                        pos += 1
                continue
            if key in ("\t", 9, curses.KEY_BTAB):
                focus = (focus + (-1 if key == curses.KEY_BTAB else 1)) % 3
                continue
            if key in ("\n", "\r", curses.KEY_ENTER, 10, 13) or (focus and key == " "):
                return None if focus == 2 else ("".join(buf).strip() or initial)
            if focus:
                if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                    focus = 1 if focus == 2 else 2
                continue
            if key in ("\x7f", "\b", curses.KEY_BACKSPACE, 8):
                if pos:
                    pos -= 1
                    del buf[pos]
            elif key == curses.KEY_DC:
                if pos < len(buf):
                    del buf[pos]
            elif key in (curses.KEY_LEFT, "\x02", 2):
                pos = max(0, pos - 1)
            elif key in (curses.KEY_RIGHT, "\x06", 6):
                pos = min(len(buf), pos + 1)
            elif key in (curses.KEY_HOME, "\x01", 1):
                pos = 0
            elif key in (curses.KEY_END, "\x05", 5):
                pos = len(buf)
            elif isinstance(key, str) and key.isprintable():
                buf.insert(pos, key)
                pos += 1
    except KeyboardInterrupt:
        return None
    finally:
        if old_mouse is not None:
            curses.mousemask(old_mouse)
        cursor(False)
        screen.touchwin()
        screen.refresh()
