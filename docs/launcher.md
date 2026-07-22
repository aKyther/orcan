# Multi-project launcher

Browser terminal (`ttyd`) starts a **project picker**, not a single tmux session.

## How it works

1. Open `http://localhost:7681`
2. Choose a project by number
3. Enter a dedicated tmux session for that project
4. Run `agent` there
5. Detach or refresh the page → picker again → same session if it still exists

Each new session gets a default window layout (shell, editor, logs, tests). Customize windows per project in `cind.config.json` — see [tmux](tmux.md).

Two browser tabs can open two projects at once (pick different numbers).

## Configure projects

Projects are declared in `cind.config.json`. See [JSON config](config.md).

```bash
cp cind.config.example.json cind.config.json
# add at least one project with an absolute path
make env
make terminal-docker
```

Example:

```json
{
  "default_project": "app-a",
  "projects": [
    { "name": "app-a", "path": "/home/you/projects/app-a", "tmux": "app-a" },
    { "name": "cind", "path": "/home/you/workspace/kyther/cind", "tmux": "cind" }
  ]
}
```

Each entry in `projects[]` is:

* mounted into the container (path parity),
* listed in the launcher menu,
* given its own tmux session (`tmux` field).

### Single project without JSON

```bash
make terminal PROJECT_DIR=/absolute/path/to/project
```

`make env` synthesizes a one-project runtime config from `PROJECT_DIR`.

## Font size (phone)

Set in `cind.config.json`:

```json
"ttyd": { "font_size": 26 }
```

Or append `?fontSize=26` to the browser URL.

Restart after changes: `make down && make terminal-docker`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Empty project list | Add at least one project to `cind.config.json`, run `make env` |
| Project path missing in container | Path must be listed in `projects[]`; rerun `make env` |
| Wrong tmux session | Each project uses `projects[].tmux`; pick by number in launcher |

See also: [JSON config](config.md), [tmux](tmux.md).
