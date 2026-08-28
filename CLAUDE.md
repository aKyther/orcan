# Orcan — agent context for this repository

You are editing the **Orcan product repo**. Official name: **Orcan** (ids: `orcan`, `ORCAN_*`).
Cursor also applies `.cursor/rules/agents.mdc` (always on).
**Keep `AGENTS.md` and `CLAUDE.md` identical** — Cursor loads `AGENTS.md`; Claude Code loads `CLAUDE.md`.

Public agent index: `docs/llms.txt` (`make docs-llms`).
Longer maps: `docs/en/ai/project-context.md`, `docs/en/change-map.md` (+ PL).

In a live **orcan workspace** (e.g. `orcan-dev`), honour that root’s context pack
(`.manifest.json`, session brief, `CONTEXT-ASSERTIONS.md`) first. After `cd orcan/`,
**this file** is the product SoT for how to change Orcan.

---

## What this is

**Work-context orchestrator** for coding agents in Docker — **not** a model manager.

| Piece | Meaning |
| --- | --- |
| **Workspace** | Named set of projects = one daily job / tmux session |
| **Path parity** | Same absolute paths host ↔ container (Docker-from-Docker) |
| **Context pack** | Ignores, AGENTS/CLAUDE seeds, human-approved Context Assertions |
| **Access** | Default **local** (`orcan enter`); optional browser (`orcan up --with-ttyd`) |
| **Agents inside** | Cursor CLI (`agent`), Claude Code (`claude`), Codex (`codex`) — tools, not models Orcan picks |

**Non-goals (do not invent):** model selection / provider routing; CI image publish /
registry-as-product; YAML user config / host-deps; treating `make dev-*` as the public
CLI; auto-rewriting mounted git repos on every start; drive-by refactors or invented flags.

Story: `docs/en/why-orcan.md` → `ideas/core-ideas.md` → `ideas/mental-model.md`.

### 30-second map

| | |
| --- | --- |
| **Public API** | `orcan` CLI (`bin/orcan`, `cli/`) — not Make |
| **Config** | JSON only: `orcan.config.json` under **`ORCAN_HOME`** (default `~/.config/orcan/`). Tool data / history: **`ORCAN_DATA`** (same default root; see `orcan help`) |
| **Ritual** | `orcan init` → `orcan sync` → `orcan build` (when needed) → `orcan up` (**up does not sync**) |
| **Runtime** | `orcan enter` → cockpit (`agent-launcher`) → tmux 3.6a → zsh; CMD = `orcan-supervisord` (keepalive\|ttyd + `context-scan`/`recap`) |
| **Cockpit** | Top: `🌀 orcan` (click = **About**) + 🔔 Problems/? + metrics · Left: workspaces + glance + ASSERTIONS (agents + decisions timeline) · Center: tmux · Bottom: status. Keys: **F2** · **F4**/‹› · **F1**/? shortcuts (**?** outside terminal) · **F5** peek brief/pending · **`i`** · **`r`** / **`p`** / **`o`** · **`lg`** (no F3) |
| **UX preview** | `make dev-*` / `scripts/dev/` → isolated `orcan:dev-ux` — **never** the user’s `orcan:latest` |
| **Image ≠ repo rules** | Image defaults: `docker/rootfs/` (+ `opt/cursor-defaults/`). Repo rules: `.cursor/rules/` + this file |
| **Done** | Surgical diff; EN+PL docs if behaviour changed; `make validate` · `test-host` · `docs-check`; UX → `dev-checklist` |

---

## How to work

```bash
orcan init                  # or: context add / context tui / edit orcan.config.json
orcan sync                  # ALWAYS after config — apply → .env, mounts/*, workspaces/*
orcan build                 # after Dockerfile | docker/rootfs | cockpit image inputs
orcan up                    # daily; --with-ttyd for browser
orcan sync --context        # inbox/compile only (host); respects [p]/[o]/model_check
orcan migrate [--yes]       # optional managed-root move (dry-run without --yes)
```

