# Cursor

This repository prepares Cursor CLI with **global defaults inside the container** and optional **project scaffolding** for `${PROJECT_DIR}`.

## Repository Cursor config vs image defaults

| Location | Purpose |
| --- | --- |
| Root `.cursor/rules/`, ignore files | Developing **this** repository |
| `docker/rootfs/opt/cursor-defaults/` | Product defaults copied into the **image** |
| `${HOME}/.cursor` in the container | Writable user state (bind: `$CIND_DATA/cursor`) |
| `${PROJECT_DIR}/.cursor` | Settings for the **mounted project** |

Do not mix these layers.

## Configuration layers

```text
Image defaults
    ↓
/opt/cursor-defaults
(from docker/rootfs/opt/cursor-defaults)

Persistent container user settings (host: ~/.config/cind/…)
    ↓
/home/developer/.cursor           ← $CIND_DATA/cursor
/home/developer/.config/cursor    ← $CIND_DATA/cursor-app (login)

Project-specific settings
    ↓
${PROJECT_DIR}/.cursor
${PROJECT_DIR}/AGENTS.md

Technical isolation
    ↓
Docker mounts
Linux permissions
Optional Docker socket
Cursor CLI permissions
```

## Why `/opt/cursor-defaults` exists

Compose bind-mounts `$CIND_DATA/cursor` at `/home/developer/.cursor`.
Anything written only to that path during `docker build` is hidden when the host dir mounts.

So the image stores defaults under `/opt/cursor-defaults`.
At startup, the entrypoint copies **missing** files into `${HOME}/.cursor`.

## Startup initialization

1. Entrypoint runs `init-cursor-home`.
2. Missing files are copied from `/opt/cursor-defaults` → `${HOME}/.cursor`.
3. Existing files are skipped (user changes are kept).
4. The original command runs (`bash`, `cursor-init-project`, …).

TMUX starts from `cursor-ttyd` when you open the browser terminal.
The entrypoint does not start TMUX.

### Idempotency

Running init many times is safe:

* first run creates missing defaults
* later runs print `Skipped` for files that already exist
* modified files are never overwritten by default

Defaults still come only from `/opt/cursor-defaults`.

### Reset Cursor user config

```bash
make clean-data
make env
make terminal
```

Open `http://localhost:7681` to continue.

### Login persistence

Cursor CLI stores different data in two host dirs under `$CIND_DATA` (default `~/.config/cind`):

| Path in container | Host path | Contents |
| --- | --- | --- |
| `~/.cursor` | `$CIND_DATA/cursor` | `cli-config.json`, chats, rules, skills |
| `~/.config/cursor` | `$CIND_DATA/cursor-app` | `auth.json` (login tokens) |

Log in once from the browser terminal (`agent login` or the interactive flow). Restarts and `make down` keep both.

!!! warning

    `make clean-data` deletes login state along with caches and CLI config under `$CIND_DATA`.

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
| `karpathy-guidelines.mdc` | Think → simplify → surgical edit → verify (Karpathy-inspired) |
| `operating-principles.mdc` | Focus, clutter avoidance, honest reporting (cind-specific) |
| `planning-and-execution.mdc` | Practical planning, scope control, validation, short completion reports |
| `code-quality.mdc` | Readable code, no unnecessary abstraction |
| `documentation-discipline.mdc` | Update existing docs, avoid duplicate or stray Markdown |
| `container-safety.mdc` | `${PROJECT_DIR}` scope, secrets, Docker socket, destructive commands |

Rules stay **generic**. They do not prescribe a language, framework, or architecture.
Stack-specific guidance belongs in the **mounted project**, not here.

### Global skills (on demand)

| Skill | Purpose |
| --- | --- |
| `karpathy-guidelines` | Recall the four behavioral principles on demand |
| `repository-analysis` | Understand a repo before large changes |
| `focused-implementation` | Smallest complete implementation |
| `final-review` | Review diff and report validation honestly |
| `docker-review` | Review Docker/Compose/Makefile setup |
| `project-bootstrap` | Scaffold missing project Cursor files |

Skills do not replace rules. Rules apply every session; skills guide specific workflows.

### What belongs in the mounted project

