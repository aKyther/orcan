"""Exercise the actual Studio export scripts without WSL or SSH."""

import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_studio_cli_kit_exports_a_clean_archive():
    source = (ROOT / "studio/app/src-tauri/src/main.rs").read_text()
    scripts = re.findall(
        r'"(set -Eeuo pipefail; kit=.*?orcan bundle create.*?)"\n', source
    )
    assert len(scripts) == 2
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
