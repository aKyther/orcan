"""Conservative developer selection; the default/CI still runs every test."""

import ast

import pytest


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