| Location | Purpose |
| --- | --- |
| `${PROJECT_DIR}/.cursor/rules/` | Rules for **this** repository only |
| `${PROJECT_DIR}/AGENTS.md` | Project goals, setup, and checks |
| `${PROJECT_DIR}/.cursorignore` | Files Cursor agents should not read |
| `${PROJECT_DIR}/.cursorindexingignore` | Keep large/secret files out of the Cursor index |
| `${PROJECT_DIR}/.claudeignore` | Claude Code discovery exclusions (same idea) |
| `${PROJECT_DIR}/.claude/settings.json` | Claude `permissions.deny` for `.env` / keys |

Workspace roots (under `/home/developer/workspaces/<name>/`) also get a generated **`AGENTS.md`** / **`CLAUDE.md`**, ignore files, and `.manifest.json` on container start — see [Workspace architecture](architecture/workspace.md#agents).

Create project files with `cursor-init-project` when needed (or `make init-project` / `make init-project-all` from the host).
Templates under `templates/` are starting points — customize them per project.

Optional handoff between `agent` and `claude`: `cind-session-brief` → `.cind/session-brief.md` (see [Context orchestration](architecture/context.md)).

!!! tip

    Workspace-level `.cursorignore` / `.claudeignore` cover the workspace root.
    When you `cd` into a project symlink, prefer the same files **inside that repo**
    (`cursor-init-project` or `make init-project-all`). Global denies in `cli-config.json` / `~/.claude/settings.json`
    still apply. Ignore files reduce accidental discovery; they are not a hard security boundary.

### Why the separation exists

| Layer | Scope | Changes when |
| --- | --- | --- |
| Image defaults (`/opt/cursor-defaults`) | Every session, every project | You rebuild the devcontainer image |
| User Cursor home (`~/.cursor`) | Persistent per developer in the container | First start seeds defaults; later edits persist |
| Mounted project (`${PROJECT_DIR}/.cursor`) | One repository | You work on that repo |

This keeps agent behavior consistent in the container while letting each project define its own stack and conventions.

!!! note

    Cursor CLI reads permissions from `~/.cursor/cli-config.json` (global) or
    `.cursor/cli.json` (project). `permissions.example.json` is documentation only.

## Project bootstrap

Templates are **not** copied into `${PROJECT_DIR}` at startup.

```bash
make terminal
```

Open `http://localhost:7681`, then:

```bash
cursor-init-project --dry-run
cursor-init-project
```

Or from the host:

```bash
make init-project-dry-run
make init-project
```

Review generated files before you commit them.

## Claude Code CLI

The image also installs Anthropic **Claude Code** (`claude`) via the official installer:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Inside the container:

```bash
claude --version
claude          # interactive session
```

| CLI | Command | Config (container-local) |
| --- | --- | --- |
| Cursor | `agent` | `~/.cursor`, `~/.config/cursor` (`$CIND_DATA` on host) |
| Claude Code | `claude` | `~/.claude` (`$CIND_DATA/claude` on host) |

Both CLIs can feed **usage into the tmux status bar** (`ctx` / `5h` / `7d`) via `cind-ai-statusline`. See [tmux → AI usage](tmux.md#ai-usage-in-the-status-bar).

Pick whichever CLI fits the task. Log in separately for each (`agent` vs `claude`).

## Path mapping

| Repository path | Container path | Purpose |
| --- | --- | --- |
| `docker/rootfs/opt/cursor-defaults` | `/opt/cursor-defaults` | Image defaults |
| `docker/rootfs/usr/local/bin/docker-entrypoint` | `/usr/local/bin/docker-entrypoint` | Startup |
| `docker/rootfs/usr/local/bin/init-cursor-home` | `/usr/local/bin/init-cursor-home` | Seed `${HOME}/.cursor` |
| `docker/rootfs/usr/local/bin/cursor-init-project` | `/usr/local/bin/cursor-init-project` | Project scaffold |

## Tips

1. Mount only the project you want edited (`PROJECT_DIR`).
2. Prefer `make terminal` unless Docker-from-Docker is required.
3. Use `cursor-init-project` for new mounted apps, not for every shell start.
4. Keep secrets out of the image and out of git.
