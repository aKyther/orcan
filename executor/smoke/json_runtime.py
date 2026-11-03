"""Exercise JSON-to-Compose launch using an isolated, existing Orcan image."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args, env):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:])
    return result.stdout


def main():
    name = "orcan-json-smoke-" + uuid.uuid4().hex[:12]
    image = os.environ.get("ORCAN_JSON_SMOKE_IMAGE", "orcan:4.0.17")
    run(["docker", "image", "inspect", image], os.environ)
    home = Path(tempfile.mkdtemp(prefix=".json-runtime-smoke-", dir=ROOT))
    env = {**os.environ, "ORCAN_HOME": str(home), "ORCAN_CONFIG_FILE": str(home / "orcan.config.json"),
           "ORCAN_RUNTIME_DIR": str(home / "mounts"), "ORCAN_INSTANCE": name,
           "COMPOSE_PROJECT_NAME": name, "ORCAN_ROOT": str(ROOT)}
    try:
        config = {"workspaces": [], "image": image, "data_root": str(home / "data"),
                  "projects_root": str(home / "data/sandbox"), "timezone": "Europe/Warsaw",
                  "resources": {"cpus": 1, "memory": "1g"},
                  "executor": {"workers": 5, "max_running": 5}}
        (home / "orcan.config.json").write_text(json.dumps(config))
        # This stale value must never reach Compose or execute as shell source.
        marker = home / "dotenv-executed"
        (home / ".env").write_text(f"TZ=WRONG\ntouch {marker}\n")
        run(["bash", "scripts/repository/sync-runtime.sh"], env)
        # Bypass the image entrypoint; no model, worker, supervisor or session starts.
        check = "import json,os; assert os.environ['TZ']=='Europe/Warsaw'; assert os.environ['ORCAN_EXECUTOR_WORKERS']=='5'; c=json.load(open('/etc/orcan/config.json')); assert c['executor']['max_running']==5; print('JSON_COMPOSE_OK')"
        script = '''source cli/lib/common.sh
orcan_load_config
export ORCAN_REDIS_ENABLED=1
orcan_compose_up_run 0 0 0 0 0 0 run --rm --no-deps --no-TTY --name "$1" --entrypoint python3 orcan -c "$2"
'''
        output = run(["bash", "-euc", script, "_", name, check], env)
        if "JSON_COMPOSE_OK" not in output or marker.exists():
            raise RuntimeError("JSON Compose environment was not verified")
        print(json.dumps({"status": "passed", "checks": 3, "dotenv_loaded": False}))
    finally:
        # Only resources belonging to this unique smoke invocation are removed.
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        subprocess.run(["docker", "network", "rm", name + "_default"], capture_output=True, timeout=20)
        shutil.rmtree(home)


if __name__ == "__main__":
    main()
