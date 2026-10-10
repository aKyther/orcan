"""Conservative developer selection; the default/CI still runs every test."""

import ast
import shutil
import subprocess

import pytest


@pytest.fixture(scope="session")
def git_template(tmp_path_factory):
    """Initialize once; consumers always receive a private copy, never a link."""
    path = tmp_path_factory.mktemp("git-template") / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    return path


@pytest.fixture
def git_repo_factory(git_template):
    def create(path):
        shutil.copytree(git_template, path)
        return path

    return create


def external_test_module(source):
    external = {"subprocess", "pty", "socket", "pexpect"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[0] in external for name in names):
            return True
    return False


def pytest_collection_modifyitems(items):
    # Classify whole modules, not individual assertions: a subprocess fixture
    # must not accidentally become a fast test. Explicit markers cover helpers
    # whose external boundary lives in another module.
    modules = {}
    for item in items:
        path = item.path
        if path not in modules:
            modules[path] = external_test_module(path.read_text(encoding="utf-8"))
        if modules[path]:
            item.add_marker(pytest.mark.integration)
