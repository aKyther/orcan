---
description: Clone Orcan, build the image, and open the browser terminal in a few commands.
---

# Quickstart

## Before you start

- Docker is running
- Absolute path to at least one git repo to mount

## Steps (host)

```bash
cd /absolute/path/to/orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Open the URL printed in the terminal (default `http://localhost:7681`).

## In the browser

1. Pick a **workspace** from the launcher (or press Enter for the default).
2. You land in **tmux** with **zsh**.
3. Check tools:

```bash
agent --version
claude --version
pwd
```

## Expected result

- Browser shows a dark terminal
- Launcher lists your workspaces
- `agent` and/or `claude` respond to `--version`

## Common problems

| Problem | Fix |
| --- | --- |
| Port 7681 busy | Set `ttyd.host_port` in config, then `make env` |
| Empty launcher | Check `orcan.config.json` workspaces, then `make env` |
| Socket errors with Docker-in-Docker | Use `make terminal-docker` (not `make terminal`) |

!!! tip
    After you edit `orcan.config.json`, run `make env` before recreating the container. `make terminal*` does **not** refresh config. See [Workflows](../guides/workflows.md).

Image variants (`orcan:latest` vs `orcan:claude`): [Installation](installation.md) and [FAQ](../faq.md).

## See also

- [Installation](installation.md)
- [Configuration](configuration.md)
- [Workflows](../guides/workflows.md)
