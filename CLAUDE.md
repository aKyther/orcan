# Orcan — agent context for this repository

You are editing the **Orcan product repo**. Official name: **Orcan** (ids: `orcan`, `ORCAN_*`).
Cursor also applies `.cursor/rules/agents.mdc` (always on).
**Keep `AGENTS.md` and `CLAUDE.md` identical** — Cursor loads `AGENTS.md`; Claude Code loads `CLAUDE.md`.

Public agent index (care / non-goals + doc map): `docs/llms.txt` (`make docs-llms`).
Longer doc map: `docs/en/ai/project-context.md` (+ PL). Change map: `docs/en/change-map.md`.

In a live **orcan workspace** (e.g. `orcan-dev`), also honour that root’s context pack
(`.manifest.json`, session brief, `CONTEXT-ASSERTIONS.md`). After `cd orcan/`, **this file**
is the product SoT for how to change Orcan.

## 30-second map

| | |
| --- | --- |
| **Product** | Work-context orchestrator (workspaces, path parity, context pack) — **not** a model manager |
| **Public API** | `orcan` CLI (`bin/orcan`, `cli/`) — not Make |
| **Config** | JSON only: `orcan.config.json` under `ORCAN_HOME` |
| **Daily ritual** | `orcan init` → `orcan sync` → `orcan build` (when needed) → `orcan up` (**up does not sync**) |
| **UX preview** | `make dev-*` / `scripts/dev/` → isolated `orcan:dev-ux` — **never** the user’s `orcan:latest` |
| **Cockpit** | `cockpit/src/orcan_cockpit/` — top bar (rail + CPU/RAM/clock) \| left: workspaces + ASSERTIONS \| tmux + hints \| bottom: status; **F2** · **`r`** review · **`p`** pause · **`o`** off/on |
| **Image defaults** | `docker/rootfs/` (+ `opt/cursor-defaults/`) ≠ this repo’s `.cursor/rules/` |
| **Done** | Surgical diff; EN+PL docs if behaviour changed; `make validate` · `test-host` · `docs-check`; UX → `dev-checklist` |


**Work-context orchestrator** for Cursor CLI (`agent`), Claude Code (`claude`), and Codex CLI (`codex`) in Docker:

- **Workspaces** — named sets of projects that form one daily job
- **Path parity** — same absolute paths host ↔ container (Docker-from-Docker)
- **Context pack** — ignores, AGENTS/CLAUDE seeds, Context Assertions
- Access: default **local** (`orcan enter`); optional browser (`orcan up --with-ttyd` → ttyd → launcher/cockpit → tmux → zsh)
- Image: `orcan:latest` / `orcan:<VERSION>`; single-agent local builds via `orcan build --claude` / `--cursor` / `--codex`

Story first: `docs/en/why-orcan.md`, `ideas/core-ideas.md`, `ideas/mental-model.md`.

## Pay attention to

