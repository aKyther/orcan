"""Agent-specific context follows the baked image manifest, not a model choice."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

NAMES = {
    "cursor": "agent",
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
    "copilot": "copilot",
}


def parse_agents(text: str) -> set[str]:
    try:
        agents = json.loads(text)["agents"]
        if not isinstance(agents, dict):
            return set()
        return {
            name
            for name in NAMES
            if agents.get(name) is True
            or type(agents.get(name)) is int
            and agents[name] == 1
        }
    except (ValueError, TypeError, KeyError):
        return set()


def enabled_agents() -> set[str]:
    path = Path(os.environ.get("ORCAN_AGENTS_FILE", "/etc/orcan/agents.json"))
    if path.is_file():
        return parse_agents(path.read_text())
    # Old images did not have a manifest. Never enable clients absent from PATH.
    return {name for name, binary in NAMES.items() if shutil.which(binary)}


def sync_files(
    root: Path, sources: dict[str, tuple[str, Path]], agents: set[str]
) -> None:
    """Prune only unchanged Orcan-owned defaults; never delete custom files."""
    record = root / ".orcan/agent-context.json"
    if record.is_symlink():
        return
    try:
        previous = json.loads(record.read_text())
        previous = previous if isinstance(previous, dict) else {}
    except (OSError, ValueError):
        previous = {}
    previous = {key: value for key, value in previous.items() if isinstance(value, str)}
    managed = {}
    for relative, (owner, source) in sources.items():
        target = root / relative
        if target.is_symlink() or not source.is_file():
            continue
        default = source.read_bytes()
        digest = hashlib.sha256(default).hexdigest()
        if owner in agents:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(default)
                managed[relative] = digest
            elif target.is_file() and hashlib.sha256(
                target.read_bytes()
            ).hexdigest() in {digest, previous.get(relative)}:
                managed[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        elif target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() in {
            digest,
            previous.get(relative),
        }:
            target.unlink()
            parent = target.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    body = json.dumps(managed, sort_keys=True, indent=2) + "\n"
    if managed or record.exists():
        record.parent.mkdir(exist_ok=True)
        if not record.exists() or record.read_text() != body:
            record.write_text(body)
