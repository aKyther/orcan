#!/usr/bin/env python3
"""Isolated Docker bind smoke; no SSH server, credentials or live Orcan changes."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    common = Path(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            text=True,
        ).strip()
    )
    # Detached executor checkouts may not be host-visible. The primary repo is a
    # canonical parity mount; copy this exact snapshot's fixture there temporarily.
    host_root = common.parent
    image = os.environ.get("ORCAN_STORAGE_TEST_IMAGE", "orcan:latest")
    subprocess.run(
        ["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, check=True
    )
    name = "orcan-storage-smoke-" + uuid4().hex[:12]
    with tempfile.TemporaryDirectory(
        prefix=".orcan-test.storage-bind-", dir=host_root
    ) as raw:
        fixture = Path(raw)
        module = fixture / "storage_config.py"
        shutil.copyfile(
            ROOT / "docker/rootfs/usr/local/lib/orcan/storage_config.py", module
        )
        payload = fixture / "payload"
        payload.mkdir()
        try:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network",
                    "none",
                    "--name",
                    name,
                    "--entrypoint",
                    "python3",
                    "--mount",
                    f"type=bind,source={payload},target={payload}",
                    "--mount",
                    f"type=bind,source={module},target=/storage_config.py,readonly",
                    "--env",
                    f"ORCAN_STORAGE_ROOT={payload}",
                    "--env",
                    "ORCAN_STORAGE_REQUIRE_MOUNT=1",
                    "--env",
                    "ORCAN_NAMED_INSTANCE=smoke",
                    image,
                    "/storage_config.py",
                    "--prepare",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("Bind smoke failed: " + result.stderr[-1200:])
            report = json.loads(result.stdout)
            assert report["ready"] is True
            assert (payload / "orcan/smoke/scratch").is_dir()
            missing = fixture / "missing"
            failed = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network",
                    "none",
                    "--entrypoint",
                    "true",
                    "--mount",
                    f"type=bind,source={missing},target=/payload",
                    image,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert failed.returncode != 0 and not missing.exists()
            print(
                json.dumps(
                    {
                        "bind_storage": "passed",
                        "missing_source_preserved": True,
                        "live_runtime_changed": False,
                    }
                )
            )
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


if __name__ == "__main__":
    main()
