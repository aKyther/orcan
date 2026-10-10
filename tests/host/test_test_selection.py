"""Explicit markers and an enforced process boundary keep fast tests honest."""

import pytest
import subprocess
import sys


def test_pure_test_cannot_launch_even_through_an_imported_helper():
    with pytest.raises(AssertionError, match="mark this test integration"):
        subprocess.run([sys.executable, "-c", "raise SystemExit(99)"], check=True)


@pytest.mark.integration
def test_explicit_integration_marker_allows_a_real_helper():
    assert subprocess.run([sys.executable, "-c", "pass"], check=False).returncode == 0
