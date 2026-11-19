"""Runtime settings use the Redis package contract, including standalone installs."""

import json

import pytest

from orcan_executor import plugin, settings


def test_runtime_consumes_package_defaults_bounds_and_environment_names(monkeypatch):
    contract = {
        "max_running": {
            "env": "ORCAN_TEST_PLUGIN_RUNNING",
            "default": 2,
            "minimum": 2,
            "maximum": 4,
        }
    }
    monkeypatch.setattr(settings, "fields", lambda: contract)
    monkeypatch.delenv("ORCAN_TEST_PLUGIN_RUNNING", raising=False)
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "99")
    assert settings.max_running() == 2
    monkeypatch.setenv("ORCAN_TEST_PLUGIN_RUNNING", "4")
    assert settings.max_running() == 4
    monkeypatch.setenv("ORCAN_TEST_PLUGIN_RUNNING", "1")
    with pytest.raises(ValueError, match="between 2 and 4"):
        settings.max_running()


def test_standalone_package_uses_its_bundled_descriptor(tmp_path, monkeypatch):
    installed = tmp_path / "env/lib/python/site-packages/orcan_executor/plugin.py"
    installed.parent.mkdir(parents=True)
    (installed.parent / "redis-plugin.json").write_text(
        json.dumps(
            {
                "id": "redis",
                "version": 1,
                "fields": {"standalone": {"default": 7}},
            }
        )
    )
    monkeypatch.setattr(plugin, "__file__", str(installed))
    plugin.fields.cache_clear()
    try:
        assert plugin.fields() == {"standalone": {"default": 7}}
    finally:
        plugin.fields.cache_clear()
