"""CI job selection is a pure contract, independent of GitHub or Git."""

import pytest
from ci_scope import scope


@pytest.mark.parametrize(
    ("path", "image", "docs"),
    [
        ("scripts/repository/studio-probe.py", False, False),
        ("scripts/repository/generate-llms-txt.py", False, True),
        ("scripts/repository/check-product-name.sh", False, True),
        ("Dockerfile", True, False),
        ("docker/rootfs/usr/local/bin/ssh", True, False),
        ("docs/en/development/testing.md", False, True),
        ("AGENTS.md", False, True),
        (".cursor/rules/agents.mdc", False, True),
        ("tests/host/test_studio_probe.py", False, False),
        (".github/workflows/ci.yml", True, True),
        ("new-unknown-input", True, True),
    ],
)
def test_changed_paths_select_required_jobs(path, image, docs):
    assert scope([path]) == {"image": image, "docs": docs}


def test_manual_and_scheduled_runs_are_full_even_without_changes():
    assert all(scope([], full=True).values())
    assert not any(scope([]).values())
    assert scope(["docs/en/index.md", "cli/commands/studio.sh"])["image"] is False
