# Makefile reference

Use this page when you already understand the product idea and need the full host command surface. For the story, start at [Home](../index.md) or [Why Orcan?](../why-orcan.md).

Run from the Orcan repository root on the **host**.

!!! note
    Keep this page aligned with `make help`. Prefer documenting every `##`-annotated target.

## Configure

| Target | Purpose |
| --- | --- |
| `make setup` | First run: scaffold config if needed → `env` → show layout |
| `make config-wizard` | Interactive edit of `orcan.config.json` |
| `make config-scaffold` | Add project from `PROJECT_DIR` |
| `make config-init` | Copy example config file |
| `make config-show` | Print workspaces |
| `make env` | Apply config → `.env` + `.orcan/*` that Compose / `terminal*` consume |
| `make require-generated` | Fail if `.env` / generated runtime files are missing (no writes) |
| `make require-env` | Fail if `.env` is missing (image build) |

## Images

| Target | Purpose |
| --- | --- |
| `make build` | Full image → `orcan:latest` (Claude + Cursor) |
| `make build-claude` | Claude-only → `orcan:claude` |
| `make rebuild` / `make rebuild-claude` | Rebuild without cache |

## Run

| Target | Purpose |
| --- | --- |
| `make terminal` | Browser terminal **without** Docker socket |
| `make terminal-docker` | Browser terminal **with** Docker socket |
| `make terminal-url` | Print URL |
| `make down` | Stop containers |
| `make logs` | Follow logs |
| `make path-check` | Show path parity summary |
| `make config` | Print resolved Compose config |

`make terminal*` does **not** run `make env`.

## Project seeds

| Target | Purpose |
| --- | --- |
| `make init-project` | Seed `PROJECT_DIR` (missing-only) |
| `make init-project-dry-run` | Preview seeds for `PROJECT_DIR` |
| `make init-project-all` | Seed every configured project path |
| `make init-project-all-dry-run` | Preview seeds for every project path |

## Docs

| Target | Purpose |
| --- | --- |
| `make docs` | Build MkDocs → `./site` (strict) |
| `make docs-serve` | Local docs server |
| `make docs-check` | Strict build + product-name check |
| `make docs-mike-dev` | Deploy mike alias `dev` |
| `make docs-mike-release` | Deploy `VERSION` + alias `latest` via mike |
| `make docs-publish` | Trigger CI (main → docs `dev`) |
| `make docs-deploy` | Alias for `docs-publish` |

## Quality

| Target | Purpose |
| --- | --- |
| `make validate` | Layout, script syntax, Compose config |
| `make test-host` | Host unit tests (no Docker image) |
| `make test` | Smoke tests (builds full image; **not** in CI) |
| `make test-path-parity` | Path parity integration test (**not** in CI) |

## Release

| Target | Purpose |
| --- | --- |
| `make version` | Show `VERSION` and local image tag names |
| `make bump-patch` / `bump-minor` / `bump-major` | Bump SemVer |
| `make release-tag` | Create annotated git tag `vX.Y.Z` (clean tree) |
| `make release-push` | Push version tag to origin |
| `make release` | Tag + push → GitHub Release (**no** image publish) |

## Clean

| Target | Purpose |
| --- | --- |
| `make clean` | Stop containers; keep `$ORCAN_DATA` |
| `make clean-data` | **Destructive** delete `$ORCAN_DATA` (confirm `yes`) |
| `make clean-volumes` | Alias for `clean-data` |

## Optional private registry

| Target | Purpose |
| --- | --- |
| `make registry-show` | Show local/remote image names |
| `make registry-login` | Log in to container registry |
| `make publish` / `make pull` | Manual image push/pull (not used by CI) |

## Renamed targets (migration)

| Old | New |
| --- | --- |
| `make shell` | `make terminal` |
| `make shell-docker` | `make terminal-docker` |
