---
description: Agent orientation for developing the Orcan repository — goals, non-goals, where to change what.
tags:
  - develop
---

# AI project context

Single orientation page for coding agents working **on the Orcan repository**.

Also read root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md) and `.cursor/rules/agents.mdc` (always on in Cursor). Do not invent a second conflicting ritual.

## Product identity

- Official name: **Orcan** (display). Technical ids use lowercase `orcan` (`orcan:latest`, `ORCAN_DATA`, `orcan.config.json`).
- **Orcan** is the only product name in documentation and user-facing text.
- **Cursor** means the Cursor editor / Cursor CLI — not the product name.
- Orcan is a **context orchestrator**, not a model manager.

## Goals

- Workspaces + path-parity mounts
- Context pack (ignores, AGENTS/CLAUDE, Context Assertions)
- Browser terminal: ttyd → launcher → tmux → zsh
- Image variants: full (Claude+Cursor) and Claude-only

## Non-goals

- Model selection UI / provider abstraction
- Auto-routing between `agent` and `claude`
- Publishing images from CI
- Auto-modifying mounted git repos on every container start

## Ritual (host)

```bash
orcan init          # or edit orcan.config.json
orcan sync
orcan build                  # when image inputs change
orcan up        # daily; does NOT run orcan sync
```

After config edits with a running container: `orcan sync && orcan down && orcan up`.

## Where to change what

| Change | Place |
| --- | --- |
| Host UX / targets | `Makefile`, `scripts/repository/` |
| Context Assertions store / Applicability Layer | `scripts/repository/context_assertions.py`, `scripts/repository/compile_context.py` |
| Container runtime | `docker/rootfs/usr/local/bin/` |
| Image packages | `Dockerfile` |
| Terminal UI (ttyd / tmux / zsh / starship / fzf / lazygit) | See [Terminal UI](../guides/terminal-ui.md); rule `.cursor/rules/terminal-ui.mdc` |
| Global agent defaults in image | `docker/rootfs/opt/cursor-defaults/` |
| Rules for developing Orcan | `.cursor/rules/`, `AGENTS.md` |
| User docs | `docs/` + short `README.md` |

## Documentation map

| Topic | Doc |
| --- | --- |
| Change map (where → file → doc) | [change-map.md](../change-map.md) |
| Why Orcan | [why-orcan.md](../why-orcan.md) |
| Core Ideas | [ideas/core-ideas.md](../ideas/core-ideas.md) |
| Mental Model | [ideas/mental-model.md](../ideas/mental-model.md) |
| Context Assertions | [ideas/context-assertions.md](../ideas/context-assertions.md) |
| Architecture | [architecture.md](../architecture.md) |
| Terminal UI | [guides/terminal-ui.md](../guides/terminal-ui.md) |
| Config schema | [reference/configuration.md](../reference/configuration.md) |
| Make targets | [reference/makefile.md](../reference/makefile.md) |
| Security | [reference/security.md](../reference/security.md) |
| Release | [development/release.md](../development/release.md) |
| Tests | [development/testing.md](../development/testing.md) |
| Public agent index | [`docs/llms.txt`](https://akyther.github.io/orcan/latest/llms.txt) (generated; `make docs-llms`) |

## Definition of done

Code change is incomplete without updating the matching docs when behaviour or interface changes. Run `make validate` and `make docs-check` before claiming done.
