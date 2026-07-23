# Common workflows

All commands below run on the **host** unless marked **(container)**.

## Daily start

```bash
cd /absolute/path/to/orcan
make terminal-docker
```

Open `http://localhost:7681`. This does **not** run `make env`.

!!! note
    After every `orcan.config.json` edit: `make env`, then `make down && make terminal-docker` (optionally `make init-project-all` first).

## Change workspaces or ports

```bash
make config-wizard    # or edit orcan.config.json
make env
make init-project-all
make down
make terminal-docker
```

## Run without host Docker socket

Safer, but no Docker-from-Docker:

```bash
make terminal
```

## Claude-only image

```bash
make build-claude
IMAGE_LOCAL=orcan:claude make terminal-docker
```

## Rebuild after Dockerfile or rootfs changes

```bash
make rebuild          # full
# or
make rebuild-claude
make down
make terminal-docker
```

## Check path parity

```bash
make path-check
```

## Inside the container

| Action | Command |
| --- | --- |
| List workspaces | `orcan-workspaces` |
| Context pack status | `orcan-context-status` |
| Seed all projects | `orcan-init-projects` |
| Create session brief | `orcan-session-brief` |
| AI status line helper | `orcan-ai-statusline` |
| Cursor CLI | `agent` / alias `ag` |
| Claude Code | `claude` / alias `cc` |

Launcher keys (browser menu): workspace number, `s` = status, `i` = init hint, `q` = quit.

## Stop and clean

```bash
make down                 # stop containers; keep ~/.config/orcan
make clean                # same idea as down for compose stacks
make clean-data           # DESTRUCTIVE: deletes ORCAN_DATA (logins, caches, shell history)
```

`make clean-data` asks you to type `yes`.

## Uninstall { #uninstall }

Full removal from this host:

```bash
cd /absolute/path/to/orcan
make down
make clean-data                 # type yes — deletes $ORCAN_DATA (default ~/.config/orcan)
docker images 'orcan*'          # review local tags
docker rmi orcan:latest orcan:full orcan:claude   # optional; add version tags if present
rm -rf /absolute/path/to/orcan  # remove the clone when finished
```

You do **not** need to delete your mounted project repos unless you want to.

## Upgrade Orcan

```bash
cd /absolute/path/to/orcan
git fetch
git checkout vX.Y.Z       # or main
make env                  # if config schema changed
make rebuild              # if Dockerfile/rootfs changed
make down && make terminal-docker
```

Releases are git tags + GitHub Release notes. There is no published container image from CI.

## See also

- [Quick start](../getting-started/quickstart.md)
- [Troubleshooting](troubleshooting.md)
- [Makefile reference](../reference/makefile.md)
- [FAQ](../faq.md)
