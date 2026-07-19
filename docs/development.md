# Development

Guide for contributors who change this repository.

## Coding style

* Prefer small, focused diffs
* Keep Makefile targets discoverable via `make help`
* Keep the Makefile thin; put host logic in `scripts/repository/`
* Put container files in `docker/rootfs/`
* Keep docs in simple B2 English
* Do not document commands that do not exist
* Do not add features only to create more files

## Source of truth

| Concern | Location |
| --- | --- |
| Container filesystem | `docker/rootfs/` |
| Runtime init | `docker/rootfs/usr/local/bin/*` |
| Image build | `Dockerfile` |
| Host orchestration | `Makefile` + Compose |
| Host helpers | `scripts/repository/` |
| Project templates | `docker/rootfs/opt/cursor-defaults/templates/` |
| This repo's Cursor rules | `.cursor/rules/`, `AGENTS.md` |
| Documentation | `README.md`, `docs/` |

## Changing the Dockerfile

1. Keep Debian Bookworm Slim as the final base.
2. Keep multi-stage copies for heavy toolchains.
3. Prefer editing files under `docker/rootfs/` over heredocs.
4. Install APT packages with `--no-install-recommends`.
5. Do not copy secrets into layers.
6. Validate with a real build.

```bash
make build
make test
```

## Changing container files

Edit under `docker/rootfs/`, then rebuild.

Examples:

* entrypoint → `docker/rootfs/usr/local/bin/docker-entrypoint`
* Cursor defaults → `docker/rootfs/opt/cursor-defaults/`
* TMUX/Vim/shell → `docker/rootfs/etc/skel/`

## Changing Cursor defaults

1. Edit files under `docker/rootfs/opt/cursor-defaults/`.
2. Rebuild the image (`make build`).
3. New files appear on next container start only if missing in the volume.
4. To force a full reset of global Cursor home: `make clean-volumes`, then start again.

Do not write defaults only into `/home/developer/.cursor` during the image build.
The named volume would hide them.

## Changing Compose

1. Keep the Docker socket out of `docker-compose.yml`.
2. Put socket + `group_add` only in `docker-compose.docker.yml`.
3. Preserve named volumes unless you have a migration plan.
4. Validate both configs:

```bash
make config
```

## Changing the Makefile

1. Keep `.PHONY` entries updated.
2. Keep `help` comments (`## ...`) accurate.
3. Never make `clean-volumes` an automatic dependency of another target.
4. Move complex host logic to `scripts/repository/`.

## Changing Cursor rules (this repository)

* Keep `.mdc` files short
* One concern per file
* Use `alwaysApply: true` only for safety/validation rules
* Do not confuse repo rules with image defaults under `docker/rootfs/opt/cursor-defaults/`

## Changing documentation

When you change a user-facing interface or path:

1. Update `README.md`
2. Update the matching page under `docs/`
3. Update `AGENTS.md` if agent workflow commands changed

```bash
make docs-serve
```

## Expected validation before you finish

* [ ] `make validate`
* [ ] `make config`
* [ ] `make build` (when Docker is available)
* [ ] `make test` (when Docker is available)
* [ ] Docs match the real Make/Compose/paths interface

Report what ran, what did not run, and any environment limits.
