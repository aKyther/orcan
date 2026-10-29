import json

from orcan_cockpit.peek import build_peek_text
from orcan_cockpit.runtime_limits import DEFAULTS, limits


def test_invalid_or_large_configuration_uses_safe_defaults(tmp_path, monkeypatch):
    config = tmp_path / "runtime.json"
    monkeypatch.setenv("ORCAN_CONFIG", str(config))
    config.write_text(
        json.dumps({"cockpit": {"pty_read_bytes": 1, "pty_read_ms": "slow"}})
    )
    assert limits() == DEFAULTS
    config.write_text("x" * (1024 * 1024 + 10))
    assert limits() == DEFAULTS


def test_valid_limits_and_bounded_brief_preview(tmp_path, monkeypatch):
    config = tmp_path / "runtime.json"
    monkeypatch.setenv("ORCAN_CONFIG", str(config))
    config.write_text(
        json.dumps(
            {"cockpit": {"pty_read_bytes": 8192, "pty_read_ms": 2, "peek_chars": 256}}
        )
    )
    assert limits()["pty_read_bytes"] == 8192
    (tmp_path / ".orcan").mkdir()
    brief = tmp_path / ".orcan/session-brief.md"
    brief.write_text("x" * 100000)
    assert build_peek_text(tmp_path) == "SESSION BRIEF\n" + "x" * 256
