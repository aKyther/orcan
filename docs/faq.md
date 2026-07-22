# FAQ

## Why Docker?

So the toolchain is repeatable and does not depend on whatever is installed on each host.

## Why not install Cursor CLI only on the host?

You can. This repository adds isolation, shared caches, and a full toolbox around Cursor CLI.

## Who should use this?

Developers who want Cursor CLI plus Node, Python, Go, Rust, and optional Docker access in one place.

## Can I use multiple projects?

Yes. List them under `workspaces[].projects` in `cind.config.json`, then:

```bash
make env
make down && make terminal-docker
```

Each workspace is one tmux session with only its listed projects. To switch focus between host repos without editing config, add both paths to the same workspace (or separate workspaces and use `Ctrl+Space w`). See [Config](config.md) and [Path parity](path-parity.md).

Do **not** pass `PROJECT_DIR=` on `make terminal` — that only affects scaffolding/`make setup`. Runtime mounts come from generated compose after `make env`.

## Can I disable TMUX?

TMUX starts only for interactive TTY shells. Non-interactive commands skip it.

To disable it permanently, remove the TMUX block from
`docker/rootfs/etc/skel/.bashrc.d/50-cind-shell.sh` and rebuild.

## Can I use Docker inside the container?

Yes:

```bash
make terminal-docker
```

!!! warning

    This mounts the host Docker socket and is powerful.

## How do I access the container terminal?

Both `make terminal` and `make terminal-docker` start ttyd — a browser-based terminal on port `7681`:

```bash
make terminal
```

Open `http://localhost:7681` (or run `make terminal` to print the URL).

On a VPS behind Tailscale, use `http://<tailscale-ip>:7681`. ttyd has no authentication — use only on localhost or a private network. See [Docker](docker.md) and [Security](security.md).

## Why do new files belong to my user?

`USER_UID` and `USER_GID` are copied from the host into the image user. That keeps ownership aligned on the bind mount.

## Where is Cursor login stored?

Login tokens live on the host at `$CIND_DATA/cursor-app` → `/home/developer/.config/cursor/auth.json` (default `~/.config/cind/cursor-app`).

CLI settings, chats, and rules live in `$CIND_DATA/cursor` → `/home/developer/.cursor`.

Both survive `make down`. Only `make clean-data` deletes them.

## Does `make down` delete caches?

No. Use `make clean-data` for that (removes `$CIND_DATA`, default `~/.config/cind`).

## Is the container a full security boundary?

No. Bind mounts and Docker socket mode reduce isolation. See [Security](security.md).

## Can I publish the docs site?

Yes. The `docs/` tree and `mkdocs.yml` are ready for MkDocs Material:

```bash
pip install mkdocs-material
mkdocs build
```
