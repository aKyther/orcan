"""Exercise the actual Studio export scripts without WSL or SSH."""

import pytest

import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_studio_cli_kit_exports_a_clean_archive():
    source_dir = ROOT / "studio/app/src-tauri/src"
    source = "\n".join(
        (source_dir / name).read_text()
        for name in ("main.rs", "installation.rs", "provisioning.rs")
    )
    scripts = [
        encoded
        for encoded in re.findall(r'"((?:\\.|[^"\\])*)"', source)
        if "orcan bundle create --output" in encoded
    ]
    assert len(scripts) == 3
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "VERSION").write_text("test\n")
        for encoded in scripts:
            script = json.loads('"' + encoded + '"').replace("{image_arg}", "")
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
            with tarfile.open(
                fileobj=io.BytesIO(result.stdout), mode="r:gz"
            ) as archive:
                assert "./manifest.json" in archive.getnames()
                assert "./install-orcan-cli.sh" in archive.getnames()
