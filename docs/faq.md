# FAQ

## Why Docker?

So the toolchain is repeatable and does not depend on whatever is installed on each host.

## Why not install Cursor CLI only on the host?

You can. This repository adds isolation, shared caches, and a full toolbox around Cursor CLI.

## Who should use this?

Developers who want Cursor CLI plus Node, Python, Go, Rust, and optional Docker access in one place.

## Can I use multiple projects?

Yes. Start a new session with another `PROJECT_DIR`:

```bash
make shell PROJECT_DIR=$HOME/projects/app-a
make shell PROJECT_DIR=$HOME/projects/app-b
```

Each command mounts one project at `/workspace`.

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

## Why do new files belong to my user?

`USER_UID` and `USER_GID` are copied from the host into the image user. That keeps ownership aligned on the bind mount.

## Where is Cursor login stored?

In the `cursor-config` named volume at `/home/developer/.cursor`.

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
