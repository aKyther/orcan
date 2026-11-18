"""Isolated host lifecycle harness shared by bundled plugin integration tests."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKEN_VARIABLES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "ORCAN_GITHUB_TOKEN",
    "GH_HOST",
    "GITLAB_TOKEN",
    "GITLAB_ACCESS_TOKEN",
    "OAUTH_TOKEN",
    "CI_JOB_TOKEN",
    "ORCAN_GITLAB_TOKEN",
)


@pytest.fixture
def shell(tmp_path: Path):
    tools = tmp_path / "tools"
    tools.mkdir()
    gh = tools / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GH_CALLS"\n'
        'test -n "$GH_SAVED_FIXTURE" || exit 1\n'
        'printf "%s" "$GH_SAVED_FIXTURE"\n'
    )
    gh.chmod(0o755)
    glab = tools / "glab"
    glab.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GLAB_CALLS"\n'
        'test -n "$GLAB_SAVED_FIXTURE" || exit 1\n'
        'printf "%s" "$GLAB_SAVED_FIXTURE"\n'
    )
    glab.chmod(0o755)
    env = {
        key: value for key, value in os.environ.items() if key not in TOKEN_VARIABLES
    }
    env.update(
        PATH=f"{tools}:{env['PATH']}",
        ORCAN_RUNTIME_DIR=str(tmp_path / "mounts"),
        ORCAN_HOME=str(tmp_path),
        ORCAN_CONFIG_FILE=str(tmp_path / "orcan.config.json"),
        GH_CALLS=str(tmp_path / "gh-calls"),
        GH_SAVED_FIXTURE="",
        GH_FIXTURE_SCRIPT=str(gh),
        GLAB_CALLS=str(tmp_path / "glab-calls"),
        GLAB_SAVED_FIXTURE="",
        GLAB_FIXTURE_SCRIPT=str(glab),
        ORCAN_ENV_FILE=str(tmp_path / "fixture.env"),
        ORCAN_ROOT=str(ROOT),
        ORCAN_SCRIPTS=str(ROOT / "scripts/repository"),
    )
    prefix = """
set -Eeuo pipefail
source cli/lib/compose.sh
source cli/commands/up.sh
# /tmp is noexec in some Orcan workspaces. Run the gh fixture via its shell.
env() {
    local args=() arg
    for arg; do
        if [[ "$arg" == gh ]]; then args+=(bash "$GH_FIXTURE_SCRIPT");
        elif [[ "$arg" == glab ]]; then args+=(bash "$GLAB_FIXTURE_SCRIPT");
        else args+=("$arg"); fi
    done
    command env "${args[@]}"
}
orcan_die() { printf '%s\\n' "$*" >&2; exit 1; }
orcan_usage_error() { orcan_die "$@"; }
orcan_info() { :; }
orcan_warn() { printf '%s\\n' "$*" >&2; }
orcan_ok() { :; }
orcan_require_docker() { :; }
orcan_require_generated() { :; }
orcan_startup_check_inputs() { :; }
orcan_startup_stage() { :; }
orcan_startup_verify() { orcan_plugins_run verify; }
orcan_load_config() { :; }
orcan_host_python() { python3 "$@"; }
orcan_maybe_hint_upgrade() { :; }
orcan_compose_ttyd_down_all_variants() { printf 'STOP\\n'; }
orcan_compose_up_run() { printf 'RUN %s %s %s %s %s %s\\n' "$1" "$2" "$3" "$4" "$5" "$7"; }
orcan_executor_url() { printf 'http://fixture.test:8765'; }
orcan_terminal_url() { printf 'http://fixture.test'; }
orcan_write_git_overlay() { printf '/fixture/ssh'; }
docker() { printf 'orcan-1 '; }
"""

    def run(script: str, **variables: str):
        return subprocess.run(
            ["bash", "-c", prefix + script],
            cwd=ROOT,
            env={**env, **variables},
            text=True,
            capture_output=True,
            check=False,
        )

    return run

