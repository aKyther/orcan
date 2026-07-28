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
| `make docs` / `docs-serve` / `docs-check` | MkDocs |
| `make docs-mike-dev` / `docs-mike-release` | Versioned docs deploy |
| `make bump-*` / `release` | Version + GitHub Release |
| `make registry-*` | Low-level registry helpers (prefer `orcan publish` / `orcan pull`) |

Deprecated user Make targets (`setup`, `env`, `terminal-docker`, `rebuild`, …) forward to `./bin/orcan` with a deprecation note. **Do not document them to end users** — use `orcan` directly.

## Optional private registry

CI does **not** publish container images. Maintainers may push manually:

```bash
orcan build --force          # ensure local image exists
orcan publish                # or: make registry-login && ./scripts/repository/registry.sh publish
```

Configure `IMAGE_REGISTRY`, `IMAGE_REPOSITORY`, and `IMAGE_TAG` in `.env` (via `orcan sync`). See [Environment variables](environment.md).
