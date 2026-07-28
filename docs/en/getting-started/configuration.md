---
description: Describe workspaces and projects in orcan.config.json — the story of your context, then how to apply it.
---

# Configuration

## Why a config file

Your multi-repo job is a **story**: which projects form which workspace. `orcan.config.json` is that story in data. Make does not invent your layout; it applies what you describe.

If Project / Workspace / Context are unclear, read [Core Ideas](../ideas/core-ideas.md) first.

## Source of truth

Host config is **JSON only**:

```text
orcan.config.json
```

Template: `orcan.config.example.json`.

After edits, always run:

```bash
orcan sync
```

!!! note
    `orcan up` does **not** run `orcan sync`. Apply config first, then recreate the container.

Then recreate the container if it is already running:

```bash
orcan down && orcan up
```

## Shape (example)

```json
{
  "workspaces": [
    {
      "name": "myapp",
      "projects": [
        {
          "name": "backend",
          "path": "/absolute/path/to/myapp/backend"
        },
        {
          "name": "frontend",
          "path": "/absolute/path/to/myapp/frontend"
        }
      ]
    }
  ],
  "tmux": {
    "initial_windows": 3,
    "window_prefix": "tab"
  },
  "ttyd": {
    "port": 7681,
    "host_port": 7681,
    "font_size": 22,
    "theme": "dark"
  },
  "resources": {
    "cpus": 2,
    "memory": "4g",
    "shm_size": "512m",
    "tmpfs_size": "512m"
  }
}
```

Defaults stay light on purpose (typical laptop). Raise them when the machine can spare more — see below.

### Field notes

| Field | Meaning |
| --- | --- |
| `workspaces[].name` | tmux session name and folder under `/home/developer/workspaces/` |
| `projects[].name` | Symlink name inside the workspace |
| `projects[].path` | Absolute host path (same path inside the container — path parity) |
| `tmux.*` | Windows created when a session starts |
| `ttyd.*` | Browser terminal port and look |
| `resources.*` | Container CPU / memory / shm / tmpfs limits |

### Raising resources

Edit `resources` in `orcan.config.json` (for example `cpus: 8`, `memory: "16g"`), then:

```bash
orcan sync
orcan down && orcan up
```

If `.env` already has `CPUS` / `MEMORY` set, `orcan sync` keeps those values. Change them in `.env` too, or remove the keys so config wins on the next `orcan sync`.

## Ways to edit

| Command | Use when |
| --- | --- |
| `orcan context wizard` | Interactive create/edit |
| `orcan context add /abs/path` | Add one project non-interactively |
| `orcan init /abs/path` | First run |
| Hand-edit JSON | You know the schema |

Show current layout:

```bash
orcan context show
```

## What `orcan sync` writes

`orcan.config.json` is the story you edit (default under `~/.config/orcan/home/`). **`orcan sync`** is what Docker / Compose can swallow: it refreshes host runtime files from that JSON (+ UID/GID). Without it, mounts and env stay stale or missing.

| Output | Role |
| --- | --- |
| `.env` | Compose and Make variables |
| `.orcan/runtime-config.json` | Mounted into the container as `/etc/orcan/config.json` |
| `.orcan/compose-projects.generated.yml` | Extra bind mounts |
| `.orcan/workspaces/<name>/` | Host-backed workspace meta |
| `$ORCAN_DATA` tree | Default `~/.config/orcan` (Cursor/Claude home, caches) |

Do not commit `.env` or `.orcan/` (gitignored).

## Seed into git checkouts (optional, rarely needed)

The **workspace** already gets a context pack on container start (`AGENTS.md`, ignores, `.cursor/rules/`). You do **not** need `orcan seed` for that.

`orcan seed` only copies the same kind of files **into each mounted git repo**. Skip it unless you want those files inside the checkouts themselves (e.g. to commit them):

```bash
orcan seed --all
orcan seed --all --dry-run
```

Full field rules and rejected keys: [Configuration reference](../reference/configuration.md).
