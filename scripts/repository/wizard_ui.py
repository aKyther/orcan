"""Shared stdlib-only prompt/output helpers for orcan's interactive wizards
(config-wizard.py, settings-wizard.py). No curses here — that's context_tui.py.
"""

from __future__ import annotations

import os
import sys

# ANSI colors — pure stdlib, no library. Off for ORCAN_NO_COLOR or a non-tty
# stream, same convention as cli/lib/log.sh's ORCAN_NO_COLOR / `[ -t 2 ]`.
_COLOR = not os.environ.get("ORCAN_NO_COLOR") and sys.stdout.isatty()


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def _bold(text: str) -> str:
    return _paint("1", text)


def _cyan(text: str) -> str:
    return _paint("36", text)


def _green(text: str) -> str:
    return _paint("32", text)


def _red(text: str) -> str:
    return _paint("31", text)


def _dim(text: str) -> str:
    return _paint("2", text)


def _yellow(text: str) -> str:
    return _paint("33", text)


def die(msg: str) -> None:
    print(_red(f"Error: {msg}"), file=sys.stderr)
    raise SystemExit(1)


def info(msg: str = "") -> None:
    print(msg)


def success(msg: str) -> None:
    """Green checkmark line. Leading whitespace in msg (indent prefixes like
    "  " or a per-project "    ") stays before the mark, not after it."""
    stripped = msg.lstrip(" ")
    indent = msg[: len(msg) - len(stripped)]
    print(f"{indent}{_green(f'✓ {stripped}')}")


def warn(msg: str) -> None:
    print(_red(f"  ! {msg}"), file=sys.stderr)


def heading(title: str) -> None:
    """Section break — words only, no step numbers (those feel like edit indices)."""
    info()
    info(_bold(_cyan(f"── {title} ──")))


def ask(prompt: str, default: str | None = None) -> str:
    if default is not None and default != "":
        suffix = f" [{default}]"
    else:
        suffix = ""
    try:
        raw = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        print()
        die("cancelled (EOF)")
    if not raw and default is not None:
        return default
    return raw


def ask_yes_no(prompt: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = ask(f"{prompt} ({hint})", "y" if default else "n").lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        warn("answer y or n")


def ask_choice(prompt: str, choices: list[str], *, default: str) -> str:
    labels = "/".join(c.upper() if c == default else c for c in choices)
    while True:
        raw = ask(f"{prompt} ({labels})", default).lower()
        for c in choices:
            if raw == c or raw == c[0]:
                return c
        warn(f"choose: {', '.join(choices)}")


def ask_menu(title: str, options: list[tuple[str, str]], *, default: str) -> str:
    """Numbered menu: options are (id, description). Accept id, number, or first letter."""
    ids = [oid for oid, _ in options]
    if default not in ids:
        default = ids[0]
    if title.strip():
        info(title)
    for i, (oid, desc) in enumerate(options, 1):
        mark = " ← Enter" if oid == default else ""
        info(f"  {i}) {desc}{mark}")
    default_num = str(ids.index(default) + 1)
    while True:
        raw = ask("Your choice", default_num).strip().lower()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        for oid, _ in options:
            if raw == oid or raw == oid[0]:
                return oid
        warn(f"pick 1–{len(options)}")
