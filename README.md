# Cursor CLI Dev Container

Isolated Docker environment for **Cursor CLI** and common developer tools.

This repository keeps your host system clean. Cursor and the toolchain run inside a container. Only the project you choose is mounted at `/workspace`.

**Who it is for:** developers who want Cursor CLI with Node, Python, Go, Rust, and optional Docker access — without installing the full toolchain on the host.

**Problem it solves:** mixed global toolchains, root-owned files from containers, and unclear boundaries between agent work and the host OS.

---

## Features

* Cursor CLI (`agent`)
* Docker-based environment on Debian Bookworm Slim
* Multi-stage image build
* Automatic TMUX in interactive shells
* Node.js, npm, pnpm
* Python 3, uv
* Go, Rust (rustc, cargo)
* Docker CLI, Compose, Buildx (optional host socket)
* Git, ripgrep, fd, fzf, bat, eza, jq, shellcheck, hyperfine
* PostgreSQL client, Redis client
* Persistent named volumes for caches and Cursor config
* Global Cursor defaults seeded at container startup
* `cursor-init-project` for optional project scaffolding
* Makefile entrypoints for everyday use

---

## Repository structure

| Path | Why it exists |
| --- | --- |
| `Dockerfile` | Builds the toolchain and installs Cursor CLI |
| `docker-compose.yml` | Base service: project mount, caches, no Docker socket |
| `docker-compose.docker.yml` | Optional overlay: host Docker socket + `DOCKER_GID` |
| `docker-compose.ssh.yml` | Optional overlay: OpenSSH for VPS / Tailscale access |
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
| `docker/rootfs/usr/local/bin/cursor-sshd` | `/usr/local/bin/cursor-sshd` | Foreground OpenSSH for VPS overlay |
| `docker/rootfs/etc/ssh/sshd_config.d/cursor.conf` | `/etc/ssh/sshd_config.d/cursor.conf` | SSH daemon settings |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` | TMUX config |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` | Vim config |
| `docker/rootfs/etc/skel/.bashrc.d/` | `/home/developer/.bashrc.d/` | Aliases, PATH, interactive TMUX |

---

## How it works

```text
Host
└── your project (PROJECT_DIR)
     │
     ▼
Docker container
├── /workspace                 ← bind mount of your project
├── /opt/cursor-defaults       ← immutable image defaults
├── /home/developer/.cursor    ← named volume (seeded at startup)
├── Cursor CLI
├── Node / pnpm
├── Python / uv
├── Go / Rust
└── Docker CLI (optional socket)
```

* **Docker** isolates tools from the host package manager.
* **One project mount** limits the agent to the work you choose.
* **UID/GID mapping** makes new files owned by your host user.
* **Named volumes** keep npm/pnpm/cargo/go/uv caches between runs.
* **`/opt/cursor-defaults`** survives the empty `cursor-config` volume mount.
* **Startup init** copies only missing Cursor files into `${HOME}/.cursor`.
* **TMUX** starts automatically so long agent sessions survive disconnects.
* **Docker socket** is optional because it grants strong host access.
* **Non-root user** reduces accidental root-owned files inside the container.

---

## Quick start

```bash
git clone <repository-url> cursor-cli-devcontainer
cd cursor-cli-devcontainer
cp .env.example .env
make env
make build
make shell PROJECT_DIR=$HOME/projects/my-app
ssh developer@localhost
```

> Tip: `make env` writes your host `USER_UID`, `USER_GID`, and `DOCKER_GID` into `.env`.
> Default SSH password is `cursor` (`DEVELOPER_PASSWORD` in `.env`).

After SSH, TMUX starts for interactive terminals. Use Cursor CLI as usual, for example:

```bash
agent --version
```

---

## Available Make commands

| Command | Description |
| --- | --- |
| `make help` | List targets |
| `make env` | Create/update `.env` from the host |
| `make build` | Build the image |
| `make rebuild` | Rebuild with `--no-cache` |
| `make shell` | Start container with **SSH** (no Docker socket) |
| `make shell-docker` | Start container with **SSH** and Docker socket |
| `make down` | Stop containers; keep named volumes |
| `make logs` | Follow logs |
| `make clean` | Stop containers; keep named volumes |
| `make clean-volumes` | Stop containers and **delete** named volumes |
| `make config` | Validate and print Compose configs |
| `make init-project` | Create missing Cursor files in mounted `/workspace` |
| `make init-project-dry-run` | Show project Cursor files without writing |
| `make validate` | Check layout, script syntax, Compose config |
| `make test` | Build (if needed) and run smoke tests |
| `make docs` | Build MkDocs site |
| `make docs-serve` | Serve MkDocs locally |

### Choose a project

```bash
make shell PROJECT_DIR=$HOME/projects/my-app
ssh developer@localhost
```

`PROJECT_DIR` must be an absolute path on the host. It is mounted at `/workspace`.

---

## Cursor defaults in the container

```text
Image defaults          →  /opt/cursor-defaults
User Cursor home        →  /home/developer/.cursor  (volume)
Project Cursor files    →  /workspace/.cursor, AGENTS.md
```