Live reconcile often avoids recreate for projects under `$ORCAN_PROJECTS_ROOT` /
`$ORCAN_HOME/workspaces/` — see `docs/en/ideas/runtime-reconcile.md`. **`orcan sync`**
always reconciles workspace meta on the **host** (`reconcile-host.py`); when the
container is up it also runs live reconcile in-container. Overlays that need recreate:
`orcan down && orcan up`.

```text
orcan enter → agent-launcher (cockpit) → tmux 3.6a → zsh
container CMD → orcan-supervisord → keepalive|ttyd + context-scan (recap default)
```

- Shortcut SoT: `cockpit/src/orcan_cockpit/shortcuts.py` (+ tmux `keybindings.conf`)
- ASSERTIONS UI: `activity.py`; Problems: `problems.py`; timeline: `timeline.py`; Peek: `peek.py` / `peek_modal.py`
- Reflection loop feedback (ASSERTIONS / Peek): `reflection_feedback.py`
- First-run tip: `first_run.py` / `onboarding.py` (flag under `~/.local/share/orcan/`)
- Chrome: `top_bar.py`, `rail.py`, `status_bar.py`, `tmux_chrome.py`, `session_glance.py`
- Terminal UI guide: `docs/en/guides/terminal-ui.md` (+ PL); rule `.cursor/rules/terminal-ui.mdc`
- Version SoT: `cockpit/pyproject.toml` → `version`; root `VERSION` is a mirror
- Docs: **EN + PL** together; B1–B2; story before commands; `docs/STYLE_GUIDE.md`

### Agent inbox vs Context Assertions

| Mechanism | Path / tool | Role |
| --- | --- | --- |
| Agent inbox | `<workspace>/.orcan/tasks/` · `orcan-inbox` | Structured task handoff (not chat dumps) |
| Context Assertions | `.orcan/context-inbox/` → `CONTEXT-ASSERTIONS.md` | Human-approved lasting context |

Do not merge these systems. Docs: `docs/en/ideas/agent-inbox.md`, `ideas/context-assertions.md`.

### UX preview (checkout only)

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
2. Behaviour/interface change → update **EN + PL** docs (+ `CHANGELOG.md` `[Unreleased]` when user-visible)
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
| Host helpers / validate / release | `scripts/repository/` |
| Host workspace reconcile / audit | `scripts/repository/reconcile-host.py`, `workspace-audit.py`; core `docker/rootfs/usr/local/lib/orcan/reconcile.py` |
| Developer UX environment | `scripts/dev/`, `make dev-*` |
| Image filesystem / binaries | `docker/rootfs/` |
| Image packages / agents | `Dockerfile` |
| Cockpit TUI | `cockpit/src/orcan_cockpit/` (`shortcuts.py`, `about_modal.py`, `activity.py`, `session_glance.py`, `problems.py`, `timeline.py`, `peek.py`, `peek_modal.py`, `reflection_feedback.py`, `first_run.py`, `onboarding.py`, `tmux_chrome.py`, `top_bar.py`, `pty_keys.py`, `pty_tmux_nav.py`, `pty_colors.py`, `pty_mouse.py`) |
| Session recap | `docker/rootfs/usr/local/lib/orcan/recap.py`, `orcan-context-recap` (`ORCAN_CONTEXT_DRIVER`) |
| Recap model probe | `docker/rootfs/usr/local/lib/orcan/context_model_check.py`, `orcan-context-model-check` |
| Automation control | `docker/rootfs/usr/local/lib/orcan/automation.py`, `$ORCAN_DATA/history/supervisor/automation.json` |
| Supervisord / context-scan | `orcan-supervisord`, `orcan-context-scan`, `docker/rootfs/usr/local/lib/orcan/session_scan.py` |
| Context Assertions compile | `scripts/repository/context_assertions.py`, `compile_context.py` |
| Host context sync | `scripts/repository/context_syncd.py` (`orcan sync --context`) |
| Terminal look | `docker/rootfs/etc/tmux/`, `cursor-ttyd`, `opt/orcan/*` |
| Image agent defaults | `docker/rootfs/opt/cursor-defaults/` |
| User docs / theme | `docs/`, `mkdocs.yml`, `overrides/` |
| Public agent index | `scripts/repository/generate-llms-txt.py` → `docs/llms.txt` |
| This guidance | `AGENTS.md` / `CLAUDE.md`, `.cursor/rules/` |

