---
description: Host requirements for Orcan — Docker isolation is a product choice, not an accident.
---

# Installation

## Why these requirements

Orcan isolates agent toolchains in Docker so the host stays thin. That choice needs Docker Compose, Make (thin host UI), Git (clone this repo and your projects), and Python 3 (config scripts on the host).

If you do not want Docker, Orcan is not the right tool — see [Why Orcan?](../why-orcan.md).

## Before you start

Orcan runs on a machine with Docker. Most people use Linux or WSL2.

## Requirements

| Tool | Notes |
| --- | --- |
| Docker Engine | With Compose v2 (`docker compose`) |
| Make | GNU Make |
| Git | To clone this repository |
| Python 3 | For host config scripts (`make env`, wizard) |

Optional:

| Tool | Notes |
| --- | --- |
| `gh` | Only for `make docs-publish` / `make release` helpers |
| Tailscale | Optional private access to the browser terminal |

Check versions:

```bash
docker version
docker compose version
make --version
python3 --version
```

## Get the code

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
```

## First configure

Describe workspaces in `orcan.config.json`, then **materialise** files Compose reads:

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
```

`make setup` scaffolds the config if missing and runs **`make env`** (writes `.env` + `.orcan/*`). Re-run `make env` after every later config edit — `make build` / `make terminal*` only consume those files; they do not regenerate them.

Or use the wizard:

```bash
make config-wizard
make env
```

## Build the image

=== "Full (default)"

    ```bash
    make build
    ```

    Tag: `orcan:latest` (also tagged `orcan:full`) — Claude Code + Cursor CLI.

=== "Claude only"

    ```bash
    make build-claude
    IMAGE_LOCAL=orcan:claude make terminal-docker
    ```

    Tag: `orcan:claude` — Claude only.

## Expected result

- `.env` and `.orcan/` exist
- Local image `orcan:latest` (or `orcan:claude`) exists
- `make path-check` prints workspace paths

## Uninstall

See [Workflows — uninstall](../guides/workflows.md#uninstall) or [FAQ](../faq.md#uninstall).

## Common problems

| Problem | What to try |
| --- | --- |
| Docker permission denied | Add your user to the `docker` group, or use rootless Docker |
| `make env` fails on `PROJECT_DIR` | Use an **absolute** path; do not use `/`, `/home`, or `/etc` as the project |
| Slow first build | Normal — the image installs toolchains and CLIs |

Next: [Quickstart](quickstart.md).
