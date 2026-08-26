#!/usr/bin/env python3
"""Generate docs/llms.txt — curated map of Orcan docs for LLM / agent clients.

Spec: https://llmstxt.org/
Run from repo root or via `make docs` / `make docs-check` (pre-build).

This file is the public orientation layer for agents that land on the docs
site without a live workspace context pack. Keep it short, opinionated, and
honest about what matters vs what to ignore.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "llms.txt"
SITE = "https://akyther.github.io/orcan/latest"
RAW = "https://raw.githubusercontent.com/aKyther/orcan/main/docs/en"
REPO = "https://github.com/aKyther/orcan/blob/main"

CONTENT = f"""# Orcan

> Work-context orchestrator for coding agents (Cursor CLI, Claude Code, Codex) in Docker — workspaces, path parity, context pack. Does **not** choose, route, or pin models.

Prefer this file over crawling the whole docs site. In a **live** Orcan workspace, the context pack (`AGENTS.md` / `CLAUDE.md`, `.manifest.json`, `.orcan/session-brief.md` if present, `CONTEXT-ASSERTIONS.md`) is stronger than this public index — read that first.

## Source priority (highest first)

1. Live workspace context pack + session brief
2. Repo [`AGENTS.md`]({REPO}/AGENTS.md) / [`CLAUDE.md`]({REPO}/CLAUDE.md) (keep identical) + [AI project context]({SITE}/ai/project-context/) when editing Orcan itself
3. This `llms.txt`
4. Linked pages below
5. Do **not** invent Make targets, CLI flags, or product features from memory

## Editing this repository (30 seconds)

| | |
| --- | --- |
| **What** | Context orchestrator — workspaces, path parity, context pack; **not** model routing |
| **API** | `orcan` CLI; Make is maintainer / `make dev-*` preview only |
| **Ritual** | `orcan init` → `orcan sync` → `orcan build` (if needed) → `orcan up` (does **not** sync) |
| **UX preview** | `make dev-restart` / `dev-doctor` / `dev-smoke` / `dev-visual` under isolated `orcan:dev-ux` |
| **Where** | CLI `bin/orcan`+`cli/`; cockpit `cockpit/`; image `docker/rootfs/`; helpers `scripts/repository/`; previews `scripts/dev/` |
| **Done** | Surgical diff; EN+PL docs; `make validate` · `test-host` · `docs-check` |

## Pay attention to (core product)