- Config is **JSON only** — `orcan.config.json` under `ORCAN_HOME` (default `~/.config/orcan/`)
- Ritual: `orcan init` → `orcan sync` → `orcan build` (when image inputs change) → `orcan up` (**does not** run sync)
- After config with a running container: prefer `orcan sync` (live reconcile when projects sit under `$ORCAN_PROJECTS_ROOT` / `$ORCAN_HOME/workspaces/`). Overlays/flags that need recreate: `orcan down && orcan up`
- Context inbox only (no config/mounts): `orcan sync --context` / `--watch` — host `context_syncd.py`; respects cockpit **`[p]`** / **`[o]`** and cached `model_check` via `automation.json`
- Version SoT: `cockpit/pyproject.toml` → `version`; root `VERSION` is a CLI/image mirror
- Docs: **EN + PL** together; B1–B2; story before commands; `docs/STYLE_GUIDE.md`
- Repo rules (`.cursor/rules/`, this `AGENTS.md`) ≠ image defaults (`docker/rootfs/opt/cursor-defaults/`)
- Host helpers: `scripts/repository/`. Checkout-only UX testing: `scripts/dev/` + `make dev-*` — **not** the public CLI
- **Cockpit box-model gotcha**: a Textual widget with `height: 1` *and* a single-sided `border-top`/`border-bottom` renders the border line only — it consumes the entire row, leaving zero space for the widget's own content, which then silently never appears. `run_test()`/headless checks do **not** catch this (they assert stored widget state, not actual terminal-glyph compositing) — verify any new thin (`height: 1`) bar by decoding real pty output through `pyte`, not just headless `Pilot`. Fixed once already for `#top-bar`/`#hint-strip`/`#status-bar` (see `app.py`) by dropping the border line and keeping only the background-color contrast — don't reintroduce a border on those without re-testing this way.
- tmux's own status line is now `status on` (single row, window tabs only) — the old identity+metrics row (`status-left.sh`/`status-right.sh`) was trimmed as redundant with the cockpit's top/bottom bars (see `docker/rootfs/etc/tmux/status.conf` header). A raw `tmux attach`/`orcan enter --tmux` outside the cockpit will not show CPU/RAM/branch/AI-usage at all — deliberate, not a bug. Also: `set -g status 1` errors (`unknown value: 1`) on a **live reload** (`prefix r`) even though it's valid on fresh load — use `status on`, tmux's canonical form, which works both ways.
- Alt+1..9 window-select can silently fail to reach tmux depending on the client: right-Alt/AltGr on international Windows keyboard layouts reports as synthetic Ctrl+Alt and gets eaten by the OS/xterm.js as character composition, not a terminal Meta combo. `prefix 0`..`prefix 9` (layout-independent) exists specifically as the reliable fallback — see `keybindings.conf`'s comment above the `M-1`..`M-9` binds.
- Textual's `Button` `DEFAULT_CSS` carries `border: tall` (renders as thick half-block rows above/below the label) *and* `min-width: 16` — both must be overridden (`border: none; min-width: 0;`) for any compact custom button row, or `width: 1fr` siblings won't actually split evenly and the button looks "giant" (see `#activity-actions` in `app.py`/`activity.py`'s Review/Pause/Turn-off row). A very narrow (`width: 1`) forced `Button` can even corrupt that whole terminal row's compositing (confirmed via real pty+pyte) — prefer a plain `Static` + `on_click` there instead (see `#sidebar-toggle`).
- `Button.press()` adds a `-active` CSS class for `active_effect_duration` (0.2s) and a second click on the *same* button inside that window is silently dropped (`_on_click` no-ops while `-active`). A test that fires `pilot.click()` twice back-to-back on one button needs `await pilot.pause(0.3)` between clicks or the second click never happens — not a wiring bug, Button's own debounce.
- `docker cp` into the `orcan-dev-ux` preview container silently no-ops in this sandbox (exits 0, file never lands — confirmed by `docker exec ... ls` afterward). Use `docker exec -i <container> sh -c 'cat > /path' < local_file` instead to push a file in for a quick live check.
- `#center`'s cards (`#center-stack`, `#hint-strip`) must carry **no outer padding on `#center` itself** — `#workspaces` (the analogous sidebar column) has none either, only its cards' own internal `padding: 0 1`. Outer padding on `#center` makes its cards render narrower than `#top-bar`'s true full-width span, which is what "cards don't line up" reports usually are.
- `#top-bar-right`'s width is set from Python (`top_bar.py`'s `refresh_metrics()`, via `rich.cells.cell_len()`), not a CSS width — `width: auto` and `content-align: right` + `width: 1fr` both have real Rich/Textual bugs (duplicate the last character at the boundary); a static oversized CSS width avoids those bugs but leaves a visible gap before the card edge. Exact-width-from-Python avoids both problems at once.

## Do not invent / non-goals

- Model selection, provider abstraction, or auto-routing between agent CLIs
- Image registry product / CI image publish — users `install.sh` + `orcan build`; `orcan publish` is manual
- YAML user profiles, `host-deps`, `requirements-host.txt`
- Documenting deprecated user Make targets to end users — they use **`orcan`**
- Confusing `make dev-*` / `.orcan-dev-ux/` with a normal `orcan:latest` install
- Auto-rewriting mounted git repos on every container start
- Drive-by refactors, speculative abstractions, or docs that invent commands/flags

## Ritual (host)

```bash
orcan init                  # or: context add / context tui / edit orcan.config.json
orcan sync                  # apply config → .env, mounts/*, workspaces/*
orcan build                 # after Dockerfile | docker/rootfs | cockpit image inputs
orcan up                    # daily; local enter by default; --with-ttyd for browser
orcan migrate [--yes]       # optional managed-root move (dry-run without --yes)
```

Release (maintainers): `make bump-patch` → update `CHANGELOG.md` → commit → `make release`.

## Runtime stack (container)

```text
orcan enter → agent-launcher (cockpit: top bar + workspaces/ASSERTIONS | tmux + status)
             → tmux 3.6a → zsh (+ navy/cyan chrome)

container CMD → orcan-supervisord → keepalive|ttyd + context-scan (background)
optional: ttyd → same launcher stack   # orcan up --with-ttyd
```

- Cockpit: **F2** ASSERTIONS section, **F4** workspaces, **F3** Git, **F1**/`?` shortcuts, **`r`** review, **`p`** pause, **`o`** off/on automation; embed forwards **C-Space** / **Alt+1…9**; resize must SIGWINCH (see `docs/en/guides/terminal-ui.md` `#cockpit-browser`)
- Shortcut SoT: `cockpit/src/orcan_cockpit/shortcuts.py` (+ tmux `keybindings.conf`); ASSERTIONS UI: `activity.py`
- Terminal UI map: `docs/en/guides/terminal-ui.md` (+ PL); rule `.cursor/rules/terminal-ui.mdc`
- Cockpit package: `cockpit/` (uv); image venv `/opt/orcan-cockpit/venv`; shim `agent-launcher`
- Iterate UX **without** touching daily install:

