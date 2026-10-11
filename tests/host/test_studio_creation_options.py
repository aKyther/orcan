"""Creation validation needs no subprocess; CLI integration checks stay separate."""

import argparse
from pathlib import Path

import pytest
from ._scripts_loader import load_script

creator = load_script("studio-enclave.py")


def options():
    return argparse.Namespace(
        identity_json=None,
        image=None,
        projects_root=None,
        ttyd_host_port=None,
        cpus=None,
        memory_gb=None,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cpus", float("nan")),
        ("cpus", 0),
        ("memory_gb", 0),
        ("ttyd_host_port", 65536),
        ("image", "orcan:latest;whoami"),
        ("projects_root", "relative"),
        ("projects_root", "/tmp/$EXPANSION"),
        ("projects_root", "/"),
        ("projects_root", "/etc"),
        ("projects_root", str(Path.home())),
    ],
)
def test_invalid_creation_options(field, value):
    args = options()
    setattr(args, field, value)
    with pytest.raises(ValueError):
        creator.build_configuration(args)


def test_valid_options_preserve_configuration(tmp_path):
    args = options()
    args.cpus, args.memory_gb, args.ttyd_host_port = 1.5, 8, 17682
    args.projects_root = str(tmp_path / "projects")
    assert creator.build_configuration(args) == {
        "workspaces": [],
        "resources": {"cpus": 1.5, "memory": "8g"},
        "ttyd": {"host_port": 17682},
        "projects_root": args.projects_root,
    }
    assert not Path(args.projects_root).exists()
