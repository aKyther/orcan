#!/usr/bin/env python3
"""Host tests for workspace-list paint signatures (idle flicker skip).

picker.py pulls Textual/libtmux at import time, so this loads only the
stdlib helpers by exec'ing the module source up to the Textual block.

Stubs are installed only for the duration of the load, then removed so
later host tests still see the real ``orcan.*`` modules.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PICKER_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "picker.py"
STATUS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "status.py"

_STUB_KEYS = (
    "libtmux",
    "libtmux.exc",
    "orcan.workspaces",
    "orcan_cockpit.session_glance",
    "orcan_cockpit.status",
)


def _load_picker_helpers():
    """Load paint helpers without importing Textual; leave sys.modules clean."""
    status_spec = importlib.util.spec_from_file_location("cockpit_status_paint", STATUS_PATH)
    status_mod = importlib.util.module_from_spec(status_spec)
    assert status_spec.loader is not None
    status_spec.loader.exec_module(status_mod)

    libtmux = types.ModuleType("libtmux")

    class _Server:
        sessions: list = []

        def has_session(self, _session: str) -> bool:
            return False

    libtmux.Server = _Server
    exc = types.ModuleType("libtmux.exc")

    class LibTmuxException(Exception):
        pass

    exc.LibTmuxException = LibTmuxException
    workspaces = types.ModuleType("orcan.workspaces")
    workspaces.compact_hints = lambda _ws: ""
    workspaces.iter_workspaces = lambda _cfg: []
    workspaces.load_config = lambda _path=None: {}
    glance = types.ModuleType("orcan_cockpit.session_glance")
    glance.format_glance = lambda lines, empty_hint="": empty_hint
    glance.glance_lines = lambda *_a, **_k: []

    src = PICKER_PATH.read_text(encoding="utf-8")
    cut = src.index("# --- Interactive Textual widget")
    helper_src = src[:cut]

    saved: dict[str, object | None] = {key: sys.modules.get(key) for key in _STUB_KEYS}
    # Prefer keeping a real ``orcan`` package if another test already loaded it;
    # only create a blank one when missing so ``orcan.workspaces`` can attach.
    created_orcan = "orcan" not in sys.modules
    if created_orcan:
        sys.modules["orcan"] = types.ModuleType("orcan")
    created_cockpit = "orcan_cockpit" not in sys.modules
    if created_cockpit:
        cockpit_pkg = types.ModuleType("orcan_cockpit")
        cockpit_pkg.__path__ = [str(ROOT / "cockpit" / "src" / "orcan_cockpit")]
        sys.modules["orcan_cockpit"] = cockpit_pkg

    sys.modules["orcan.workspaces"] = workspaces
    sys.modules["libtmux"] = libtmux
    sys.modules["libtmux.exc"] = exc
    sys.modules["orcan_cockpit.session_glance"] = glance
    sys.modules["orcan_cockpit.status"] = status_mod

    mod = types.ModuleType("cockpit_picker_paint")
    mod.__dict__["__name__"] = "cockpit_picker_paint"
    mod.__dict__["__file__"] = str(PICKER_PATH)
    try:
        exec(compile(helper_src, str(PICKER_PATH), "exec"), mod.__dict__)
    finally:
        for key, previous in saved.items():
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous  # type: ignore[assignment]
        if created_orcan:
            sys.modules.pop("orcan", None)
        if created_cockpit:
            sys.modules.pop("orcan_cockpit", None)
    return mod


picker = _load_picker_helpers()


def _row(**overrides):
    base = {
        "name": "dev",
        "root": "/tmp/dev",
        "session": "dev",
        "live": False,
        "repo_count": 0,
        "projects": [],
    }
    base.update(overrides)
    return base


class WorkspaceListPaintSignatureTests(unittest.TestCase):
    def test_identical_rows_share_signature(self) -> None:
        rows = [_row(), _row(name="other", session="other")]
        a = picker.workspace_list_paint_signature(
            rows, active_session=None, expanded=False
        )
        b = picker.workspace_list_paint_signature(
            rows, active_session=None, expanded=False
        )
        self.assertEqual(a, b)

    def test_live_flag_changes_signature(self) -> None:
        dead = [_row(live=False)]
        live = [_row(live=True)]
        self.assertNotEqual(
            picker.workspace_list_paint_signature(
                dead, active_session=None, expanded=False
            ),
            picker.workspace_list_paint_signature(
                live, active_session=None, expanded=False
            ),
        )

    def test_active_session_changes_signature_not_structure(self) -> None:
        rows = [_row(session="a"), _row(name="b", session="b")]
        self.assertEqual(
            picker.workspace_list_structure(rows),
            picker.workspace_list_structure(rows),
        )
        self.assertNotEqual(
            picker.workspace_list_paint_signature(
                rows, active_session="a", expanded=False
            ),
            picker.workspace_list_paint_signature(
                rows, active_session="b", expanded=False
            ),
        )

    def test_structure_tracks_membership(self) -> None:
        a = [_row(session="a")]
        b = [_row(session="a"), _row(name="b", session="b")]
        self.assertNotEqual(
            picker.workspace_list_structure(a),
            picker.workspace_list_structure(b),
        )

    def test_row_text_marks_live_and_active(self) -> None:
        text = picker.format_workspace_row_text(
            _row(live=True, name="ws"),
            active_session="dev",
            expanded=False,
        )
        self.assertIn("active", text)
        self.assertNotIn("●", text)
        self.assertIn("ws", text)

    def test_expanded_includes_root(self) -> None:
        with mock.patch.object(picker, "project_git_label", return_value="x"):
            text = picker.format_workspace_row_text(
                _row(root="/home/developer/workspaces/dev", repo_count=1, projects=[{}]),
                active_session=None,
                expanded=True,
            )
        self.assertIn("repo", text)
        self.assertIn("\n", text)

if __name__ == "__main__":
    unittest.main()
