"""Exercise the actual Studio export scripts without WSL or SSH."""

import pytest

import io
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_studio_cli_kit_exports_a_clean_archive():
    script = (ROOT / "studio/app/src-tauri/src/cli_export.sh").read_text()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "VERSION").write_text("test\n")
        prelude = """
orcan() {
    shift 2
    python3 "$EXPORTER" --root "$KIT_ROOT" "$@"
}
"""
        result = subprocess.run(
            ["bash", "-c", prelude + script],
            env={
                **os.environ,
                "EXPORTER": str(ROOT / "scripts/repository/orcan-cli-kit.py"),
                "KIT_ROOT": str(root),
            },
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
        assert b'"ok": true' in result.stderr
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
            assert "./manifest.json" in archive.getnames()
            assert "./install-orcan-cli.sh" in archive.getnames()


def test_failed_export_cleans_temporary_directory(tmp_path):
    script = (ROOT / "studio/app/src-tauri/src/cli_export.sh").read_text()
    result = subprocess.run(
        ["bash", "-c", "orcan() { return 7; }; " + script],
        env={**os.environ, "TMPDIR": str(tmp_path)},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 7
    assert result.stdout == b""
    assert list(tmp_path.iterdir()) == []
