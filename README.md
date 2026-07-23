# orcan

**Context orchestrator** for coding agents: workspaces, path-parity mounts, ignore/instruction seeds, and a browser tmux launcher. **Cursor CLI** (`agent`) and **Claude Code** (`claude`) run as tools inside that environment. **Models are out of scope** for orcan — each CLI chooses its own.

This repository keeps your host system clean. Tools run inside a container. Projects use [path parity](docs/path-parity.md). Workspaces are declared in `orcan.config.json` (one tmux session per workspace).

**Who it is for:** developers who want a shared agent environment (Node, Python, Go, Rust, optional Docker) without installing the full toolchain on the host — and without managing models in orcan config.

**Problem it solves:** mixed global toolchains, root-owned files from containers, and unclear boundaries between agent work and the host OS. See [Context orchestration](docs/architecture/context.md).

---

## Features

* Cursor CLI (`agent`) — **full** image variant
* Claude Code CLI (`claude`) — **full** and **claude-only** variants
* Two image tags: `orcan:latest` (Claude+Cursor), `orcan:claude` (Claude only)
* Docker-based environment on Debian Bookworm Slim
* Multi-stage image build
* Multi-workspace launcher → one **tmux session per workspace** (browser ttyd + **zsh**)
* Workspace **context pack** (manifest, AGENTS/CLAUDE, ignores) — see [docs/architecture/context.md](docs/architecture/context.md)
* Starship prompt, fzf, delta, lazygit (image defaults)
* Node.js, npm, pnpm; Python 3 + **uv**; Go; Rust
* Docker CLI, Compose, Buildx (optional host socket)
* Git, ripgrep, fd, fzf, bat, eza, jq, yq, tree, curl, shellcheck, hyperfine
* PostgreSQL client, Redis client
* Persistent host data under `~/.config/orcan` (`ORCAN_DATA` binds — not named volumes)
* Global Cursor defaults seeded at container startup
* `cursor-init-project` / `make init-project-all` for optional per-repo scaffolding
* `orcan-session-brief` for optional agent/claude handoff
* Makefile entrypoints for everyday use

---

## Repository structure

| Path | Why it exists |
| --- | --- |
| `Dockerfile` | Builds the toolchain and installs Cursor CLI |
| `docker-compose.yml` | Base service: path-parity mounts + `$ORCAN_DATA` binds, no Docker socket |
| `docker-compose.docker.yml` | Optional overlay: host Docker socket + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | Browser terminal (ttyd) for local / Tailscale access |
| `orcan.config.json` | Workspaces and projects (JSON only; run `make env` after edits) |
| `AGENTS.md` | Orientation for coding agents working on this repo |
| `Makefile` | Short host commands for build, shell, cleanup |
| `docker/rootfs/` | Files installed into the image (paths match the container) |
| `scripts/repository/` | Host-only maintenance helpers |
| `tests/smoke/` | Container smoke tests |
| `.env.example` | Safe template for UID/GID and `PROJECT_DIR` |
| `.dockerignore` | Keeps the build context small and free of secrets |
| `.cursorignore` | Limits what Cursor agents can read **in this repo** |
| `.cursorindexingignore` | Keeps large/noise files out of the index |
| `.cursor/rules/` | Cursor rules **for developing this repository** |
| `docs/` | Full MkDocs Material documentation |
| `mkdocs.yml` | Docs site configuration |
| `LICENSE` | MIT license |

### Repository files vs container files

| Kind | Location | Audience |
| --- | --- | --- |
| Repository control | root (`Dockerfile`, Compose, `Makefile`, docs) | Humans and host tooling |
| Image filesystem | `docker/rootfs/` | Copied into the container image |
| Host helpers | `scripts/repository/` | Run on the host only |
| Repo Cursor config | `.cursor/rules/`, ignore files | Agents working on **this** repo |
| Image Cursor defaults | `docker/rootfs/opt/cursor-defaults/` | Seeded into `${HOME}/.cursor` at startup |
| Project templates | `…/opt/cursor-defaults/templates/` | Applied only by `cursor-init-project` |

