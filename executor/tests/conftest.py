import json
import subprocess
import sys

import pytest


def commit(repo):
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "Fixture"], check=True)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.delenv("TTYD_CREDENTIAL", raising=False)
    monkeypatch.setenv("ORCAN_EXECUTOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCAN_EXECUTOR_QUEUE", "orcan-executor-tests")
    monkeypatch.setenv("ORCAN_REDIS_ENABLED", "1")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
    (root / ".orcan").mkdir()
    (root / "marker").write_text("snapshot")
    (root / "check.py").write_text(
        'import sys\nfrom pathlib import Path\nassert Path("marker").read_text() == "snapshot"\nprint("success noise" * 100000)\n'
    )
    (root / ".orcan/checks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": {
                    "selected": {
                        "requires_tests": True,
                        "steps": [{"argv": [sys.executable, "check.py", "{tests}"]}],
                    },
                    "quality": {"steps": [{"argv": [sys.executable, "check.py"]}]},
                },
            }
        )
    )
    commit(root)
    return root
