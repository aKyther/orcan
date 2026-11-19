# Testing

## Host checks (fast — CI)

Install `uv` before running host tests. `make test-host` automatically loads
`requirements-test.txt` into a uv-managed environment, then runs Pytest and the
release checks. It does not need global Python packages and does not modify the
checkout's `.venv` or create a project lockfile.

The root `pyproject.toml` contains tool settings only. Use `uv run --no-project`
for ad hoc commands from the repository root. A root `uv.lock` produced by a
plain `uv run` is a local artifact and is ignored. Dependency lockfiles remain
tracked separately in `plugins/cockpit/uv.lock` and `plugins/redis/uv.lock`.

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

Desktop UI, Tauri, Rust and fixture-browser checks run in the separate
[Orcan Studio repository](https://github.com/aKyther/orcan-studio).
Orcan retains tests for its `orcan studio …` host bridge.

Full host checks always run. Changed-path selection controls image/Trivy and docs
jobs. Unknown paths, unavailable Git history, manual dispatch and the weekly
schedule run the full scope. The classifier and its tests are `ci_scope.py` and
`test_ci_scope.py`. Host checks share uv dependencies
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

Container creation options are checked by `studio-enclave.py:build_configuration`;
`test_studio_creation_options.py` exercises validation without spawning Python.
The CLI integration suite still checks rejection and absence of config writes.
Studio inventory and deletion bind to a connection/report snapshot via
`context-scope.ts`. Changing either expires the pending approval. Worktree/branch
reads wait until the Worktrees view opens; a new report invalidates loaded views.
The shared approval gate tests that no mutation callback is sent after a target
switch, disconnect or report refresh; stable approval sends exactly one. Workspace
rename/removal, Git parent updates and worktree deletion all use this gate.
Branch discovery exposes idle/loading/ready/failed states; reopening Worktrees
retries failed reads without duplicating a pending or successful request.
Map tests check retained SVG path identity across resize and removal of old edges.

`test_context_presenters.py` contains isolated formatting contracts; Git-backed
context tests remain in `test_context_tui.py`. Labels and rows live in
`scripts/repository/context_presenters.py`, without curses or command execution.
Directory/selection/history models live in `context_selection.py`. Presenter
tests import these small modules directly, not the terminal application.
Native context endpoints share argument builders in `context.rs`. Branch discovery
and the activity view own their DOM/state in `branch-picker.ts` and `activity-panel.ts`;
the main UI coordinates them through callbacks. `container-creator.ts` owns the
complete creation form and readiness/approval snapshot. Native CLI installation
is in `installation.rs`; bounded execution in `execution.rs`. Curses-free config
mutations live in `context_mutations.py`.

CLI archive production has one source, `src-tauri/src/cli_export.sh`, embedded by
`cli_export.rs`. Host tests exercise archive contents and failure cleanup, not
the number or location of Rust call sites. Rust tests check optional image arguments.
Probe Git facts use three local processes per unique path: common directory,
porcelain-v2 status (branch, upstream, counts, dirtiness), and origin URL. Facts
are reused only within the current report; updates still recheck live Git state.

Studio browser tests and render measurements moved with the desktop application.
See its README for the standalone browser test and preview commands.

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
Generated build caches are excluded from validation.

## Smoke tests (Codex selection — local)

```bash
make test
```

Runs `tests/smoke/test-container.sh` after `orcan build --agent codex`. It asserts the selected manifest and Codex CLI. Not run in CI (image build is too heavy).

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
| Bind | `127.0.0.1` (loopback only); set `ORCAN_PREVIEW_BIND=0.0.0.0` explicitly for a LAN test |
| Scenario | `busy` |

Set `ORCAN_PREVIEW_SCENARIO` (or edit the saved `settings.json`) to choose the
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
Cockpit smoke (inside preview): `plugins/cockpit/smoke/test-cockpit-tui.py` via `make dev-smoke`.
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

## Executor cockpit and chart checks

`uv run --project plugins/cockpit --locked python plugins/cockpit/smoke/test-cockpit-jobs.py`
checks the Jobs sheet with a fake executor, without touching a user tmux session.
`uv run --project plugins/redis --locked pytest plugins/redis/tests` covers admission races,
lane leases, timeouts, compact history and chart aggregations.

With local Playwright/Chromium and its system libraries available, run
`NODE_PATH="$PWD/.orcan-dev-ux/playwright-node/node_modules" node plugins/redis/smoke/executor-dashboard.js`.
It creates synthetic SQLite data and a temporary loopback server, checks chart
rendering, tables, details, period changes and a narrow viewport, then removes its
own fixtures. It does not connect to a live executor or Codex session. A screenshot
is written to `/tmp/orcan-executor-dashboard.png`; override with
`ORCAN_DASHBOARD_SCREENSHOT`. Missing browser libraries are an environment failure,
not a passing browser test. The committed `cockpit-executor-final` profile runs
host/executor tests, the fake cockpit smoke, JavaScript syntax and strict docs.

Redis communication tests run an isolated Redis process over a private temporary
Unix socket (when `redis-server` is installed), verify health and stream persistence
across a graceful AOF restart, and clean up that process only. This is not a claim
about crash-loss guarantees. Recovery tests use a real child process inheriting
an execution lock to prove that recovery refuses an active child. Other tests
cover partial publication, durable outbox replay, stale/coalesced samples and
sanitized connection failures. No live broker is restarted.


## Cockpit responsiveness

The deterministic regression blocks discovery, Git details and brief reads while
checking that input works, repeated refreshes share one read, obsolete results
are ignored and Escape closes the brief. It never attaches to a user's tmux.

```bash
./tests/host/run.sh plugins/cockpit/tests/test_cockpit_probe.py plugins/cockpit/tests/test_cockpit_paint_skip.py
PYTHONPATH=docker/rootfs/usr/local/lib uv run --project plugins/cockpit --locked python plugins/cockpit/smoke/test-cockpit-responsiveness.py
```

`plugins/cockpit/smoke/cockpit-load.py` adds a finite real PTY/private-tmux benchmark.
It generates terminal output and synthetic slow metadata, then adds a busy child
process. Each case runs for four seconds by default (`--seconds 1..30`). JSON
reports sent/acknowledged/pending keys, nearest-rank p95/max key-to-ACK latency,
event-loop lag, read-callback duration and received bytes. Pending keys must be
reported alongside latency: a missing ACK is not a fast response. This headless
harness does not measure ttyd, browser rendering or network latency.

Run heavy cases in a capped disposable container with an existing compatible
Orcan image. Resolve checkout paths before Docker bind mounts. No user home,
Docker socket or live tmux server is mounted; the image is not rebuilt or restarted.

```bash
repo=$(pwd -P)
docker run --rm --cpus=0.5 --memory=512m --pids-limit=128 --network=none \
  --tmpfs /tmp:rw,size=128m \
  --entrypoint /opt/orcan/plugins/cockpit/.venv/bin/python \
  --mount "type=bind,source=$repo/cockpit/src,target=/source/cockpit/src,readonly" \
  --mount "type=bind,source=$repo/docker/rootfs/usr/local/lib/orcan,target=/source/orcan,readonly" \
  --mount "type=bind,source=$repo/plugins/cockpit/smoke/cockpit-load.py,target=/load-test.py,readonly" \
  -e PYTHONPATH=/source/cockpit/src:/source -e HOME=/tmp \
  orcan:latest /load-test.py --seconds 4
```

Compare the same image, CPU quota, duration and harness on both revisions.
Repeat noisy cases before drawing conclusions; a short run is a diagnostic,
not a performance guarantee. Check a normal CPU budget as well as the deliberately
restricted 0.5-CPU case. Do not add machine-specific latency thresholds to CI;
the deterministic blocked-read regression supplies the stable acceptance check.
