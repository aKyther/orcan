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
make env
```

!!! note
    `make terminal*` does **not** run `make env`. Apply config first, then recreate the container.

Then recreate the container if it is already running:

```bash
make down && make terminal-docker
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
make env
make down && make terminal-docker
```

If `.env` already has `CPUS` / `MEMORY` set, `make env` keeps those values. Change them in `.env` too, or remove the keys so config wins on the next `make env`.

## Ways to edit

| Command | Use when |
| --- | --- |
| `make config-wizard` | Interactive create/edit |
| `make config-scaffold PROJECT_DIR=…` | Add one project non-interactively |
| `make setup PROJECT_DIR=…` | First run |
| Hand-edit JSON | You know the schema |

Show current layout:

```bash
make config-show
make path-check
```

## What `make env` writes

`orcan.config.json` is the story you edit. **`make env`** is what Docker / Compose can swallow: it refreshes host runtime files from that JSON (+ UID/GID). Without it, mounts and env stay stale or missing.

| Output | Role |
| --- | --- |
| `.env` | Compose and Make variables |
| `.orcan/runtime-config.json` | Mounted into the container as `/etc/orcan/config.json` |
| `.orcan/compose-projects.generated.yml` | Extra bind mounts |
| `.orcan/workspaces/<name>/` | Host-backed workspace meta |
| `$ORCAN_DATA` tree | Default `~/.config/orcan` (Cursor/Claude home, caches) |

Do not commit `.env` or `.orcan/` (gitignored).

## Seed project files (optional)

Orcan does **not** rewrite every mounted repo on startup. To seed ignores/templates once:

```bash
make init-project-all
# or dry-run:
make init-project-all-dry-run
```

Full field rules and rejected keys: [Configuration reference](../reference/configuration.md).
