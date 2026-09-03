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
| `make test-host` | Unit tests for config I/O, `apply-config`, version / release check, preview script checks |
| `make docs-check` | Strict MkDocs (EN+PL) + product-name check |

## Smoke tests (full image — local)

```bash
make test
```

Runs `tests/smoke/test-container.sh` after `orcan build`. Expects the **full** image (`agent` present). Not run in CI (image build is too heavy).

## Maintainer previews (`scripts/dev/`)

Checkout-local helpers under `scripts/dev/`. They are **not** the public `orcan` CLI. Prefer the thin `make dev-*` wrappers so the developer testing workflow is easy to discover without disturbing an installed daily Orcan stack.

### Full developer browser environment — `orcan-preview`

Isolated Docker stack from **this** checkout: own image, Compose project, home/data, ttyd port, and container. Does not replace `orcan:latest` or touch `~/.config/orcan`.

```bash
make dev-start                           # build only if missing + start
# open http://127.0.0.1:17681
make dev-restart                         # fast refresh from checkout source
make dev-status
make dev-doctor                          # isolation + health + HTTP + checkout cockpit
make dev-smoke                           # real Textual + tmux PTY
make dev-a11y                            # keyboard/focus/axe (+ 480x320 viewport)
make dev-visual                          # Chromium screenshot regression (900x700 / compact)
make dev-test                            # separate real-Docker lifecycle; orcan-1 unchanged
make dev-checklist                       # print pre-merge automated + manual browser checks
make dev-shell                           # shell inside isolated preview
make dev-enter                           # isolated developer launcher
make dev-stop                            # keep image/cache
make dev-reset                           # stop + delete default fixture state
```

| Make target | Script command | Role |
| --- | --- | --- |
| `dev-start` | `start [--port PORT\|auto]` | Start; build only when the image is missing; choose a free default port |
| `dev-restart` | `restart [--port PORT\|auto]` | Refresh cockpit directly from checkout and recreate; wait until healthy |
| — | `rebuild [--no-cache]` | Full image rebuild for Dockerfile, rootfs, or dependency changes |
| `dev-status` | `status` / `url` | Health + URLs |
| `dev-doctor` | `doctor` | Docker, isolation identity, health, HTTP, checkout bind, cockpit from checkout |
| `dev-visual` | — | Chromium screenshot regression (`dev-ux.spec.js`; needs healthy preview) |
| `dev-visual-update` | — | Intentionally replace screenshot baselines after review |
| `dev-a11y` | — | Tab/focus, no overflow, axe serious/critical, tiny `480x320` (`dev-a11y.spec.js`) |
| `dev-logs` | `logs` | Follow container logs |
| `dev-shell` | `shell` | `orcan enter --shell` in the preview container |
| `dev-enter` | `enter` | Isolated developer launcher |
| `dev-stop` | `stop` | Compose down (isolation-checked) |
| `dev-checklist` | `checklist` | Pre-merge Make targets + manual browser flow (viewports, axe, Alt/resize) |
| `dev-reset` | `reset` | Stop and remove **default** `.orcan-dev-ux/` only |
| `dev-test` | — | Separate uniquely named stack; assert `orcan-1` unchanged |
| — | `check` | Validate generated config/env; no Docker |

Defaults (overridable):

| Item | Default |
| --- | --- |
| Fixture root | `.orcan-dev-ux/` (gitignored) under the checkout |
| Image | `orcan:dev-ux` |
| Container | `orcan-dev-ux` |
| Compose project | `orcan-dev-ux` |
| Host ttyd port | `17681` |
| Bind | `0.0.0.0` (LAN); set `ORCAN_PREVIEW_BIND=127.0.0.1` for loopback only |
| Scenario | `busy` |

Set `ORCAN_PREVIEW_SCENARIO` (or edit the saved `settings.env`) to choose the
`orcan.config.json` fixture that `write_fixture` generates:

| Scenario | Fixture written to `orcan.config.json` |
| --- | --- |
| `busy` | Default — one `dev-ux` workspace, the checkout as its only project, 3 windows |
| `empty` | One bare `scratch` workspace, single window — the near-empty cockpit |
| `long-names` | Overlong workspace and project names plus a second project, to test rail wrapping / clipping |

