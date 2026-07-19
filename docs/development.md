# Development

Guide for contributors who change this repository.

## Coding style

* Prefer small, focused diffs
* Keep Makefile targets discoverable via `make help`
* Keep docs in simple B2 English
* Do not document commands that do not exist
* Do not add features only to create more files

## Changing the Dockerfile

1. Keep Debian Bookworm Slim as the final base.
2. Keep multi-stage copies for heavy toolchains.
3. Install APT packages with `--no-install-recommends`.
4. Clean APT lists after installs.
5. Do not copy secrets into layers.
6. Validate with a real build.

```bash
make build
```

Then smoke-test tools inside a shell.

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
4. Fail clearly when `*-docker` targets lack a socket.

## Changing Cursor rules

* Keep `.mdc` files short
* One concern per file
* Use `alwaysApply: true` only for safety/validation rules
* Use globs for Dockerfile/Compose/docs-focused rules

## Changing Cursor defaults

1. Edit files under `cursor-home/`.
2. Rebuild the image (`make build`).
3. New files appear on next container start only if missing in the volume.
4. To force a full reset of global Cursor home: `make clean-volumes`, then start again.

Do not write defaults only into `/home/developer/.cursor` during the image build.
The named volume would hide them.

## Changing documentation

When you change a user-facing interface:

1. Update `README.md`
2. Update the matching page under `docs/`
3. Update `AGENTS.md` if agent workflow commands changed

Preview docs:

```bash
pip install mkdocs-material
mkdocs serve
```

## Expected validation before you finish

* [ ] `make config`
* [ ] `make help`
* [ ] `make build` (when Docker is available)
* [ ] Tool smoke checks in a container
* [ ] Docs match the real Make/Compose interface

Report what ran, what did not run, and any environment limits.
