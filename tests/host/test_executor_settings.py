"""Shared executor settings and interactive edits preserve workspace data."""

import pytest
from orcan.executor_config import DEFAULTS, resolve

from ._scripts_loader import load_script


@pytest.mark.parametrize(
    "value",
    [{"max_running": 0}, {"max_running": True}, {"split_lanes": 1}, {"unknown": 3}, []],
)
def test_invalid_executor_configuration_is_rejected(value):
    with pytest.raises(ValueError):
        resolve(value)


def test_runtime_config_materializes_executor_defaults_and_overrides():
    apply = load_script("apply-config.py")
    assert apply._resolved_runtime_settings({})["executor"] == DEFAULTS
    assert (
        apply._resolved_runtime_settings({"executor": {"max_running": 1}})["executor"][
            "max_running"
        ]
        == 1
    )


def test_settings_wizard_edits_executor_without_touching_workspaces(monkeypatch):
    wizard = load_script("settings-wizard.py")
    original = [{"name": "preserved", "projects": []}]
    cfg = {"workspaces": original}
    answers = iter(["2", "40", "900", "7200"])
    monkeypatch.setattr(wizard, "ask", lambda *args: next(answers))
    monkeypatch.setattr(wizard, "ask_yes_no", lambda *args, **kwargs: True)
    wizard.edit_executor(cfg)
    assert cfg["workspaces"] is original
    assert cfg["executor"] == {
        "split_lanes": True,
        "max_running": 2,
        "max_pending": 40,
        "timeout_seconds": 900,
        "retention_seconds": 7200,
    }
