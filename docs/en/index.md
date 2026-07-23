---
description: Context orchestrator for Cursor CLI and Claude Code in Docker — workspaces, path parity, browser terminal.
---

# Orcan

**Orcan** is a context orchestrator for coding agents. It runs **Cursor CLI** (`agent`) and **Claude Code** (`claude`) inside Docker, with path-parity mounts, workspaces, and a browser terminal (ttyd → tmux → zsh).

Orcan does **not** choose models. Each CLI uses its own account and model settings.

## Why use it

- Keep heavy toolchains off the host
- One config for several repos (workspaces)
- Same absolute paths on host and in the container ([path parity](concepts/path-parity.md))
- Shared agent context (ignores, `AGENTS.md` / `CLAUDE.md`) without rewriting every git checkout on every start

## Minimal example

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Open `http://localhost:7681`, pick a workspace, then run `agent` or `claude`.

## Next steps

| Goal | Page |
| --- | --- |
| Install and first run | [Quickstart](getting-started/quickstart.md) |
| Requirements | [Installation](getting-started/installation.md) |
| Edit workspaces | [Configuration](getting-started/configuration.md) |
| Daily workflows | [Common workflows](guides/workflows.md) |
| When something breaks | [Troubleshooting](guides/troubleshooting.md) |
| Make targets | [Makefile reference](reference/makefile.md) |
| How Orcan thinks about context | [Architecture](concepts/architecture.md) |
| Develop this repo | [Development](development/overview.md) |
| AI / Cursor agents working on Orcan | [AI project context](ai/project-context.md) |

## Status

Version **0.1.1** (see [Changelog](changelog.md)). Distributed as **git clone + Makefile**. Images are built locally (`make build`). CI does not publish container images.

## See also

- [FAQ](faq.md)
- [Deployment](deployment.md)
- [Host and container interface](interface.md)
- [GitHub repository](https://github.com/aKyther/orcan)
