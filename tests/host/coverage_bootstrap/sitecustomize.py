"""Activated only by the coverage runner's private PYTHONPATH entry."""

import os
import sys

root = os.environ.get("ORCAN_COVERAGE_ROOT")
# Version/PATH discovery frequently invokes Python -c. It executes no source
# file under test, so do not start an expensive collector for those helpers.
script = os.path.realpath(sys.argv[0]) if sys.argv else ""
instrument = root and any(
    script.startswith(os.path.realpath(root) + suffix)
    for suffix in ("/scripts/repository/", "/cockpit/src/")
)

if os.environ.get("COVERAGE_PROCESS_START") and instrument:
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
