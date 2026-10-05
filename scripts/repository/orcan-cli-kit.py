#!/usr/bin/env python3
"""Create a minimal, offline-installable Orcan CLI kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path


RUNTIME_PATHS = (
    "bin",
    "cli",
    "scripts/repository",
    "docker",
    "cockpit",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.docker.yml",
    "docker-compose.keepalive.yml",
    "docker-compose.ttyd.yml",
    ".env.example",
    "VERSION",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", help="optional local Docker image to include")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing path: {output}")
    output.mkdir(parents=True)
    runtime = output / "orcan-runtime.tar.gz"
    with tarfile.open(runtime, "w:gz") as archive:
        for relative in RUNTIME_PATHS:
            source = root / relative
            if source.exists():
                archive.add(source, arcname=relative, recursive=True)
    installer = Path(__file__).with_name("orcan-cli-kit-install.sh")
    shutil.copy2(installer, output / "install-orcan-cli.sh")
    (output / "install-orcan-cli.sh").chmod(0o755)
    artifacts = [runtime, output / "install-orcan-cli.sh"]
    if args.image:
        image = output / "orcan-image.tar"
        subprocess.run(["docker", "save", "--output", str(image), args.image], check=True)
        artifacts.append(image)
    manifest = {
        "format": 1,
        "version": (root / "VERSION").read_text().strip(),
        "artifacts": [{"name": item.name, "sha256": digest(item), "bytes": item.stat().st_size} for item in artifacts],
        "contains_user_configuration": False,
        "contains_projects": False,
        "contains_secrets": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"ok": True, "kit": str(output), "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
