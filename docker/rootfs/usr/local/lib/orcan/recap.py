"""Cascading session recap — compact batches, merge rolling state, flush on drift.

Background worker (via ``orcan-context-recap`` / ``orcan-context-scan``):

  1. Every *N* user turns (default 20) → compact that batch only.
  2. Merge batch compact with the session's *rolling compact* from prior batches.
  3. Repeated themes survive merges; noise drops out over time.
  4. When the new batch topic *drifts* from the rolling compact → flush the
     mature rolling text to ``context-inbox`` (human review) and start a fresh
     cascade seeded with the new batch compact.
  5. ``--flush`` (session end) flushes whatever remains in the rolling compact.

State:

  ``<workspace>/.orcan/reflection-state.json`` — ``last_transcript_line`` (shared
  with the Claude Stop hook / legacy reflect driver).

  ``<workspace>/.orcan/recap/<session-key>.json`` — rolling compact + cascade metadata.

Human accept/reject stays required — recap only matures *candidates* in the inbox.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from orcan.session_scan import SessionRef, lines_for_turn_batch, state_key, unread_turn_count

REFLECTION_STATE_NAME = "reflection-state.json"
RECAP_DIRNAME = "recap"
MAX_TRANSCRIPT_CHARS = 8000
MAX_ROLLING_CHARS = 6000
MAX_CONTEXT_CHARS = 8000
MAX_PROPOSALS_PER_FLUSH = 8
DEFAULT_BRANCH_NAMES = {"main", "master"}

ModelRunner = Callable[[str], str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_session_filename(session_key: str) -> str:
    return session_key.replace(":", "_").replace("/", "_")


def reflection_state_path(workspace_root: Path) -> Path:
    return workspace_root / ".orcan" / REFLECTION_STATE_NAME


def recap_state_path(workspace_root: Path, session_key: str) -> Path:
    return workspace_root / ".orcan" / RECAP_DIRNAME / f"{_safe_session_filename(session_key)}.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_last_transcript_line(workspace_root: Path, session_key: str) -> int:
    state = load_json(reflection_state_path(workspace_root))
    session_state = state.get(session_key)
    if isinstance(session_state, dict):
        return int(session_state.get("last_transcript_line", 0) or 0)
    return 0


def set_last_transcript_line(workspace_root: Path, session_key: str, end_line: int) -> None:
    path = reflection_state_path(workspace_root)
    state = load_json(path)
    session_state = state.setdefault(session_key, {})
    if isinstance(session_state, dict):
        session_state["last_transcript_line"] = end_line
    save_json(path, state)


def record_recap_error(workspace_root: Path, session_key: str, message: str) -> None:
    path = reflection_state_path(workspace_root)
    state = load_json(path)
    session_state = state.setdefault(session_key, {})
    if isinstance(session_state, dict):
        session_state["last_recap_error"] = message
        session_state["last_recap_error_at"] = _now_iso()
    save_json(path, state)


def clear_recap_error(workspace_root: Path, session_key: str) -> None:
    path = reflection_state_path(workspace_root)
    state = load_json(path)
    session_state = state.get(session_key)
    if not isinstance(session_state, dict):
        return
    changed = False
    for key in ("last_recap_error", "last_recap_error_at"):
        if key in session_state:
            session_state.pop(key, None)
            changed = True
    if changed:
        save_json(path, state)


def new_cascade_state(*, rolling_compact: str) -> dict[str, Any]:
    return {
        "cascade_id": uuid.uuid4().hex[:12],
        "generation": 1,
        "rolling_compact": rolling_compact,
        "batch_count": 1,
        "updated_at": _now_iso(),
    }


@dataclass(frozen=True)
class MergeResult:
    drift: bool
    rolling_compact: str
    drift_reason: str = ""


def extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_json_array(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)]


def default_model_runner(prompt: str, *, model: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", model, prompt],
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise RuntimeError(f"model call exited {result.returncode}: {result.stderr.strip()[:200]}")
    return result.stdout


def compact_batch_prompt(transcript_slice: str) -> str:
    return f"""You compact a coding-session transcript batch into durable facts worth remembering.

Input: JSONL transcript lines from ONE batch (~20 user turns). Output ONLY plain text —
a short bullet list (one line per fact). Each bullet is ONE concise sentence a human could
confirm as true for future sessions. Skip tool chatter, one-off debugging, and anything
already obvious from the repo layout. If nothing durable, output exactly: (none)

=== Transcript batch ===
{transcript_slice}
"""


def merge_rolling_prompt(previous: str, batch_compact: str, accepted_context: str) -> str:
    return f"""You merge two session recaps for a coding assistant's background knowledge.

