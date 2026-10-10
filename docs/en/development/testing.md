# Testing

## Host checks (fast — CI)

Install `uv` before running host tests. `make test-host` automatically loads
`requirements-test.txt` into a uv-managed environment, then runs Pytest and the
release checks. It does not need global Python packages and does not modify the
checkout's `.venv` or create a project lockfile.

```bash
make validate
make test-host
make docs-check
```

| Target | What it does |
| --- | --- |
| `make validate` | Required files, shell/Python syntax, pyproject version, product-name, Compose `config` if Docker is up |
| `make test-host` | Pytest host tests for config I/O, `apply-config`, version / release check, preview script checks |
| `make format` / `make format-check` | Apply / verify Ruff formatting for host helpers, cockpit, and host tests |
| `make docs-check` | Strict MkDocs build + product-name check |

## Fast development loop

Run the smallest relevant check while editing. Full host tests remain the
default for `make test-host` and CI; CI collects coverage in that same run,
not a second execution of the suite.

```bash
make test-fast
make test-host TEST_ARGS="tests/host/test_named_instances.py -k registry"
make test-integration
make test-host TEST_ARGS="--durations=20"
```

`test-fast` excludes explicitly marked integration tests, classes and modules.
Use `@pytest.mark.integration` or `pytestmark = pytest.mark.integration` for
Git/CLI, PTY or network operations, including those in imported fixtures/helpers.
Unmarked tests cannot launch subprocesses: an autouse fixture rejects `Popen`
and asks for a mocked boundary or an integration marker. Imports alone no longer
determine selection. These modes are developer shortcuts, not replacements
for full CI. `TEST_ARGS` also accepts pytest paths, node IDs and `-k` filters;
it applies to `test-host`, `test-fast`, `test-integration` and `test-coverage`.

For Studio-only changes, use `npm test` and `npm run build` in `studio/app`,
plus `cargo test --manifest-path studio/Cargo.toml` for native Rust changes.
Run the full checks before handoff.

CI runs UI behavior tests and native application tests as well as the Rust core.
Full host checks always run. Changed-path selection skips Studio builds for
docs/test-only changes and skips image builds/Trivy for Studio/host-only changes.
Image/runtime changes run both image and Studio checks. Unknown paths, unavailable
Git history, manual dispatch and the weekly schedule run the full scope. Trivy's
severity policy is unchanged. Docs deploy only after documentation changes.
The classifier and its pure tests are `ci_scope.py` and `test_ci_scope.py`;
update them when adding a new build input. Browser downloads use a pinned-version
cache, separate from native build artifacts.

Studio jobs cache npm/Cargo dependencies and compiled dependency directories, not
installers, app executables or incremental output. Keys include the Rust compiler,
platform and build mode. Linux CI omits development debug symbols and logs cache
directory sizes; compare restore/save times with compile time before expanding
the cache. Host checks share uv dependencies
instead of installing the test requirements into two Python environments.

Pure worktree contracts live in `test_git_worktrees.py`; real Git operations
live in `test_git_worktrees_integration.py`. Use `git_repo_factory` for isolated
empty repositories: its session template is copied, including `.git`, never
shared or hardlinked. Keep scenario-specific remotes and commits in each test.
Use `committed_git_repo_factory` when only an initial HEAD is needed. It copies
a session template with one empty commit and local fixture identity; branches
and configuration remain private. Real worktree lifecycle tests reuse this
template rather than repeating init/config/commit for every checkout.
UI tests share `tests/helpers.mjs`: TypeScript compilation is cached, but each
test gets fresh module state. No browser emulator is needed for these contracts.

`test_context_presenters.py` contains isolated formatting contracts; Git-backed
context tests remain in `test_context_tui.py`. Labels and rows live in
`scripts/repository/context_presenters.py`, without curses or command execution.
Directory/selection/history models live in `context_selection.py`. Presenter
tests import these small modules directly, not the terminal application.
Native context endpoints share argument builders in `context.rs`. Branch discovery
and the activity view own their DOM/state in `branch-picker.ts` and `activity-panel.ts`;
the main UI coordinates them through callbacks.

Studio has five real browser smoke flows, independent of the cockpit suite:
connection gating, map selection/resize anchors, drag/stage/discard, and a synthetic
100-project/10-workspace map checking filters, both anchors and retained drafts,
and creator readiness/approval invalidation after changing its target.
They use fixture data, block host snapshots, and contact no SSH or Docker target.
CI runs them after the UI tests. Locally:

```bash
npm install --no-save --no-package-lock --prefix .orcan-dev-ux/playwright-node @playwright/test@1.55.0
.orcan-dev-ux/playwright-node/node_modules/.bin/playwright install chromium --with-deps
make studio-test-browser
```

The browser check starts and stops its own Vite server on port 1438; do not point
it at the daily Orcan runtime. Headless browser dependencies are needed only for
this check, not `npm test`. Map geometry owns coalesced frame scheduling in
`map-connections.ts`; project selection updates classes/edges, not all cards.
Context rendering builds lookup maps once per render, without persisting a second
source of truth alongside the probe report.

Default CI coverage measures the test process, not helper subprocesses. All tests
still run, including real CLI operations. For an accurate extended diagnostic:

```bash
make test-coverage-subprocess TEST_ARGS="tests/host/test_studio_probe.py"
```

This explicit mode enables Python subprocess startup instrumentation and combines
per-process data after the suite. It adds overhead; do not add another full run
to CI. Child commands keep their working directories;
reports are collected in the checkout even for tests running in temporary folders.
Separately installed Python interpreters without coverage and killed processes
may not contribute. Inline Python version/PATH discovery is not instrumented.
Normal `test-host`/`test-fast` do not enable instrumentation.

Probe inspection deduplicates canonical paths only within one request. Unknown
Git status is not clean and cannot authorize an update. Configuration writes use
unique temporary files and atomic replacement. Host writers serialize commits
with a bounded parent-directory lock, preserving configuration symlinks.

Studio captures local, WSL and system-SSH commands with a deadline and drains
stdout/stderr concurrently. Read-only probes have a 90-second limit and a Cancel
check button; other captured commands allow up to 15 minutes. Native SSH connection
setup has a 45-second limit. Host clone operations allow 14 minutes, other Studio
mutations five minutes. A timeout or cancellation does not roll back remote work:
refresh the host before retrying. Streaming image transfers retain their separate
progress/resume workflow with a five-minute idle deadline; active transfers have
no fixed total-duration limit. Provisioning and SSH preparation also bound stdin
commands. These limits are policy, not performance benchmarks.
Command responses and diagnostics have a 16 MiB limit per stream. Exceeding it
is an explicit failure, never silently truncated JSON; image bytes use a separate
streaming path and are not subject to this response limit.

Worktree apply responses can have `ok: true` with `outcome: partial`: the request
returned a usable result, but not every attachment succeeded. `completed` and
`pending_workspaces` describe the steps. Studio's Retry attachments rechecks each
remaining membership and never recreates the worktree. A failed queued creation
becomes an attachment to the preserved checkout. No automatic rollback deletes
project data. After restarting Studio, use the worktree inventory to attach or
clean up preserved worktrees.

`load_config` snapshots automatically check their revision before saving; Studio
supplies its explicit read snapshot. A stale save is rejected, not merged or
silently overwritten. This is not a transaction with arbitrary
external editors, which should not write the same configuration concurrently.

Every Docker probe request and read-only worktree Git command has a timeout.
New images advertise installed agents in labels, avoiding a helper container on
each probe; legacy images retain the bounded manifest fallback. There is no
persistent cache of mutable repository status or image tags.

Validation scans source files once using Git's tracked/non-ignored file list,
excluding build output, dependency folders, virtual environments and secrets.
Keep `studio/target` as a build cache; validation does not need to inspect it.

## Smoke tests (Codex selection — local)

```bash
make test
```

Runs `tests/smoke/test-container.sh` after `orcan build --agent codex`. It asserts the selected manifest and Codex CLI. Not run in CI (image build is too heavy).

## Maintainer previews (`scripts/dev/`)

Checkout-local helpers under `scripts/dev/`. They are **not** the public `orcan` CLI. Prefer the thin `make dev-*` wrappers so the developer testing workflow is easy to discover without disturbing an installed daily Orcan stack.

### Fast Studio UX preview — `orcan-studio-preview`

This is a separate browser-only Vite container for reviewing the Studio layout,
copy, loading states, and confirmation flow from another Tailscale device. It
uses representative fixture data: it never opens SSH, Docker, the credential
vault, or a real Orcan Sandbox.

```bash
make studio-preview-start
# open the printed http://100.x.x.x:1420/?demo=1 URL from a Tailscale device
make studio-preview-logs
make studio-preview-stop
```

The helper discovers the host's first Tailscale IPv4 address and refuses a
non-Tailscale bind. Set `ORCAN_STUDIO_PREVIEW_BIND=100.x.x.x` to choose another
Tailscale address and `ORCAN_STUDIO_PREVIEW_PORT=1420` to change the port.
Vite hot-reloads frontend edits; no `.exe`, `.app`, or Tauri bundle is built.
Use `npm run tauri dev` for an integration check against the real native
backend.

To review the layout with this host's real workspaces, save a read-only probe
snapshot. The preview's "Demo workstation" Enclave then shows it; other
Enclaves and every action stay simulated. The snapshot is served only by the
Vite dev server (never bundled) and is visible to your tailnet.

```bash
make studio-preview-snapshot        # runs orcan studio probe --json on the host
make studio-preview-snapshot-clear  # back to fixture data
```

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
| Bind | `127.0.0.1` (loopback only); set `ORCAN_PREVIEW_BIND=0.0.0.0` explicitly for a LAN test |
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
    The preview is a writable terminal and binds only to `127.0.0.1` by default.
    Use `ORCAN_PREVIEW_BIND=0.0.0.0` only for a deliberate LAN test; it is not
    saved for later runs. Then run `make dev-stop`. `make dev-test` always removes its separate temporary stack
    and state when it finishes, including after a failure.

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


## See also

- [Development overview](overview.md)
- [Terminal UI](../guides/terminal-ui.md)
- [Release process](release.md)
- [Makefile](../reference/makefile.md)
- [Path parity](../concepts/path-parity.md)
