"""Opt-in experimental terminal delivery; never select the active/default pane."""

import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from . import origin
from .settings import state_dir


def registry():
    directory = state_dir() / "agent-instances"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def load(instance):
    if origin.uuid_value(instance) != instance:
        raise ValueError("A canonical Orcan agent instance UUID is required")
    path = registry() / (instance + ".json")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            content = stream.read(8193)
        if len(content) > 8192:
            raise ValueError("Oversized agent registration")
        value = json.loads(content)
        if value["instance_id"] != instance:
            raise ValueError("Agent registration mismatch")
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError(
            "Agent is not registered; launch with exec orcan-executor agent -- COMMAND"
        ) from None


def validate(instance, observed=None):
    record = load(instance)
    try:
        if not record["pid_namespace"] or record["pid_namespace"] != origin.pid_namespace():
            raise ValueError("Agent PID namespace changed")
        target = origin.tmux_identity(record["tmux"]["socket"], record["tmux"]["pane_id"])
        for key in ("server", "owner"):
            for field in ("pid", "start_ticks"):
                if target[key][field] != record["tmux"][key][field]:
                    raise ValueError("tmux pane or server was replaced")
        if target["dead"] or target["owner"]["state"] in {"Z", "X"}:
            raise ValueError("Agent pane has exited")
        if observed is not None:
            if (
                observed.get("status") != "tmux_observed"
                or observed.get("agent_instance_id") != instance
                or observed["tmux"]["socket"] != target["socket"]
                or observed["tmux"]["pane_id"] != target["pane_id"]
            ):
                raise ValueError("submit is not bound to this agent's tmux pane")
        return record, target
    except (KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        raise ValueError("Agent tmux identity cannot be confirmed") from error


def prepare_submission(observed):
    instance = observed.get("agent_instance_id")
    if not instance:
        raise ValueError(
            "--notify-tmux requires a registered agent in tmux; use exec orcan-executor agent -- COMMAND"
        )
    _, target = validate(instance, observed)
    if target["in_mode"]:
        raise ValueError("--notify-tmux cannot submit from tmux copy-mode")
    return instance


def launch(arguments):
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments:
        raise ValueError("agent requires an executable after --")
    executable = shutil.which(arguments[0])
    if executable is None:
        raise ValueError("Agent executable is unavailable")
    observed = origin.collect()
    if observed["status"] != "tmux_observed" or observed["tmux"]["dead"]:
        raise ValueError("agent requires a live, confirmed tmux pane")
    # Replace the pane owner rather than returning to a shell on agent exit.
    # Then an exit race cannot paste a result into a successor shell.
    if observed["tmux"]["owner"]["pid"] != os.getpid():
        raise ValueError("Run exec orcan-executor agent -- COMMAND so the agent owns the pane")
    instance = str(uuid4())
    value = {
        "instance_id": instance,
        "pid_namespace": observed["pid_namespace"],
        "tmux": observed["tmux"],
        "executable": Path(executable).name,
    }
    path = registry() / (instance + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
    environment = dict(os.environ, ORCAN_AGENT_INSTANCE_ID=instance)
    try:
        os.execvpe(executable, [executable, *arguments[1:]], environment)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def send(instance, text):
    if origin.uuid_value(instance) != instance:
        raise ValueError("A canonical Orcan agent instance UUID is required")
    # Serialize entire paste + Enter against other results for this instance.
    with (registry() / (instance + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            _, target = validate(instance)
            if target["in_mode"]:
                return "unavailable", "tmux pane is in copy-mode; no input sent"
        except ValueError:
            return "unavailable", "Agent/pane identity is no longer valid; no input sent"
        prefix = ["tmux", "-S", target["socket"]]
        buffer = "orcan-result-" + uuid4().hex

        def command(*args, **kwargs):
            return subprocess.run(
                [*prefix, *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=5,
                **kwargs,
            )

        attempted = False
        try:
            command("load-buffer", "-b", buffer, "-", input=text.encode())
            validate(instance)
            attempted = True
            command("paste-buffer", "-d", "-p", "-r", "-b", buffer, "-t", target["pane_id"])
            validate(instance)
            command("send-keys", "-t", target["pane_id"], "Enter")
            return "queued", "tmux paste and Enter completed; agent consumption is unconfirmed"
        except (ValueError, OSError, subprocess.SubprocessError):
            return (
                ("unknown", "Terminal input acceptance uncertain; not retried")
                if attempted
                else ("unavailable", "Terminal delivery unavailable; no input attempted")
            )
        finally:
            try:
                command("delete-buffer", "-b", buffer)
            except (OSError, subprocess.SubprocessError):
                pass
