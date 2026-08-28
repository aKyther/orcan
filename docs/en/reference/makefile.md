# Makefile (maintainers)

End users use the **`orcan` CLI** — see [CLI reference](cli.md). Image lifecycle on the host is:

| User need | Command |
| --- | --- |
| Pull or build | `orcan build` (pull `VERSION`, local build on miss — **never publishes**) |
| Force local rebuild | `orcan build --force` or `--no-cache` |
| Pull registry only | `orcan pull` |
| Push to registry | `orcan publish` (**manual**, maintainers) |

This repository ships a Makefile only for **maintainers** working in a git checkout:

| Target | Role |
| --- | --- |
| `make validate` | Layout + script syntax |
| `make test-host` | Host unit tests |
| `make test` / `make test-path-parity` | Container tests (needs Docker) |
| `make dev-test` | Isolated developer UX lifecycle (needs Docker + `orcan:dev-ux`) |
| `make docs` / `docs-serve` / `docs-check` | MkDocs |
| `make docs-llms` | Regenerate `docs/llms.txt` (also runs before docs / docs-check) |
| `make docs-mike-latest` / `docs-mike-release` | Versioned docs deploy |
| `make tag` | Checkpoint: bump + CHANGELOG cut + commit + tag, all pushed (see [Release process](../development/release.md)) |
| `make release` | The real, deliberate release: CalVer + tag + push |
| `make registry-*` | Low-level registry helpers (prefer `orcan publish` / `orcan pull`) |

Deprecated user Make targets (`setup`, `env`, `terminal-docker`, `rebuild`, …) forward to `./bin/orcan` with a deprecation note. **Do not document them to end users** — use `orcan` directly.

## Developer environment (`make dev-*`)

Isolated browser UX for testing cockpit / ttyd / launcher changes. **Not** the public `orcan` interface — own image, port, and state under `.orcan-dev-ux/`.

| Target | Role |
| --- | --- |
| `make dev-start` | Start; build image only if missing |
| `make dev-restart` | Refresh cockpit from checkout and recreate |
| `make dev-status` | Health + local/LAN URLs |
| `make dev-doctor` | Isolation identity, health, HTTP, checkout cockpit source |
| `make dev-smoke` | Textual + real embedded tmux PTY smoke |
| `make dev-visual` | Chromium screenshot regression (needs healthy preview) |
| `make dev-visual-update` | Replace screenshot baselines after review |
| `make dev-a11y` | Tab/focus, overflow, axe, tiny `480x320` viewport |
| `make dev-shell` | Enter the isolated preview container |
| `make dev-enter` | Enter the isolated developer launcher |
| `make dev-logs` | Follow container logs |
| `make dev-stop` | Stop stack; keep image/cache |
| `make dev-reset` | Stop and delete default `.orcan-dev-ux/` state |
| `make dev-checklist` | Pre-merge automated targets + manual browser flow |
| `make dev-test` | Separate uniquely named stack; assert `orcan-1` unchanged |

Underlying scripts (same behaviour): `./scripts/dev/orcan-preview …` and `./scripts/dev/terminal-ui-preview` (fast tmux-only, no Docker).

Defaults: image `orcan:dev-ux`, host port `17681`, workspace `dev-ux`, scenario `busy`. Full flags, scenarios, and isolation rules: [Testing — maintainer previews](../development/testing.md).

## Optional private registry

CI does **not** publish container images. Maintainers may push manually:

```bash
orcan build --force          # ensure local image exists
orcan publish                # or: make registry-login && ./scripts/repository/registry.sh publish
```

Configure `IMAGE_REGISTRY`, `IMAGE_REPOSITORY`, and `IMAGE_TAG` in `.env` (via `orcan sync`). See [Environment variables](environment.md).
