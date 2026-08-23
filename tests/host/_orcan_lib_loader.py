"""Test helper: load docker/rootfs/usr/local/lib/orcan/<name>.py as a real
`orcan.<name>` submodule (so intra-package imports like `from orcan.agent_inbox
import ...` resolve correctly), without relying on sys.path package discovery.

Not a test module itself (no test_*.py name, not picked up by discover).

Why this exists: this checkout's own workspaces/orcan/ directory (a synced
workspace happens to be named "orcan") can shadow the real `orcan` package
if it's ever resolved via plain sys.path search instead of being loaded
explicitly by file path — see tests/host/test_reconcile.py.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB_ORCAN_DIR = ROOT / "docker" / "rootfs" / "usr" / "local" / "lib" / "orcan"


def load_orcan_module(name: str) -> types.ModuleType:
    """Return orcan.<name>, loading (and registering) the `orcan` package stub first."""
    pkg = sys.modules.get("orcan")
    if pkg is None or getattr(pkg, "__path__", None) != [str(LIB_ORCAN_DIR)]:
        pkg = types.ModuleType("orcan")
        pkg.__path__ = [str(LIB_ORCAN_DIR)]
        sys.modules["orcan"] = pkg

    full_name = f"orcan.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(full_name, LIB_ORCAN_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    setattr(pkg, name, module)
    return module
