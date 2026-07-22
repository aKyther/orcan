# Getting started

First run uses **Make only** — no manual copying of `.env.example` or config templates.

## 1. Clone

```bash
git clone <repository-url> cursor-cli-devcontainer
cd cursor-cli-devcontainer
```

## 2. Setup

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
```

`make setup`:

1. Creates `cind.config.json` from `PROJECT_DIR` if the file is missing (one workspace, one project)
2. Runs `make env` — creates `.env`, generated Compose mounts, runtime config
3. Prints workspace layout (`make config-show`) and next steps

Developing **this** cind repo (defaults `PROJECT_DIR` to the clone):

```bash
make setup
```

### Add more repos later

```bash
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
make down && make terminal-docker
```

Optional: `make config-init` copies the full multi-workspace **example** when you prefer editing a template by hand.

See [JSON config](config.md) for `mount_mode`, `windows[]`, ttyd, and resources.

## 3. Check mounts (optional)

```bash
make path-check
```

## 4. Build

```bash
make build
```

The first build downloads base images. Later builds reuse Docker layer caches.

## 5. Start the terminal

```bash
make terminal-docker
```

No variables needed — uses existing `.env` and generated files. Does **not** run `make env`.

Use `make terminal` if you do **not** need the host Docker socket.

Open `http://localhost:7681` or run `make terminal-url`.

**After editing `cind.config.json`:** run `make env`, then `make down && make terminal-docker`.

Remote host on **Tailscale**: `http://<tailscale-ip>:7681`.

In the browser: **workspace picker** → one tmux session per workspace (one window per project).

!!! warning

    ttyd has no authentication. Use only on localhost or a Tailscale tailnet.

## 6. Confirm tools

After picking a workspace in the browser:

```bash
agent --version
test -d "${HOME}/.cursor"
```

## 7. Optional: scaffold Cursor files in a project

From the host (pass the repo path explicitly):

```bash
make init-project PROJECT_DIR=/absolute/path/to/repo
```

## Next steps

* [Makefile](makefile.md) — all targets (`setup`, `config-scaffold`, …)
* [JSON config](config.md)
* [Project launcher](launcher.md)
* [Path parity](path-parity.md)
* [Security — Tailscale](security.md#remote-access-tailscale)
