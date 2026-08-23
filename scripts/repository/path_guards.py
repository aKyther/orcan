"""Shared path safety checks for host-side config / mounts."""

from __future__ import annotations

from pathlib import Path

# Exact match only — children under /home/<user>/… are normal project paths.
SENSITIVE_EXACT = frozenset({"/", "/home"})

# Exact match *or* any path under these roots (e.g. /var/lib/docker).
SENSITIVE_TREES = frozenset({"/root", "/etc", "/usr", "/var", "/opt"})


def is_sensitive_path(path: Path | str) -> bool:
    """True if *path* is a forbidden system root or lives under one.

    ``/home`` itself is blocked, but ``/home/you/code/app`` is allowed.
    ``/var``, ``/etc``, ``/usr``, ``/opt``, and ``/root`` block the whole tree.
    """
    resolved = Path(path)
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = Path(path)
    text = str(resolved)
    if text in SENSITIVE_EXACT or text in SENSITIVE_TREES:
        return True
    for root in SENSITIVE_TREES:
        root_path = Path(root)
        try:
            if resolved == root_path or resolved.is_relative_to(root_path):
                return True
        except (ValueError, OSError):
            if text == root or text.startswith(root + "/"):
                return True
    return False
