# JSON config profile

Use a JSON file to declare **which projects are mounted** into the container and shown in the browser launcher.
Keep `.env` for host identity (`USER_UID`, `USER_GID`, `DOCKER_GID`).

## Quick start

```bash
cp cind.config.example.json cind.config.json
# edit paths in cind.config.json (at least one project)
make env
make path-check
make terminal-docker
```

Or pass a config explicitly:

```bash
make terminal-docker CONFIG=./cind.config.json
```

If `./cind.config.json` exists, `make env` picks it up automatically.

## Example

```json
{
  "default_project": "app-a",
  "projects": [
    {
      "name": "app-a",
      "path": "/home/you/projects/app-a",
      "tmux": "app-a"
    },
    {
      "name": "cind",
      "path": "/home/you/workspace/kyther/cind",
      "tmux": "cind"
    }
  ],
  "ttyd": {
    "port": 7681,
    "host_port": 7681,
    "font_size": 22
  },
  "resources": {
    "cpus": 8,
    "memory": "16g",
    "shm_size": "2g",
    "tmpfs_size": "2g"
  }
}
```

Rules:

* `projects` is **required** and must contain **at least one** project
* each `projects[].path` is mounted into the container with path parity (same absolute path on host and inside)
* `default_project` must match a `projects[].name` (defaults to the first project if omitted)
* `tmux` is the persistent session name for that project
* optional `windows[]` defines tmux windows on first session create (see [tmux](tmux.md))

### Project windows (optional)

```json
"windows": [
  {"name": "editor", "icon": "📝", "dir": "."},
  {"name": "server", "icon": "🐍", "dir": ".", "command": "make run"},
  {"name": "logs", "icon": "⚙", "dir": "."},
  {"name": "shell", "icon": "🖥", "dir": "."}
]
```

Omit `windows` to use cind defaults (shell, editor, logs, tests when present).

## What `make env` does

1. Reads `CONFIG` / `cind.config.json`
2. Writes `.env` keys used by Compose (`PROJECT_DIR`, ttyd, resources)
3. Writes `.cind/runtime-config.json` (mounted into the container as `/etc/cind/config.json`)
4. Writes `.cind/compose-projects.generated.yml` (one path-parity volume per project)

The browser launcher reads `/etc/cind/config.json` and shows the project list.

## Migration from `projects_dir`

Older configs used a separate `projects_dir` plus `projects[]`. That field was removed.

Before:

```json
{
  "projects_dir": "/home/you/workspace/kyther",
  "projects": [{ "name": "cind", "path": ".../cind", "tmux": "cind" }]
}
```

After:

```json
{
  "projects": [{ "name": "cind", "path": "/home/you/workspace/kyther/cind", "tmux": "cind" }]
}
```

Each listed project is mounted individually. Add sibling repos as separate entries in `projects[]`.

## Files

| File | Role |
| --- | --- |
| `cind.config.example.json` | Template (committed) |
| `cind.config.json` | Your local profile (gitignored) |
| `.cind/runtime-config.json` | Generated runtime copy (gitignored) |
| `.cind/compose-projects.generated.yml` | Generated Compose mounts (gitignored) |
| `.env` | Host UID/GID + values derived from JSON |
