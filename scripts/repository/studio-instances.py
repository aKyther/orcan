"""Discover configured named runtimes without changing their data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def inventory(root: Path) -> list[dict[str, str | None]]:
    instances: list[dict[str, str | None]] = [
        {"instance": None, "container": "orcan-1", "home": str(root)}
    ]
    directory = root / "instances"
    if directory.is_dir():
        for home in sorted(directory.iterdir()):
            if (
                home.is_dir()
                and not home.is_symlink()
                and re.fullmatch(r"[a-z][a-z0-9-]{0,47}", home.name)
                and (
                    (home / "orcan.config.json").is_file()
                    or (home / "mounts/runtime-config.json").is_file()
                )
            ):
                instances.append(
                    {
                        "instance": home.name,
                        "container": f"orcan-{home.name}",
                        "home": str(home),
                    }
                )
    return instances


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    print(json.dumps({"instances": inventory(parser.parse_args().root)}))
