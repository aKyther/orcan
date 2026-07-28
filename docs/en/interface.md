---
description: orcan CLI on the host, container CLIs, and orcan.config.json — Orcan has no REST API.
---

# Host and container interface

This is the **contract** surface after you know the mental model: `orcan` on the host, CLIs in the container, JSON config. Orcan has **no HTTP / REST API**.

The supported public interfaces are:

1. **`orcan` CLI** — configure, build, run, diagnose (see [CLI reference](reference/cli.md))
2. **Container CLIs** — `agent`, `claude`, and `orcan-*` helpers
3. **Config file** — `orcan.config.json` (validated by host scripts; see JSON Schema below)

## Host (`orcan`)

High-signal commands:

```bash
orcan init | sync | context wizard | context show
orcan build [--claude|--cursor] [--force]
orcan up | up --with-docker | down
orcan logs | doctor | url
```

User ritual: `orcan init` → `orcan build` → `orcan up`. After config edits: `orcan sync && orcan down && orcan up`.

## Maintainer Make

The git checkout also ships a **Makefile** for docs, tests, and release — not for day-to-day use. See [Makefile reference](reference/makefile.md) and [Development overview](development/overview.md).

## Container helpers

| Command | Role |
| --- | --- |
| `agent` / `ag` | Cursor CLI (full image) |
| `claude` / `cc` | Claude Code |
| `orcan-workspaces` | List workspaces |
| `orcan-context-status` | Context pack status |
| `orcan-init-projects` | Optional: seed project templates (advanced) |
| `orcan-session-brief` | Optional session handoff file |
| `orcan-ai-statusline` | Optional AI usage in tmux status |

## Config surface

See [Configuration reference](reference/configuration.md) and [Environment variables](reference/environment.md).

Machine-readable schema: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json) (next to `orcan.config.example.json`).

## See also

- [Architecture](architecture.md)
- [User guide — workflows](guides/workflows.md)
- [Source on GitHub](https://github.com/aKyther/orcan)
