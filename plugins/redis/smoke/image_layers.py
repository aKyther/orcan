"""Validate the real Docker recipe/context without building a full runtime image."""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(arguments, **kwargs):
    result = subprocess.run(
        arguments, cwd=ROOT, capture_output=True, text=True, timeout=180, **kwargs
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:] or result.stdout[-2500:])
    return result


def main():
    run(
        [
            "docker",
            "buildx",
            "build",
            "--check",
            "--target",
            "runtime",
            "--build-arg",
            "GO_IMAGE=debian:bookworm-slim",
            "--build-arg",
            "RUST_IMAGE=debian:bookworm-slim",
            ".",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="orcan-context-check-") as directory:
        # A local exporter exercises .dockerignore with real BuildKit; no image tag,
        # runtime services or host bind mounts are involved.
        destination = Path(directory) / "context"
        run(
            [
                "docker",
                "buildx",
                "build",
                "--file",
                "-",
                "--output",
                "type=local,dest=" + str(destination),
                ".",
            ],
            input="FROM scratch\nCOPY . /\n",
        )
        expected = {
            "Dockerfile",
            ".dockerignore",
            "docker",
            "plugins",
            "requirements-actions.txt",
        }
        actual = {path.name for path in destination.iterdir()}
        if actual != expected:
            raise RuntimeError(
                "Build context includes unexpected top-level files: " + str(actual - expected)
            )
        for project in ("plugins/cockpit", "plugins/redis"):
            entries = {path.name for path in (destination / project).iterdir()}
            if not {"pyproject.toml", "uv.lock", "src", "plugin.json"} <= entries:
                raise RuntimeError("Incomplete extension context: " + project)
            if entries & {"tests", "smoke", ".venv", "__pycache__"}:
                raise RuntimeError("Non-runtime files leaked into context: " + project)
        size = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
        if size > 64 * 1024 * 1024:
            raise RuntimeError("Unexpectedly large source context: " + str(size))
        for name in ("docker/installers/install-jvm.sh", "plugins/redis/src", "plugins/cockpit/src"):
            if not (destination / name).exists():
                raise RuntimeError("Required source missing from context: " + name)
    print(
        json.dumps(
            {
                "status": "passed",
                "context_bytes": size,
                "runtime_image_built": False,
                "live_runtime_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
