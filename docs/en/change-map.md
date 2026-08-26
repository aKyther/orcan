---
description: Where to change what in Orcan — repo paths and matching docs for humans and agents.
tags:
  - guide
  - develop
---

# Change map

Short index for **finding the right place to edit** — and the doc that explains it. For agent orientation on this repository, also see [AI project context](ai/project-context.md) and root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md).

## Product change → place → doc

| You want to change… | Edit here | Read |
| --- | --- | --- |
| Host UX / Make targets | `Makefile`, `scripts/repository/` | [Makefile](reference/makefile.md) |
| Cockpit TUI (`agent-launcher`) | `cockpit/src/orcan_cockpit/` (`shortcuts.py`, `activity.py`, `top_bar.py`) | [Workflows — local terminal](guides/workflows.md#local-terminal), [Terminal UI](guides/terminal-ui.md) |
| Session recap / scan driver | `docker/rootfs/usr/local/lib/orcan/recap.py`, `orcan-context-recap`, `orcan-context-scan` | [Context Assertions](ideas/context-assertions.md), [Environment](reference/environment.md) |
| Recap model probe | `docker/rootfs/usr/local/lib/orcan/context_model_check.py`, `orcan-context-model-check` | [Context Assertions](ideas/context-assertions.md), [Environment](reference/environment.md) |
| Supervisord / Reflection scan | `docker/rootfs/etc/orcan/supervisor.d/`, `orcan-supervisord`, `orcan-context-scan`, `session_scan.py` | [Docker](reference/docker.md#process-layout-supervisord), [Context Assertions](ideas/context-assertions.md) |
| Host context sync / automation control | `scripts/repository/context_syncd.py`, `docker/rootfs/usr/local/lib/orcan/automation.py` | [Context Assertions](ideas/context-assertions.md), [CLI](reference/cli.md) |
| Isolated UX / tmux preview (checkout) | `make dev-*`, `scripts/dev/` | [Testing](development/testing.md), [Makefile](reference/makefile.md) |
| Config schema / wizard | `scripts/repository/config-*.py`, `apply-config.py` | [Config reference](reference/configuration.md), [Config guide](getting-started/configuration.md) |
| Context Assertions / compile | `scripts/repository/context_assertions.py`, `compile_context.py` | [Context Assertions](ideas/context-assertions.md) |
| Managed workspaces / worktrees | `scripts/repository/managed_workspace.py`, `git_worktrees.py` | [Workspaces](concepts/workspaces.md), [Runtime reconcile](ideas/runtime-reconcile.md) |
| Container runtime binaries | `docker/rootfs/usr/local/bin/` | [Docker](reference/docker.md), [Interface](interface.md) |
| Image packages / agents | `Dockerfile` | [Docker](reference/docker.md), [Deployment](deployment.md) |
| Terminal look (ttyd / tmux / zsh / …) | `docker/rootfs/` (see Terminal UI map) | [Terminal UI](guides/terminal-ui.md) |
| Global agent defaults in image | `docker/rootfs/opt/cursor-defaults/` | [Cursor and Claude](reference/cursor-and-claude.md) |
| Rules while developing Orcan | `.cursor/rules/`, `AGENTS.md` / `CLAUDE.md` | [AI project context](ai/project-context.md) |
| User-facing docs / site theme | `docs/`, `mkdocs.yml`, `overrides/` | [STYLE_GUIDE](https://github.com/aKyther/orcan/blob/main/docs/STYLE_GUIDE.md), this site |
| Docs palette / favicon | `docs/assets/stylesheets/orcan.css`, `docs/assets/images/favicon.svg` | [Terminal UI](guides/terminal-ui.md) (product colours) |
| Public agent docs index | `docs/llms.txt` (generated; 30s map + care / non-goals) | [llms.txt](https://akyther.github.io/orcan/latest/llms.txt) |

## Idea pages (read before Make)

| Topic | Doc |
| --- | --- |
| Why Orcan | [Why Orcan?](why-orcan.md) |
| Project / Workspace / Context | [Core Ideas](ideas/core-ideas.md) |
| How pieces relate | [Mental Model](ideas/mental-model.md) |
| Path parity | [Path parity](concepts/path-parity.md) |
| Architecture | [Architecture](architecture.md) |
| Security trade-offs | [Security](reference/security.md) |

## Ritual (host)

```bash
orcan init          # or edit orcan.config.json
orcan sync
orcan build         # when image inputs change
orcan up            # daily; does NOT run orcan sync
```

After config edits with a running container: prefer `orcan sync` (live reconcile when
projects sit under the stable mounts). Recreate only when overlays/flags require it:
`orcan down && orcan up`.

!!! tip
    Prefer this page for “where do I click?”, [AI project context](ai/project-context.md) for agent ritual, and [CLI reference](reference/cli.md) for flags.

## See also

- [Tags](tags.md) — browse pages by topic label  
- [Troubleshooting](guides/troubleshooting.md)  
- [Testing](development/testing.md)