- **Workspaces** = named sets of projects that form one daily job
- **Path parity** = same absolute paths on host and in the container (required for Docker-from-Docker)
- **Context pack** = ignores, AGENTS/CLAUDE seeds, Context Assertions — what agents should read
- **Config is JSON only** — `orcan.config.json` under **`ORCAN_HOME`**; tool data / history under **`ORCAN_DATA`** (both default `~/.config/orcan`; no YAML user profiles, no host PyYAML stack)
- **Ritual** — `orcan init` → `orcan sync` → `orcan build` (when image inputs change) → `orcan up` (daily; does **not** run sync)
- **Default access** — local `orcan enter`; browser is optional (`orcan up --with-ttyd`)
- **Runtime stack** — cockpit (`agent-launcher`: top bar — click **◆ orcan** = About; workspaces + session glance + ASSERTIONS \| tmux; **F1**/? shortcuts only; **F2** / **F4** / **`i`** / **`r`** / **`p`** / **`o`**; lazygit via **`lg`**, not F3) → tmux 3.6a → zsh; container CMD `orcan-supervisord` (keepalive|ttyd + `context-scan`/`recap`); host `orcan sync --context` for inbox-only compile
- **Known key limit** — under ttyd/xterm.js and some desktop terminals, **Alt+←/→/↑/↓** often arrives as Ctrl+arrow. Cockpit: Ctrl/Alt+arrows = focus pane, Ctrl+Shift+arrows = split (`pty_tmux_nav.py`, `BROWSER_KEY_LIMIT` in F1); raw `--tmux` keeps conf — see [Terminal UI — nav mix]({SITE}/guides/terminal-ui/#cockpit-nav-mix)
- **Version SoT** — `cockpit/pyproject.toml` `version`; root `VERSION` is a CLI/image mirror
- **Docs** — EN + PL must stay in sync; B1–B2; story before commands; [STYLE_GUIDE]({REPO}/docs/STYLE_GUIDE.md)

## Do not invent / out of scope (non-goals)

- Model selection UI, provider abstraction, or auto-routing between `agent` / `claude` / `codex`
- Treating Orcan as an image registry product — users `install.sh` + `orcan build`; publish is **manual** (`orcan publish`); CI does **not** publish images
- YAML user config / reintroducing `host-deps` or `requirements-host.txt`
- Documenting deprecated user Make targets (`setup`, `env`, `terminal-docker`, …) — end users use the **`orcan` CLI**
- Confusing **`scripts/dev/`** / `make dev-*` with the public CLI — that is checkout-only developer UX testing
- Confusing **repo** rules (`.cursor/rules/`, this repo’s `AGENTS.md` / `CLAUDE.md`) with **image** defaults (`docker/rootfs/opt/cursor-defaults/`)
- Auto-modifying mounted git repos on every container start
- Drive-by refactors, speculative abstractions, or docs that invent commands

## Care about when changing the Orcan repo

- Surgical diffs; match existing style; update EN **and** PL docs when behaviour changes
- After UX/cockpit/ttyd edits: `make dev-restart` (isolated; loads checkout cockpit) — not the user’s daily `orcan:latest`; verify with `make dev-doctor` / `dev-smoke` / `dev-a11y` / `dev-visual` (see `make dev-checklist`)
- Context inbox / automation: `orcan sync --context` (host); cockpit **`[p]`** pause / **`[o]`** off → `automation.json`; scan skips recap when cached `model_check` fails (`orcan-context-model-check`)
- Fast tmux-only chrome: `./scripts/dev/terminal-ui-preview`
- Optional Docker isolation smoke: `make dev-test` (skips cleanly if image/daemon missing)
- Before claiming done: `make validate`, `make test-host`, `make docs-check` (and `make test` when Docker behaviour changes)
- Regenerate this file with `make docs-llms` (also runs before `docs` / `docs-check`)
- No `Co-Authored-By` (or similar AI attribution) on commits

## Start here (product story)

- [Why Orcan?]({SITE}/why-orcan/): Problem, when to use / not use, design non-goals
- [Core Ideas]({SITE}/ideas/core-ideas/): Project, Workspace, Context
- [Mental Model]({SITE}/ideas/mental-model/): How the pieces relate (incl. path parity)
- [Quick Start]({SITE}/getting-started/quickstart/): First successful run
- [Change map]({SITE}/change-map/): What to edit → where in the repo → which doc

## Concepts (read before deep reference)

- [Workspaces]({SITE}/concepts/workspaces/): Named project sets and sessions
- [Path parity]({SITE}/concepts/path-parity/): Same absolute paths host ↔ container
- [Architecture]({SITE}/architecture/): Layers and why they look this way
- [Context Assertions]({SITE}/ideas/context-assertions/): Compiled, human-approved context
- [Runtime reconcile]({SITE}/ideas/runtime-reconcile/): How sync affects a running container
- [Agent inbox]({SITE}/ideas/agent-inbox/): Structured handoff notes (not chat dumps)

## Reference (after the story)

- [CLI]({SITE}/reference/cli/): Public `orcan` commands and flags
- [Configuration]({SITE}/reference/configuration/): `orcan.config.json` fields
- [Environment variables]({SITE}/reference/environment/): Host / container env
- [Docker]({SITE}/reference/docker/): Image contents and Compose
- [Makefile]({SITE}/reference/makefile/): Maintainer targets + `make dev-*`
- [Security]({SITE}/reference/security/): Capability ladder and mount trade-offs
- [Host and container interface]({SITE}/interface/): What crosses the boundary

## Develop on Orcan

- [AI project context]({SITE}/ai/project-context/): Goals, non-goals, where-to-change table
- [Terminal UI]({SITE}/guides/terminal-ui/): Navy/cyan palette; iteration via `make dev-*`
- [Testing]({SITE}/development/testing/): validate, host tests, `make dev-*` / `dev-test` / `dev-smoke` / `dev-a11y` / `dev-visual` / `dev-checklist`
- [Development overview]({SITE}/development/overview/): Repo map and separation rules
- [AGENTS.md / CLAUDE.md (repo)]({REPO}/AGENTS.md): Rules for agents editing this repository (keep both files identical)

## Markdown sources (EN)

- [Why Orcan (md)]({RAW}/why-orcan.md)
- [Core Ideas (md)]({RAW}/ideas/core-ideas.md)
- [Mental Model (md)]({RAW}/ideas/mental-model.md)
- [Change map (md)]({RAW}/change-map.md)
- [AI project context (md)]({RAW}/ai/project-context.md)
- [Testing (md)]({RAW}/development/testing.md)
- [CLI (md)]({RAW}/reference/cli.md)

## Optional

- [Polish docs root]({SITE}/pl/): Same content in Polish
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