| Repository path | Container path | Purpose |
| --- | --- | --- |
| `docker/rootfs/opt/cursor-defaults` | `/opt/cursor-defaults` | Image-provided Cursor defaults |
| `docker/rootfs/usr/local/bin/docker-entrypoint` | `/usr/local/bin/docker-entrypoint` | Container startup |
| `docker/rootfs/usr/local/bin/init-cursor-home` | `/usr/local/bin/init-cursor-home` | User config initialization |
| `docker/rootfs/usr/local/bin/cursor-init-project` | `/usr/local/bin/cursor-init-project` | Project template initialization |
| `docker/rootfs/usr/local/bin/cursor-ttyd` | `/usr/local/bin/cursor-ttyd` | Browser terminal (ttyd + tmux) |
| `docker/rootfs/usr/local/bin/orcan-ai-statusline` | `/usr/local/bin/orcan-ai-statusline` | Claude/Cursor statusLine → tmux usage cache |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` | TMUX config |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` | Vim config |
| `docker/rootfs/etc/skel/.zshrc` + `.zshrc.d/` | `/home/developer/.zshrc*` | Default shell (zsh + plugins + Starship) |
| `docker/rootfs/etc/skel/.bashrc.d/` | `/home/developer/.bashrc.d/` | Bash fallback |
| `docker/rootfs/opt/orcan/` | seeded gitconfig + starship | Missing-only into `$HOME` |

---

## How it works

```text
Host
└── your project (PROJECT_DIR=/home/user/projects/my-app)
     │
     ▼
Docker container
├── /home/user/projects/my-app   ← same path (path parity)
├── /opt/cursor-defaults         ← immutable image defaults
├── /home/developer/.cursor      ← $ORCAN_DATA/cursor (seeded at startup)
├── Cursor CLI
├── Node / pnpm
├── Python / uv
├── Go / Rust
└── Docker CLI (optional socket)
```

* **Docker** isolates tools from the host package manager.
* **Context orchestration** — workspaces, context pack, ignores; CLIs are plugs; models out of scope ([docs](docs/architecture/context.md)).
* **`orcan.config.json` workspaces** isolate project sets (no cross-workspace mixing).
* **UID/GID mapping** makes new files owned by your host user.
* **`$ORCAN_DATA` host binds** keep npm/pnpm/cargo/go/uv caches and Cursor/Claude login between runs.
* **`/opt/cursor-defaults`** seeds `${HOME}/.cursor` at startup (missing files only).
* **tmux** via the browser launcher; switch sessions with `Ctrl+Space w`.
* **Docker socket** is optional because it grants strong host access.
* **Non-root user** reduces accidental root-owned files inside the container.

---

## Quick start

Everything goes through **Make** — no manual `cp` of `.env` or config templates (`make env` creates `.env` when missing).

### Ritual (config → env → terminal)

| Step | Command | When |
| --- | --- | --- |
| 1. Config | `make config-wizard` or `make setup` / `config-scaffold` | Create or edit workspaces |
| 2. Apply | `make env` | Always after config changes |
| 3. Seed (optional) | `make init-project-all` | After new projects |
| 4. Run | `make terminal-docker` | Start browser terminal |

`make terminal` / `make terminal-docker` **do not** run `make env`. After any config change: `make env`, then `make down && make terminal-docker` if a container is already running.

**Daily (no config change):** `make terminal-docker` only.

### First run

```bash
git clone <repository-url> orcan
cd orcan

make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Or interactive config (poetry/uv-style), then apply and start:

```bash
make config-wizard
make env
make build
make terminal-docker
```

Open `http://localhost:7681` (or `http://<tailscale-ip>:7681` on a remote host in your tailnet). Pick a workspace → tmux session.

`make setup`:

* creates `orcan.config.json` from `PROJECT_DIR` if missing (one workspace, one project)
* runs `make env` (`.env`, mounts, runtime config)
* prints `make config-show` output and next steps

### More repos or workspaces

```bash
make config-wizard
# or non-interactive:
make config-scaffold PROJECT_DIR=/home/you/gotibooks/backend WORKSPACE=gotibooks
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
make down && make terminal-docker
```

Optional: `make config-init` copies the full example from `orcan.config.example.json` to edit by hand.

Example shape (usually from wizard / `setup` / `config-scaffold`):

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        { "name": "backend", "path": "/home/you/gotibooks/backend" },
        { "name": "frontend", "path": "/home/you/gotibooks/frontend" }
      ]
    }
  ]
}
```

Docs: [config](docs/config.md) · [Makefile](docs/makefile.md) · [workspace architecture](docs/architecture/workspace.md)

### Developing this repository (orcan)

`PROJECT_DIR` defaults to the clone directory:

```bash
make setup
make build
make terminal-docker
```

> `make env` / `make setup` write `USER_UID`, `USER_GID`, `DOCKER_GID`, and generated mounts automatically.

In the browser terminal:

```bash
agent --version
claude --version
```

---

## Publish image to GitLab (build once, run anywhere)

Typical flow: build on a machine with good network/CPU, push to **GitLab Container Registry**, pull on a VPS — without rebuilding from Dockerfile each time.

```text
Laptop / CI                          GitLab registry                    VPS
─────────────────                    ───────────────                    ───
make build  →  orcan:latest
make publish ─────────────────────►  registry…/group/orcan:latest
                                                                    make pull
                                                                    → orcan:latest
                                                                    make terminal-docker
