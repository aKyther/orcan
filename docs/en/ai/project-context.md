---
description: Agent orientation for developing the Orcan repository — goals, non-goals, where to change what.
tags:
  - develop
---

# AI project context

Single **docs** orientation page for coding agents working **on the Orcan repository**.

**In-repo SoT:** root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md) / [`CLAUDE.md`](https://github.com/aKyther/orcan/blob/main/CLAUDE.md) (keep identical) and `.cursor/rules/agents.mdc` (always on). Do not invent a second conflicting ritual. Public care/non-goals index: [`docs/llms.txt`](https://akyther.github.io/orcan/latest/llms.txt) (`make docs-llms`).

When you are inside an orcan workspace (e.g. `orcan-dev`), read the workspace context pack first, then `cd` into the `orcan` project and follow **that** repo’s `AGENTS.md`.

## Product identity

- Official name: **Orcan** (display). Technical ids: `orcan`, `ORCAN_*`.
- **Cursor** means the Cursor editor / CLI — not the product name.
- Orcan is a **context orchestrator**, not a model manager.

| Piece | Meaning |
| --- | --- |
| Workspace | Named set of projects = one daily job |
| Path parity | Same absolute paths host ↔ container |
| Context pack | Ignores, AGENTS/CLAUDE, Context Assertions |
| Access | Local `orcan enter` by default; optional `orcan up --with-ttyd` |
| Cockpit | Top bar + workspaces/ASSERTIONS + embedded tmux; see [Terminal UI](../guides/terminal-ui.md) |

## Goals

- Workspaces + path-parity mounts
- Context pack (ignores, AGENTS/CLAUDE, Context Assertions)
- Local enter by default; optional browser: ttyd → cockpit (`agent-launcher`) → tmux → zsh
- Image variants: full and single-agent (`--claude` / `--cursor` / `--codex`)
- Background Reflection via supervisord `context-scan` (default **recap**; legacy `ORCAN_CONTEXT_DRIVER=reflect`)

## Non-goals

- Model selection UI / provider abstraction / auto-routing between CLIs
- Publishing images from CI; treating Orcan as a registry product
- YAML user config / host-deps
- Auto-modifying mounted git repos on every container start
- Confusing `make dev-*` with the public `orcan` CLI
- Cockpit F3/Git shortcut — use shell **`lg`** (lazygit) inside the terminal
- “Fixing” browser **Alt+arrows** by restoring Ctrl=split in cockpit — many terminals deliver Alt as Ctrl; cockpit nav mix is intentional (`pty_tmux_nav.py` / `BROWSER_KEY_LIMIT`); see [Terminal UI — nav mix](../guides/terminal-ui.md#cockpit-nav-mix)

## Ritual (host)

```bash
orcan init          # or edit orcan.config.json
orcan sync          # ALWAYS after config (up does not sync)
orcan build         # when image inputs change
orcan up            # daily; --with-ttyd for browser
```

Prefer live reconcile via `orcan sync` when possible; recreate when overlays require it (`orcan down && orcan up`). Details: [Runtime reconcile](../ideas/runtime-reconcile.md).

## Where to change what

| Change | Place |
| --- | --- |
| Host UX / targets | `Makefile`, `scripts/repository/` |
| Isolated UX / tmux preview | `make dev-*` / `scripts/dev/` — [Testing](../development/testing.md) |
| Cockpit TUI | `cockpit/src/orcan_cockpit/` (shortcuts: `shortcuts.py`; About: `about_modal.py`; ASSERTIONS: `activity.py`; glance: `session_glance.py`; chrome: `top_bar.py`; PTY: `pty_keys.py`, `pty_tmux_nav.py`, `pty_colors.py`) |
| Session recap | `docker/rootfs/usr/local/lib/orcan/recap.py`, `orcan-context-recap` |
| Recap model probe | `docker/rootfs/usr/local/lib/orcan/context_model_check.py`, `orcan-context-model-check` |
| Context Assertions store / compile | `scripts/repository/context_assertions.py`, `compile_context.py` |
| Host context sync daemon | `scripts/repository/context_syncd.py` (`orcan sync --context`) |
| Automation control | `docker/rootfs/usr/local/lib/orcan/automation.py` + `$ORCAN_DATA/history/supervisor/automation.json` (cockpit **`[p]`** / **`[o]`**) |
| Supervisord / context-scan | `orcan-supervisord`, `orcan-context-scan` under `docker/rootfs/usr/local/bin/` |
| Container runtime | `docker/rootfs/usr/local/bin/` |
| Image packages | `Dockerfile` |
| Terminal UI | [Terminal UI](../guides/terminal-ui.md); rule `.cursor/rules/terminal-ui.mdc` |
| Global agent defaults in image | `docker/rootfs/opt/cursor-defaults/` |
| Rules for developing Orcan | `.cursor/rules/`, `AGENTS.md` / `CLAUDE.md` |
| Public agent index | `scripts/repository/generate-llms-txt.py` → `docs/llms.txt` |
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
| Make / `dev-*` | [reference/makefile.md](../reference/makefile.md) |
| Security | [reference/security.md](../reference/security.md) |
| Release | [development/release.md](../development/release.md) |
| Tests | [development/testing.md](../development/testing.md) |
| Public agent index | [`docs/llms.txt`](https://akyther.github.io/orcan/latest/llms.txt) |

## Definition of done

Incomplete without matching docs when behaviour or interface changes (EN + PL). Prefer `make dev-restart` for cockpit/ttyd UX checks; use `make dev-smoke` / `dev-a11y` / `dev-visual` (see `make dev-checklist`) when layout or browser chrome changed. Before claiming done: `make validate`, `make test-host`, and `make docs-check` when docs/public surface changed.