The next `start`/`restart` applies a changed scenario. If a saved/default port
is occupied, preview chooses the next free port; an explicitly requested busy
port fails instead. Mutating operations use a lock. Cockpit Python is loaded
directly from the checkout, so normal UX changes need only the fast `restart`;
use `rebuild` after Dockerfile, rootfs, lockfile, or dependency changes. The
image records its source commit and dirty state, displayed after startup.

Isolation guards refuse defaults that would collide with a normal install (`orcan:latest`, port `7681`, Compose project `orcan`, instance `1`, or the real `ORCAN_HOME`). `reset` refuses any non-default `ORCAN_PREVIEW_ROOT`.

`make dev-test` starts an additional uniquely named container, checks health,
HTTP, checkout path parity, Textual, and the real tmux PTY, removes it, and
confirms that the `orcan-1` ID did not change.

`make dev-visual` / `make dev-a11y` require a healthy preview (`orcan-preview doctor`
runs first). They use an isolated Playwright container
(`mcr.microsoft.com/playwright:v1.55.0-noble` by default; override with
`ORCAN_PLAYWRIGHT_IMAGE`), install `@playwright/test` + `@axe-core/playwright`
under `.orcan-dev-ux/playwright-node/`, and write failure artifacts under
`.orcan-dev-ux/artifacts/playwright/`. Override the target URL with
`ORCAN_DEV_UX_URL` if needed. Screenshot baselines live next to
`tests/browser/dev-ux.spec.js-snapshots/`.

`make dev-checklist` prints the **Before merge (automated)** list
(`dev-doctor`, `dev-smoke`, `dev-a11y`, `dev-visual`, `dev-test`) plus the
manual browser flow (F4/F1, workspace details, Enter selection, Alt+1…9, resize, compact `900x700`, tiny
`480x320`, axe). The accessibility suite also asserts Tab reaches the terminal
and that a `480x320` viewport keeps the xterm usable.

!!! warning
    Default bind is `0.0.0.0` so LAN access works. Do not run on an untrusted network without ttyd authentication.

### Fast tmux chrome — `terminal-ui-preview`

No Docker. Spins an **isolated tmux server** (private socket) from `docker/rootfs/etc/tmux/` in the checkout. Your normal Orcan tmux is untouched.

```bash
./scripts/dev/terminal-ui-preview              # attach; exit/detach cleans up
./scripts/dev/terminal-ui-preview --check      # assert status=2, 3 windows; no attach
./scripts/dev/terminal-ui-preview --size 140x40
```

Inside the preview: prefix **C-Space**; **C-Space r** reloads UI files from the checkout. Gallery windows exercise short/long tab titles and tiled panes.

Prefer this for status-bar / keybinding / layout edits. Prefer `orcan-preview` when you need ttyd, launcher/cockpit, or a real image build.

Host tests: `tests/host/test_orcan_preview.py`, `tests/host/test_terminal_ui_preview.py`.
Cockpit smoke (inside preview): `tests/smoke/test-cockpit-tui.py` via `make dev-smoke`.
Browser: `tests/browser/dev-ux.spec.js` (`make dev-visual`), `tests/browser/dev-a11y.spec.js`
(`make dev-a11y`). Lifecycle isolation: `tests/integration/test-dev-ux.sh` (`make dev-test`).

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
    CI does **not** build container images and does **not** run `make test`,
    `make test-path-parity`, or `make dev-*` / `dev-test` / `dev-visual`.
    A green PR means validate + host tests + docs — not a verified image or
    browser UX run. Run those locally when Docker or cockpit UX behaviour changes.

Versioned docs URLs: https://akyther.github.io/orcan/latest/ — see [Deployment](../deployment.md).

Polish search uses the English lunr analyzer (lunr has no Polish stemmer).

## See also

- [Development overview](overview.md)
- [Terminal UI](../guides/terminal-ui.md)
- [Release process](release.md)
- [Makefile](../reference/makefile.md)
- [Path parity](../concepts/path-parity.md)
