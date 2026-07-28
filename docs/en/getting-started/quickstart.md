---
description: Install the orcan CLI, sync config, build the image, open the browser terminal.
---

# Quickstart

You should already know why Orcan exists ([Why Orcan?](../why-orcan.md)) and what a **workspace** is ([Core Ideas](../ideas/core-ideas.md)). This page only gets you running.

## Before you start

- Docker is running  
- Absolute path to at least one git repo to mount  

## Install the CLI

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

```bash
orcan doctor
```

(`install.sh` adds `~/.local/bin` to your shell rc; in the *current* terminal you may need `export PATH="$HOME/.local/bin:$PATH"` or a new shell.)

## Steps

Config is JSON under `~/.config/orcan/home/`. Docker only sees what **`orcan sync`** writes (`.env` + `.orcan/*`).

```bash
orcan init /absolute/path/to/your/repo   # scaffold + sync
orcan sync                               # refresh after later edits (safe to re-run)
orcan build
orcan up
```

!!! note
    `orcan init` already runs `sync` once. Keep `orcan sync` in the habit: **every** config edit needs it before `orcan build` / `orcan up`. Those commands do **not** regenerate runtime files.

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
| Port 7681 busy | Set `ttyd.host_port` in config, then `orcan sync` |
| Empty launcher | Check workspaces in config, then `orcan sync` |
| Socket errors with Docker-in-Docker | Use `orcan up --with-docker` |

!!! tip
    After you edit `orcan.config.json`, run `orcan sync` before recreating the container. `orcan up` does **not** refresh config. See [Workflows](../guides/workflows.md).

Image variants: [Installation](installation.md) and [FAQ](../faq.md).

## See also

- [Installation](installation.md)  
- [Configuration](configuration.md)  
- [CLI reference](../reference/cli.md)  
- [Mental Model](../ideas/mental-model.md)
