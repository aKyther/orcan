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
| Python 3 | Host config scripts — `orcan sync`, `init` (incl. wizard), `context`. Stdlib only; no pip. |
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
```

`install.sh` puts the launcher in `~/.local/bin` and appends that directory to your shell rc (idempotent; skip with `ORCAN_SKIP_PATH=1`). A `curl | bash` install **cannot** change the parent shell’s `PATH`, so before `orcan doctor`:

1. Confirm `~/.local/bin` is on `PATH` (`echo "$PATH"` or `command -v orcan`).
2. If the installer added the rc line but this session still lacks it, reload the shell — e.g. `exec bash -l`, `exec zsh -l`, or open a new terminal. One-shot: `export PATH="$HOME/.local/bin:$PATH"`.
3. If rc was not updated, add the export yourself, reload, then continue.

```bash
orcan doctor
```

From a git checkout of this repository you can also run `./bin/orcan` without installing.

## First configure

Describe workspaces in `~/.config/orcan/orcan.config.json`, then **materialise** files Compose reads:

```bash
orcan init /absolute/path/to/your/repo
```

`orcan init` scaffolds the config if missing and runs **`orcan sync`** (writes `.env` + `mounts/*` under `ORCAN_HOME`). Re-run `orcan sync` after every later config edit — `orcan build` / `orcan up` only consume those files; they do not regenerate them.

Or use the wizard:

```bash
orcan init
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

- Config and `.env` exist under `~/.config/orcan/`
- Local image `orcan:latest` exists
- `orcan context show` prints workspace paths

Git author identity is filled by `orcan sync`. To attach host SSH keys for push/pull, use `orcan up --with-git` (see [Quickstart](quickstart.md#git-inside-the-container)).

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
| `orcan: command not found` | Ensure `~/.local/bin` is on `PATH`, then reload the shell (`exec bash -l` / new terminal) or `export PATH="$HOME/.local/bin:$PATH"`; re-run `install.sh` if the rc line is missing |

Next: [Quickstart](quickstart.md) · [CLI reference](../reference/cli.md).