```

### Pieces involved

| Piece | Role |
| --- | --- |
| Local image `orcan:latest` | What Compose runs (`docker-compose.yml` → `image: orcan:latest`, service `orcan`) |
| `IMAGE_REGISTRY` | Registry host — `registry.gitlab.com` or your self-hosted GitLab |
| `IMAGE_REPOSITORY` | Path under the registry, e.g. `mygroup/orcan` |
| `IMAGE_TAG` | Tag (default `latest`) |
| `make registry-login` | `docker login` with GitLab username + PAT / Deploy Token |
| `make publish` | Tags local image → pushes to registry |
| `make pull` | Pulls remote image and retags as `orcan:latest` for Compose |
| `make registry-show` | Prints configured local/remote names (sanity check) |

Remote image name:

```text
${IMAGE_REGISTRY}/${IMAGE_REPOSITORY}:${IMAGE_TAG}
# e.g. registry.gitlab.com/mygroup/orcan:latest
```

### 1. Configure `.env` (once per machine)

```dotenv
IMAGE_REGISTRY=registry.gitlab.com
IMAGE_REPOSITORY=mygroup/orcan
IMAGE_TAG=latest
```

Self-hosted GitLab: set `IMAGE_REGISTRY` to your registry hostname (often `registry.example.com`).

Do **not** put tokens in `.env` or git. Use a Personal Access Token or Deploy Token with `read_registry` + `write_registry`.

### 2. Log in

```bash
make registry-login
# prompts: GitLab username + token
```

Non-interactive:

```bash
REGISTRY_USER=myuser REGISTRY_PASSWORD=glpat-... make registry-login
```

### 3. Build and push (build machine)

```bash
make build          # or make rebuild
make registry-show  # optional check
make publish
```

### 4. Pull and run (VPS)

Same clone of this repo + same `IMAGE_*` in `.env`, plus your `orcan.config.json` / `make env` for mounts:

```bash
make registry-login
make pull
make env            # if config / mounts not ready yet
make terminal-docker
```

`make pull` only updates the **image**. Workspace mounts and `.env` still come from `make env` / `orcan.config.json` on that host.

### When to rebuild vs pull

| Change | On build machine | On VPS |
| --- | --- | --- |
| Dockerfile / `docker/rootfs/` (tmux, tools, …) | `make rebuild` → `make publish` | `make pull` |
| `orcan.config.json` (workspaces, paths) | — | `make env` → restart terminal |
| Only `.env` limits (`CPUS`, ports) | — | edit `.env` → restart terminal |

More detail: [docs/makefile.md](docs/makefile.md#publish-image-to-gitlab) · [docs/docker.md](docs/docker.md#publish-to-gitlab-container-registry).

---

## Available Make commands

| Command | Description |
| --- | --- |
| `make help` | List targets |
| `make setup` | First run: scaffold config if missing, then `make env` |
| `make config-wizard` | Interactive create/edit `orcan.config.json` |
| `make config-scaffold` | Non-interactive add project from `PROJECT_DIR` |
| `make config-show` | Print config + runtime manifest |
| `make env` | Apply config → `.env`, mounts, runtime (run after wizard/edits) |
| `make build` | Build **full** image (Claude + Cursor) → `orcan:latest` |
| `make build-claude` | Build **Claude-only** image → `orcan:claude` |
| `make rebuild` | Rebuild full image with `--no-cache` |
| `make rebuild-claude` | Rebuild Claude-only image with `--no-cache` |
| `make registry-login` | Log in to GitLab Container Registry |
| `make publish` | Tag + push image to registry |
| `make pull` | Pull published image → `orcan:latest` |
| `make terminal` | Start browser terminal (no Docker socket; does not run `make env`) |
| `make terminal-docker` | Start browser terminal + Docker socket (does not run `make env`) |
| `make terminal-url` | Print the browser terminal URL |
| `make down` | Stop containers; keep host data (`ORCAN_DATA`) |
| `make logs` | Follow logs |
| `make clean` | Stop containers; keep host data |
| `make clean-data` | Delete `$ORCAN_DATA` (`~/.config/orcan`) — login + caches |
| `make clean-volumes` | Alias for `clean-data` |
| `make path-check` | Show host/container project path parity |
| `make config` | Validate and print Compose configs |
| `make init-project` | Create missing Cursor files in `PROJECT_DIR` |
| `make init-project-dry-run` | Show project Cursor files without writing |
| `make validate` | Check layout, script syntax, Compose config |
| `make test` | Build (if needed) and run smoke tests |
| `make test-path-parity` | Integration test for path parity + Docker socket |
| `make docs` | Build MkDocs site |
| `make docs-serve` | Serve MkDocs locally |

### Configure vs run

| When | Command |
| --- | --- |
| Create / edit config | `make config-wizard` (or `make setup` / `config-scaffold`) |
| Apply config | `make env` |
| Start terminal | `make terminal` or `make terminal-docker` |
| After config change (container already up) | `make env` → `make down && make terminal-docker` |
| Push image to GitLab | `make build` → `make registry-login` → `make publish` |
| Pull image on VPS | `make registry-login` → `make pull` → `make terminal-docker` |

`make terminal*` reads `.env` as-is — it does not overwrite `CPUS`, mounts, or runtime files.

### Choose a project

Preferred: edit via wizard or `orcan.config.json`, then apply:

```bash
make config-wizard   # or edit orcan.config.json by hand
make env
make path-check
make down && make terminal-docker
```

Single project without a config file yet (first `make env` only):

```bash
make env PROJECT_DIR=$HOME/projects/my-app
make path-check
make terminal
```

Then open `http://localhost:7681` (or `make terminal-url`).

