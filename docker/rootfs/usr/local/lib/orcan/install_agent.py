"""Build-time CLI installer with structured sources and checksum verification."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orcan.image_profile import agent_entry

BINARIES = {
    "claude": "claude",
    "cursor": "agent",
    "codex": "codex",
    "gemini": "gemini",
    "copilot": "copilot",
}


def download(url: str, target: Path, checksum: str = "") -> None:
    digest = hashlib.sha256()
    size = 0
    with (
        urllib.request.urlopen(url, timeout=60) as response,
        target.open("wb") as output,
    ):
        if not response.url.startswith("https://"):
            raise ValueError("Source redirected outside HTTPS")
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > 1024 * 1024 * 1024:
                raise ValueError("Agent download exceeds 1 GiB")
            digest.update(block)
            output.write(block)
    if checksum and digest.hexdigest() != checksum:
        raise ValueError("Agent source checksum mismatch")


def install(entry: dict, home: Path) -> None:
    source, name, version = entry["source"], entry["name"], entry["version"]
    if source["type"] == "npm":
        command = [
            "npm",
            "install",
            "-g",
            "--prefix",
            str(home / ".local"),
            source["package"] + "@" + version,
        ]
        if source.get("registry"):
            command += ["--registry", source["registry"]]
        subprocess.run(
            command,
            check=True,
            env={
                **os.environ,
                **({"npm_config_ignore_scripts": "false"} if name == "copilot" else {}),
            },
        )
    else:
        with tempfile.TemporaryDirectory(prefix="orcan-agent-") as temporary:
            temporary = Path(temporary)
            archive = temporary / "source"
            arch = {
                "x86_64": "x64",
                "amd64": "x64",
                "aarch64": "arm64",
                "arm64": "arm64",
            }.get(platform.machine())
            if not arch:
                raise ValueError("Unsupported agent architecture")
            download(
                source["url"].replace("{arch}", arch), archive, source.get("sha256", "")
            )
            if source["type"] == "installer":
                subprocess.run(
                    ["bash", str(archive), *([version] if name == "claude" else [])],
                    check=True,
                )
            else:
                extracted = temporary / "unpacked"
                extracted.mkdir()
                with tarfile.open(archive, "r:gz") as package:
                    package.extractall(extracted, filter="data")
                entries = list(extracted.iterdir())
                root = (
                    entries[0]
                    if len(entries) == 1 and entries[0].is_dir()
                    else extracted
                )
                if not (root / "cursor-agent").is_file():
                    raise ValueError("Cursor archive has no cursor-agent executable")
                destination = home / ".local/share/cursor-agent/versions" / version
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError("Agent version directory already exists")
                shutil.move(str(root), destination)
                (home / ".local/bin").mkdir(parents=True, exist_ok=True)
                for binary in ["agent", "cursor-agent"]:
                    link = home / ".local/bin" / binary
                    link.unlink(missing_ok=True)
                    link.symlink_to(destination / "cursor-agent")


def main():
    name = sys.argv[1]
    profile = json.loads(os.environ.get("ORCAN_BUILD_PROFILE_JSON") or "{}")
    selected = next(
        (
            entry
            for entry in profile.get("agents", [])
            if isinstance(entry, dict) and entry.get("name") == name
        ),
        {"name": name},
    )
    # Normalized built-in sources have no custom checksum requirement.
    entry = agent_entry(
        {key: value for key, value in selected.items() if key != "source"}
    )
    if selected.get("source") != entry["source"]:
        entry = agent_entry(selected)
    install(entry, Path.home())
    subprocess.run(
        [str(Path.home() / ".local/bin" / BINARIES[name]), "--version"], check=True
    )


if __name__ == "__main__":
    main()
