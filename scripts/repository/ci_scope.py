"""Select expensive CI jobs conservatively; unknown paths run everything."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def scope(paths: list[str], *, full: bool = False) -> dict[str, bool]:
    selected = dict.fromkeys(("studio", "image", "docs"), full)
    for path in paths:
        if path.startswith(("docs/", "overrides/")) or path in {
            "mkdocs.yml",
            "requirements-docs.txt",
            "README.md",
            "CHANGELOG.md",
        }:
            selected["docs"] = True
        elif path.startswith("studio/") or path.startswith("tests/browser/studio"):
            selected["studio"] = True
        elif path.startswith(("docker/", "cockpit/")) or path in {
            "Dockerfile",
            ".dockerignore",
            "VERSION",
        }:
            selected["image"] = True
            selected["studio"] = True  # runtime/report compatibility
        elif path.startswith(("cli/", "bin/", "scripts/repository/")):
            selected["studio"] = True
            if path.endswith("ci_scope.py"):
                selected = dict.fromkeys(selected, True)
        elif path.startswith("tests/host/") or path in {
            ".coveragerc",
            "pytest.ini",
            "requirements-test.txt",
            "pyproject.toml",
        }:
            continue  # the full host checks always run
        elif path in {"AGENTS.md", "CLAUDE.md", "LICENSE"} or path.startswith(
            ".cursor/"
        ):
            continue
        else:
            selected = dict.fromkeys(selected, True)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    paths = []
    full = args.full or not args.base or set(args.base) == {"0"}
    if not full:
        try:
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-only",
                    "--no-renames",
                    "-z",
                    args.base,
                    args.head,
                ],
                capture_output=True,
                check=True,
                timeout=30,
            )
            paths = (
                result.stdout.decode("utf-8", errors="replace").rstrip("\0").split("\0")
                if result.stdout
                else []
            )
        except (OSError, subprocess.SubprocessError):
            full = True  # missing history must never skip a relevant check
    output = "".join(
        f"{name}={str(enabled).lower()}\n"
        for name, enabled in scope(paths, full=full).items()
    )
    print(output, end="")
    if destination := os.environ.get("GITHUB_OUTPUT"):
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write(output)


if __name__ == "__main__":
    main()
