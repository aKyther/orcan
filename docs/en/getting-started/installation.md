---
description: Host requirements for Orcan — Docker isolation is a product choice, not an accident.
---

# Installation

## Why these requirements

Orcan isolates agent toolchains in Docker so the host stays thin. That choice needs Docker Compose, Git (clone this repo and your projects), Python 3 (config scripts on the host), and Bash (the `orcan` CLI).

If you do not want Docker, Orcan is not the right tool — see [Why Orcan?](../why-orcan.md).

## Before you start

Orcan runs on a machine with Docker. Most people use Linux or WSL2.

## Requirements

| Tool | Notes |
| --- | --- |
| Docker Engine | With Compose v2 (`docker compose`) |
| Git | To clone installs and your projects |
| Python 3 | Host config scripts — `orcan sync`, `init`, `context` (wizard). Stdlib only; no pip. |
| Bash | CLI launcher |

Optional:

| Tool | Notes |
| --- | --- |
| `gh` | Only for `make docs-publish` / `make release` helpers |
| Tailscale | Optional private access to the browser terminal |

Check versions:

```bash
docker version
docker compose version
python3 --version
bash --version
```

## Install the CLI

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
orcan doctor
```

From a git checkout of this repository you can also run `./bin/orcan` without installing.

## First configure

Describe workspaces in `~/.config/orcan/home/orcan.config.json`, then **materialise** files Compose reads:

```bash
orcan init /absolute/path/to/your/repo
```

`orcan init` scaffolds the config if missing and runs **`orcan sync`** (writes `.env` + `.orcan/*` under `ORCAN_HOME`). Re-run `orcan sync` after every later config edit — `orcan build` / `orcan up` only consume those files; they do not regenerate them.

Or use the wizard:

```bash
orcan context wizard
orcan sync
```

## Build the image

=== "Both agents (default)"

    ```bash
    orcan build
    ```

    Tags: `orcan:latest` and `orcan:<VERSION>`.

=== "Claude Code only (no pull)"

    ```bash
    orcan build --claude
    IMAGE_LOCAL=orcan:0.1.1-claude orcan up
    ```

    Tag: `orcan:<VERSION>-claude` (does not overwrite `latest`).

=== "Cursor CLI only (no pull)"

    ```bash
    orcan build --cursor
    IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
    ```

    Tag: `orcan:<VERSION>-cursor`.

## Expected result

- Config and `.env` exist under `~/.config/orcan/home/`
- Local image `orcan:latest` exists
- `orcan context show` prints workspace paths

## Uninstall

```bash
orcan uninstall              # remove launcher + install clone
orcan uninstall --purge-data # also delete ORCAN_DATA after confirmation
```

See [Workflows — uninstall](../guides/workflows.md#uninstall) or [FAQ](../faq.md#uninstall).

## Common problems

| Problem | What to try |
| --- | --- |
| Docker permission denied | Add your user to the `docker` group, or use rootless Docker |
| `orcan sync` fails on `PROJECT_DIR` | Use an **absolute** path; do not use `/`, `/home`, or `/etc` as the project |
| Slow first build | Normal — the image installs toolchains and CLIs |
| `orcan: command not found` | Add `~/.local/bin` to `PATH`, or re-run `install.sh` |

Next: [Quickstart](quickstart.md) · [CLI reference](../reference/cli.md).
