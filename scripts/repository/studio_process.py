"""Bounded Studio mutations; failures never imply rollback or a safe retry."""

from __future__ import annotations

import subprocess

CHECK_TIMEOUT = 15
MUTATION_TIMEOUT = 300
IMPORT_TIMEOUT = 840  # below Studio's 900s transport deadline


def run_command(
    command: list[str], *, timeout: int = MUTATION_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command,
            124,
            "",
            "Operation timed out; changes are not rolled back. Refresh the host before retrying.",
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))
