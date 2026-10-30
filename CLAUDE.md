# Orcan — agent context for this repository

You are editing the **Orcan product repo**. Official name: **Orcan** (ids: `orcan`, `ORCAN_*`).
Cursor also applies `.cursor/rules/agents.mdc` (always on).
**Keep `AGENTS.md` and `CLAUDE.md` identical** — Cursor loads `AGENTS.md`; Claude Code loads `CLAUDE.md`.

Public agent index: `docs/en/llms.txt` (`make docs-llms`).
Longer maps: `docs/en/ai/project-context.md`, `docs/en/change-map.md`.

In a live **orcan workspace** (e.g. `orcan-dev`), honour that root’s context pack
(`.manifest.json`, session brief) first. After `cd orcan/`,
**this file** is the product SoT for how to change Orcan.

---

## What this is

**Work-context orchestrator** for coding agents in Docker — **not** a model manager.

| Piece | Meaning |
| --- | --- |
| **Workspace** | Named set of projects = one daily job / tmux session |
| **Path parity** | Same absolute paths host ↔ container (Docker-from-Docker) |
| **Context pack** | Paths, ignores, AGENTS/CLAUDE seeds, and optional session brief |
| **Access** | Default **local** (`orcan enter`); optional browser (`orcan up --with-ttyd`) |
| **Agents inside** | Cursor CLI (`agent`), Claude Code (`claude`), Codex, Gemini CLI and GitHub Copilot CLI — tools, not models Orcan picks |

**Non-goals (do not invent):** model selection / provider routing; CI image publish /
registry-as-product; YAML user config / host-deps; treating `make dev-*` as the public
CLI; auto-rewriting mounted git repos on every start; drive-by refactors or invented flags.

Story: `docs/en/why-orcan.md` → `ideas/core-ideas.md` → `ideas/mental-model.md`.

### 30-second map

| | |
| --- | --- |
| **Public API** | `orcan` CLI (`bin/orcan`, `cli/`) — not Make |
| **Config** | JSON only: `orcan.config.json` under **`ORCAN_HOME`** (default `~/.config/orcan/`). Tool data / history: **`ORCAN_DATA`** (same default root; see `orcan help`) |
| **Ritual** | `orcan init` → `orcan sync` → `orcan build --agent codex` (when needed) → `orcan up` (**up does not sync**) |
| **Runtime** | `orcan enter` → cockpit (`agent-launcher`) → tmux 3.6a → zsh; CMD = `orcan-supervisord` (`keepalive` or `ttyd`) |
| **Cockpit** | Top: `🌀 orcan` (About) + workspace pill + metrics · Overlay: workspaces + glance · Center: tmux · Bottom: status. Keys: **F4** · **F1**/? · **F5** brief · **`i`** · **`lg`** |
| **UX preview** | `make dev-*` / `scripts/dev/` → isolated `orcan:dev-ux` — **never** the user’s `orcan:latest` |
| **Image ≠ repo rules** | Image defaults: `docker/rootfs/` (+ `opt/cursor-defaults/`). Repo rules: `.cursor/rules/` + this file |
| **Done** | Surgical diff; English docs if behaviour changed; `make validate` · `test-host` · `docs-check`; UX → `dev-checklist` |

---

## How to work

```bash
orcan init                  # or: context add / context tui / edit orcan.config.json
orcan sync                  # ALWAYS after config — apply → .env, mounts/*, workspaces/*
orcan build --agent codex   # after Dockerfile | docker/rootfs | cockpit image inputs
orcan up                    # daily; --with-ttyd for browser
orcan migrate [--yes]       # optional managed-root move (dry-run without --yes)
```

Live reconcile often avoids recreate for projects under `$ORCAN_PROJECTS_ROOT` /
`$ORCAN_HOME/workspaces/` — see `docs/en/ideas/runtime-reconcile.md`. **`orcan sync`**
always reconciles workspace meta on the **host** (`reconcile-host.py`); when the
container is up it also runs live reconcile in-container. Overlays that need recreate:
`orcan down && orcan up`.

```text
orcan enter → agent-launcher (cockpit) → tmux 3.6a → zsh
container CMD → orcan-supervisord → keepalive|ttyd
```

