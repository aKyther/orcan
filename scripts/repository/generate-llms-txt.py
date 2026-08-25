#!/usr/bin/env python3
"""Generate docs/llms.txt — curated map of Orcan docs for LLM / agent clients.

Spec: https://llmstxt.org/
Run from repo root or via `make docs` / `make docs-check` (pre-build).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "llms.txt"
SITE = "https://akyther.github.io/orcan/latest"
RAW = "https://raw.githubusercontent.com/aKyther/orcan/main/docs/en"

CONTENT = f"""# Orcan

> Work-context orchestrator for coding agents (Cursor CLI, Claude Code, Codex) in Docker — workspaces, path parity, context pack. Does not choose or route models.

Orcan describes which repositories belong together, mounts them with the same absolute paths on host and in the container, seeds agent-facing starter files, and runs agents inside Docker. Prefer the pages below over crawling the whole site. In a live Orcan workspace, also read the context pack (`AGENTS.md`, `.manifest.json`) — that is stronger than this public index.

## Start here

- [Why Orcan?]({SITE}/why-orcan/): Problem, when to use / not use, non-goals
- [Core Ideas]({SITE}/ideas/core-ideas/): Project, Workspace, Context
- [Mental Model]({SITE}/ideas/mental-model/): How the pieces relate (incl. path parity)
- [Quick Start]({SITE}/getting-started/quickstart/): First successful run
- [Change map]({SITE}/change-map/): What to edit → where in the repo → which doc

## Concepts and architecture

- [Workspaces]({SITE}/concepts/workspaces/): Named project sets and sessions
- [Path parity]({SITE}/concepts/path-parity/): Same absolute paths host ↔ container
- [Architecture]({SITE}/architecture/): Layers and why they look this way
- [Context Assertions]({SITE}/ideas/context-assertions/): Compiled, human-approved context
- [Runtime reconcile]({SITE}/ideas/runtime-reconcile/): How sync affects a running container
- [Agent inbox]({SITE}/ideas/agent-inbox/): Handoff notes for agents

## Reference (after the story)

- [CLI]({SITE}/reference/cli/): `orcan` commands and flags
- [Configuration]({SITE}/reference/configuration/): `orcan.config.json` fields
- [Environment variables]({SITE}/reference/environment/): Host / container env
- [Docker]({SITE}/reference/docker/): Image contents and Compose
- [Security]({SITE}/reference/security/): Capability ladder and mount trade-offs
- [Host and container interface]({SITE}/interface/): What crosses the boundary

## Develop on Orcan

- [AI project context]({SITE}/ai/project-context/): Agent ritual and where-to-change table
- [Change map]({SITE}/change-map/): Same map for humans and agents
- [Terminal UI]({SITE}/guides/terminal-ui/): Navy/cyan palette across ttyd/tmux/zsh
- [Testing]({SITE}/development/testing/): validate, docs-check, host tests
- [AGENTS.md (repo)](https://github.com/aKyther/orcan/blob/main/AGENTS.md): Rules for agents editing this repository

## Markdown sources (EN)

- [Why Orcan (md)]({RAW}/why-orcan.md)
- [Core Ideas (md)]({RAW}/ideas/core-ideas.md)
- [Mental Model (md)]({RAW}/ideas/mental-model.md)
- [Change map (md)]({RAW}/change-map.md)
- [AI project context (md)]({RAW}/ai/project-context.md)
- [CLI (md)]({RAW}/reference/cli.md)

## Optional

- [Polish docs root](https://akyther.github.io/orcan/latest/pl/): Same content in Polish
- [FAQ]({SITE}/faq/)
- [Changelog]({SITE}/changelog/)
- [Deployment]({SITE}/deployment/)
- [GitHub repository](https://github.com/aKyther/orcan)
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = CONTENT.lstrip("\n")
    if not text.endswith("\n"):
        text += "\n"
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
