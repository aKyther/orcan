"""Bounded submission identity. Observations are not notification authorization."""

import os
import re
import subprocess
from pathlib import Path
from uuid import UUID

FORMAT = "\x1f".join(
    "#{" + field + "}"
    for field in (
        "session_id",
        "window_id",
        "pane_id",
        "pane_pid",
        "pid",
        "pane_dead",
        "pane_in_mode",
        "session_name",
        "window_name",
    )
)


def uuid_value(value):
    try:
        parsed = str(UUID(value))
        return parsed if parsed == value.lower() else None
    except (ValueError, TypeError, AttributeError):
        return None


def process_identity(pid):
    try:
        data = Path(f"/proc/{int(pid)}/stat").read_text()
        fields = data[data.rfind(")") + 2 :].split()
        return {"pid": int(pid), "start_ticks": int(fields[19]), "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def pid_namespace():
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return None


def tmux_identity(socket, pane):
    if (
        not isinstance(socket, str)
        or not socket.startswith("/")
        or len(socket) > 1024
        or any(not c.isprintable() for c in socket)
        or not re.fullmatch(r"%[0-9]+", pane or "")
    ):
        raise ValueError("Invalid tmux socket or pane identity")
    result = subprocess.run(
        ["tmux", "-S", socket, "display-message", "-p", "-t", pane, FORMAT],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=1,
        check=True,
    )
    fields = result.stdout.rstrip("\n").split("\x1f")
    if len(fields) != 9 or any(len(value) > 256 for value in fields):
        raise ValueError("Incomplete tmux identity")
    session, window, actual_pane, pane_pid, server_pid, dead, mode, session_name, window_name = (
        fields
    )
    if (
        not re.fullmatch(r"\$[0-9]+", session)
        or not re.fullmatch(r"@[0-9]+", window)
        or actual_pane != pane
        or not pane_pid.isdecimal()
        or not server_pid.isdecimal()
        or dead not in {"0", "1"}
        or mode not in {"0", "1"}
    ):
        raise ValueError("Unconfirmed tmux pane identity")
    server = process_identity(int(server_pid))
    owner = process_identity(int(pane_pid))
    if server is None or owner is None:
        raise ValueError("tmux processes cannot be confirmed in this PID namespace")
    return {
        "socket": socket,
        "session_id": session,
        "window_id": window,
        "pane_id": pane,
        "session_name": clean(session_name),
        "window_name": clean(window_name),
        "server": server,
        "owner": owner,
        "dead": dead == "1",
        "in_mode": mode == "1",
    }


def clean(value):
    return "".join(c for c in str(value) if c.isprintable())[:256]


def collect():
    result = {
        "version": 1,
        "status": "not_in_tmux",
        "pid_namespace": pid_namespace(),
        "submitter": process_identity(os.getpid()),
        "cwd": str(Path.cwd()),
        "workspace_reported": clean(os.environ.get("ORCAN_WORKSPACE_ROOT", "")) or None,
        "agent_instance_id": uuid_value(os.environ.get("ORCAN_AGENT_INSTANCE_ID")),
        "codex_thread_id_reported": uuid_value(os.environ.get("CODEX_THREAD_ID")),
    }
    reported_pane = os.environ.get("TMUX_PANE", "")
    result["pane_reported"] = clean(reported_pane) or None
    raw = os.environ.get("TMUX", "")
    if not raw or not reported_pane:
        return result
    try:
        socket, server, _ = raw.rsplit(",", 2)
        target = tmux_identity(socket, reported_pane)
        if str(target["server"]["pid"]) != server:
            raise ValueError("tmux server mismatch")
        result.update(status="tmux_observed", tmux=target)
    except (ValueError, OSError, subprocess.SubprocessError):
        result["status"] = "tmux_unconfirmed"
    return result
