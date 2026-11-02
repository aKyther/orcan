"""Real native install in an ephemeral existing image; no model or live service used."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4


def main():
    root = Path.cwd() / "docker/rootfs/usr/local/lib/orcan"
    sources = {name: (root / name).read_text() for name in ("install_agent.py", "image_profile.py")}
    script = (
        "import pathlib,subprocess,sys,tempfile\n"
        "with tempfile.TemporaryDirectory(prefix='orcan-agent-smoke-') as directory:\n"
        " root=pathlib.Path(directory)/'orcan'; root.mkdir(); (root/'__init__.py').touch()\n"
        f" sources={json.dumps(sources)}\n"
        " for name,content in sources.items(): (root/name).write_text(content)\n"
        " subprocess.run([sys.executable,str(root/'install_agent.py'),'claude'],check=True)\n"
    )
    name = "orcan-claude-installer-smoke-" + uuid4().hex[:12]
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--name",
                name,
                "--env",
                "ORCAN_BUILD_PROFILE_JSON=",
                "--entrypoint",
                "/opt/orcan-executor/venv/bin/python",
                "orcan:4.0.17",
                "-",
            ],
            input=script,
            text=True,
            timeout=360,
        )
        return result.returncode
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
