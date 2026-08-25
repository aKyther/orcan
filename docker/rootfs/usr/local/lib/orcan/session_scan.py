"""Discover Claude Code / Cursor agent transcripts on disk and count turns.

Filesystem-driven Reflection feeder (no agent hooks). Claude Stop seeding
still exists separately; this module is the unified path for Claude + Cursor.
Codex is out of scope here for now.

Layouts observed in the orcan image (agent homes are bind-mounted):

  Claude:  $CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-id>.jsonl
  Cursor:  ~/.cursor/projects/<encoded-cwd>/agent-transcripts/<id>/<id>.jsonl

Encoding: absolute cwd with leading slash stripped and ``/`` → ``-``.
Claude prefixes the result with ``-``; Cursor does not.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


AGENTS = ("claude", "cursor")


@dataclass(frozen=True)
class SessionRef:
    agent: str
    session_id: str
    transcript_path: Path
    cwd: str


def claude_home() -> Path:
    raw = (os.environ.get("CLAUDE_CONFIG_DIR") or "").strip()
    return Path(raw) if raw else Path.home() / ".claude"


def cursor_home() -> Path:
    return Path.home() / ".cursor"


def encode_claude_project_dir(cwd: Path) -> str:
    return "-" + _encode_cwd(cwd)


def encode_cursor_project_dir(cwd: Path) -> str:
    return _encode_cwd(cwd)


def _encode_cwd(cwd: Path) -> str:
    resolved = str(cwd.resolve())
    return resolved.lstrip("/").replace("/", "-")


def candidate_cwds(workspace_root: Path, project_paths: Iterable[Path] | None = None) -> list[Path]:
    """Workspace root first, then each mounted project path (deduped).

    Agents often launch at the workspace root (tmux), but may also start
    inside a project checkout — both encodings must be scanned.
    """
    seen: set[str] = set()
    out: list[Path] = []
    for path in (workspace_root, *(project_paths or ())):
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def discover_sessions(
    workspace_root: Path,
    *,
    agents: Iterable[str] = AGENTS,
    project_paths: Iterable[Path] | None = None,
    claude_root: Path | None = None,
    cursor_root: Path | None = None,
) -> list[SessionRef]:
    """All Claude/Cursor transcripts whose project dir matches a candidate cwd."""
    wanted = {a for a in agents if a in AGENTS}
    cwds = candidate_cwds(workspace_root, project_paths)
    found: list[SessionRef] = []
    if "claude" in wanted:
        found.extend(_discover_claude(claude_root or claude_home(), cwds))
    if "cursor" in wanted:
        found.extend(_discover_cursor(cursor_root or cursor_home(), cwds))
    found.sort(key=lambda s: (s.agent, s.session_id))
    return found


def _discover_claude(home: Path, cwds: list[Path]) -> list[SessionRef]:
    projects = home / "projects"
    if not projects.is_dir():
        return []
    out: list[SessionRef] = []
    for cwd in cwds:
        proj = projects / encode_claude_project_dir(cwd)
        if not proj.is_dir():
            continue
        for path in sorted(proj.glob("*.jsonl")):
            # Skip nested subagent transcripts under <session-id>/subagents/
            if path.parent != proj:
                continue
            out.append(
                SessionRef(
                    agent="claude",
                    session_id=path.stem,
                    transcript_path=path,
                    cwd=str(cwd),
                )
            )
    return out


def _discover_cursor(home: Path, cwds: list[Path]) -> list[SessionRef]:
    projects = home / "projects"
    if not projects.is_dir():
        return []
    out: list[SessionRef] = []
    for cwd in cwds:
        transcripts = projects / encode_cursor_project_dir(cwd) / "agent-transcripts"
        if not transcripts.is_dir():
            continue
        for session_dir in sorted(p for p in transcripts.iterdir() if p.is_dir()):
            path = session_dir / f"{session_dir.name}.jsonl"
            if not path.is_file():
                # Fall back to any single jsonl in the session dir
                matches = sorted(session_dir.glob("*.jsonl"))
                if not matches:
                    continue
                path = matches[0]
            out.append(
                SessionRef(
                    agent="cursor",
                    session_id=session_dir.name,
                    transcript_path=path,
                    cwd=str(cwd),
                )
            )
    return out


def is_turn_line(agent: str, line: str) -> bool:
    """Whether a JSONL line counts as one 'turn' toward the batch threshold.

    Claude: real user messages (not tool_result echo-backs).
    Cursor: role=user rows.
    Roughly aligned with "completed user round" rather than every assistant
    tool step — closer to the Stop-hook turn counter's user-visible cadence.
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(obj, dict):
        return False
    if agent == "claude":
        if obj.get("type") != "user":
            return False
        content = (obj.get("message") or {}).get("content") if isinstance(obj.get("message"), dict) else None
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "tool_result":
                return False
        return True
    if agent == "cursor":
        return obj.get("role") == "user"
    return False


def count_turns(agent: str, lines: Iterable[str]) -> int:
    return sum(1 for line in lines if is_turn_line(agent, line))


def unread_turn_count(session: SessionRef, from_line: int) -> tuple[int, int, list[str]]:
    """Return (turn_count, total_lines, new_lines) for lines after from_line."""
    path = session.transcript_path
    if not path.is_file():
        return 0, 0, []
    try:
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0, 0, []
    if from_line < 0 or from_line > len(all_lines):
        from_line = 0
    new_lines = all_lines[from_line:]
    return count_turns(session.agent, new_lines), len(all_lines), new_lines


def lines_for_turn_batch(
    session: SessionRef, from_line: int, max_turns: int
) -> tuple[list[str], int, int]:
    """Return (batch_lines, end_line, turns_in_batch).

    ``end_line`` is the next ``last_transcript_line`` offset (exclusive end index
    into the transcript file). Includes all JSONL lines from ``from_line`` up to
    and including the line where the ``max_turns``-th user turn occurs.
    """
    if max_turns < 1:
        return [], from_line, 0
    path = session.transcript_path
    if not path.is_file():
        return [], from_line, 0
    try:
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], from_line, 0
    if from_line < 0 or from_line > len(all_lines):
        from_line = 0
    turns = 0
    end = from_line
    for i in range(from_line, len(all_lines)):
        end = i + 1
        if is_turn_line(session.agent, all_lines[i]):
            turns += 1
            if turns >= max_turns:
                break
    return all_lines[from_line:end], end, turns


def state_key(session: SessionRef) -> str:
    """Key in reflection-state.json shared with orcan-context-reflect.

    Claude keeps a bare session_id so the Stop hook and the scanner share
    ``last_transcript_line``. Cursor (no hook) is namespaced to avoid rare
    UUID collisions with Claude.
    """
    if session.agent == "claude":
        return session.session_id
    return f"{session.agent}:{session.session_id}"
