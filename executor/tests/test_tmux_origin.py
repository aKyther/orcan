import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

from orcan_executor import cli, engine, events, notifications, origin, store, tmux_adapter

INSTANCE = "019bcf10-1000-7000-8000-000000000002"


@pytest.fixture(autouse=True)
def no_live_tmux(monkeypatch):
    for key in ("TMUX", "TMUX_PANE", "ORCAN_AGENT_INSTANCE_ID", "CODEX_THREAD_ID"):
        monkeypatch.delenv(key, raising=False)


def test_origin_without_tmux_is_metadata_not_a_destination(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", INSTANCE)
    monkeypatch.setenv("UNRELATED_SECRET", "DO_NOT_COLLECT")
    value = origin.collect()
    assert value["status"] == "not_in_tmux"
    assert value["codex_thread_id_reported"] == INSTANCE
    assert value["submitter"]["pid"] == os.getpid()
    assert "DO_NOT_COLLECT" not in json.dumps(value)


def test_stale_tmux_environment_is_not_confirmed(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/test.sock,99,0")
    monkeypatch.setenv("TMUX_PANE", "%1")
    monkeypatch.setattr(origin, "tmux_identity", Mock(side_effect=ValueError))
    assert origin.collect()["status"] == "tmux_unconfirmed"


@pytest.mark.parametrize("arguments", [[], ["--directory", "--include", "check.py"]])
def test_notify_tmux_rejects_before_job_or_snapshot(repo, monkeypatch, capsys, arguments):
    submit = Mock()
    monkeypatch.setattr(engine, "submit", submit)
    assert (
        cli.main(
            ["submit", "--repo", str(repo), "--profile", "quality", "--notify-tmux", *arguments]
        )
        == 1
    )
    submit.assert_not_called()
    with store.database() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert "--notify-tmux requires" in capsys.readouterr().out


def test_default_submit_keeps_notifications_opt_in_and_records_origin(repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "enqueue", Mock())
    monkeypatch.setattr(events, "publish_pending", Mock())
    assert cli.main(["submit", "--repo", str(repo), "--profile", "quality"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["origin"]["status"] == "not_in_tmux"
    assert notifications.listing(output["job_id"]) == []
    records = store.origins(output["job_id"])
    assert records[0]["id"] == output["submission_id"]
    assert records[0]["origin"] == output["origin"]
    assert cli.main(["origins", output["job_id"]]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == output["submission_id"]


def test_joined_submissions_preserve_separate_origins(repo):
    first = engine.submit(repo, "HEAD", "one", "quality", [], 30, reuse=True, origin={"agent": "a"})
    second = engine.submit(
        repo, "HEAD", "two", "quality", [], 30, reuse=True, origin={"agent": "b"}
    )
    assert second["id"] == first["id"]
    assert second["submission_mode"] == "joined"
    assert second["submission_id"] != first["submission_id"]
    assert second["origin"] == {"agent": "b"}
    assert {row["origin"]["agent"] for row in store.origins(first["id"])} == {"a", "b"}


def test_historical_submission_has_no_invented_origin(repo):
    job = engine.submit(repo, "HEAD", "old", "quality", [], 30)
    with store.database() as db:
        db.execute(
            "INSERT INTO submissions(id,job_id,created,mode,sha,task) VALUES(?,?,?,?,?,?)",
            ("historic", job["id"], store.now(), "created", job["sha"], "old"),
        )
    assert (
        next(row for row in store.origins(job["id"]) if row["id"] == "historic")["origin"] is None
    )


def record(monkeypatch):
    proc = {"pid": os.getpid(), "start_ticks": 123, "state": "S"}
    target = {
        "socket": "/tmp/isolated.sock",
        "pane_id": "%17",
        "session_id": "$1",
        "window_id": "@2",
        "owner": proc,
        "server": dict(proc),
        "dead": False,
        "in_mode": False,
    }
    value = {"instance_id": INSTANCE, "pid_namespace": origin.pid_namespace(), "tmux": target}
    path = tmux_adapter.registry() / (INSTANCE + ".json")
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    monkeypatch.setattr(origin, "tmux_identity", Mock(return_value=target))
    return target


@pytest.mark.parametrize("change", ["owner", "server", "dead", "namespace", "panel"])
def test_replaced_target_is_rejected_before_job(repo, monkeypatch, capsys, change):
    target = record(monkeypatch)
    observed = {"status": "tmux_observed", "agent_instance_id": INSTANCE, "tmux": dict(target)}
    if change in {"owner", "server"}:
        target[change] = dict(target[change], start_ticks=999)
    elif change == "dead":
        target["dead"] = True
    elif change == "namespace":
        monkeypatch.setattr(origin, "pid_namespace", lambda: "different")
    else:
        observed["tmux"]["pane_id"] = "%99"
    monkeypatch.setattr(origin, "collect", lambda: observed)
    submit = Mock()
    monkeypatch.setattr(engine, "submit", submit)
    assert cli.main(["submit", "--repo", str(repo), "--profile", "quality", "--notify-tmux"]) == 1
    submit.assert_not_called()


def test_explicit_tmux_submit_uses_separate_adapter_and_receipt(repo, monkeypatch, capsys):
    target = record(monkeypatch)
    observed = {"status": "tmux_observed", "agent_instance_id": INSTANCE, "tmux": target}
    monkeypatch.setattr(origin, "collect", lambda: observed)
    monkeypatch.setattr(cli, "enqueue", Mock())
    monkeypatch.setattr(events, "publish_pending", Mock())
    assert cli.main(["submit", "--repo", str(repo), "--profile", "quality", "--notify-tmux"]) == 0
    output = json.loads(capsys.readouterr().out)
    job = output["job_id"]
    engine.run_job(job)
    send = Mock(return_value=("queued", "input accepted, not consumed"))
    monkeypatch.setattr(tmux_adapter, "send", send)
    assert notifications.deliver(job) == 1
    assert notifications.deliver(job) == 0
    instance, text = send.call_args.args
    assert instance == INSTANCE and "--tmux-instance " + INSTANCE in text
    delivery = notifications.listing(job)[0]
    assert delivery["adapter"] == "tmux" and delivery["status"] == "queued"
    assert cli.main(["ack", job, "--tmux-instance", INSTANCE]) == 0
    assert notifications.listing(job)[0]["status"] == "consumed"


def test_ambiguous_terminal_delivery_is_not_retried(repo, monkeypatch):
    record(monkeypatch)
    job = engine.submit(repo, "HEAD", "uncertain", "quality", [], 30)
    engine.run_job(job["id"])
    notifications.register(job["id"], INSTANCE, "tmux")
    send = Mock(return_value=("unknown", "paste acceptance unknown"))
    monkeypatch.setattr(tmux_adapter, "send", send)
    assert notifications.deliver(job["id"]) == 1
    assert notifications.deliver(job["id"]) == 0
    send.assert_called_once()


def test_send_uses_literal_buffer_and_revalidates_before_enter(monkeypatch):
    target = record(monkeypatch)
    commands = []

    def run(argv, **kwargs):
        commands.append((argv, kwargs))

    monkeypatch.setattr(tmux_adapter.subprocess, "run", run)
    text = "result: $(do-not-execute) ; Enter\nline two"
    assert tmux_adapter.send(INSTANCE, text)[0] == "queued"
    assert commands[0][1]["input"] == text.encode()
    assert any("paste-buffer" in argv and "-p" in argv for argv, _ in commands)
    assert next(argv for argv, _ in commands if "send-keys" in argv) == [
        "tmux",
        "-S",
        target["socket"],
        "send-keys",
        "-t",
        "%17",
        "Enter",
    ]
    assert origin.tmux_identity.call_count == 3


def test_target_exiting_after_paste_never_receives_enter(monkeypatch):
    target = record(monkeypatch)
    origin.tmux_identity.side_effect = [target, target, ValueError("gone")]
    commands = []
    monkeypatch.setattr(tmux_adapter.subprocess, "run", lambda argv, **kw: commands.append(argv))
    assert tmux_adapter.send(INSTANCE, "result")[0] == "unknown"
    assert not any("send-keys" in argv for argv in commands)


def test_agent_wrapper_requires_exec_and_passes_original_arguments(monkeypatch):
    target = record(monkeypatch)
    monkeypatch.setattr(
        origin,
        "collect",
        lambda: {
            "status": "tmux_observed",
            "pid_namespace": origin.pid_namespace(),
            "tmux": target,
        },
    )
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/fake-agent")
    captured = {}

    def execute(executable, arguments, environment):
        captured.update(
            executable=executable,
            arguments=arguments,
            instance=environment["ORCAN_AGENT_INSTANCE_ID"],
        )
        path = tmux_adapter.registry() / (captured["instance"] + ".json")
        assert path.stat().st_mode & 0o777 == 0o600
        assert "private-argument" not in path.read_text()
        raise SystemExit(77)

    monkeypatch.setattr(os, "execvpe", execute)
    with pytest.raises(SystemExit):
        tmux_adapter.launch(["--", "fake-agent", "private-argument"])
    assert captured["arguments"] == ["/usr/bin/fake-agent", "private-argument"]
    assert not (tmux_adapter.registry() / (captured["instance"] + ".json")).exists()
    target["owner"] = dict(target["owner"], pid=os.getpid() + 1)
    with pytest.raises(ValueError, match="Run exec"):
        tmux_adapter.launch(["fake-agent"])


def test_real_isolated_tmux_wrapper_to_dummy_terminal(repo, tmp_path, monkeypatch):
    if shutil.which("tmux") is None:
        pytest.skip("tmux unavailable")
    socket = tmp_path / "tmux.sock"
    ready, received = tmp_path / "ready.json", tmp_path / "received.txt"
    receiver = tmp_path / "receiver.py"
    receiver.write_text(
        "import os,json,sys,tty,time\nfrom pathlib import Path\n"
        "tty.setraw(sys.stdin.fileno())\nsys.stdout.write('\\x1b[?2004h');sys.stdout.flush()\n"
        f"Path({str(ready)!r}).write_text(json.dumps({{key:os.environ[key] for key in ['TMUX','TMUX_PANE','ORCAN_AGENT_INSTANCE_ID']}}))\n"
        "data=b''\nwhile b'\\r' not in data: data+=os.read(0,4096)\n"
        f"Path({str(received)!r}).write_bytes(data)\n"
        "time.sleep(60)\n"
    )
    command = "exec " + shlex.join(
        [sys.executable, "-m", "orcan_executor.cli", "agent", "--", sys.executable, str(receiver)]
    )

    def tmux(*arguments):
        return subprocess.run(
            ["tmux", "-S", str(socket), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )

    try:
        tmux("-f", "/dev/null", "new-session", "-d", "-s", "fixture", command)
        deadline = time.monotonic() + 4
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "dummy terminal did not register"
        for key, value in json.loads(ready.read_text()).items():
            monkeypatch.setenv(key, value)
        observed = origin.collect()
        instance = tmux_adapter.prepare_submission(observed)
        job = engine.submit(repo, "HEAD", "isolated tmux", "quality", [], 30, origin=observed)
        notifications.register(job["id"], instance, "tmux")
        engine.run_job(job["id"])
        assert notifications.deliver(job["id"]) == 1
        deadline = time.monotonic() + 3
        while not received.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        data = received.read_bytes()
        assert job["id"].encode() in data and data.endswith(b"\x1b[201~\r")
        assert data.startswith(b"\x1b[200~")
        assert notifications.listing(job["id"])[0]["status"] == "queued"
        tmux("kill-pane", "-t", observed["tmux"]["pane_id"])
        with pytest.raises(ValueError):
            tmux_adapter.validate(instance)
    finally:
        subprocess.run(
            ["tmux", "-S", str(socket), "kill-server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
