# Getting started

First run uses **Make only** — no manual copying of `.env.example` or config templates.

## Ritual

| Step | Command | Notes |
| --- | --- | --- |
| Config | `make config-wizard` or `make setup` | Write/edit `orcan.config.json` |
| Apply | `make env` | Always after config changes |
| Build (once) | `make build` | Image |
| Run | `make terminal-docker` | Does **not** call `make env` |

Daily (no config change): `make terminal-docker` only.

## 1. Clone

```bash
git clone <repository-url> orcan
cd orcan
```

## 2. Setup

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
```

`make setup`:

1. Creates `orcan.config.json` from `PROJECT_DIR` if missing (one workspace, one project)
2. Runs `make env` — creates `.env`, generated Compose mounts, runtime config
3. Prints workspace layout (`make config-show`) and next steps

Or build the config interactively first:

```bash
make config-wizard
make env
```

Developing **this** orcan repo (defaults `PROJECT_DIR` to the clone):

```bash
make setup
```

### Add more repos later

```bash
make config-wizard
# or:
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
make down && make terminal-docker
```

Optional: `make config-init` copies the full multi-workspace **example** when you prefer editing a template by hand.

See [Config](config.md) for the wizard, tmux tabs, ttyd, and resources.

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

**After `make config-wizard` or any config edit:** run `make env`, then `make down && make terminal-docker`.

Remote host on **Tailscale**: `http://<tailscale-ip>:7681`.

In the browser: **workspace picker** → one **tmux session per workspace** → **zsh** panes with Starship (git branch autodetect) → tabs `tab-1` … `tab-3`.

To open another workspace without leaving tmux: `Ctrl+Space` then `w` (session list — all workspaces are started when the launcher loads). Or detach (`d`) and pick from the menu.

!!! warning

    ttyd has no authentication. Use only on localhost or a Tailscale tailnet.

## 6. Confirm tools

After picking a workspace in the browser:

```bash
agent --version
claude --version
test -d "${HOME}/.cursor"
```

Handy aliases (always in the image — see `/etc/orcan/shell/aliases.sh`):

| Alias | Meaning |
| --- | --- |
| `ll` / `la` | list files (`eza`) |
| `g` | `rg` (ripgrep) |
| `gs` / `gd` / `ga` / `gc` / `gp` / `gco` | git short aliases |
| `gl` | git log graph |
| `lg` | lazygit |
| `ff` / `g` | fd / ripgrep |
| Ctrl-R | fzf history (zsh) |
| `cc` | `claude` |
| `ccy` | `claude --dangerously-skip-permissions` (no approval prompts) |
| `ag` | `agent` |
| `agy` | `agent --yolo` (skip tool approval prompts) |
| `brief` | `orcan-session-brief` (optional workspace handoff file) |
| `ctx` | `orcan-context-status` (context pack / ignore gaps) |

## 7. Optional: scaffold Cursor/Claude files in a project

From the host (pass the repo path explicitly):

```bash
make init-project PROJECT_DIR=/absolute/path/to/repo
# or every projects[].path in orcan.config.json (do this after make env):
make init-project-all
```

Inside the container: `orcan-session-brief` / `brief`, `orcan-context-status` / `ctx`. Launcher: `s` = status, `i` = init hint.

## Next steps

* [Context orchestration](architecture/context.md) — what orcan owns vs agent models
* [Makefile](makefile.md) — all targets (`setup`, `config-wizard`, `config-scaffold`, …)
* [Config](config.md) — JSON profile + wizard
* [Project launcher](launcher.md)
* [Path parity](path-parity.md)
* [Security — Tailscale](security.md#remote-access-tailscale)
