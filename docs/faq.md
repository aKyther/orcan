# FAQ

## Why Docker?

So the toolchain is repeatable and does not depend on whatever is installed on each host.

## Why not install Cursor CLI only on the host?

You can. This repository adds isolation, shared caches, and a full toolbox around Cursor CLI.

## Who should use this?

Developers who want Cursor CLI plus Node, Python, Go, Rust, and optional Docker access in one place.

## Can I use multiple projects?

Yes. Stop the current container (`make down`) and start again with another `PROJECT_DIR`:

```bash
make down
make shell PROJECT_DIR=$HOME/projects/app-a
make down
make shell PROJECT_DIR=$HOME/projects/app-b
```

Each command mounts one project at the same absolute path on host and container (`PROJECT_DIR`). See [Path parity](path-parity.md).

## Can I disable TMUX?

TMUX starts only for interactive TTY shells. Non-interactive commands skip it.

To disable it permanently, remove the TMUX block from
`docker/rootfs/etc/skel/.bashrc.d/50-cursor-dev.sh` and rebuild.

## Can I use Docker inside the container?

Yes:

```bash
make shell-docker
```

!!! warning

    This mounts the host Docker socket and is powerful.

## How do I access the container terminal?

Both `make shell` and `make shell-docker` start ttyd — a browser-based terminal on port `7681`:

```bash
make shell
```

Open `http://localhost:7681` (or run `make terminal` to print the URL).

On a VPS behind Tailscale, use `http://<tailscale-ip>:7681`. ttyd has no authentication — use only on localhost or a private network. See [Docker](docker.md) and [Security](security.md).

## Why do new files belong to my user?

`USER_UID` and `USER_GID` are copied from the host into the image user. That keeps ownership aligned on the bind mount.

## Where is Cursor login stored?

Login tokens live in the `cursor-app-config` volume at `/home/developer/.config/cursor/auth.json`.

CLI settings, chats, and rules live in the `cursor-config` volume at `/home/developer/.cursor`.

Both survive `make down`. Only `make clean-volumes` deletes them.

## Does `make down` delete caches?

No. Use `make clean-volumes` for that.

## Is the container a full security boundary?

No. Bind mounts and Docker socket mode reduce isolation. See [Security](security.md).

## Can I publish the docs site?

Yes. The `docs/` tree and `mkdocs.yml` are ready for MkDocs Material:

```bash
pip install mkdocs-material
mkdocs build
```