**Layout (scan):** `bin/orcan`+`cli/` · `install.sh` · `Dockerfile`+compose ·
`docker/rootfs/` · `cockpit/` (image venv `/opt/orcan-cockpit/venv`) ·
`scripts/repository/` · `scripts/dev/` · `Makefile` · `docs/` · `tests/`

Three tiers, on explicit maintainer request only — never implied by "fix
this" / "test this":

- Regular commits (incl. fixes pushed out just to test somewhere) do
  **not** bump the version or tag — commit normally; `CHANGELOG.md`
  entries stay under `[Unreleased]`.
- `make tag` (`PART=patch|minor|major`, default patch) — a personal,
  frequent SemVer checkpoint: bumps + moves `[Unreleased]` into
  `[X.Y.Z]` + commits + tags, **fully pushed** (commit and tag both
  reach origin — nothing local-only). The tag lives under
  `checkpoint/vX.Y.Z`, not bare `vX.Y.Z`, so it stays invisible to
  `orcan update`/`downgrade` (they only match `^v[0-9]+\.[0-9]+\.[0-9]+$`)
  and to `release.yml`'s `v*.*.*` trigger — a checkpoint can never become
  an update target or fire a release on its own.
- `make release` (`Q=YY.Q`, default: current quarter) — the rare,
  deliberate public stop. Ensures a real, pushed bare `vX.Y.Z` tag
  exists (creating one if `make tag` hasn't already — this is what CI /
  `orcan update`/`downgrade` / GitHub Releases key off, unchanged),
  pushes a second bare CalVer tag (e.g. `26.3`) at the same commit, and
  adds a CHANGELOG divider + extra mike docs alias.

---

## Cockpit / Textual pitfalls (read before UX edits)

Hard-won; `run_test()` / headless `Pilot` often miss these — verify thin chrome via real pty + `pyte` when needed.

- **Box model:** a Textual widget with `height: 1` *and* a single-sided `border-top`/`border-bottom` consumes the whole row (content never appears). `#top-bar` / `#hint-strip` / `#status-bar` use background contrast only — do not reintroduce borders without pty verification.
- **tmux status:** `status on` (one row, window tabs). Identity/metrics live in cockpit bars — raw `tmux attach` / `orcan enter --tmux` will not show CPU/RAM/branch. Prefer `status on` over `status 1` (live reload `prefix r` rejects `1`).
- **Alt+1..9:** right-Alt/AltGr on international Windows layouts often fails — use `prefix 0`..`prefix 9` fallback (`keybindings.conf`).
- **Buttons:** override Textual `DEFAULT_CSS` (`border: none; min-width: 0`) for compact rows; very narrow forced `Button` can corrupt a row — prefer `Static` + `on_click` (`#sidebar-toggle`). `Button.press()` debounces ~0.2s — space `pilot.click()` with `pause(0.3)`.
- **`#center`:** no outer padding on `#center` itself (aligns with `#workspaces` / `#top-bar`).
- **`#top-bar-right`:** width from Python via `rich.cells.cell_len()` — avoid `width: auto` / `content-align: right` bugs.
- **Preview file push:** `docker cp` into `orcan-dev-ux` can silently no-op in this sandbox — use `docker exec -i … cat > path < local`.
- **F1 vs `?`:** with embedded terminal focused, `?` is typed into the shell — only **F1** opens shortcuts; hint strip shows `F1` only in terminal context.
- **Browser Alt+arrows:** ttyd/xterm.js and some desktop terminals often deliver Alt+←/→/↑/↓ as Ctrl+arrow (no distinct Meta). Cockpit maps Ctrl/Alt+arrows → focus and Ctrl+Shift+arrows → split (`pty_tmux_nav.py`); F1/`?` footer = `BROWSER_KEY_LIMIT`. Raw `--tmux` keeps conf. See [Terminal UI — nav mix](docs/en/guides/terminal-ui.md#cockpit-nav-mix).
