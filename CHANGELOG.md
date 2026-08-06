# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2026-08-06

### Added

- `orcan init`/config-wizard UX pass, pure stdlib — no new dependency:
  - Tab-completion for directory-path prompts (`readline`, directories only,
    `~` preserved as typed rather than expanded on screen). Degrades to
    plain `input()` if `readline` isn't available.
  - ANSI colors: cyan/bold section headings, green `✓` for completed steps
    (`success()`, indent-preserving — a `"  "`-prefixed message keeps its
    indent *before* the mark), red for warnings/errors, yellow for the
    project-adding sub-step (visually distinct from the workspace-adding
    stage's cyan heading). Off automatically for `ORCAN_NO_COLOR` or a
    non-tty stream — same convention as `cli/lib/log.sh`.
  - Host-side (`scripts/repository/config-wizard.py`), so — unlike
    container-side tools — this is live immediately, no `orcan build`/
    container recreate needed.
  - Tests: `tests/host/test_config_wizard.py` (`SuccessIndentTests`,
    `ColorGatingTests`, `PathCompleterTests`).
  - When creating a new managed worktree, offers a fast-forward-only
    `git pull` of the source repo's currently-checked-out branch first
    (default yes) — so a new worktree branches from fresh `HEAD`, not a
    stale local `master`/`main`. Silent no-op on detached HEAD; a dirty
    tree, missing upstream, or a non-fast-forward pull are reported and
    skipped rather than failing the wizard. New
    `git_worktrees.py::pull_current_branch()` /`current_branch()`,
    `config-wizard.py::_offer_pull_before_worktree()`. Tests:
    `tests/host/test_git_worktrees.py` (`PullCurrentBranchTests`, real
    bare-remote fast-forward integration test), `test_config_wizard.py`
    (`OfferPullBeforeWorktreeTests`).
- Default `lazygit` config (`docker/rootfs/opt/orcan/lazygit-config.yml`,
  missing-only copy to `~/.config/lazygit/config.yml` on container start,
  same idiom as `/opt/orcan/gitconfig`): `git.paging.useConfig: true` so
  lazygit reuses git's own `delta` pager instead of a separately specified
  one (avoids the two configs drifting apart); `update.method: never` since
  lazygit's version is pinned by the image's `LAZYGIT_VERSION` build arg,
  not upgradable in place; `disableStartupPopups: true`. No nerd-font icons
  set — the image doesn't bundle one, so `gui.nerdFontsVersion` stays unset.
- `orcan-context-review`: best-effort duplicate/conflict pre-check before
  showing pending candidates. One batched `claude -p --model haiku` call
  (in-container only — `claude` isn't guaranteed on whatever host machine
  `orcan` itself runs on) compares every pending candidate against
  `CONTEXT-ASSERTIONS.md`; a flagged candidate gets one extra line
  (`⚠ possibly duplicates existing: "..."` / `⚠ may conflict with existing:
  "..."`) above its usual detail block. Purely informational — decision
  mechanics (`[y]es/[n]o/[s]kip` → `.orcan/context-decisions/*.json` →
  applied by the next `orcan sync`) are unchanged; the check never skips,
  blocks, or decides anything, and silently no-ops if `claude` is missing,
  the call fails/times out, or `CONTEXT-ASSERTIONS.md` doesn't exist yet.
  Skip it with `--no-check`. Tests: `tests/host/test_context_review.py`.
- `orcan-context-review`: consolidation offer, building on the pre-check
  above. The same model call that flags a candidate `duplicate`/`conflict`
  now also drafts a merged replacement (no second call). Accepting that
  candidate triggers one more prompt — queue the drafted merge and flag the
  overlapping existing item for retirement? A "yes" calls
  `orcan-context-propose` twice more (a `--queue` proposal for the merged
  text, tagged `--source consolidation` — new valid value alongside
  `manual`/`reflection` — and a `--flag-existing` on the superseded item),
  going through the same review cycle as any other drop; nothing merges or
  retires immediately. Keeps the store a de-duplicated body of knowledge
  instead of a purely linear log. Tests: `tests/host/test_context_review.py`.
- `orcan sync`: prints a one-line summary per workspace after compiling —
  `context: N assertion(s) compiled into CONTEXT-ASSERTIONS.md for workspace
  '<name>'` (or `context: 0 assertions compiled for workspace '<name>'`).
  Previously the only way to see what the Applicability Layer actually
  matched was `orcan context assert select --workspace NAME --project PATH
  [...]` (still there, still the tool for previewing *before* running sync).
  `scripts/repository/compile_context.py::compile_workspace()`. Tests:
  `tests/host/test_compile_context.py`.
- `orcan-context-review`: reviews fresh, undecided drops straight from
  `.orcan/context-inbox/` too, not only the host-generated
  `context-review-queue.json` — no prior `orcan sync` needed for these,
  since a propose drop already carries its full content. `[y]es/[n]o`
  rewrites the drop's own `"decision"` field in place, exactly what
  interactive `orcan-context-propose` already does by hand
  (`docker/rootfs/usr/local/bin/orcan-context-propose`'s `prompt_decision()`
  → `payload["decision"]`); `compile_context.py::_process_inbox()` already
  honored that field (propose + accept/reject in one pass) — this was
  previously only reachable one candidate at a time via the interactive
  propose prompt, now `orcan-context-review` batches it. Collapses "sync →
  review → sync" into "review → sync" for anything proposed in-container
  (by hand or by the Reflection hook) that hasn't been synced yet. Queue-
  based candidates (already imported, or proposed straight from the host)
  and `reconsider` items are unaffected — those still need the prior sync,
  since the container has no other way to see a store id or an existing
  accepted item's content. Both sources merge into one reviewed list; the
  header names how many came from each when both are present. New functions
  in `orcan-context-review` itself: `load_inbox_candidates()`,
  `write_inbox_decision()`. Tests: `tests/host/test_context_review.py`.

### Fixed

- `orcan context hook enable|disable|status`: retargeted from a project
  checkout's `.claude/settings.json` to the workspace's generated root
  `.claude/settings.json` (`scripts/repository/claude_hook.py`). Claude Code
  loads hooks once, at launch, from the directory it was started in — and
  every `orcan up` tmux window starts at the workspace root
  (`cursor-tmux-workspace-attach -c "${WORKSPACE_ROOT}"`), never inside a
  project checkout. The old per-project placement meant the `Stop` hook
  (`orcan-context-reflect`, batched Reflection) never actually fired in the
  default multi-window workflow. Command now takes workspace name(s)
  (`--all` for every workspace) resolved via `.orcan/workspace.manifest.json`
  instead of project paths; requires `orcan sync` to have run at least once
  for that workspace. `orcan up`'s post-start summary now reports one
  workspace-level hook status instead of a per-project list. Output lines
  now also print the workspace's full generated-root path, not just its
  name. With no `WORKSPACE`/`--all` given, the command now first tries to
  infer the workspace from `cwd` (matching it against registered
  `projects[].path` in the manifest — same idea as `orcan-context-reflect`'s
  own project inference), so running it from inside a project checkout
  scopes to just that project's workspace. If `cwd` matches nothing:
  `status` (read-only) falls back to showing every configured workspace,
  with an explicit `Note:` line so the listing never reads as if it were
  about `cwd`; `enable`/`disable` (mutating) still require an explicit
  target once there's more than one workspace, to avoid toggling the hook
  everywhere by accident.

## [0.4.1] - 2026-08-04

### Added

- `/do <rough draft>` slash command + `prompt-refiner` subagent, seeded into
  every workspace's `~/.claude/{agents,commands}` at container start
  (`docker/rootfs/opt/claude-defaults/`, copied by the new
  `init-claude-home`, missing-only — same idiom as `init-cursor-home`).
  `/do` hands your raw draft to the cheap `prompt-refiner` subagent (haiku),
  which compiles it into a minimal `Goal:`/`Constraints:`/`Validation:`
  prompt preserving intent exactly (no invented requirements, no scope
  changes, defers to "inspect the repository" instead of guessing), then
  executes the compiled version in the same turn — the raw draft is treated
  as non-authoritative once refined. Not a token-saving mechanism (the raw
  draft still enters the orchestrating agent's context the moment `/do`
  fires) — see `orcan-prompt-clean` below for that case.
- `orcan-prompt-clean` (container CLI): manual, out-of-session variant of
  the same prompt-compiler instruction — pipe or type a rough draft, get
  the compiled prompt on stdout, paste it yourself. Exists because Claude
  Code's `UserPromptSubmit` hook can only add context alongside a prompt,
  not replace it (anthropics/claude-code#27365), so true token savings need
  the draft to never enter an interactive session's context at all.
- `orcan init`/wizard: `uv init`/`poetry init`-style default — when the
  current directory isn't already mounted anywhere in the config, it's
  suggested as the workspace name and project path (Enter-Enter accepts it).
  Pure logic in `suggest_cwd_project()` (`scripts/repository/config-wizard.py`),
  wired into "create new config", "add workspace" and "add another
  workspace" — never re-suggested once cwd is already registered in the
  in-progress config.
- `orcan init`/wizard: when the current directory *is* already registered,
  it says so in one line (workspace/project name + path) and exits — `orcan
  init` still runs `sync` right after, but doesn't force you through a
  reconfigure flow. Answering "y" to "Change anything?" falls through to the
  normal edit menu as before. (`find_cwd_match()`.)

- `orcan context hook enable|disable|status [PATH ...] [--all] [--dry-run]`
  (`scripts/repository/claude_hook.py`): host-side, stdlib-only toggle for
  the optional Claude Code `Stop` hook (`orcan-context-reflect`, batched
  Reflection). Merges/removes `hooks.Stop` in a project's
  `.claude/settings.json` idempotently, backs up the file before writing,
  takes effect immediately — no `orcan sync` needed, no container required.
  Claude-only by design (Cursor CLI's own `stop` hook is not reliably wired
  in headless mode as of this writing, and Cursor already sees Reflection's
  output passively via the `AGENTS.md`/`CLAUDE.md` pack — see
  `docs/en/ideas/context-assertions.md`). Replaces the old manual copy of
  `docker/rootfs/opt/cursor-defaults/templates/claude/hooks.example.json`
  (removed).

### Changed

- **Breaking:** `orcan context wizard` is gone. `orcan init` is now the one
  entry point: with no `PATH` it launches the interactive config wizard
  (create a new `orcan.config.json`, or edit an existing one — same as the
  old `context wizard`); `orcan init PATH` keeps the previous non-interactive
  scaffold for scripts/CI. Running `orcan context wizard` prints a pointer to
  `orcan init` and exits non-zero.

## [0.4.0] - 2026-08-04

### Added

- Default ttyd font size `19` (was `22`).
- ttyd reconnect resilience: `agent-launcher` auto-reattaches to the last
  workspace after a WebSocket drop (2s countdown; Enter → menu;
  `ORCAN_AUTO_REATTACH=0` to disable). `TTYD_PING_INTERVAL` /
  `ttyd.ping_interval` defaults to 20s (was ttyd's built-in 5s).
- Context Assertions (RFC-0001): `orcan context assert propose|list|show|accept|reject|retire|select` —
  human-approved, conditional statements the Context Compiler may fold into a
  workspace's Context Pack. Each assertion is anchored to a project (storage
  only) and carries an applicability predicate (workspace / repo-set /
  branch / date window) evaluated fresh per workspace at `orcan sync` time —
  so the same repo can carry different, non-conflicting assertions across
  different workspaces. No automatic acceptance; store is git-versioned
  under `$ORCAN_DATA/context/<project-id>/`. `orcan sync` compiles matches
  into `CONTEXT-ASSERTIONS.md` at the workspace root, surfaced from
  `AGENTS.md`/`CLAUDE.md` when present. Identity is keyed by each repo's git
  common-dir, not its working-copy path, so a branch worktree
  (`orcan context worktree create`) shares its store with the main
  checkout — refined by the existing `branch` applicability atom — instead
  of starting from an empty one. `orcan-context-propose` / `orcan-context-review`
  (in-container) let you draft and decide without a host terminal: they drop
  JSON files into a mounted inbox (`<workspace_root>/.orcan/context-inbox/`,
  `context-decisions/`); `orcan sync` imports them (quarantining anything
  malformed or unresolvable instead of failing) and regenerates
  `context-review-queue.json` before compiling. Proposing — interactively or
  from an automated post-task reflection step — never implies acceptance;
  only a human decision (immediate or queued) does.
  `orcan-context-propose --flag-existing ID --reason TEXT` marks an
  already-`accepted` assertion for reconsideration without touching the
  store; `orcan-context-review` offers `[k]eep`/`[r]etire` for it — retiring
  is always a human decision, never automatic.
  `orcan-context-reflect` adds batched, automated Reflection: an opt-in
  Claude Code `Stop` hook (template:
  `docker/rootfs/opt/cursor-defaults/templates/claude/hooks.example.json`,
  not applied by default) that tracks a per-session turn counter and
  transcript offset in `reflection-state.json`, stays a near-zero-cost no-op
  below the threshold (default 20 turns), and at the threshold asks a
  lightweight model (`claude -p --model haiku`) to compare recent activity
  against the workspace's current `CONTEXT-ASSERTIONS.md` and queue
  candidates/flags through the same propose tool — never accepting anything
  itself. `--force` runs it on demand regardless of the counter.
  RFC-0002 extends the Context Assertion record itself: `epistemic_status`
  (`fact`/`interpretation`/`hypothesis`/`conclusion`), `criticality`
  (`normal`/`high`), and typed `relations` (`depends_on`/`risk_of`/
  `supersedes`/`conflicts_with`) to an existing accepted assertion — all
  proposable (including by `orcan-context-reflect`) but only human-correctable
  at accept time, never system-inferred. The Applicability Layer does one
  bounded 1-hop traversal: a matched assertion's `accepted` relation targets
  are pulled in too, but only when the target's project is mounted in the
  same workspace, and never past the existing item-count limit. See
  [docs/en/ideas/context-assertions.md](docs/en/ideas/context-assertions.md).

### Fixed

- Git worktree projects (`orcan context worktree create`, or any project
  path that happens to be a linked worktree) now also bind-mount their main
  repo's `.git` directory. A worktree's own `.git` is only a pointer file
  into that shared git dir (object database, refs, per-worktree metadata);
  without it mounted too, every git command inside the worktree failed with
  `fatal: not a git repository`. `apply-config.py` resolves this by reading
  the worktree's `.git` pointer directly (no `git` subprocess needed, since
  git isn't usable there yet) — works for any worktree regardless of how it
  was created, not only ones Orcan itself tracked. Deliberately mounts only
  `<main-repo>/.git`, never the main checkout's working-tree files — a
  feature-branch worktree must not also expose the main branch's checked-out
  files, or `orcan context worktree create`'s isolation would be pointless.

## [0.3.2] - 2026-07-29

### Added

- `orcan enter` (alias `go-in`): local terminal into the running container — launcher / `--shell` / `--tmux`
- User **dotfiles** under `$ORCAN_DATA/dotfiles` (aliases, zsh/bashrc snippets, tmux/vim/starship/git overlays); image defaults stay

### Changed

- Rename workspace picker to `agent-launcher` (`cursor-launcher` remains a compatibility symlink)
- Docs: local attach alongside ttyd (`orcan enter`, workflows, quickstart, FAQ)

## [0.3.1] - 2026-07-28

### Added

- Image tooling for agents: `gh`, `openssh-client`, `rsync`, `sqlite3`, `ast-grep` (`sg`); `USE_BUILTIN_RIPGREP=0` so Claude prefers system `rg`

### Fixed

- `orcan sync`: `DOCKER_GID` (and host UID/GID) no longer stuck at stale `.env` values — re-detect after sourcing `.env` (socket GID was overwritten by `999` from `.env.example`)

## [0.3.0] - 2026-07-28

### Added

- In-container git identity matches the host: `orcan sync` copies global `user.name` / `user.email` into `GIT_AUTHOR_*` / `GIT_COMMITTER_*`
- `orcan up --with-git`: mount host `~/.ssh` (and SSH agent when `SSH_AUTH_SOCK` is set) for push/pull — same pattern as `--with-docker`; both flags print a security warning (agents inside can use the mounted socket/keys)
- Git worktree helpers for context: `orcan context worktrees`, `add --from-worktree`, `worktree create`; wizard can offer existing worktrees
- Managed worktrees under `$ORCAN_DATA/worktrees/<workspace>/<project>/` (`orcan context worktree`; wizard mounts paths by default with optional worktree help)
- Wizard worktree create: detect branch/path conflicts, explain, then retry / use existing / mount original

### Changed

- Config wizard UX: quick map + numbered menus; Enter mounts as-is; mid-flow project list; next steps (`sync` / `down && up`) after save
- Wizard labels: drop `[1]` / step numbers — use `› Project` / section titles; numbers only in choice menus
- Compose container name is `orcan-1` (not `orcan-orcan-1` / folder-based); optional `ORCAN_INSTANCE` for `orcan-2`, …
- Wizard prompts: after project path ask for **project name** (not “workspace”) so labels stay clear
- Drop `orcan context feature` — use wizard / `orcan context worktree` (incl. `remove --workspace`)

## [0.2.1] - 2026-07-28

### Changed

- Config wizard UX: numbered steps, clearer summary, fewer confirmation prompts (path errors re-prompt directly; optional tmux/ttyd behind one question)
- Soft update hint on `orcan up` when a newer release tag exists (cached ~12h; `ORCAN_NO_UPDATE_CHECK=1` to skip)
- `orcan update` checks out the newest SemVer release tag (`vX.Y.Z`); use `--main` for bleeding edge
- `install.sh`: numbered progress steps; appends `~/.local/bin` to shell rc automatically (idempotent; `ORCAN_SKIP_PATH=1` to skip)

## [0.2.0] - 2026-07-28

### Added

- **`orcan` CLI** (`bin/orcan`, `cli/`, `install.sh`): `init`, `sync`, `context`, `up` / `up --with-docker`, `down`, `build`, `pull`, `publish`, `seed`, `update`, `doctor`, `uninstall` — public UX no longer requires Make
- `orcan build`: both agents → `orcan:latest` + `orcan:<VERSION>`; `--claude`/`--cursor` → `orcan:<VERSION>-claude|cursor` (no pull, no overwrite of `latest`)
- Container devtool hygiene: no `__pycache__` / `.pyc` in projects; ruff/mypy/pip/uv/pytest (and related) caches under `$HOME/.cache` (`$ORCAN_DATA/cache` on the host)
- Persist Claude Code login across restarts: `CLAUDE_CONFIG_DIR` → mounted `~/.claude`, chown that volume, migrate legacy `~/.claude.json`
- tmux: prefix `u` picks/copies http(s) URLs with soft-wrap joined (`capture-pane -J`); enable OSC 8 `hyperlinks` terminal-features

### Fixed

- Claude deny templates: drop obsolete `Write(path)` rules (use `Edit` only; removes startup warnings)
- Docs mike deploy: re-sync `gh-pages` before push + retry; serialize CI `dev` and Release on concurrency group `docs-gh-pages`

### Changed

- GitHub Release notes: `install.sh` → `orcan init` → `orcan build` → `orcan up` (no Makefile)
- `orcan build` never publishes (pull → local build only); `orcan publish` is manual
- `orcan seed` demoted in help; user docs no longer treat it as a ritual step
- User-facing EN/PL docs: Make → `orcan` CLI
- Docs / help / installer: **Python 3 on the host** required for `sync` / wizard / `init`
- User config home defaults to `~/.config/orcan/home` (`ORCAN_HOME`); install clone at `~/.local/share/orcan`
- Makefile is maintainer-oriented; deprecated user targets forward to `./bin/orcan`
- Default container resources: **2** CPU / **4g** RAM (shm/tmpfs **512m**); raise via `resources` in config
- Docs: first-run flow uses `orcan sync` to materialise `.env` / `.orcan/*` for Compose
- Docs: remove historical product-name migration notes; **Orcan** is the only documented product name
- Docs storytelling rewrite: Why Orcan / Core Ideas / Mental Model; Home and Architecture narrative-first; Reference last in nav
- tmux status bar at bottom (tabs above, metrics below); metric icons instead of text labels; Starship separates path and git with `│`

## [0.1.1] - 2026-07-23

### Fixed

- `docs-mike.sh`: put `.venv-docs/bin` on `PATH` so `mike` can find `mkdocs` in CI

### Added

- Docs style guide (`docs/STYLE_GUIDE.md`)
- `orcan.config.schema.json` for editor / tooling validation
- FAQ and workflows: uninstall, bug report, contribute
- Mermaid runtime diagram; OG/meta descriptions; image-variant tabs

### Changed

- `make bump-*` also syncs `mkdocs.yml` / README / Home docs version strings
- Quickstart trimmed to first-run only
- Renamed docs “Public interface” → “Host and container interface” (`interface.md`)
- `.env.example` resource defaults aligned with config (8 CPU / 16g)
- Makefile reference covers all `##` help targets
- Docs social links: GitHub / Issues / Releases (Discussions deferred until enabled)
- Documentation restructured for MkDocs (Getting started / Guides / Concepts / Reference / Development / AI)
- Product display name standardized to **Orcan**; README shortened to an entry page
- Docs build uses `requirements-docs.txt`; Make targets `docs-check` and `docs-publish`
- Release/CI no longer publish container images (clone + `make build`)
- Bilingual docs: English (default) + Polish via `mkdocs-static-i18n` (`docs/en/`, `docs/pl/`)
- Versioned docs with **mike** (`latest` / SemVer / `dev`); CI uses mike instead of orphan gh-pages deploys

## [0.1.0] — 2026-07-23

### Added

- Context orchestrator for Cursor CLI (`agent`) and Claude Code (`claude`) in Docker
- Image variants: `full` (Claude+Cursor) and `claude` (Claude only)
- JSON config (`orcan.config.json`), config wizard, path-parity mounts
- Browser terminal (ttyd) → tmux → zsh workspace launcher
- GitHub Actions CI (validate + MkDocs → `gh-pages`)
- SemVer releases via `VERSION` + git tags → GitHub Releases (no image registry)

[Unreleased]: https://github.com/aKyther/orcan/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/aKyther/orcan/releases/tag/v0.4.2
[0.4.1]: https://github.com/aKyther/orcan/releases/tag/v0.4.1
[0.4.0]: https://github.com/aKyther/orcan/releases/tag/v0.4.0
[0.3.2]: https://github.com/aKyther/orcan/releases/tag/v0.3.2
[0.3.1]: https://github.com/aKyther/orcan/releases/tag/v0.3.1
[0.3.0]: https://github.com/aKyther/orcan/releases/tag/v0.3.0
[0.2.1]: https://github.com/aKyther/orcan/releases/tag/v0.2.1
[0.2.0]: https://github.com/aKyther/orcan/releases/tag/v0.2.0
[0.1.1]: https://github.com/aKyther/orcan/releases/tag/v0.1.1
[0.1.0]: https://github.com/aKyther/orcan/releases/tag/v0.1.0