1. ``rolling_compact`` — facts distilled from earlier batches in this cascade.
2. ``batch_compact`` — facts from the newest batch only.

Tasks:
- Merge into one tighter ``rolling_compact``: keep durable facts that appear in either part,
  drop redundancy and noise, strengthen wording when both agree.
- Detect **topic drift**: true when the new batch is mostly about a genuinely different task
  or subsystem than the rolling compact (not just a new sub-step of the same work).

Output ONLY JSON (no markdown fences):
  {{"drift": false, "drift_reason": "", "rolling_compact": "bullet list text"}}

When drift is true, set ``rolling_compact`` to ``batch_compact`` unchanged (a fresh cascade
will start from it). Be conservative — only drift when topics clearly diverge.

=== Already accepted in workspace (for dedup hints only) ===
{accepted_context}

=== Previous rolling compact ===
{previous}

=== New batch compact ===
{batch_compact}
"""


def flush_prompt(rolling_compact: str, accepted_context: str, project: str) -> str:
    return f"""Turn a session recap into Context Assertion candidates for human review.

The recap below was distilled over many batches. Extract at most {MAX_PROPOSALS_PER_FLUSH}
items worth a human confirming for project "{project}". Skip anything already covered below.

Output ONLY a JSON array (no markdown fences). Each element:
  {{"action": "propose", "title": "...", "content": "one concise fact sentence",
    "justification": "why future sessions need this", "kind": "fact",
    "epistemic_status": "fact", "criticality": "normal"}}

If nothing worth surfacing, output exactly: []

=== Already accepted ===
{accepted_context}

