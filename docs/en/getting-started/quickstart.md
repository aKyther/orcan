---
description: Clone Orcan, build the image, and open the browser terminal — after you understand the product idea.
---

# Quickstart

You should already know why Orcan exists ([Why Orcan?](../why-orcan.md)) and what a **workspace** is ([Core Ideas](../ideas/core-ideas.md)). This page only gets you running.

## Before you start

- Docker is running  
- Absolute path to at least one git repo to mount  

## Steps (host)

Config is JSON. Docker only sees what **`make env`** writes (`.env` + `.orcan/*`).

```bash
cd /absolute/path/to/orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo   # scaffold config if needed, then make env
make env                                             # refresh .env + .orcan/* for Compose (safe to re-run)
make build
make terminal-docker
```

!!! note
    `make setup` already runs `make env` once. Keep `make env` in the habit: **every** config edit needs it before `make build` / `make terminal*`. Those targets do **not** regenerate runtime files.

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

Image variants: [Installation](installation.md) and [FAQ](../faq.md).

## See also

- [Installation](installation.md)  
- [Configuration](configuration.md)  
- [Mental Model](../ideas/mental-model.md)
