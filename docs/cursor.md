# Cursor

This repository prepares Cursor CLI with **global defaults inside the container** and optional **project scaffolding** for `/workspace`.

## Repository Cursor config vs image defaults

| Location | Purpose |
| --- | --- |
| Root `.cursor/rules/`, ignore files | Developing **this** repository |
| `docker/rootfs/opt/cursor-defaults/` | Product defaults copied into the **image** |
| `${HOME}/.cursor` in the container | Writable user state (named volume) |
| `/workspace/.cursor` | Settings for the **mounted project** |

Do not mix these layers.

## Configuration layers

```text
Image defaults
    ↓
/opt/cursor-defaults
(from docker/rootfs/opt/cursor-defaults)

Persistent container user settings
    ↓
/home/developer/.cursor           (named volume: cursor-config)
/home/developer/.config/cursor    (named volume: cursor-app-config; login)

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

TMUX still starts only from `~/.bashrc.d/50-cursor-dev.sh` for interactive terminals.
The entrypoint does not start TMUX.

### Idempotency

Running init many times is safe:

* first run creates missing defaults
* later runs print `Skipped` for files that already exist
* modified files are never overwritten by default

The image keeps an empty, developer-owned `${HOME}/.cursor` directory so the first
named-volume mount stays writable. Defaults still come only from `/opt/cursor-defaults`.

### Reset Cursor user config

```bash
make clean-volumes
make shell
ssh developer@localhost
```

### Login persistence

Cursor CLI stores different data in two volumes:

| Path | Volume | Contents |
| --- | --- | --- |
| `~/.cursor` | `cursor-config` | `cli-config.json`, chats, rules, skills |
| `~/.config/cursor` | `cursor-app-config` | `auth.json` (login tokens) |

Log in once after SSH (`agent login` or the interactive flow). Restarts and `make down` keep both volumes.

!!! warning

    `make clean-volumes` deletes login state along with caches and CLI config.

For scripts/CI, set `CURSOR_API_KEY` instead of interactive login.

## What ships in the defaults

Source tree: `docker/rootfs/opt/cursor-defaults/`.

| Path | Role |
| --- | --- |
| `rules/` | Global always-on rules (agent behavior in every session) |
| `skills/` | Reusable skills the agent can apply on demand |
| `templates/` | Project templates for `cursor-init-project` |
| `cli-config.json` | Cursor CLI global config |
| `permissions.example.json` | Example permissions block (not auto-loaded) |

## Global profile (rules and skills)

Every new Cursor CLI session in the container starts with the same **global profile**.
This shapes how the agent thinks and works. It is **not** tied to the mounted project.

On container start, `init-cursor-home` copies missing files from `/opt/cursor-defaults` into `~/.cursor`.
Existing files in the volume are never overwritten.

### Global rules (always active)

| Rule | Purpose |
| --- | --- |
| `operating-principles.mdc` | Understand the repo, stay focused, avoid clutter, report honestly |
| `planning-and-execution.mdc` | Practical planning, scope control, validation, short completion reports |
| `code-quality.mdc` | Readable code, no unnecessary abstraction |
| `documentation-discipline.mdc` | Update existing docs, avoid duplicate or stray Markdown |
| `container-safety.mdc` | `/workspace` scope, secrets, Docker socket, destructive commands |

Rules stay **generic**. They do not prescribe a language, framework, or architecture.
Stack-specific guidance belongs in the **mounted project**, not here.

### Global skills (on demand)

| Skill | Purpose |
| --- | --- |
| `repository-analysis` | Understand a repo before large changes |
| `focused-implementation` | Smallest complete implementation |
| `final-review` | Review diff and report validation honestly |
| `docker-review` | Review Docker/Compose/Makefile setup |
| `project-bootstrap` | Scaffold missing project Cursor files |

Skills do not replace rules. Rules apply every session; skills guide specific workflows.

### What belongs in the mounted project

| Location | Purpose |
| --- | --- |
| `/workspace/.cursor/rules/` | Rules for **this** repository only |
| `/workspace/AGENTS.md` | Project goals, setup, and checks |
| `/workspace/.cursorignore` | Files the agent should not read |

Create project files with `cursor-init-project` when needed.
Templates under `templates/` are starting points — customize them per project.

### Why the separation exists

| Layer | Scope | Changes when |
| --- | --- | --- |
| Image defaults (`/opt/cursor-defaults`) | Every session, every project | You rebuild the devcontainer image |
| User Cursor home (`~/.cursor`) | Persistent per developer in the container | First start seeds defaults; later edits persist |
| Mounted project (`/workspace/.cursor`) | One repository | You work on that repo |

This keeps agent behavior consistent in the container while letting each project define its own stack and conventions.

!!! note

    Cursor CLI reads permissions from `~/.cursor/cli-config.json` (global) or
    `.cursor/cli.json` (project). `permissions.example.json` is documentation only.

## Project bootstrap

Templates are **not** copied into `/workspace` at startup.

```bash
make shell
ssh developer@localhost
cursor-init-project --dry-run
cursor-init-project
```

Or from the host:

```bash
make init-project-dry-run
make init-project
```

Review generated files before you commit them.

## Path mapping

| Repository path | Container path | Purpose |
| --- | --- | --- |
| `docker/rootfs/opt/cursor-defaults` | `/opt/cursor-defaults` | Image defaults |
| `docker/rootfs/usr/local/bin/docker-entrypoint` | `/usr/local/bin/docker-entrypoint` | Startup |
| `docker/rootfs/usr/local/bin/init-cursor-home` | `/usr/local/bin/init-cursor-home` | Seed `${HOME}/.cursor` |
| `docker/rootfs/usr/local/bin/cursor-init-project` | `/usr/local/bin/cursor-init-project` | Project scaffold |

## Tips

1. Mount only the project you want edited (`PROJECT_DIR`).
2. Prefer `make shell` unless Docker-from-Docker is required.
3. Use `cursor-init-project` for new mounted apps, not for every shell start.
4. Keep secrets out of the image and out of git.