- Shortcut SoT: `cockpit/src/orcan_cockpit/shortcuts.py` (+ tmux `keybindings.conf`)
- First-run tip: `first_run.py` / `onboarding.py` (flag under `~/.local/share/orcan/`)
- Chrome: `top_bar.py`, `rail.py`, `status_bar.py`, `tmux_chrome.py`, `session_glance.py`
- Terminal UI guide: `docs/en/guides/terminal-ui.md`; rule `.cursor/rules/terminal-ui.mdc`
- Version SoT: `cockpit/pyproject.toml` → `version`; root `VERSION` is a mirror
- Docs: English; B1–B2; story before commands; `docs/STYLE_GUIDE.md`

### SSH inside the container

`orcan up --with-ssh` mounts host `~/.ssh` read-only. Container
`/usr/local/bin/ssh` delegates to OpenSSH with `ControlPath` set to
`~/.cache/orcan/ssh/%C` (private directory, mode 700), so multiplexing sockets
can be created and reused. `ControlMaster` and `ControlPersist` still follow
user configuration. Use `ssh` via PATH; explicit `/usr/bin/ssh` bypasses this
override. Do not make the host SSH mount writable or store runtime sockets
under `~/.ssh`. Do not read keys or credentials while diagnosing SSH issues.

### Python test dependencies

Use `make test-host`: its runner requires `uv` and loads `requirements-test.txt`
into a uv-managed environment with `--no-project`, without changing the checkout's
`.venv` or creating a project lockfile. Do not install test packages into system
Python. If `pytest` is missing from a direct Python invocation, use the runner
instead of reporting a blocker. Install `uv` first if it is unavailable.

For a focused test, use:

```bash
make test-host TEST_ARGS="tests/host/test_attach_cli.py"
make test-fast              # pure contracts while editing; full suite before handoff
```

### Image profiles and generated context

`orcan build --plan` resolves JSON `build.agents` and optional Go/Rust source images.
The installed `/etc/orcan/agents.json` controls agent-specific workspace/project
and home seeds. Preserve custom files; prune only unchanged owned workspace defaults.
The product repository keeps its maintained AGENTS/CLAUDE pair; generated workspaces
create CLAUDE.md only for Claude. See `docs/en/guides/image-profiles.md`.

### Agent inbox

`<workspace>/.orcan/tasks/` and `orcan-inbox` provide structured task handoff without copying chat transcripts. See `docs/en/ideas/agent-inbox.md`.

### Optional background executor

`orcan up --with-redis` enables Redis, Celery and a read-only dashboard inside Orcan.
Implementation: `executor/` (locked Python 3.12), Supervisor program templates and
`docker-compose.redis.yml`. See `docs/en/guides/background-executor.md`.
Workspace AGENTS/CLAUDE guidance is generated in `orcan.reconcile.executor_guidance`.
Keep default execution unchanged when disabled; readiness is checked at runtime.
Never send successful build output to agents. Completion JSON is bounded; long
logs and JUnit failures are consumed through bounded artifact reads. Default
detailed-result retention is one hour; compact history/measurements remain for 30 days
(up to 10000 expired entries). Prefer committed executor profiles for approved heavy
builds, analysis, code/report generation and docs, as well as tests. Quick reads and
interactive edits stay direct. Preserve active/dirty worktrees.
Use `orcan-executor doctor --lane LANE` for the profile queue and inspect effective
`settings` before heavy submissions. The shared `max_running` cap limits jobs,
not tool threads or per-job CPU/RAM. Keep Gradle/compiler parallelism explicit.
Profiles may declare timeout_seconds; --timeout wins over profile/runtime defaults.
Pending admission rotates repository turns per lane (Git common directory groups
worktrees), with FIFO inside each repository and the shared global cap unchanged.
For a continuing owned task, opt in with submit --replace-pending UNIQUE_TASK_GROUP
and the explicit session notification UUID. Only unclaimed queued ancestor-SHA
checks with the same group/owner/profile/selectors/lane/timeout may be replaced.
Never reuse a replacement group across independent tasks. Running/shared work is
protected; divergent/rebased histories require explicit review/cancellation.
Superseded cancellation does not verify the newer SHA; consume its own result.
Use `orcan-executor diagnostics` for sanitized Redis memory/AOF, publication failures,
heartbeat timestamps and interrupted-job candidates. Cached diagnostics older than 90s
are stale. Never infer stopped execution from a missing heartbeat alone: child
processes may hold run.lock. `recover --job` rechecks the execution lock and refuses
active or completed jobs; it does not retry failed tests or delete old worktrees.
Redis memory and visibility-timeout budgets are configurable through orcan settings.
Treat queued_locally as pending recovery, including missing lane workers. Do not
poll or block on listeners. Prefer session notifications and return control.
Dashboard charts compare measured log/result/detail bytes and elapsed times;
bytes/4 token estimates and summed task duration are not actual model costs or time saved.
Use isolated smoke fixtures, never restart the live Orcan for verification.
`executor/src/orcan_executor/notifications.py` owns explicit local Codex queue delivery. No destination
means no invocation. Queued is not consumed; ambiguous attempts must not auto-retry.
Use fake transports in tests, never a real session/model. Payload bytes are measured;
model token usage/cost remain unavailable without provider-reported usage.

