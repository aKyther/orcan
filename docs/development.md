# Development

Guide for contributors and coding agents who change this repository.

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
| This repo's Cursor rules | `.cursor/rules/` (see `agents.mdc`) |
| Documentation | `README.md`, `docs/` |

## Agent guide

Agents working on **this** repository should follow `.cursor/rules/agents.mdc`.
That file is always applied in Cursor.

Key points:

* Work only inside `PROJECT_DIR` (the mounted project for end users; this repo when you develop it).
* Repository rules (`.cursor/`) are separate from image defaults (`docker/rootfs/opt/cursor-defaults/`).
* After infrastructure changes, run `make validate` and `make build` / `make test` when Docker is available.
* Update `README.md` and the matching `docs/` page when Make or Compose commands change.

Mounted projects can still get their own `AGENTS.md` from `cursor-init-project` templates.
That is for the **user's project**, not for developing this repository.

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
2. Global rules (`rules/`) apply to every session — keep them generic (no language or framework specifics).
3. Global skills (`skills/`) are reusable workflows; avoid duplicating rule content.
4. Project templates (`templates/`) are copied by `cursor-init-project` — keep them project-scoped.
5. Rebuild the image (`make build`).
6. New files appear on next container start only if missing in the volume.
7. To force a full reset of global Cursor home: `make clean-volumes`, then start again.

Do not write defaults only into `/home/developer/.cursor` during the image build.
The named volume would hide them.

## Changing Compose

1. Keep the Docker socket out of `docker-compose.yml`.
2. Put socket + `group_add` only in `docker-compose.docker.yml`.
3. Put OpenSSH publish/password settings only in `docker-compose.ssh.yml`.
4. Preserve named volumes unless you have a migration plan.
5. Validate configs:

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
* Use `alwaysApply: true` only for safety/validation rules and the agent guide
* Do not confuse repo rules with image defaults under `docker/rootfs/opt/cursor-defaults/`

## Changing documentation

When you change a user-facing interface or path:

1. Update `README.md`
2. Update the matching page under `docs/`
3. Update `.cursor/rules/agents.mdc` if agent workflow commands changed

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

## Roadmap

Optional hardening and publishing ideas. None of these are required to use the project today.

| Idea | Why |
| --- | --- |
| Pin tool and base image versions | Reproducible builds over time |
| Verify SHA256 of downloaded binaries | Stronger supply-chain checks |
| CI builds for `amd64` and `arm64` | Catch arch-specific breakages early |
| Scan images with Trivy | Find known CVEs before publish |
| Publish to GHCR | Share a prebuilt image |
| Slim language variants | Smaller images for focused stacks |
| Optional SSH agent forwarding | Safer than mounting `~/.ssh` |
| Image smoke tests in CI | Fail fast when a tool disappears |
| Dependabot or Renovate | Keep base images and actions current |
