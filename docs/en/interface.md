---
description: Host Makefile, container CLIs, and orcan.config.json — Orcan has no REST API.
---

# Host and container interface

Orcan has **no HTTP / REST API**.

The supported public interfaces are:

1. **Host Makefile** — configure, build, run, test, docs, release
2. **Container CLIs** — `agent`, `claude`, and `orcan-*` helpers
3. **Config file** — `orcan.config.json` (validated by host scripts; see JSON Schema below)

## Host (Make)

Canonical list: [Makefile reference](reference/makefile.md).

High-signal targets:

```bash
make setup | config-wizard | env
make build | build-claude
make terminal | terminal-docker
make validate | docs-check | test
make release
```

## Container helpers

| Command | Role |
| --- | --- |
| `agent` / `ag` | Cursor CLI (full image) |
| `claude` / `cc` | Claude Code |
| `orcan-workspaces` | List workspaces |
| `orcan-context-status` | Context pack status |
| `orcan-init-projects` | Seed project templates |
| `orcan-session-brief` | Optional session handoff file |
| `orcan-ai-statusline` | Optional AI usage in tmux status |

## Config surface

See [Configuration reference](reference/configuration.md) and [Environment variables](reference/environment.md).

Machine-readable schema: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json) (next to `orcan.config.example.json`).

## See also

- [Architecture](concepts/architecture.md)
- [User guide — workflows](guides/workflows.md)
- [Source on GitHub](https://github.com/aKyther/orcan)
