# Configuration

## What this does

Explains how Orcan stores workspaces and how you apply changes.

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
    "cpus": 8,
    "memory": "16g",
    "shm_size": "2g",
    "tmpfs_size": "2g"
  }
}
```

### Field notes

| Field | Meaning |
| --- | --- |
| `workspaces[].name` | tmux session name and folder under `/home/developer/workspaces/` |
| `projects[].name` | Symlink name inside the workspace |
| `projects[].path` | Absolute host path (same path inside the container — path parity) |
| `tmux.*` | Windows created when a session starts |
| `ttyd.*` | Browser terminal port and look |
| `resources.*` | Container CPU / memory limits |

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

## Migrating from older “cind” installs

If you still have old host data:

```bash
mv ~/.config/cind ~/.config/orcan
```

Old local files like `cind.config.json` are obsolete. Use `orcan.config.json` only.

Full field rules and rejected keys: [Configuration reference](../reference/configuration.md).
