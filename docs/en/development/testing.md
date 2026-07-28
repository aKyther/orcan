# Testing

## Host checks (fast — CI)

```bash
make validate
make test-host
make docs-check
```

| Target | What it does |
| --- | --- |
| `make validate` | Required files, shell/Python syntax, VERSION, product-name, Compose `config` if Docker is up |
| `make test-host` | Unit tests for config I/O, `apply-config`, VERSION / release check |
| `make docs-check` | Strict MkDocs (EN+PL) + product-name check |

## Smoke tests (full image — local)

```bash
make test
```

Runs `tests/smoke/test-container.sh` after `orcan build`. Expects the **full** image (`agent` present). Not run in CI (image build is too heavy).

## Path parity

```bash
make test-path-parity
```

Needs Docker and the host socket. Skips cleanly if unavailable. Not run in CI.

## CI

GitHub Actions (`.github/workflows/ci.yml`) on `main` / PRs:

1. `make validate`
2. `make test-host`
3. `make docs-check`
4. On push to `main` only: `mike deploy` alias **`dev`**
5. On git tag `vX.Y.Z` (Release workflow): `mike deploy X.Y.Z` + alias **`latest`**

!!! warning
    CI does **not** build container images and does **not** run `make test` or `make test-path-parity`.
    A green PR means validate + host tests + docs — not a verified image smoke run. Run those locally when Docker behaviour changes.

Versioned docs URLs: https://akyther.github.io/orcan/latest/ — see [Deployment](../deployment.md).

Polish search uses the English lunr analyzer (lunr has no Polish stemmer).