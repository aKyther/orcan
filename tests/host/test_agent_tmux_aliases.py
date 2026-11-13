"""Interactive tmux shortcuts keep argv boundaries and replace the pane shell."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALIASES = ROOT / "docker/rootfs/etc/orcan/shell/aliases.sh"
pytestmark = pytest.mark.integration

CASES = [
    ("codex-tmux", ["codex"]),
    ("codex-yolo-tmux", ["codex", "--dangerously-bypass-approvals-and-sandbox"]),
    ("claude-tmux", ["claude"]),
    ("cc-tmux", ["claude"]),
    ("claude-yolo-tmux", ["claude", "--dangerously-skip-permissions"]),
    ("ccy-tmux", ["claude", "--dangerously-skip-permissions"]),
    ("agent-tmux", ["agent"]),
    ("ag-tmux", ["agent"]),
    ("agent-yolo-tmux", ["agent", "--yolo"]),
    ("agy-tmux", ["agent", "--yolo"]),
    ("codex-tmux-yolo", ["codex", "--dangerously-bypass-approvals-and-sandbox"]),
    ("claude-tmux-yolo", ["claude", "--dangerously-skip-permissions"]),
    ("agent-tmux-yolo", ["agent", "--yolo"]),
]


def shell_command(shell, script, *arguments):
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} unavailable")
    flags = ["--noprofile", "--norc"] if shell == "bash" else ["-f"]
    prefix = "shopt -s expand_aliases\n" if shell == "bash" else ""
    return [executable, *flags, "-c", prefix + script, "alias-fixture", *arguments]


@pytest.fixture
def executable_dir():
    # /tmp may be mounted noexec. Execute fixture CLIs from this checkout;
    # each test owns and removes only its unique temporary directory.
    root = ROOT / ".orcan-test.aliases"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=root) as directory:
        yield Path(directory)


def fake_command(directory, name):
    path = directory / name
    path.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "print(json.dumps({'argv':sys.argv[1:],'pid':os.getpid()}))\n"
    )
    path.chmod(0o700)


@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize("name,client", CASES)
def test_tmux_aliases_preserve_flags_resume_arguments_and_exec(
    executable_dir, shell, name, client
):
    fake_command(executable_dir, "orcan-executor")
    fake_command(executable_dir, "agent")
    extra = [
        "resume",
        "--last",
        "prompt with spaces; $(literal)",
        "--model",
        "chosen-model",
    ]
    # zsh parses -c before sourcing aliases. Parse only this fixed command
    # again afterwards; user arguments remain quoted positional parameters.
    script = (
        '. "$1"\nshift\n'
        + "eval "
        + shlex.quote(name + ' "$@"')
        + "\nprintf SHELL_RETURNED\n"
    )
    process = subprocess.Popen(
        shell_command(shell, script, str(ALIASES), *extra),
        env={
            **os.environ,
            "PATH": f"{executable_dir}:/usr/bin:/bin",
            "ORCAN_REDIS_ENABLED": "1",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, stderr
    observed = json.loads(stdout)  # No trailing shell output after exec.
    assert observed == {"argv": ["agent", "--", *client, *extra], "pid": process.pid}


@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize(
    "enabled,executor", [("0", True), ("", True), ("1", False), ("1", True)]
)
def test_aliases_follow_plugin_configuration_without_changing_standard_aliases(
    tmp_path, shell, enabled, executor
):
    if executor:
        fake_command(tmp_path, "orcan-executor")
    script = (
        '. "$1"\n'
        + "\n".join(
            f"alias {shlex.quote(name)} 2>/dev/null || :" for name, _ in CASES[:6]
        )
        + "\nalias cc ccy\n"
    )
    # command is a shell builtin. Control availability independent of host tools.
    script = (
        'command() { case "$2" in orcan-executor) [ "$TEST_EXECUTOR" = 1 ];; *) return 1;; esac; }\n'
        + script
    )
    result = subprocess.run(
        shell_command(shell, script, str(ALIASES)),
        env={
            **os.environ,
            "ORCAN_REDIS_ENABLED": enabled,
            "TEST_EXECUTOR": str(int(executor)),
        },
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    assert ("codex-tmux=" in result.stdout) == (enabled == "1" and executor)
    assert ("claude-tmux=" in result.stdout) == (enabled == "1" and executor)
    assert "cc='claude'" in result.stdout or "cc=claude" in result.stdout
    assert "ccy='claude --dangerously-skip-permissions'" in result.stdout
