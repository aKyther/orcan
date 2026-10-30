#!/usr/bin/env python3
"""Isolated smoke transport fixture. Never contacts a model or a real session."""

import json
import os
import sys
from pathlib import Path

if len(sys.argv) != 6 or sys.argv[1:3] != ["queue", "--thread"] or sys.argv[4] != "--message":
    sys.exit(2)

assert sys.argv[3] == "019bcf10-1000-7000-8000-000000000001"
assert len(sys.argv[5].encode()) <= 4096
state = Path(os.environ["ORCAN_EXECUTOR_STATE_DIR"])
with (state / "notification-smoke.jsonl").open("a") as output:
    output.write(json.dumps({"thread": sys.argv[3], "message": sys.argv[5]}) + "\n")