=== Rolling recap to promote ===
{rolling_compact}
"""


def compact_batch(transcript_slice: str, *, model: str, runner: ModelRunner | None = None) -> str:
    run = runner or (lambda p: default_model_runner(p, model=model))
    raw = run(compact_batch_prompt(transcript_slice)).strip()
    if raw.lower() in ("(none)", "none", "[]"):
        return ""
    return raw[:MAX_ROLLING_CHARS]


def merge_rolling(
    previous: str,
    batch_compact: str,
    accepted_context: str,
    *,
    model: str,
    runner: ModelRunner | None = None,
) -> MergeResult:
    if not previous.strip():
        return MergeResult(drift=False, rolling_compact=batch_compact)
    if not batch_compact.strip():
        return MergeResult(drift=False, rolling_compact=previous)
    run = runner or (lambda p: default_model_runner(p, model=model))
    obj = extract_json_object(run(merge_rolling_prompt(previous, batch_compact, accepted_context)))
    rolling = str(obj.get("rolling_compact") or "").strip()
    if not rolling:
        rolling = batch_compact if obj.get("drift") else f"{previous.strip()}\n{batch_compact.strip()}"
    return MergeResult(
        drift=bool(obj.get("drift")),
        rolling_compact=rolling[:MAX_ROLLING_CHARS],
        drift_reason=str(obj.get("drift_reason") or "").strip(),
    )


def extract_flush_actions(
    rolling_compact: str,
    accepted_context: str,
    project: str,
    *,
    model: str,
    runner: ModelRunner | None = None,
) -> list[dict[str, Any]]:
    if not rolling_compact.strip():
        return []
    run = runner or (lambda p: default_model_runner(p, model=model))
    return extract_json_array(run(flush_prompt(rolling_compact, accepted_context, project)))


def dispatch_proposal(
    action: dict[str, Any],
    *,
    workspace_root: Path,
    project: str,
    branch: str,
    propose_bin: Path,
) -> None:
    kind = action.get("action")
    if kind != "propose":
        return
    content = str(action.get("content") or "").strip()
    justification = str(action.get("justification") or "").strip()
    if not content or not justification:
        return
    args = [
        sys.executable,
        str(propose_bin),
        "--workspace-root",
        str(workspace_root),
        "--project",
        project,
        "--text",
        content,
        "--justification",
        justification,
        "--title",
        str(action.get("title") or ""),
        "--kind",
        str(action.get("kind") or "fact"),
        "--queue",
        "--source",
        "recap",
    ]
    if branch and branch not in DEFAULT_BRANCH_NAMES:
        args += ["--branch", branch]
    epistemic_status = str(action.get("epistemic_status") or "").strip()
    if epistemic_status:
        args += ["--epistemic-status", epistemic_status]
    criticality = str(action.get("criticality") or "").strip()
    if criticality:
        args += ["--criticality", criticality]
    subprocess.run(args, capture_output=True, text=True, env=dict(os.environ), stdin=subprocess.DEVNULL)


def flush_rolling_to_inbox(
    rolling_compact: str,
    *,
    workspace_root: Path,
    project: str,
    branch: str,
    accepted_context: str,
    model: str,
    propose_bin: Path,
    runner: ModelRunner | None = None,
) -> int:
    actions = extract_flush_actions(rolling_compact, accepted_context, project, model=model, runner=runner)
    queued = 0
    for action in actions[:MAX_PROPOSALS_PER_FLUSH]:
        if action.get("action") == "propose":
            dispatch_proposal(action, workspace_root=workspace_root, project=project, branch=branch, propose_bin=propose_bin)
            queued += 1
    return queued


def read_accepted_context(workspace_root: Path) -> str:
    pack = workspace_root / "CONTEXT-ASSERTIONS.md"
    if not pack.is_file():
        return "(none yet)"
    text = pack.read_text(encoding="utf-8")
    if len(text) > MAX_CONTEXT_CHARS:
        return text[-MAX_CONTEXT_CHARS:]
    return text


def process_one_batch(
    session: SessionRef,
    workspace_root: Path,
    *,
    project: str,
    branch: str,
    threshold: int,
    model: str,
    dry_run: bool,
    flush_remaining: bool,
    propose_bin: Path,
    runner: ModelRunner | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[int, bool]:
    """Process one recap batch. Returns (proposals_queued, did_work)."""
    emit = log or (lambda _msg: None)
    sk = state_key(session)
    from_line = get_last_transcript_line(workspace_root, sk)
    unread, _total, _ = unread_turn_count(session, from_line)
    if unread == 0:
        return 0, False

    max_turns = unread if flush_remaining and unread < threshold else threshold
    batch_lines, end_line, turns = lines_for_turn_batch(session, from_line, max_turns)
    if turns == 0:
        return 0, False
    if not flush_remaining and turns < threshold:
        return 0, False

    transcript_slice = "\n".join(batch_lines)
    if len(transcript_slice) > MAX_TRANSCRIPT_CHARS:
        transcript_slice = transcript_slice[-MAX_TRANSCRIPT_CHARS:]

    emit(
        f"recap batch {session.agent}:{session.session_id[:8]}… "
        f"turns={turns} lines={from_line}→{end_line}"
    )
    if dry_run:
        return 0, True

    accepted = read_accepted_context(workspace_root)
    try:
        batch_compact = compact_batch(transcript_slice, model=model, runner=runner)
    except (OSError, RuntimeError) as exc:
        record_recap_error(workspace_root, sk, f"compact failed: {exc}")
        return 0, True

    if not batch_compact.strip():
        set_last_transcript_line(workspace_root, sk, end_line)
        clear_recap_error(workspace_root, sk)
        emit("recap batch empty — advanced offset only")
        return 0, True

    recap_path = recap_state_path(workspace_root, sk)
    recap = load_json(recap_path)
    queued = 0
    previous = str(recap.get("rolling_compact") or "").strip()

    if not previous:
        recap = new_cascade_state(rolling_compact=batch_compact)
        emit(f"recap cascade started ({recap['cascade_id']})")
    else:
        merged = merge_rolling(previous, batch_compact, accepted, model=model, runner=runner)
        if merged.drift:
            emit(f"recap drift — flushing cascade {recap.get('cascade_id', '?')}: {merged.drift_reason or '(no reason)'}")
            queued += flush_rolling_to_inbox(
                previous,
                workspace_root=workspace_root,
                project=project,
                branch=branch,
                accepted_context=accepted,
                model=model,
                propose_bin=propose_bin,
                runner=runner,
            )
            old_gen = int(recap.get("generation", 1))
            recap = new_cascade_state(rolling_compact=merged.rolling_compact)
            recap["generation"] = old_gen + 1
        else:
            recap["rolling_compact"] = merged.rolling_compact
            recap["batch_count"] = int(recap.get("batch_count", 0)) + 1
            recap["updated_at"] = _now_iso()
            emit(f"recap merged batch #{recap['batch_count']} (cascade {recap.get('cascade_id', '?')})")

    save_json(recap_path, recap)
    set_last_transcript_line(workspace_root, sk, end_line)

    if flush_remaining:
        remaining, _, _ = unread_turn_count(session, end_line)
        if remaining == 0:
            rolling = str(recap.get("rolling_compact") or "").strip()
            if rolling:
                emit("recap flush — promoting rolling compact to inbox")
                queued += flush_rolling_to_inbox(
                    rolling,
                    workspace_root=workspace_root,
                    project=project,
                    branch=branch,
                    accepted_context=accepted,
                    model=model,
                    propose_bin=propose_bin,
                    runner=runner,
                )
                save_json(recap_path, new_cascade_state(rolling_compact=""))

    clear_recap_error(workspace_root, sk)
    return queued, True