```bash
make dev-start         # isolated orcan:dev-ux (default :17681; auto-picks free port)
make dev-restart       # after cockpit UX edits (loads checkout source)
make dev-doctor        # isolation + health + HTTP + checkout cockpit source
make dev-smoke         # Textual + embedded tmux PTY
make dev-a11y          # Playwright focus/axe + 480x320 (needs running preview)
make dev-visual        # Playwright screenshot regression (needs running preview)
make dev-checklist      # pre-merge automated + manual browser checks
make dev-stop
make dev-test          # separate stack; assert orcan-1 unchanged (needs image)
./scripts/dev/terminal-ui-preview   # tmux chrome only (no Docker)
```

Details: `docs/en/development/testing.md`, `docs/en/reference/makefile.md`.

## Runtime modification

Adding/removing a project/workspace under the two stable mounts does **not** require recreate — see `docs/en/ideas/runtime-reconcile.md` / mental model.

- `orcan.reconcile.apply_workspaces()` — boot (`init-workspace`) and on demand (`orcan-runtime-reconcile` via `orcan sync`)
- Tmux: `orcan-tmux-reconcile-sessions` creates missing sessions; orphans reported (kill only with `orcan sync --prune-orphans`)
- Read-only desired vs actual: `orcan-runtime-status`

## Agent handoff vs Context Assertions

| Mechanism | Path / tool | Role |
| --- | --- | --- |
| Agent inbox | `<workspace>/.orcan/tasks/` · `orcan-inbox` | Structured task handoff (not chat dumps) |
| Context Assertions | `.orcan/context-inbox/` → `CONTEXT-ASSERTIONS.md` | Human-approved lasting context |

Do not merge these systems. Docs: `docs/en/ideas/agent-inbox.md`, `ideas/context-assertions.md`.

## Where to change what

| Change | Place |
| --- | --- |
| Public CLI | `bin/orcan`, `cli/` |
| Host helpers / validate / release | `scripts/repository/` |
| Developer UX environment | `scripts/dev/`, `make dev-*` |
| Image filesystem / binaries | `docker/rootfs/` |
| Image packages / agents | `Dockerfile` |
| Cockpit TUI | `cockpit/src/orcan_cockpit/` (`shortcuts.py`, `activity.py`, `top_bar.py`, `pty_keys.py`, `pty_colors.py`) |
| Session recap | `docker/rootfs/usr/local/lib/orcan/recap.py`, `orcan-context-recap` (driver: `ORCAN_CONTEXT_DRIVER`) |
| Recap model probe | `docker/rootfs/usr/local/lib/orcan/context_model_check.py`, `orcan-context-model-check` |
| Automation control | `docker/rootfs/usr/local/lib/orcan/automation.py`, `$ORCAN_DATA/history/supervisor/automation.json` |
| Supervisord / context-scan | `docker/rootfs/usr/local/bin/orcan-supervisord`, `orcan-context-scan` |
| Terminal look | `docker/rootfs/etc/tmux/`, `cursor-ttyd`, `opt/orcan/*` — see Terminal UI guide |
| Image agent defaults | `docker/rootfs/opt/cursor-defaults/` |
| Context Assertions compile | `scripts/repository/context_assertions.py`, `compile_context.py` |
| Context Assertions reflection scan | `docker/rootfs/usr/local/lib/orcan/session_scan.py`, `orcan-context-scan` |
| User docs / theme | `docs/`, `mkdocs.yml`, `overrides/` |
| Public agent index | `scripts/repository/generate-llms-txt.py` → `docs/llms.txt` |
| This guidance | `AGENTS.md` / `CLAUDE.md` (identical), `.cursor/rules/` |

## File map (short)

| Path | Role |
| --- | --- |
| `bin/orcan`, `cli/` | Public CLI |
| `install.sh` | curl\|bash installer |
| `Dockerfile`, `docker-compose*.yml` | Image + runtime overlays |
| `docker/rootfs/` | Files in the image |
| `cockpit/` | Cockpit uv project |
| `scripts/repository/` | Host product helpers |
| `scripts/dev/` | Checkout-only previews |
| `Makefile` | Maintainer + `dev-*` |
| `docs/` | MkDocs EN+PL |
| `tests/` | Host / smoke / path-parity |
| `.cursor/rules/` | Cursor rules for **this** repo |

## Definition of done

1. Small, surgical diff — only what the request needs
2. Behaviour/interface change → update **EN + PL** docs (+ `CHANGELOG.md` `[Unreleased]` when user-visible)
3. UX/cockpit changes → prefer `make dev-restart` (checkout-mounted cockpit) over the user’s daily stack; verify with `make dev-smoke` / `dev-a11y` / `dev-visual` (see `make dev-checklist`)
4. `llms.txt` care/non-goals changed → edit generator, then `make docs-llms`
5. If you change this file → copy the same content to `CLAUDE.md` (Claude Code loads it)
6. Run and report:

```bash
make validate
make test-host
make docs-check          # when docs / public surface changed
make test                # when Docker/image behaviour changed and Docker is available
./bin/orcan help         # / doctor as needed
```

Label what ran, what did not, and environment limits. Do not claim success without running the check.

## Commits

No `Co-Authored-By` (or similar AI-attribution) trailer. The human is the sole author of record.
