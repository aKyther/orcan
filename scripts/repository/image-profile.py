#!/usr/bin/env python3
"""Resolve a build profile using the same validation as image installation."""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "docker/rootfs/usr/local/lib")
)
from orcan.image_profile import main, resolve  # noqa: E402, F401

if __name__ == "__main__":
    raise SystemExit(main())
