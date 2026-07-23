# Config profile (JSON)

Declare **workspaces** (each with 1+ mounted repos) in **`orcan.config.json`**.
Keep `.env` for host identity (`USER_UID`, `USER_GID`, `DOCKER_GID`).

Host scripts use **stdlib Python only** (`json`) — no PyYAML for config.

## Quick start

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

### After the wizard (or any config edit)

```bash
make config-wizard          # create / edit orcan.config.json
make env                    # apply → .env, mounts, runtime
make down && make terminal-docker   # if container already running
```

`make terminal-docker` does **not** call `make env`.

Non-interactive add: `make config-scaffold PROJECT_DIR=... WORKSPACE=name` then `make env`.

Optional template: `make config-init` (copies `orcan.config.example.json`).

## Config wizard

`make config-wizard` walks you through creating or editing `orcan.config.json`:

1. Create workspace? → name
2. Add projects → name + absolute path (validates existence; retry on errors)
3. More workspaces / projects until you stop
4. Optional tmux / ttyd defaults
5. If a config already exists → for each workspace: **keep / change / delete**; on keep or change, ask **Add another project to workspace …?**; then add more workspaces

Writes JSON. Then run `make env` before `make terminal-docker`.

`make terminal` / `make terminal-docker` do **not** regenerate config — run `make env` after edits.

## Workspaces

A **workspace** = one tmux session + one directory + **only** the repos listed in that entry’s `projects[]`.

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        { "name": "backend", "path": "/home/you/gotibooks/backend" },
        { "name": "frontend", "path": "/home/you/gotibooks/frontend" }
      ]
    },
    {
      "name": "orcan",
      "projects": [
        { "name": "orcan", "path": "/home/you/workspace/kyther/orcan" }
      ]
    }
  ]
}
```

### Isolation (projects do not mix)

| `workspaces[]` entry | Owns |
| --- | --- |
| `name` | tmux session + dir `/home/developer/workspaces/<name>/` |
| `projects[]` | **Only** the symlinks under that dir |

- Projects of workspace A never appear under workspace B’s root.
- The same host path may be listed in two workspaces (two symlinks); that is optional and explicit — not automatic sharing.
- `make env` regenerates mounts; container start runs `init-workspace`, which creates only the listed symlinks and **removes orphan** symlinks left from older configs.
- Removing a workspace from config also deletes its `.orcan/workspaces/<name>/` meta dir on the next `make env` (and again at container start). Run `make env` after edits — otherwise stale dirs stay visible under `/home/developer/workspaces/`.

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

`orcan.config.json` may include a `resources` block — used as **defaults on first `make env` only**.

For host-specific limits (Docker CPU cap, RAM), edit **`.env`**:

```dotenv
CPUS=4
MEMORY=8g
```

`make env` and `make terminal-docker` **do not overwrite** host limits in `.env` once set (`CPUS`, `MEMORY`, `TTYD_*`, …).

`make terminal` / `make terminal-docker` **never** call `make env` — run `make env` explicitly after config edits.

### ttyd (browser terminal)

Defaults are applied automatically (no chooser at start):

```json
"ttyd": {
  "port": 7681,
  "host_port": 7681,
  "font_size": 22,
  "font_family": "Menlo, Monaco, 'Courier New', monospace",
  "theme": "dark"
}
```

`theme: "dark"` selects a built-in xterm.js palette; or pass a raw JSON theme string. Seeded into `.env` on first `make env` only (`TTYD_*`).

## What `make env` does

1. Reads `CONFIG` or discovers `orcan.config.json`
2. Writes `.env` keys (UID/GID, mounts, workspace paths)
3. Seeds `CPUS`, `MEMORY`, `TTYD_*` in `.env` **only if missing** — edit `.env` for host limits (not overwritten on `make env`)
4. Generates `.orcan/runtime-config.json`, compose project mounts, workspace meta dirs

## Files

| Path | Role |
| --- | --- |
| `orcan.config.example.json` | Template (committed) |
| `orcan.config.json` | Your local profile (gitignored) |
| `.orcan/` | Generated runtime (gitignored) |

## Migrating from YAML

Older setups may still have `*.config.yaml`. Host config is **JSON-only** now:

```bash
yq -o=json cind.config.yaml > orcan.config.json   # or orcan.config.yaml
rm -f cind.config.yaml orcan.config.yaml
make env
```

## Migrating from the former name “cind”

| Old | New |
| --- | --- |
| `cind.config.json` | `orcan.config.json` |
| `.cind/` | `.orcan/` |
| `~/.config/cind` (`CIND_DATA`) | `~/.config/orcan` (`ORCAN_DATA`) |
| image / Compose service `cind` | `orcan` |
| CLI helpers `cind-*` | `orcan-*` |

```bash
# optional host data move
mv ~/.config/cind ~/.config/orcan
make env
make rebuild
make down && make terminal-docker
```

The clone directory may still be named `…/cind` until you rename it on disk; `PROJECT_DIR` should match the real path.