Each `projects[]` entry is mounted with path parity (same absolute path on host and in the container). See [docs/path-parity.md](docs/path-parity.md).

---

## Cursor defaults in the container

```text
Image defaults          →  /opt/cursor-defaults
User Cursor home        →  /home/developer/.cursor  (volume)
Project Cursor files    →  ${PROJECT_DIR}/.cursor, AGENTS.md
```

On every container start, missing files are copied from `/opt/cursor-defaults` into `${HOME}/.cursor`.
Existing files are never overwritten.

**Global profile:** always-on rules and reusable skills under `/opt/cursor-defaults` (seeded into `~/.cursor`). Project-specific rules live in the mounted repo. Details: [docs/cursor.md](docs/cursor.md#global-profile-rules-and-skills).

Scaffold a mounted project explicitly (from the browser terminal):

```bash
cursor-init-project --dry-run
cursor-init-project
```

Or:

```bash
make init-project-dry-run
make init-project
```

Review generated files before committing them.

Reset global container Cursor config by deleting host data:

```bash
make clean-data
```

> Warning: that also deletes language caches and bash history under `$ORCAN_DATA`.

Details: [docs/cursor.md](docs/cursor.md).

---

## UID, GID, and permissions

| Variable | Meaning |
| --- | --- |
| `USER_UID` | Host user ID; used as the container user ID |
| `USER_GID` | Host group ID; used as the container group ID |
| `DOCKER_GID` | Group ID of `/var/run/docker.sock` on the host |

These values are taken from the host so files created in `PROJECT_DIR` stay owned by you, not by root.

---

## Docker socket

> **Warning:** Mounting `/var/run/docker.sock` lets the container control the host Docker Engine.
> That is strong access to the host. Use it only when you need Docker-from-Docker workflows.

| Mode | Command | Socket |
| --- | --- | --- |
| Default | `make terminal` | No |
| Docker-enabled | `make terminal-docker` | Yes |

The overlay file is `docker-compose.docker.yml`. Both modes include the browser terminal via `docker-compose.ttyd.yml`.

---

## Browser terminal

`make terminal` and `make terminal-docker` start the container with **ttyd** — a web-based terminal on port `7681`.

```bash
make build
make terminal-docker
```

Projects come from `orcan.config.json` (not `PROJECT_DIR=` on the Make line). After config edits: `make env`, then recreate the container.

Open in your browser:

```text
http://localhost:7681
```

| Field | Default |
| --- | --- |
| URL | `http://localhost:7681` |
| Host port | `7681` (`TTYD_HOST_PORT`) |
| Shell | **zsh** + Starship (git autodectect); plugins baked in |
| Theme | `TTYD_THEME=dark` (from config / `.env`, no startup chooser) |
| Projects | Listed from `orcan.config.json` (workspace launcher) |
| TMUX | One session per workspace (`Ctrl+Space w` to switch) |

**Remote access:** there is no SSH into this environment. Use the browser terminal only.

On a machine reachable via **Tailscale**, open:

```text
http://<tailscale-ip>:7681
```

Locally:

```text
http://localhost:7681
```

> **Warning:** ttyd has **no authentication**. Use only on **localhost** or a **private network (Tailscale)**.
> Do not expose port `7681` to the public Internet without auth and TLS.

Stack: `docker-compose.ttyd.yml` runs `cursor-ttyd` → workspace picker → tmux.
Details: [docs/docker.md](docs/docker.md) and [docs/security.md](docs/security.md).

---

## Isolation and limits

**Isolated (best effort):**

* Host package installs stay untouched
* Toolchain lives in the image
* Caches live under `$ORCAN_DATA` on the host (`~/.config/orcan`)

**Not fully isolated:**

* The mounted project is writable on the host
* Docker socket mode can manage host containers and images
* `sudo` inside the container is root **in the container**
* Git identity is **not** shared with the host — configure inside the container if needed

> **Warning:** Do not mount your whole home directory or the host root filesystem.

---

## TMUX and Vim

Shell and editor configs live in the image filesystem:

* `docker/rootfs/etc/skel/.tmux.conf` → `/home/developer/.tmux.conf`
* `docker/rootfs/etc/skel/.vimrc` → `/home/developer/.vimrc`
* `docker/rootfs/etc/skel/.bashrc.d/50-orcan-shell.sh` → sourced from `~/.bashrc`

The browser launcher attaches you to a tmux session named after the workspace (`workspaces[].name`). Tabs are `tab-1`… (not other workspaces).

| Action | Keys |
| --- | --- |
| Prefix | `Ctrl-Space` |
| Switch workspace session | `Ctrl-Space` `w` |
| New window | `Alt-c` |
| Split horizontal | `Ctrl-Down` |
| Split vertical | `Ctrl-Right` |
| Zoom pane | `Alt-Enter` |
| Detach | `Ctrl-Space` `d` |

---

## Update the image

```bash
make rebuild
```

To also delete caches and Cursor/Claude login under `$ORCAN_DATA`:

```bash
make clean-data
make rebuild
```

---

## Troubleshooting

| Problem | What to try |
| --- | --- |
| Permission errors in `PROJECT_DIR` | Run `make env` so UID/GID match the host |
| `docker.sock` permission denied | Use `make terminal-docker` after `make env` (sets `DOCKER_GID`) |
| No TTY / odd terminal | Run from a real terminal; ensure `stdin_open`/`tty` stay enabled |
| TMUX did not start | Non-interactive commands skip TMUX; check `[ -t 0 ]` |
| Stale image | `make rebuild` |
| Cursor CLI not logged in | Log in once inside the container; auth persists under `$ORCAN_DATA` (`~/.config/orcan`) |

More detail: [docs/troubleshooting.md](docs/troubleshooting.md).

---

## Security

* Prefer `make terminal` unless you need Docker-from-Docker
* Keep secrets out of the image and out of git
* Do not commit `.env`
* Do not mount sensitive host paths
* Treat Docker socket mode as privileged
* Review `.cursorignore` when you add new secret locations

Full notes: [docs/security.md](docs/security.md).

---

## FAQ

**Why Docker?**  
So the toolchain is repeatable and does not pollute the host.

**Why not install Cursor only on the host?**  
You can. This repo adds a full isolated toolbox and clearer project boundaries.

**Can I switch projects?**  
Yes. Start a new session with another `PROJECT_DIR` (run `make down` first if a container is already running).

**Can I disable TMUX?**  
Yes. Start a non-interactive command, or remove the TMUX block from
`docker/rootfs/etc/skel/.bashrc.d/50-orcan-shell.sh` and rebuild.

**Can I use Docker inside the container?**  
Yes, with `make terminal-docker` when the host socket is available.

**Why do files belong to my user?**  
Because `USER_UID` / `USER_GID` match your host account.

More questions: [docs/faq.md](docs/faq.md).

---

## Documentation

Full docs live in `docs/` and are built with MkDocs Material.
For contributors and agents, see [docs/development.md](docs/development.md).

```bash
pip install mkdocs-material
mkdocs serve
```

---

## License

MIT. See [LICENSE](LICENSE).
