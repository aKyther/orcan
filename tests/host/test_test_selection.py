"""Selection never imports a test module or mistakes prose for a boundary."""

import pytest

from .conftest import external_test_module


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess as process",
        "from subprocess import run",
        "def fixture():\n    import pty",
        "from socket import socket",
    ],
)
def test_external_boundaries_are_integration(source):
    assert external_test_module(source)


def test_pure_imports_and_documentation_remain_fast():
    assert not external_test_module('import json\nmessage = "import subprocess"')
