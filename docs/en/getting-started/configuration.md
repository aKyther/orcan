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
  "plugins": {
    "ttyd": {
      "enabled": false,
      "host_port": 7681,
      "font_size": 14,
      "renderer": "webgl"
    },
    "redis": { "enabled": false, "workers": 1 }
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
| `plugins.<id>.enabled` | Default selection for `orcan up`; edit the grouped list in `orcan settings` |
| `tmux.*` | Windows created when a session starts |
| `plugins.ttyd.*` | Browser terminal port, look (`theme`: `dark`/`navy`, `mocha`, or raw JSON), renderer (`webgl` by default; `canvas` fallback), and `ping_interval` (WebSocket keepalive) |
| `resources.*` | Container CPU / memory / shm / tmpfs limits |

### Raising resources

Edit `resources` in `orcan.config.json` (for example `cpus: 8`, `memory: "16g"`), then:

```bash
orcan sync
orcan down && orcan up
```

JSON settings are authoritative. A legacy `.env` is ignored and left unchanged.

## Ways to edit

| Command | Use when |
| --- | --- |
| `orcan init` | Interactive create/edit |
| `orcan context add /abs/path` | Add one project non-interactively |
| `orcan context tui` | TUI: parent folder → multi-select repos → workspace (+ optional shared-branch worktrees) |
| `orcan context add --from-worktree /abs/repo SELECTOR` | Add an existing git worktree |
| `orcan context worktrees [/abs/repo]` | List worktrees for a repo |
| `orcan context worktree create --repo … --branch …` | Create a worktree and pin it |
| `orcan init /abs/path` | First run |
| Hand-edit JSON | You know the schema |

Show current layout:

```bash
orcan context show
```

## What `orcan sync` writes

`orcan.config.json` is the story you edit (default under `~/.config/orcan/`). **`orcan sync`** is what Docker / Compose can swallow: it refreshes host runtime files from that JSON (+ UID/GID). Without it, workspace manifests and mounts stay stale or missing. Host settings are resolved directly from JSON when commands run.

| Output | Role |
| --- | --- |
| `mounts/runtime-config.json` | Mounted into the container as `/etc/orcan/config.json` |
| `mounts/compose-projects.generated.yml` | Extra bind mounts |
| `mounts/compose-git.generated.yml` | Written by `orcan up --ssh` (SSH mounts) |
| `mounts/compose-network.generated.yml` | Written by `orcan up --network NAME` (join an existing Docker network) |
| `workspaces/<name>/` | Host-backed workspace meta |
| `$ORCAN_DATA` tree | Default `~/.config/orcan` (Cursor/Claude home, caches) |

Do not edit or commit generated `mounts/` or `workspaces/` files.

## Upgrade from dotenv configuration

Orcan no longer reads, writes or sources `.env`. Compose receives validated settings
in its process environment and is explicitly prevented from loading `.env` itself.
Existing `.env` files remain untouched; move non-secret custom settings into JSON
before recreating a container. Keep credentials out of JSON and manifests.

| Previous dotenv setting | JSON field |
| --- | --- |
| `CPUS`, `MEMORY`, `SHM_SIZE`, `TMPFS_SIZE` | `resources.cpus`, `resources.memory`, `resources.shm_size`, `resources.tmpfs_size` |
| `TTYD_HOST_PORT`, `TTYD_BIND`, `TTYD_FONT_SIZE` | `plugins.ttyd.host_port`, `plugins.ttyd.bind`, `plugins.ttyd.font_size` |
| Other `TTYD_*` display settings | Corresponding lowercase key under `plugins.ttyd` |
| `ORCAN_EXECUTOR_WORKERS`, `ORCAN_EXECUTOR_MAX_RUNNING` | `plugins.redis.workers`, `plugins.redis.max_running` |
| Other executor queue and timeout settings | Corresponding key under `plugins.redis` |
| `ORCAN_DATA`, `ORCAN_PROJECTS_ROOT` | `data_root`, `projects_root` |
| `IMAGE_LOCAL` | `image` |
| `IMAGE_REGISTRY`, `IMAGE_REPOSITORY`, `IMAGE_TAG` | `registry.host`, `registry.repository`, `registry.tag` |
| `TZ` | `timezone` |
| `ULIMIT_NOFILE`, `ULIMIT_NPROC` | `resources.nofile`, `resources.nproc` |
| `ORCAN_EXECUTOR_PORT` | `plugins.redis.port` |

Host UID, GID, socket group and Git identity are detected at command time.
`ORCAN_HOME`, `ORCAN_CONFIG_FILE` and named-instance CLI flags still locate the
configuration. `ORCAN_DATA` and `ORCAN_PROJECTS_ROOT` remain fallback locations
when the matching JSON field is absent. Other persistent settings come from JSON.
Authentication can use host CLI logins or temporary process variables, including
`TTYD_CREDENTIAL`; it is never copied into a generated configuration file.

Run `orcan sync`, finish active executor jobs, then recreate with your access flags.
The old shell-format launch record is not imported: use explicit flags for the first
start after this upgrade. Later `up --resume` uses `mounts/last-up.json`.


## Seed into git checkouts (optional, rarely needed)

The **workspace** already gets a context pack on container start (`AGENTS.md`, ignores, `.cursor/rules/`). You do **not** need `orcan seed` for that.

`orcan seed` only copies the same kind of files **into each mounted git repo**. Skip it unless you want those files inside the checkouts themselves (e.g. to commit them):

```bash
orcan seed --all
orcan seed --all --dry-run
```

Full field rules and rejected keys: [Configuration reference](../reference/configuration.md).

Choose default integrations in the [plugin list](../guides/plugins.md). Old
top-level `ttyd`/`executor` sections remain readable; a reviewed plugin save in
`orcan settings` groups them under `plugins`.
