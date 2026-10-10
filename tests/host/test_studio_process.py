"""Fast command-policy contracts: never execute an external helper."""

import studio_process as process


def test_mutations_have_a_deadline(monkeypatch):
    seen = {}

    def run(command, **kwargs):
        seen.update(kwargs)
        return process.subprocess.CompletedProcess(command, 0, "done", "")

    monkeypatch.setattr(process.subprocess, "run", run)
    assert process.run_command(["orcan", "sync"]).stdout == "done"
    assert seen["timeout"] == process.MUTATION_TIMEOUT


def test_timeout_is_not_reported_as_rollback(monkeypatch):
    def run(command, **kwargs):
        raise process.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(process.subprocess, "run", run)
    result = process.run_command(["git", "clone"], timeout=process.IMPORT_TIMEOUT)
    assert result.returncode == 124
    assert "not rolled back" in result.stderr
    assert "Refresh" in result.stderr
