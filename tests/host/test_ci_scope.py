"""CI job selection is a pure contract, independent of GitHub or Git."""

import pytest
from ci_scope import scope


@pytest.mark.parametrize(
    ("path", "studio", "image", "docs"),
    [
        ("studio/app/src/main.ts", True, False, False),
        ("tests/browser/studio.spec.js", True, False, False),
        ("scripts/repository/studio-probe.py", True, False, False),
        ("Dockerfile", True, True, False),
        ("docker/rootfs/usr/local/bin/ssh", True, True, False),
        ("docs/en/development/testing.md", False, False, True),
        ("tests/host/test_studio_probe.py", False, False, False),
        (".github/workflows/ci.yml", True, True, True),
        ("new-unknown-input", True, True, True),
    ],
)
def test_changed_paths_select_required_jobs(path, studio, image, docs):
    assert scope([path]) == {"studio": studio, "image": image, "docs": docs}


def test_manual_and_scheduled_runs_are_full_even_without_changes():
    assert all(scope([], full=True).values())
    assert not any(scope([]).values())
    assert scope(["docs/en/index.md", "studio/app/src/main.ts"])["image"] is False
