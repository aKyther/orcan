"""tmux chrome helpers — breadcrumb, pin-main-agent, task templates.

Stdlib-only so host tests can mock ``subprocess`` without Textual.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_TMUX_TIMEOUT_S = 2
_PIN_FILE = ".orcan/main-pane"


def _tmux(*args: str) -> str:
    try:
        out = subprocess.check_output(
            ["tmux", *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_TMUX_TIMEOUT_S,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return out.strip()


def session_breadcrumb(session: str | None) -> str:
    """``w1 › claude`` for the active window/pane, or empty."""
    if not session:
        return ""
    raw = _tmux(
        "display-message",
        "-p",
        "-t",
        f"={session}:",
        "#{window_index}|#{pane_current_command}",
    )
    if "|" not in raw:
        return ""
    win, cmd = raw.split("|", 1)
    win = win.strip() or "?"
    cmd = (cmd.strip() or "zsh").split("/")[-1]
    return f"w{win} › {cmd}"


def list_agent_panes(session: str | None, *, limit: int = 6) -> list[dict[str, str]]:
    """Active-window panes: ``{id, cmd, path, title}``."""
    if not session:
        return []
    raw = _tmux(
        "list-panes",
        "-t",
        f"={session}:",
        "-F",
        "#{pane_id}\t#{pane_current_command}\t#{b:pane_current_path}\t#{pane_title}",
    )
    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append(
            {
                "id": parts[0].strip(),
                "cmd": (parts[1].strip() or "zsh").split("/")[-1],
                "path": parts[2].strip() if len(parts) > 2 else "",
                "title": parts[3].strip() if len(parts) > 3 else "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def pin_main_pane(session: str, workspace_root: str | Path, pane_id: str | None = None) -> bool:
    """Remember the active (or given) pane id under ``.orcan/main-pane``."""
    root = Path(workspace_root)
    if pane_id is None:
        pane_id = _tmux("display-message", "-p", "-t", f"={session}:", "#{pane_id}")
    if not pane_id.startswith("%"):
        return False
    path = root / _PIN_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pane_id + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def read_pinned_pane(workspace_root: str | Path) -> str | None:
    path = Path(workspace_root) / _PIN_FILE
    if not path.is_file():
        return None
    try:
        pane_id = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return pane_id if pane_id.startswith("%") else None


def focus_pinned_pane(session: str, workspace_root: str | Path) -> bool:
    pane_id = read_pinned_pane(workspace_root)
    if not pane_id:
        return False
    try:
        subprocess.run(
            ["tmux", "select-pane", "-t", pane_id],
            check=False,
            timeout=_TMUX_TIMEOUT_S,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def split_run(session: str, command: str, *, vertical: bool = True) -> bool:
    """``tmux split-window`` running *command* in *session*."""
    argv = [
        "tmux",
        "split-window",
        "-v" if vertical else "-h",
        "-t",
        f"={session}:",
        command,
    ]
    try:
        result = subprocess.run(argv, check=False, timeout=_TMUX_TIMEOUT_S, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def run_url_picker(session: str) -> bool:
    """tmux ``pick-url.sh`` against the attached session."""
    script = "/etc/tmux/scripts/pick-url.sh"
    if not Path(script).is_file():
        # Checkout / preview mirror.
        alt = Path(__file__).resolve().parents[3] / "docker" / "rootfs" / "etc" / "tmux" / "scripts" / "pick-url.sh"
        script = str(alt) if alt.is_file() else script
    try:
        result = subprocess.run(
            ["tmux", "run-shell", "-t", f"={session}:", script],
            check=False,
            timeout=30,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


# One-click task templates for the command palette.
TASK_TEMPLATES: dict[str, str] = {
    "claude": "claude",
    "review": "orcan-context-review; echo; read -p 'Press Enter to close…' _",
    "lazygit": "lg || lazygit",
}
