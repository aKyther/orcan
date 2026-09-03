"""Test helper: import a scripts/repository/<file>.py module by file path.

Several of those scripts have a hyphen in the name (apply-config.py,
config-wizard.py, config-scaffold.py, config-show.py, settings-wizard.py,
workspace-audit.py, reconcile-host.py) and can't be imported by module
name, so each test used to repeat the same importlib incantation. Use
this instead:

    from _scripts_loader import load_script
    apply_config = load_script("apply-config.py")

Not a test module itself (no test_*.py name, not picked up by discover).
Mirrors _orcan_lib_loader.py for the docker/rootfs `orcan` package.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "repository"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_script(filename: str, *, name: str | None = None) -> types.ModuleType:
    """Return the module for scripts/repository/<filename> (hyphens allowed)."""
    mod_name = name or Path(filename).stem.replace("-", "_")
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS_DIR / filename)
    assert spec and spec.loader, f"cannot load {filename}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module
