"""Shared subprocess boundary for host and Cockpit tests."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def reject_external_process(*args, **kwargs):
    raise AssertionError(
        "Pure tests cannot start subprocesses. Mock the boundary or mark this test integration."
    )


@pytest.fixture(autouse=True)
def pure_process_boundary(request, monkeypatch):
    path = Path(str(request.node.path))
    guarded = any(
        path.is_relative_to(ROOT / scope)
        for scope in ("tests/host", "plugins/cockpit/tests")
    )
    if guarded and request.node.get_closest_marker("integration") is None:
        monkeypatch.setattr(subprocess, "Popen", reject_external_process)
