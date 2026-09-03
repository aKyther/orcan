"""Shared path safety checks for host-side config / mounts."""

from __future__ import annotations

import os
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


class PathGuardError(ValueError):
    """A project / mount path failed a safety or existence check."""


def checked_project_dir(
    path: Path | str,
    *,
    must_exist: bool = True,
    require_readable: bool = True,
) -> Path:
    """Resolve *path* and enforce the shared project-path policy.

    One place for the "absolute, no ~, not a system tree, not $HOME" rules
    that config-wizard / apply-config / config-scaffold each used to spell
    out. Raises :class:`PathGuardError` (message only, no label) on any
    violation. With ``must_exist=False`` the directory need not exist yet
    (caller will mkdir) and the existence / readability checks are skipped.
    """
    raw = str(path)
    if "~" in raw:
        raise PathGuardError(f"must not contain ~ (got: {raw})")
    p = Path(raw)
    if not p.is_absolute():
        raise PathGuardError(f"must be an absolute path (got: {raw})")
    if must_exist:
        if not p.exists():
            raise PathGuardError(f"does not exist: {raw}")
        if not p.is_dir():
            raise PathGuardError(f"is not a directory: {raw}")
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise PathGuardError(f"cannot resolve path: {exc}") from exc
    if is_sensitive_path(resolved):
        raise PathGuardError(f"refusing sensitive path: {resolved}")
    if resolved == Path.home().resolve():
        raise PathGuardError(f"refusing to mount entire home: {resolved}")
    if must_exist and require_readable and not os.access(resolved, os.R_OK):
        raise PathGuardError(f"is not readable: {resolved}")
    return resolved