### UX preview (checkout only)

To confirm a change actually runs (not just `make test-host`), drive the app
via the isolated dev stack below — needs Docker in the container
(`orcan up --with-docker`; check with `docker info`).

```bash
make dev-start         # isolated orcan:dev-ux (default :17681)
make dev-restart       # after cockpit UX edits (loads checkout source)
make dev-doctor / dev-smoke / dev-a11y / dev-visual / dev-checklist
make dev-stop
make dev-test          # separate stack; assert orcan-1 unchanged
./scripts/dev/terminal-ui-preview   # tmux chrome only (no Docker)
```

Details: `docs/en/development/testing.md`.

### Definition of done

1. Small, surgical diff — only what the request needs
2. Behaviour/interface change → update English docs (+ `CHANGELOG.md` `[Unreleased]` when user-visible)
3. UX/cockpit → prefer `make dev-restart`; verify with `dev-smoke` / `dev-a11y` / `dev-visual`
4. `llms.txt` care/non-goals changed → edit `scripts/repository/generate-llms-txt.py`, then `make docs-llms`
5. If you change this file → copy the same content to `CLAUDE.md`
6. Run and report (label what you did **not** run):

```bash
make validate && make test-host
make docs-check          # when docs / public surface changed
make test                # when Docker/image behaviour changed and Docker is available
```

No `Co-Authored-By` (or similar AI-attribution) trailer. The human is the sole author of record.

---

## Where to change what

| Change | Place |
| --- | --- |
| Public CLI | `bin/orcan`, `cli/` |
| Studio connections / secrets | `studio/app/src/profile-model.ts`, `ssh-trust.ts`, `transport.ts`; native `profiles.rs`, `ssh.rs` under `studio/app/src-tauri/src/` |
| Studio context / transfers | `studio/app/src/context-model.ts`, `context-drafts.ts`, `branch-picker.ts`, `container-creator.ts`, `provision-progress.ts`; native `context.rs`, `installation.rs`, `execution.rs`, `provisioning.rs`, `enclave.rs`; host `scripts/repository/studio-*.py` |
| Studio map / browser tests | `studio/app/src/map-connections.ts`; `tests/browser/studio.spec.js`, `studio.config.js`; `make studio-test-browser` (fixture-only) |
| Studio demo / behavior tests | Lazy-loaded `studio/app/src/demo.ts`; `studio/app/tests/*.test.mjs`, shared `helpers.mjs`; see `docs/en/change-map.md` |
| Host context selection / labels | `scripts/repository/context_selection.py`, `context_presenters.py`; terminal interaction in `context_tui.py` |
| Host helpers / validate / release | `scripts/repository/` |
| Host workspace reconcile / audit | `scripts/repository/reconcile-host.py`, `workspace-audit.py`; core `docker/rootfs/usr/local/lib/orcan/reconcile.py` |
| Developer UX environment | `scripts/dev/`, `make dev-*` |
| Image filesystem / binaries | `docker/rootfs/` |
| Image packages / agents | `Dockerfile` |
| Cockpit TUI | `cockpit/src/orcan_cockpit/` (`shortcuts.py`, `about_modal.py`, `session_glance.py`, `peek.py`, `peek_modal.py`, `first_run.py`, `onboarding.py`, `tmux_chrome.py`, `top_bar.py`, `pty_keys.py`, `pty_tmux_nav.py`, `pty_colors.py`, `pty_mouse.py`) |
| Terminal look | `docker/rootfs/etc/tmux/`, `cursor-ttyd`, `opt/orcan/*` |
| Image agent defaults | `docker/rootfs/opt/cursor-defaults/` |
| User docs / theme | `docs/`, `mkdocs.yml`, `overrides/` |
| Public agent index | `scripts/repository/generate-llms-txt.py` → `docs/en/llms.txt` |
| This guidance | `AGENTS.md` / `CLAUDE.md`, `.cursor/rules/` |

