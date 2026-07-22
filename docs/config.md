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
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    },
    {
      "name": "cind",
      "projects": [
        {"name": "cind", "path": "/home/you/workspace/kyther/cind"}
      ]
    }
  ]
}
```

Rules:

* `workspaces` must contain **at least one** workspace
* each workspace must contain **at least one** project in `projects[]`
* workspace container path: `/home/developer/workspaces/<name>`
* tmux session name = workspace `name` (do not set a separate `tmux` field)
* project `name` = subdirectory under workspace root
* no `alias`, no `default_project`, no `default_workspace`, no `mount_mode`, no per-workspace `tmux`
* each project uses **path parity** (same absolute path on host and in container) plus a **symlink** under the workspace root
* container entrypoint uses the **first** workspace in the list for startup paths (`WORKSPACE_*` in `.env`); the launcher still lists **all** workspaces

### After editing workspaces

```bash
make env
make down && make terminal-docker
```

Then in the browser launcher pick the workspace by number. Each entry is a separate tmux session under `/home/developer/workspaces/<name>/`.

Check:

```bash
make config-show
make path-check
```

### Resource limits (CPUS, memory, …)

`cind.config.json` may include a `resources` block — used as **defaults on first `make env` only**.

For host-specific limits (Docker CPU cap, RAM), edit **`.env`**:

```dotenv
CPUS=4
MEMORY=8g
```

`make env` and `make terminal-docker` **do not overwrite** host limits in `.env` once set (`CPUS`, `MEMORY`, `TTYD_*`, …).

`make terminal` / `make terminal-docker` **never** call `make env` — run `make env` explicitly after config edits.

### Legacy single-workspace shape

Still supported — equivalent to one entry in `workspaces[]`:

```json
{
  "workspace": {
    "name": "gotibooks",
    "projects": [
      {"name": "backend", "path": "/home/you/gotibooks/backend"}
    ]
  }
}
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace label, directory, and tmux session name |
| `projects[].name` | Symlink subdirectory under workspace root |
| `projects[].path` | Host absolute path (parity mount) |

Do not set `meta_path`, `root`, `role`, or per-workspace `tmux`.

### tmux tabs (global)

Root-level `tmux` configures **window defaults** (not the session name):

```json
"tmux": {
  "initial_windows": 3,
  "window_prefix": "tab"
}
```

Creates `tab-1`, `tab-2`, `tab-3` in the workspace root. Session name is always `workspaces[].name`. Developers rename tabs with tmux (`prefix ,`) or add windows (`Alt+c`).

Do not confuse tabs with workspaces: **one config workspace → one tmux session**; tabs are only extra shells inside that session.

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
5. Writes `.cind/compose-projects.generated.yml` (workspace root bind per workspace + path-parity bind per repo)
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
