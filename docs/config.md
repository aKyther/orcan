# Config profile (YAML)

Declare **workspaces** (each with 1+ mounted repos) in **`cind.config.yaml`**.
Keep `.env` for host identity (`USER_UID`, `USER_GID`, `DOCKER_GID`).

Host scripts need **PyYAML**. `make host-deps` / `make env` create a local `.venv` and install it (see `requirements-host.txt`). Alternatively: `sudo apt install python3-yaml`.

JSON (`cind.config.json`) is still accepted if no YAML file is present. Prefer YAML for new setups.

## Quick start

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

### After the wizard (or any config edit)

```bash
make config-wizard          # create / edit cind.config.yaml
make env                    # apply → .env, mounts, runtime
make down && make terminal-docker   # if container already running
```

`make terminal-docker` does **not** call `make env`.

Non-interactive add: `make config-scaffold PROJECT_DIR=... WORKSPACE=name` then `make env`.

Optional template: `make config-init` (copies `cind.config.example.yaml`).

## Config wizard

`make config-wizard` walks you through creating or editing `cind.config.yaml`:

1. Create workspace? → name
2. Add projects → name + absolute path (validates existence; retry on errors)
3. More workspaces / projects until you stop
4. Optional tmux / ttyd defaults
5. If a config already exists → for each workspace: **keep / change / delete**; on keep or change, ask **Add another project to workspace …?**; then add more workspaces

Writes YAML (offers to migrate off JSON). Then run `make env` before `make terminal-docker`.

Discovery order for `make env`: `cind.config.yaml` → `cind.config.yml` → `cind.config.json`.
`make terminal` / `make terminal-docker` do **not** regenerate config — run `make env` after edits.

## Workspaces

A **workspace** = one tmux session + one directory + **only** the repos listed in that entry’s `projects[]`.

```yaml
workspaces:
  - name: gotibooks
    projects:
      - name: backend
        path: /home/you/gotibooks/backend
      - name: frontend
        path: /home/you/gotibooks/frontend

  - name: cind
    projects:
      - name: cind
        path: /home/you/workspace/kyther/cind
```

### Isolation (projects do not mix)

| `workspaces[]` entry | Owns |
| --- | --- |
| `name` | tmux session + dir `/home/developer/workspaces/<name>/` |
| `projects[]` | **Only** the symlinks under that dir |

- Projects of workspace A never appear under workspace B’s root.
- The same host path may be listed in two workspaces (two symlinks); that is optional and explicit — not automatic sharing.
- `make env` regenerates mounts; container start runs `init-workspace`, which creates only the listed symlinks and **removes orphan** symlinks left from older configs.
- Removing a workspace from config also deletes its `.cind/workspaces/<name>/` meta dir on the next `make env` (and again at container start). Run `make env` after edits — otherwise stale dirs stay visible under `/home/developer/workspaces/`.

Rules:

* `workspaces` must contain **at least one** workspace
* each workspace must contain **at least one** project in `projects[]`
* workspace container path: `/home/developer/workspaces/<name>`
* tmux session name = workspace `name` (do not set a separate `tmux` field)
* project `name` = subdirectory under **that** workspace root only
* no `alias`, no `default_project`, no `default_workspace`, no `mount_mode`, no per-workspace `tmux`
* each project uses **path parity** (same absolute path on host and in container) plus a **symlink** under its workspace root
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

`cind.config.yaml` may include a `resources` block — used as **defaults on first `make env` only**.

For host-specific limits (Docker CPU cap, RAM), edit **`.env`**:

```dotenv
CPUS=4
MEMORY=8g
```

`make env` and `make terminal-docker` **do not overwrite** host limits in `.env` once set (`CPUS`, `MEMORY`, `TTYD_*`, …).

`make terminal` / `make terminal-docker` **never** call `make env` — run `make env` explicitly after config edits.

### ttyd (browser terminal)

Defaults are applied automatically (no chooser at start):

```yaml
ttyd:
  port: 7681
  host_port: 7681
  font_size: 22
  font_family: "Menlo, Monaco, 'Courier New', monospace"
  theme: dark
```

`theme: dark` selects a built-in xterm.js palette; or pass a raw JSON theme string. Seeded into `.env` on first `make env` only (`TTYD_*`).

### Legacy single-workspace shape

Still supported — equivalent to one entry in `workspaces[]`:

```yaml
workspace:
  name: gotibooks
  projects:
    - name: backend
      path: /home/you/gotibooks/backend
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace label, directory, and tmux session name |
| `projects[].name` | Symlink subdirectory under workspace root |
| `projects[].path` | Host absolute path (parity mount) |

Do not set `meta_path`, `root`, `role`, or per-workspace `tmux`.

### tmux tabs (global)

Root-level `tmux` configures **window defaults** (not the session name):

```yaml
tmux:
  initial_windows: 3
  window_prefix: tab
```

Creates `tab-1`, `tab-2`, `tab-3` in the workspace root. Session name is always `workspaces[].name`. Developers rename tabs with tmux (`prefix ,`) or add windows (`Alt+c`).

Do not confuse tabs with workspaces: **one config workspace → one tmux session**; tabs are only extra shells inside that session.

Generated files (per workspace):

* `.cind/<name>.container.code-workspace` — open inside container
* `.cind/<name>.host.code-workspace` — open from host (absolute paths)
* `<workspace.root>/.manifest.json` — written at container startup

Full design: [Virtual workspace](architecture/workspace.md).

## What `make env` does

1. Reads `CONFIG` or discovers `cind.config.yaml` / `.yml` / `.json`
2. Writes `.env` keys used by Compose (workspace paths, generated paths)
3. Seeds `CPUS`, `MEMORY`, `TTYD_*` in `.env` **only if missing** — edit `.env` for host limits (not overwritten on `make env`)
4. Writes `.cind/runtime-config.json` (mounted into the container as `/etc/cind/config.json`)
5. Writes `.cind/compose-projects.generated.yml` (bind `.cind/workspaces` → `/home/developer/workspaces`, plus path-parity bind per repo)
6. Writes `.cind/workspace.manifest.json` and `*.code-workspace` files

The browser launcher reads `/etc/cind/config.json` (generated) and lists all workspaces.

## Files

| File | Role |
| --- | --- |
| `cind.config.example.yaml` | Template (committed) |
| `cind.config.example.json` | Deprecated JSON template (still valid) |
| `cind.config.yaml` | Your local profile (gitignored) — **preferred** |
| `cind.config.json` | Legacy local profile (gitignored; used if no YAML) |
| `.cind/runtime-config.json` | Generated runtime copy for the container (gitignored) |
| `.cind/compose-projects.generated.yml` | Generated Compose mounts (gitignored) |
| `.env` | Host UID/GID, resource limits, values derived from config |
| `requirements-host.txt` / `.venv` | PyYAML for host `make env` / scaffold |

### Migrating from JSON

1. Keep `cind.config.json` working as-is, **or**
2. `cp cind.config.example.yaml cind.config.yaml`, copy your workspaces into YAML, then remove or rename the JSON file (YAML is preferred when both exist).
3. `make env`