**Layout (scan):** `bin/orcan`+`cli/` · `install.sh` · `Dockerfile`+compose ·
`docker/rootfs/` · `cockpit/` (image venv `/opt/orcan-cockpit/venv`) ·
`scripts/repository/` · `scripts/dev/` · `Makefile` · `docs/` · `tests/`

Versioning is explicit. Ordinary commits keep changes under `[Unreleased]`.
For the current development flow, increment the patch metadata and synchronized
mirrors with each intended commit, as requested by the maintainer.
`make tag PART=patch|minor|major` creates and pushes a normal immutable `vX.Y.Z`
change tag with synchronized package metadata and changelog. A tag is not a release.
`make release TAG=vX.Y.Z` declares readiness for that existing remote tag and its
exact SHA through the manually dispatched release workflow. It never bumps versions,
adds CalVer/checkpoint tags, or moves/deletes existing tags. Fix forward with a new
version. Historical tags and changelog sections remain unchanged.

---

## Cockpit / Textual pitfalls (read before UX edits)

Hard-won; `run_test()` / headless `Pilot` often miss these — verify thin chrome via real pty + `pyte` when needed.

- **Box model:** a Textual widget with `height: 1` *and* a single-sided `border-top`/`border-bottom` consumes the whole row (content never appears). `#top-bar` / `#status-bar` are `height: 3` bordered cards for this reason — keep an even height if you re-add a border.
- **tmux status:** `status on` (one row, window tabs). Identity/metrics live in cockpit bars — raw `tmux attach` / `orcan enter --tmux` will not show CPU/RAM/branch. Prefer `status on` over `status 1` (live reload `prefix r` rejects `1`).
- **Alt+1..9:** right-Alt/AltGr on international Windows layouts often fails — use `prefix 0`..`prefix 9` fallback (`keybindings.conf`).
- **Buttons:** override Textual `DEFAULT_CSS` (`border: none; min-width: 0`) for compact rows; very narrow forced `Button` can corrupt a row — prefer `Static` + `on_click` (`#sidebar-toggle`). `Button.press()` debounces ~0.2s — space `pilot.click()` with `pause(0.3)`.
- **`#center`:** no outer padding on `#center` itself (aligns with `#workspaces` / `#top-bar`).
- **`#top-bar-right`:** width from Python via `rich.cells.cell_len()` — avoid `width: auto` / `content-align: right` bugs.
- **Preview file push:** `docker cp` into `orcan-dev-ux` can silently no-op in this sandbox — use `docker exec -i … cat > path < local`.
- **F1 vs `?`:** with embedded terminal focused, `?` is typed into the shell — only **F1** opens shortcuts from there.
- **Browser Alt+arrows:** ttyd/xterm.js and some desktop terminals often deliver Alt+←/→/↑/↓ as Ctrl+arrow (no distinct Meta). Cockpit maps Ctrl/Alt+arrows → focus and Ctrl+Shift+arrows → split (`pty_tmux_nav.py`); F1/`?` footer = `BROWSER_KEY_LIMIT`. Raw `--tmux` keeps conf. See [Terminal UI — nav mix](docs/en/guides/terminal-ui.md#cockpit-nav-mix).
