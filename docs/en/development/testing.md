# Testing

## Host checks (fast — CI)

```bash
make validate
make test-host
make docs-check
```

| Target | What it does |
| --- | --- |
| `make validate` | Required files, shell/Python syntax, pyproject version, product-name, Compose `config` if Docker is up |
| `make test-host` | Unit tests for config I/O, `apply-config`, version / release check |
| `make docs-check` | Strict MkDocs (EN+PL) + product-name check |

## Smoke tests (full image — local)

```bash
make test
```

Runs `tests/smoke/test-container.sh` after `orcan build`. Expects the **full** image (`agent` present). Not run in CI (image build is too heavy).

## Isolated UX preview

Run the complete browser terminal and launcher UI from the current checkout
without replacing the installed Orcan image or touching its config, data,
container, port, or tmux server:

```bash
./scripts/dev/orcan-preview up
# open http://127.0.0.1:17681
./scripts/dev/orcan-preview down
```

The preview uses a separate `ORCAN_HOME`, `ORCAN_DATA`, Compose project,
container (`orcan-ux-preview`), image (`orcan:ux-preview`), and ttyd port. It
also seeds two disposable Context Assertions so the cockpit side panel can be
tested immediately. Useful lifecycle commands are `status`, `url`, `logs`,
`shell`, and `rebuild`; see `./scripts/dev/orcan-preview --help`.

The preview publishes on `0.0.0.0` so it can also be opened through the host's
LAN address. Do not run it on an untrusted network without ttyd authentication.

For tmux status-bar and layout edits, use the faster checkout-native preview:

```bash
./scripts/dev/terminal-ui-preview
```

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
