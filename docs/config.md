# JSON config profile

Use a JSON file to declare **workspaces** (each with 1+ mounted repos) shown in the browser launcher.
Keep `.env` for host identity (`USER_UID`, `USER_GID`, `DOCKER_GID`).

## Quick start

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Add repos: `make config-scaffold PROJECT_DIR=... WORKSPACE=name` then `make env`.

Optional template: `make config-init` (full example file).

Or pass a config explicitly:

```bash
make terminal-docker CONFIG=./cind.config.json
```

If `./cind.config.json` exists, `make env` picks it up automatically.

## Workspaces

A **workspace** = one tmux session + one directory + 1+ repos.

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "tmux": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend", "role": "service"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend", "role": "service"}
      ]
    },
    {
      "name": "cind",
      "tmux": "cind",
      "projects": [
        {"name": "cind", "path": "/home/you/workspace/kyther/cind", "role": "orchestrator"}
      ]
    }
  ]
}
```

Rules:

* `workspaces` must contain **at least one** workspace
* each workspace must contain **at least one** project in `projects[]`
* workspace container path defaults to `/home/developer/workspaces/<name>`
* `tmux` defaults to workspace `name` (one session per workspace)
* project `name` = subdirectory under workspace root
* no `alias`, no `default_project`, no `default_workspace`
* container entrypoint uses the **first** workspace in the list for startup paths

### Mount modes (`parity` vs `workspace`)

| Mode | When | Container path |
| --- | --- | --- |
| `parity` (default) | Docker via host socket, bind mounts 1:1 | Same as host `path` |
| `workspace` | Code review, AI analysis, no host path mirror | `<workspace.root>/<name>` |

Set default per workspace with `mount_mode`, override per repo with `projects[].mount`.

```json
{
  "name": "code-review",
  "mount_mode": "workspace",
  "projects": [
    {"name": "upstream", "path": "/host/path/repo"}
  ]
}
```

Workspace-only mode defaults root to `/home/developer/workspaces/<name>`. Parity mode uses `/workspace` (single) or `/workspace/<name>` (multiple).

Full guide: [Mount modes](architecture/mount-modes.md).

### Resource limits (CPUS, memory, …)

`cind.config.json` may include a `resources` block — used as **defaults on first `make env` only**.

For host-specific limits (Docker CPU cap, RAM), edit **`.env`**:

```dotenv
CPUS=4
MEMORY=8g
```

`make env` and `make terminal-docker` **do not overwrite** these once set.

### Legacy single-workspace shape

Still supported — equivalent to one entry in `workspaces[]`:

```json
{
  "workspace": {
    "name": "gotibooks",
    "root": "/workspace",
    "meta_path": "/home/you/gotibooks-workspace",
    "tmux": "gotibooks",
    "projects": [
      {"name": "backend", "path": "/home/you/gotibooks/backend"}
    ]
  }
}
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace label in launcher; directory under `/home/developer/workspaces/` |
| `root` | Override container path (default `/home/developer/workspaces/<name>`) |
| `meta_path` | Host dir for cross-repo `.cursor/rules` (default: `.cind/workspaces/<name>/`) |
| `tmux` | tmux session name (defaults to workspace `name`) |
| `projects[].name` | Subdirectory under workspace root |
| `role` | Hint for agents (`service`, `orchestrator`, `docs`, …) |

### Project windows (optional)

```json
"windows": [
  {"name": "editor", "icon": "📝", "dir": "."},
  {"name": "server", "icon": "🐍", "dir": ".", "command": "make run"},
  {"name": "logs", "icon": "⚙", "dir": "."}
]
```

Omit `windows` for default layout (one window per repo). See [tmux](tmux.md).

Generated files (per workspace):

* `.cind/<name>.container.code-workspace` — open inside container
* `.cind/<name>.host.code-workspace` — open from host (absolute paths)
* `<workspace.root>/.manifest.json` — written at container startup

Full design: [Virtual workspace](architecture/workspace.md).

## What `make env` does

1. Reads `CONFIG` / `cind.config.json`
2. Writes `.env` keys used by Compose (workspace paths, generated paths)
3. Seeds `CPUS`, `MEMORY`, `TTYD_*` in `.env` **only if missing** — edit `.env` for host limits (not overwritten on `make env`)
4. Writes `.cind/runtime-config.json` (mounted into the container as `/etc/cind/config.json`)
5. Writes `.cind/compose-projects.generated.yml` (meta_path bind per workspace + path-parity bind per repo)
6. Writes `.cind/workspace.manifest.json` and `*.code-workspace` files

The browser launcher reads `/etc/cind/config.json` and lists all workspaces.

## Files

| File | Role |
| --- | --- |
| `cind.config.example.json` | Template (committed) |
| `cind.config.json` | Your local profile (gitignored) |
| `.cind/runtime-config.json` | Generated runtime copy (gitignored) |
| `.cind/compose-projects.generated.yml` | Generated Compose mounts (gitignored) |
| `.env` | Host UID/GID, resource limits, values derived from config |
