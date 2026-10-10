"""Regression checks for source scanning and the developer test runner."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def scan(repository):
    source = (ROOT / "scripts/repository/validate.sh").read_text()
    body = source[source.index("# One scan") : source.index("if (( fail )); then")]
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\nfail=0\n" + body + "\nexit $fail"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


def test_scan_checks_tracked_and_new_sources(repository):
    stale = "/".join(["scripts", "init-project.sh"])
    path = repository / "source.txt"
    path.write_text(stale)
    assert scan(repository).returncode == 1
    subprocess.run(["git", "add", "source.txt"], cwd=repository, check=True)
    assert scan(repository).returncode == 1
    path.write_text("current source\n")
    assert scan(repository).returncode == 0


def test_scan_excludes_even_tracked_build_output_and_secrets(repository):
    stale = "/".join(["scripts", "init-project.sh"])
    for name in [
        "studio/target/build.txt",
        "node_modules/dependency.txt",
        "dist/bundle.txt",
        "site/page.txt",
        ".venv-docs/file.txt",
        ".env",
        "secrets/test.txt",
        "test.key",
        ".ssh/test",
        "keys/test",
    ]:
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stale)
        subprocess.run(["git", "add", name], cwd=repository, check=True)
    assert scan(repository).returncode == 0


def test_scan_does_not_treat_git_errors_as_success(tmp_path):
    assert scan(tmp_path).returncode == 1


@pytest.fixture
def runner_environment(tmp_path):
    # Do not inherit exported shell functions (including a uv wrapper), tokens
    # or startup hooks. Tests need only executables and a disposable user home.
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "LANG": "C.UTF-8",
    }


def run_runner(environment, *arguments, check=True):
    # Mock uv in the same shell so shell/PATH startup policies cannot launch
    # nested real pytest runs while testing the runner itself.
    return subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            'uv() { printf "%s\\n" "$@"; }; source "$1" "${@:2}"',
            "test-runner",
            str(ROOT / "tests/host/run.sh"),
            *arguments,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=check,
        timeout=10,
    )


@pytest.mark.parametrize("mode", ["all", "fast", "integration"])
def test_runner_forwards_module_filters_and_selection(runner_environment, mode):
    result = run_runner(
        {**runner_environment, "ORCAN_TEST_MODE": mode},
        "tests/host/test_config_io.py",
        "-k",
        "name",
    )
    assert "tests/host/test_config_io.py\n-k\nname" in result.stdout
    if mode == "fast":
        assert "-m\nnot integration" in result.stdout
    elif mode == "integration":
        assert "-m\nintegration" in result.stdout
    else:
        assert "-m\npytest\n-q\ntests/host" in result.stdout


def test_coverage_runs_pytest_once_then_reports(runner_environment):
    result = run_runner({**runner_environment, "ORCAN_TEST_MODE": "all"}, "--coverage")
    assert result.stdout.count("pytest\n-q") == 1
    assert "coverage\nrun\n--branch" in result.stdout
    assert "coverage\nreport\n--show-missing" in result.stdout


def test_runner_rejects_unknown_selection(runner_environment):
    result = run_runner({**runner_environment, "ORCAN_TEST_MODE": "typo"}, check=False)
    assert result.returncode == 2
    assert "Unknown ORCAN_TEST_MODE" in result.stderr
