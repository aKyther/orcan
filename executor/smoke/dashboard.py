"""Run the isolated browser smoke with checkout or shared development tooling."""

import os
import subprocess
from pathlib import Path


def main():
    common = Path(
        subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()
    ).resolve()
    candidates = [
        Path.cwd() / "node_modules",
        common.parent / ".orcan-dev-ux/playwright-node/node_modules",
    ]
    paths = [str(path) for path in candidates if (path / "playwright").is_dir()]
    if os.environ.get("NODE_PATH"):
        paths.append(os.environ["NODE_PATH"])
    environment = dict(os.environ, NODE_PATH=os.pathsep.join(paths))
    return subprocess.call(["node", "tests/smoke/executor-dashboard.js"], env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