On every container start, missing files are copied from `/opt/cursor-defaults` into `${HOME}/.cursor`.
Existing files are never overwritten.

**Global profile:** five always-on rules and five reusable skills shape every session (understanding repos, focused changes, honest validation, minimal docs). Project-specific rules live only in the mounted repo. Details: [docs/cursor.md](docs/cursor.md#global-profile-rules-and-skills).

Scaffold a mounted project explicitly (after SSH):

```bash
make shell
ssh developer@localhost
cursor-init-project --dry-run
cursor-init-project
```

Or:

```bash
make init-project-dry-run
make init-project
```

Review generated files before committing them.

Reset global container Cursor config by deleting the volume:

```bash
make clean-volumes
```

> Warning: that also deletes language caches and bash history volumes.

Details: [docs/cursor.md](docs/cursor.md).

---

## UID, GID, and permissions

| Variable | Meaning |
| --- | --- |
| `USER_UID` | Host user ID; used as the container user ID |
| `USER_GID` | Host group ID; used as the container group ID |
| `DOCKER_GID` | Group ID of `/var/run/docker.sock` on the host |

These values are taken from the host so files created in `/workspace` stay owned by you, not by root.

---

## Docker socket

> **Warning:** Mounting `/var/run/docker.sock` lets the container control the host Docker Engine.
> That is strong access to the host. Use it only when you need Docker-from-Docker workflows.

| Mode | Command | Socket |
| --- | --- | --- |
| Default | `make shell` | No |
| Docker-enabled | `make shell-docker` | Yes |

The overlay file is `docker-compose.docker.yml`. Both modes include OpenSSH via `docker-compose.ssh.yml`.

---

## SSH access

`make shell` and `make shell-docker` start the container with OpenSSH in the background.

```bash
make build
make shell PROJECT_DIR=/absolute/path/to/project
ssh developer@localhost
```

| Field | Default |
| --- | --- |
| User | `developer` |
| Password | `cursor` (`DEVELOPER_PASSWORD` in `.env`) |
| Host port | `22` (`SSH_HOST_PORT`) |

On a VPS behind Tailscale, use the machine's Tailscale IP instead of `localhost`.

```bash
ssh developer@<tailscale-ip>
```

> **Warning:** The default password is weak. Use it only on a Tailscale (or similarly private) network.
> If the host already runs `sshd` on port 22, set `SSH_HOST_PORT` to a free port or stop the host daemon.

The overlay file is `docker-compose.ssh.yml`. It does not mount host `~/.ssh` or `~/.gitconfig`.
Details: [docs/docker.md](docs/docker.md) and [docs/security.md](docs/security.md).

---

## Isolation and limits

**Isolated (best effort):**

* Host package installs stay untouched
* Toolchain lives in the image
* Caches live in named volumes

**Not fully isolated:**

* The mounted project is writable on the host
* Docker socket mode can manage host containers and images
* `sudo` inside the container is root **in the container**
* Read-only mounts of `~/.gitconfig` and `~/.ssh` share host identity with the container

> **Warning:** Do not mount your whole home directory or the host root filesystem.

---

## TMUX and Vim

Shell and editor configs live in the image filesystem:

* `docker/rootfs/etc/skel/.tmux.conf` → `/home/developer/.tmux.conf`
* `docker/rootfs/etc/skel/.vimrc` → `/home/developer/.vimrc`
* `docker/rootfs/etc/skel/.bashrc.d/50-cursor-dev.sh` → sourced from `~/.bashrc`

TMUX starts automatically in interactive sessions (`exec tmux new-session -A -s cursor`).

| Action | Keys |
| --- | --- |
| Prefix | `Ctrl-Space` |
| New window | `Alt-c` |
| Split horizontal | `Ctrl-Down` |
| Split vertical | `Ctrl-Right` |
| Zoom pane | `Alt-Enter` |
| Detach | `Ctrl-Space` `d` |
| Reattach | `tmux attach -t cursor` |

---

## Update the image

```bash
make rebuild
```

To also delete caches and Cursor config volumes:

```bash
make clean-volumes
make rebuild
```

---

## Troubleshooting

| Problem | What to try |
| --- | --- |
| Permission errors in `/workspace` | Run `make env` so UID/GID match the host |
| `docker.sock` permission denied | Use `make shell-docker` after `make env` (sets `DOCKER_GID`) |
| No TTY / odd terminal | Run from a real terminal; ensure `stdin_open`/`tty` stay enabled |
| TMUX did not start | Non-interactive commands skip TMUX; check `[ -t 0 ]` |
| Stale image | `make rebuild` |
| Cursor CLI not logged in | Log in once inside the container; auth persists in `cursor-app-config` (`~/.config/cursor`) |

More detail: [docs/troubleshooting.md](docs/troubleshooting.md).

---

## Security

* Prefer `make shell` unless you need Docker-from-Docker
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
`docker/rootfs/etc/skel/.bashrc.d/50-cursor-dev.sh` and rebuild.

**Can I use Docker inside the container?**  
Yes, with `make shell-docker` when the host socket is available.

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
