# Cursor

This repository prepares Cursor CLI with **global defaults inside the container** and optional **project scaffolding** for `/workspace`.

## Configuration layers

```text
Image defaults
    ↓
/opt/cursor-defaults

Persistent container user settings
    ↓
/home/developer/.cursor   (named volume: cursor-config)

Project-specific settings
    ↓
/workspace/.cursor
/workspace/AGENTS.md

Technical isolation
    ↓
Docker mounts
Linux permissions
Optional Docker socket
Cursor CLI permissions
```

| Layer | Path | Lifetime |
| --- | --- | --- |
| Image defaults | `/opt/cursor-defaults` | Immutable in the image |
| User/global Cursor home | `${HOME}/.cursor` | Named volume (survives rebuilds) |
| Project settings | `/workspace/.cursor`, `AGENTS.md` | Bind-mounted project |

!!! warning

    Global rules and CLI permissions are **guidance**.
    They are not a security sandbox.
    Real isolation comes from Docker mounts, Linux permissions, and keeping the Docker socket optional.

## Why `/opt/cursor-defaults` exists

Compose mounts a named volume at `/home/developer/.cursor`.
Anything written only to that path during `docker build` is hidden when the empty volume mounts.

So the image stores defaults under `/opt/cursor-defaults`.
At startup, the entrypoint copies **missing** files into `${HOME}/.cursor`.

## Startup initialization

1. Entrypoint runs `init-cursor-home`.
2. Missing files are copied from `/opt/cursor-defaults` → `${HOME}/.cursor`.
3. Existing files are skipped (user changes are kept).
4. The original command runs (`bash`, `cursor-init-project`, …).

TMUX still starts only from `.bashrc` for interactive terminals.
The entrypoint does not start TMUX.

### Idempotency

Running init many times is safe:

* first run creates missing defaults
* later runs print `Skipped` for files that already exist
* modified files are never overwritten by default

The image keeps an empty, developer-owned `${HOME}/.cursor` directory so the first
named-volume mount stays writable. Defaults still come only from `/opt/cursor-defaults`.

### Reset Cursor user config

Deleting the volume removes login state and customized global files:

```bash
make clean-volumes
make shell
```

The next start seeds defaults again from `/opt/cursor-defaults`.

## What ships in the defaults

Source tree in this repo: `cursor-home/`.

| Path | Role |
| --- | --- |
| `rules/` | Global always-on rules (`container-safety`, `general-quality`) |
| `skills/` | Reusable skills (`project-bootstrap`, `docker-review`) |
| `templates/` | Project templates for `cursor-init-project` |
| `cli-config.json` | Cursor CLI global config (verified format) |
| `permissions.example.json` | Example permissions block (not auto-loaded) |

!!! note

    Cursor CLI reads permissions from `~/.cursor/cli-config.json` (global) or
    `.cursor/cli.json` (project), not from a standalone `permissions.json`.
    This image seeds `cli-config.json`. `permissions.example.json` is documentation only.

## Project bootstrap

Templates are **not** copied into `/workspace` at startup.

Initialize a project explicitly:

```bash
make shell
cursor-init-project --dry-run
cursor-init-project
```

Or from the host:

```bash
make init-project-dry-run
make init-project
```

| Mode | Behavior |
| --- | --- |
| default | create missing files only |
| `--dry-run` | print actions, write nothing |
| `--force` | overwrite after timestamped `.bak.*` backups |

Review generated files before you commit them.

## Cursor CLI command

```bash
agent --version
```

## Project files in *this* repository

| File | Main job |
| --- | --- |
| `AGENTS.md` | Agent instructions for this infra repo |
| `.cursor/rules/*.mdc` | Repo-specific Cursor rules |
| `.cursorignore` | Block secrets/junk from the agent |
| `.cursorindexingignore` | Reduce indexing noise |

!!! note

    `.cursorignore` limits **access**.
    `.cursorindexingignore` mainly limits **indexing**.

## Tips

1. Mount only the project you want edited (`PROJECT_DIR`).
2. Prefer `make shell` unless Docker-from-Docker is required.
3. Use `cursor-init-project` for new mounted apps, not for every shell start.
4. Keep secrets out of the image and out of git.
