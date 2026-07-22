# Getting started

This page walks through the first run from an empty clone to a working browser terminal.

## 1. Clone the repository

```bash
git clone <repository-url> cursor-cli-devcontainer
cd cursor-cli-devcontainer
```

## 2. Configure projects

### Option A — multi-project (recommended)

Copy the JSON template and list every project you want to mount:

```bash
cp .env.example .env
cp cind.config.example.json cind.config.json
```

Edit `cind.config.json`:

```json
{
  "default_project": "my-app",
  "projects": [
    {
      "name": "my-app",
      "path": "/home/you/projects/my-app",
      "tmux": "my-app"
    }
  ]
}
```

Rules:

* `projects` must contain **at least one** project
* each `path` must be an **absolute** host path (no `~` or relative paths)
* each project is mounted into the container and shown in the launcher menu
* `default_project` sets the container `working_dir` (defaults to the first project)

See [JSON config](config.md) for `windows[]`, ttyd, and resources.

### Option B — single project (no JSON)

Skip `cind.config.json`. `make env` will create a one-project runtime from `PROJECT_DIR`:

```bash
cp .env.example .env
```

## 3. Generate `.env` and project mounts

```bash
make env
```

`make env` fills:

* `USER_UID` / `USER_GID` from your host account
* `DOCKER_GID` from `/var/run/docker.sock` when present
* `PROJECT_DIR` (default project path)
* `.cind/compose-projects.generated.yml` (one Docker volume per project)
* `.cind/runtime-config.json` (launcher + tmux)

If `./cind.config.json` exists, it is used automatically. Override with:

```bash
make env CONFIG=/path/to/other.config.json
```

For single-project mode without JSON:

```bash
make env PROJECT_DIR=$HOME/projects/my-app
```

!!! tip

    Use absolute paths only — not `.`, `../`, or `~/project`. See [Path parity](path-parity.md).

## 4. Check path parity

```bash
make path-check
```

Shows the default project and every mounted project path.

## 5. Build the image

```bash
make build
```

The first build downloads base images and tool stages. Later builds are faster because of Docker layer and BuildKit caches.

## 6. Start the terminal

```bash
make terminal-docker
```

Use `make terminal` if you do **not** need the host Docker socket.

Open the URL (default `http://localhost:7681`) or run:

```bash
make terminal-url
```

In the browser you see the **project launcher** — pick a project by number. Each choice attaches to a dedicated tmux session for that project.

Two browser tabs → two projects at once.

!!! note

    `make terminal` does **not** mount the Docker socket.
    Use `make terminal-docker` when you need `docker compose` against the host daemon.

!!! warning

    ttyd has no authentication. Use only on localhost or a private network (Tailscale).

## 7. Confirm tools

In the browser terminal (after picking a project):

```bash
agent --version
test -d "${HOME}/.cursor"
cursor-init-project --help
```

## 8. Optional: scaffold Cursor files in the mounted project

```bash
cursor-init-project --dry-run
cursor-init-project
```

Or from the host:

```bash
make init-project-dry-run
make init-project
```

## Adding another project later

1. Add an entry to `projects[]` in `cind.config.json`
2. `make env`
3. `make down && make terminal-docker`
4. Open the browser — the new project appears in the menu

## Next steps

* [JSON config](config.md) — full schema
* [Project launcher](launcher.md) — multi-project workflow
* [tmux](tmux.md) — sessions, windows, keybindings
* [Path parity](path-parity.md) — why absolute paths matter
* [Makefile](makefile.md) — all Make targets
