"""Activated only by the coverage runner's private PYTHONPATH entry."""

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ImportError:
        pass  # A separately installed interpreter cannot collect coverage.
    else:
        # Subprocess tests often change cwd. Resolve sources relative to the
        # checkout, then restore the actual command's working directory.
        original = os.getcwd()
        try:
            os.chdir(os.environ["ORCAN_COVERAGE_ROOT"])
            coverage.process_startup()
        finally:
            os.chdir(original)
