# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.1] - 2026-08-24

### Added

- **`orcan doctor` flags a leftover pre-2.0 `space/` projects root.** After
  the rename to `sandbox/`, a stale `ORCAN_PROJECTS_ROOT=…/space` makes
  Docker recreate the missing bind as `root:root`. Doctor fails that check
  and points at `scripts/migrations/rename-space-to-sandbox.sh` (or
  `sudo rmdir` when the leftover is empty).
- **`shfmt` + `difft` (difftastic) in the image.** `shfmt` formats shell
  scripts; `difft` gives a structural diff, useful when a large refactor's
  line diff is hard to read. Both added to the "prefer the faster tool"
  guidance in the Cursor `operating-principles.mdc` rule and the generated
  per-workspace `AGENTS.md`/`CLAUDE.md`.
- **Claude Code now gets the same 6 Skills Cursor already had.**
  `/opt/claude-defaults/skills/` mirrors `/opt/cursor-defaults/skills/`
  (`docker-review`, `final-review`, `focused-implementation`,
  `karpathy-guidelines`, `project-bootstrap`, `repository-analysis`) —
  `init-claude-home` seeds them into `~/.claude/skills/` the same generic,
  missing-only way it already seeds agents/commands, so this needs no
  per-project setup and applies to every workspace in the container.
  `karpathy-guidelines` was adapted (its Cursor copy pointed at a
  Cursor-only rule file); the other five were identical for both agents
  already.
- **No AI co-author trailers in commits.** Root `AGENTS.md`, the generated
  per-workspace `AGENTS.md`/`CLAUDE.md`, and Cursor's `operating-principles.mdc`
  now all say the same thing: an agent-created commit gets no `Co-Authored-By`
  (or similar) trailer — the human is the sole author of record.

### Fixed

- **CI `image-scan` failed before producing a CVE table.** The job set
  `permissions: contents: read`, which zeroes every other `GITHUB_TOKEN`
  scope — so `trivy-action` could not use `actions/cache` for the vuln DB
  or authenticate to `ghcr.io/aquasecurity/trivy-db`. Grant `actions: write`
  + `packages: read`, pass the token as `TRIVY_USERNAME`/`TRIVY_PASSWORD`,
  and raise the scan timeout to 10m for the full image.

## [2.0.0] - 2026-08-23

### Security

- **ttyd publishes on loopback by default.** Compose uses
  `TTYD_BIND` (default `127.0.0.1`) so the browser terminal is not exposed on
  all host interfaces. Set `TTYD_BIND=0.0.0.0` (or `ttyd.bind` in config) for
  Tailscale/LAN. Optional HTTP basic auth via `TTYD_CREDENTIAL=user:password`
  in `.env` (not stored in `orcan.config.json`).
- **Sensitive path checks cover whole trees.** Mount/config paths under
  `/etc`, `/usr`, `/var`, `/opt`, and `/root` are refused (not only the exact
  roots). `/home/<user>/…` project paths remain allowed; exact `/` and `/home`
  are still blocked.
- **CI now scans the image for CVEs.** New `image-scan` job in `ci.yml` builds
  the image (not published) and runs Trivy (CRITICAL/HIGH, unfixed CVEs
  ignored).
- **Third-party GitHub Actions pinned by commit SHA, not tag.** `actions/
  checkout`, `actions/setup-python`, `softprops/action-gh-release`, and the
  new `aquasecurity/trivy-action` are pinned to a specific commit (version in
  a trailing comment). Floating tags on third-party Actions have been
  hijacked before (`tj-actions/changed-files`, CVE-2025-30066;
  `reviewdog/action-setup`, CVE-2025-30154) — a tag can be moved, a commit
  SHA cannot.
- **Workspace deletion is loudly destructive, on purpose.** Dropping a
  workspace from config still deletes its whole on-disk tree on the next
  reconcile (not just the managed symlinks) — behavior unchanged, but now
  stated up front in `reconcile.py`'s docstring, spelled out in the deletion
  warning message (what's actually lost: session brief, agent-inbox tasks,
  unsynced Context Assertions drops), and documented as a `!!! warning` in
  [Security](docs/en/reference/security.md).

### Documentation

- Security and mental-model docs spell out intentional tradeoffs: single-user
  trust model; Tailscale as the recommended remote path for ttyd (credentials
  optional secondary layer); `--with-docker` as known high-risk opt-in with
  `--with-network` as the safer reachability alternative; `sandbox/` as the
  stable projects-root anchor; cross-workspace visibility from one parent
  mount (enables dynamic workspace add/remove without recreate). PL CLI /
  workflows now document `--with-network`.
- **New EN+PL page: [Agent inbox](docs/en/ideas/agent-inbox.md).** Documents
  the `.orcan/tasks/` propose → approve → claim → complete lifecycle and the
  `orcan-inbox` CLI. [Security](docs/en/reference/security.md) gained a
  matching section spelling out that `policy: auto` + `executor: shell` means
  a claimed task runs a real shell command with no human step in between.
- **New `SECURITY.md`** at the repo root: private vulnerability reporting via
  GitHub Security Advisories, pointing to the security reference doc for the
  actual threat model.

### Added

- **`ss` / `netstat` in the image.** Added `iproute2` / `net-tools` to the
  Dockerfile package list — basic network diagnostics were missing.
- **`orcan up --with-ttyd`.** Plain `orcan up` now starts a local-only
  container (`orcan enter`); the browser terminal (ttyd) is opt-in via
  `--with-ttyd`. Capability ladder: local → `--with-ttyd` → `--with-network`
  → `--with-docker`.

### Fixed

- Clearer CLI errors when `.env` or generated runtime is missing or stale:
  distinguish what `orcan build` vs `orcan up` need, with explicit next steps.

- **`validate-project-dir.sh` matches `path_guards.py`.** Same tree rules for
  `/var`, `/etc`, `/usr`, `/opt`, `/root` in sync and wizard.
- **Host tests:** settings wizard (`ttyd.bind` prompts) and managed-root filter
  aligned with `$ORCAN_PROJECTS_ROOT/.worktrees`.
- **README:** documents local `orcan up` vs `--with-ttyd` and sync/build split.
- **`make validate`** now also runs `shellcheck` over every script it already
  syntax-checks (error-severity findings fail the build; lower-severity ones
  are printed but non-blocking, since existing scripts already carried a few).

### Changed

- **`orcan uninstall`** stops every `orcan up` overlay variant (including
  local-only keepalive stacks), not only the legacy ttyd compose files.
- **`orcan doctor`** reports running container, last up flags, ttyd on/off +
  URL, and local image presence.
- **`orcan url`** shares the same URL helper as `orcan up --with-ttyd`; detects
  legacy ttyd stacks via published ports when `up-state.env` is missing.
- **Docs (security, interface, deployment EN+PL):** capability ladder includes
  `--with-ttyd`; docker/network documented as mutually exclusive.
- **Landing pages (index, why-orcan, FAQ EN+PL):** local `orcan enter` as default;
  browser terminal via `--with-ttyd`. **`orcan migrate`** and **`orcan-inbox`**
  documented in CLI reference / ideas.
- **Architecture, mental-model, quickstart, troubleshooting EN+PL:** local entry
  default; browser via `--with-ttyd`.
- **`orcan up` hints:** docker vs network shown as pick-one, not both.

- **`orcan up` rejects `--with-docker` together with `--with-network`.** Pick
  socket control or network reachability — not both.

- Stale help text still pointing at `$ORCAN_DATA/worktrees` now says
  `$ORCAN_PROJECTS_ROOT/.worktrees`.

### Added

- **Runtime workspace modification**: a project added under the managed
  root (`ORCAN_PROJECTS_ROOT`, default `~/.config/orcan/sandbox`) now
  becomes visible in an already-running container via `orcan sync` alone —
  no `orcan down && orcan up`, no lost tmux/agent sessions. Mechanism:
  `docker-compose.yml` gains one stable, always-mounted managed-root
  volume; `apply-config.py` stops emitting a per-project Compose bind for
  anything already under it; `orcan sync` execs the new
  `orcan-runtime-reconcile` inside a running container instead of only
  regenerating host-side files.
- `orcan migrate` — moves existing project checkouts under the managed
  root (dry-run by default) so they stop needing their own bind mount.
- New container-side runtime commands: `orcan-runtime-reconcile`,
  `orcan-runtime-status`, `orcan-tmux-ensure`, `orcan-tmux-reconcile-sessions`
  (thin wrappers over shared `orcan.reconcile` / tmux logic — the same
  mechanism container boot and live changes both use).
- Tmux session cleanup for a removed/renamed workspace is now report-only
  by default (never auto-kills a session that might have an active agent
  in it).
- `orcan context recent` — usage history (recent workspaces), keyed by the
  same canonical project identity Context Assertions already uses.
- `orcan-inbox` — filesystem-based agent task handoff/inbox
  (propose/approve/claim/complete/list/watch), modeled on the existing
  Context Assertions propose→review→accept lifecycle; default approval
  policy requires human approval before a task is claimable.
- `tests/integration/test-runtime-reconcile.sh` — proves the above end to
  end against a real (isolated) container: add a project, reconcile,
  assert the container was never recreated and an active tmux session
  survives.
- **Codex CLI support** alongside Claude Code and Cursor CLI: `INSTALL_CODEX`
  build arg (default on, installed under `~/.local` via `npm install -g
  --prefix ~/.local @openai/codex` — not `pnpm add -g`, since `PNPM_HOME`
  is bind-mounted at runtime and would shadow a baked-in global install),
  `orcan build --codex` → `orcan:<VERSION>-codex`, `${ORCAN_DATA}/codex`
  bind-mounted to `~/.codex`. The single-agent variant is no longer
  hardcoded to "claude"/"cursor" — `/etc/orcan/variant` is now `full` (all
  three) or a `+`-joined subset (e.g. `claude+codex`). `CodexExecutor`
  added to `orcan.agent_executor` (`codex exec <prompt>`).

### Fixed

- `~/.codex` (a fresh bind mount) was root-owned on first boot —
  `docker-entrypoint`'s permission-fix loop covered `.cursor`/`.claude`/
  `.cache` but not the new `.codex` dir, so Codex failed to write its
  session/sqlite state ("permission denied") until fixed. Now covered.
- Explicit "prefer the faster tool" guidance (`rg`/`fd`/`eza`/`bat`/`delta`/
  `sg` over `grep`/`find`/`ls`/`cat`) in the Cursor `operating-principles.mdc`
  rule and the generated per-workspace `AGENTS.md`/`CLAUDE.md`.

### Changed

- **Breaking: managed projects root renamed `space/` → `sandbox/`.** Default
  `ORCAN_PROJECTS_ROOT` is now `~/.config/orcan/sandbox` (was
  `~/.config/orcan/space`). Migrate: `bash scripts/migrations/rename-space-to-sandbox.sh`,
  then `orcan sync && orcan down && orcan up`.
- **Breaking: managed worktrees live under `$ORCAN_PROJECTS_ROOT/.worktrees/`.**
  Default `~/.config/orcan/sandbox/.worktrees/<workspace>/<project>/` (was
  `$ORCAN_DATA/worktrees/...`, briefly also `sandbox/worktrees/...`). The
  leading dot keeps branch checkouts out of normal project listings under
  `sandbox/`, while still using the stable projects-root bind (no recreate).
  Migrate: `bash scripts/migrations/move-worktrees-into-sandbox.sh`, then
  `orcan sync`.
- **Breaking: container home layout.** Host `$ORCAN_DATA` uses a single
  `cache/` bind → `~/.cache` and `history/` → `~/.local/share/orcan/history`
  (replacing `shell-history` / `/command-history` and flat `npm|pnpm|cargo|go`
  binds). `~/orcan/` is a symlink map inside the container. Migrate:
  `bash scripts/migrations/consolidate-container-data.sh`, then
  `orcan sync && orcan down && orcan up`.

## [1.0.1] - 2026-08-14

### Fixed

- `orcan init` crashed immediately with `NameError: name '_init_colors' is
  not defined` on both the scan and manage TUI screens — a rename to
  `_init_curses_session()` updated the definition but not its two call
  sites. Neither `py_compile` nor the test suite catches this class of bug
  (`main_loop()` is curses-dependent, so nothing in the suite actually
  calls it). Fixed; verified this time with `ruff check --select F821`
  across every file touched in the v1.0.0 changes.

## [1.0.0] - 2026-08-14

### Changed

- Browser terminal look: default ttyd theme is dark navy / near-black / subtle cyan
  (was Catppuccin Mocha). Preset names `dark` and `navy` map to the new palette;
  `mocha` / `catppuccin` keep the previous look. tmux status, pane borders, and
  messages use matching truecolor styles (still no Nerd Font).
- Image tmux bumped to **3.6a** (static build from `tmux/tmux-builds`; Debian
  bookworm still packages 3.3a). Status tabs are centred; inactive panes dim;
  borders use `spaces` (gap-like) on 3.6+; modal cyan pane scrollbars on 3.5+;
  navy popups/menus; vi copy-mode (`v`/`y`).
- Pane title strip (top) now carries the clock and cpu/mem (⚙/🧠), right-aligned
  next to the pane index/command/path — moved off the bottom status-right bar,
  which keeps AI usage · brief marker · git branch · battery. New script
  `docker/rootfs/etc/tmux/scripts/pane-border-right.sh`.
- Bottom-left status simplified to just the tmux-prefix indicator (○/◉) — the
  workspace/session name pill was dropped; it duplicated the directory name
  already shown top-left (panes start in the workspace root, so the pane
  title's path basename already reads as the workspace name).
- Starship / zsh UX polish (same palette): cyan path + git, `cmd_duration` after
  2s, fzf navy theme with previews, menu-select completion, quieter autosuggest
  ghost text. No new shell frameworks (still autosuggestions + syntax + fzf).
- lazygit default theme aligned to the same navy/cyan palette
  (`docker/rootfs/opt/orcan/lazygit-config.yml`).
- Docs: [Terminal UI](docs/en/guides/terminal-ui.md) (+ PL) — palette, file map,
  agent checklist; Cursor rule `.cursor/rules/terminal-ui.mdc`.
- **Breaking:** flattened `~/.config/orcan/` — `ORCAN_HOME` and `ORCAN_DATA`
  now default to the same root (`~/.config/orcan`, no more nested `home/`
  segment). Generated runtime files moved from the hidden `.orcan/` to a
  visible `mounts/`; workspace root directories moved from `.orcan/workspaces/`
  to a top-level `workspaces/` (these are the host-backed dirs bind-mounted
  into the container at `/home/developer/workspaces/<name>` — no longer
  hidden three levels deep under a dotfile). The global worktree registry
  (`$ORCAN_DATA/worktrees/manifest.json`) and the global workspace index
  (`$ORCAN_HOME/.orcan/workspace.manifest.json`) are renamed to
  `worktrees/registry.json` and `workspaces/index.json` respectively, to stop
  three unrelated files all being called some variant of `manifest.json`.
  No automatic migration (pre-1.0), but there is a script for it:
  `scripts/migrations/flatten-orcan-home.sh` moves existing config/`.env`/
  workspace meta to the new layout in place (safe to re-run, never
  overwrites). Run it once on the host before the first `orcan sync` /
  `orcan build` with the new code. See `scripts/migrations/README.md`.
- The Claude Code Stop hook (`orcan-context-reflect`, batched Reflection) is
  now **on by default** instead of opt-in: `orcan sync` seeds it into a
  workspace's `.claude/settings.json` the first time that workspace is
  synced. Opting out is what's configurable — `orcan context hook disable`
  sticks across every later sync, since sync only ever seeds a workspace
  whose `.claude/settings.json` doesn't exist yet.
- `orcan init` (no PATH) now defaults to a curses TUI instead of the old
  sequential prompt wizard — the wizard's edit flow walked every workspace,
  then every project inside it, one keep/change/delete prompt at a time,
  which got tedious with many projects. With an existing config it opens
  straight into a **manage** screen (grid view, jump to any row: `r` rename,
  `p` change path, `d` delete project, `W` delete workspace, `n` to scan a
  folder and add more); with no config yet it goes straight to the existing
  scan-and-select screen. The old wizard is still there: `orcan init --cli`.
  tmux/ttyd settings moved out of the wizard entirely — see `orcan settings`
  below — they're tool settings, not workspace data, so they no longer show
  up while creating/editing workspaces.
- `orcan context tui`'s scan screen: text prompts (workspace name, branch,
  rename, path) are now a real line editor — pre-filled, cursor at the end,
  Left/Right/Home/End/Backspace/Delete, plus Ctrl-B/F/A/E fallbacks for
  terminals without dedicated arrow/Home/End keys (mobile terminal apps).
  Esc/Ctrl-C cancels. `curses.set_escdelay(25)` so a bare Esc doesn't sit
  for ~1s waiting to see if an arrow-key sequence follows, which reads as
  "Esc doesn't work" over a mobile/SSH terminal.
- Plain (non-git) directories are now selectable scan candidates alongside
  git repos, tagged `(no git — mount only)` — worktree mode is skipped for
  them automatically (mounted as-is) with a note after apply, instead of
  only ever finding git repos.
- `d`/`W` (delete project/workspace) in the manage screen now offer to also
  remove the managed worktree from disk (`git worktree remove` + registry
  cleanup), with a second, explicit confirmation if the worktree has
  uncommitted changes (`git status --porcelain`) that would be permanently
  lost by `--force`.
- `CONTEXT-ASSERTIONS.md` now always includes a **Workspace composition**
  section (every mounted project + its current branch) and is written
  whenever a workspace has at least one project — even with zero matched
  assertions (previously the file was deleted entirely in that case, so
  there was no way to see what composition produced, or failed to
  produce, a given result).
- Automated Reflection (`orcan-context-reflect`) now scopes a `propose`
  drafted on anything but `main`/`master` to that branch by default
  (`--branch <current>`), instead of unconditional — Reflection runs
  mid-work and can't yet know whether something is durably true or just an
  artifact of unmerged, in-progress code; the human reviewer widens the
  scope at accept time if it turns out to be universal.

### Added

- `orcan settings` — edit tool-level settings (tmux windows/prefix, ttyd
  port/font) in `orcan.config.json`, independent of `orcan init`
  (workspaces/projects). `scripts/repository/settings-wizard.py`.
- `orcan context tui` — curses TUI: parent folder → multi-select git repos →
  create/update a workspace; optional **one** branch name creates a managed
  worktree per selection. Flags: `--dir`, `--workspace`, `--branch`, `--select`,
  `--yes`, `--sync`, `--force`. Remembers last parent/branch in
  `$ORCAN_HOME/mounts/context-tui-state.json`. Host stdlib only (curses).
- `orcan up --with-network NAME` — join an existing Docker network from the
  workspace container (dynamically generated `mounts/compose-network.generated.yml`
  overlay, mirroring `--with-git`'s pattern). Lower-risk alternative to
  `--with-docker` when you only need reachability to other containers, not
  control over the host Docker engine. **Mutually exclusive with `--with-docker`**
  (pick network reachability or socket control, not both); combines with `--with-git`.
- `orcan context worktree prune [--force] [--no-config]` — reconciles
  `worktrees/registry.json` against disk (and `orcan.config.json`): drops
  registry entries whose worktree directory is gone, reports orphan
  directories under `$ORCAN_DATA/worktrees` the registry doesn't know about
  and registry entries no longer referenced by any workspace, removing both
  only with `--force`. Dry-run by default.
- `orcan context tui`'s scan screen: `e` opens an arrow-key directory
  browser (`.. (up)`/Enter/`s` select, `f` filter) instead of a blind
  type-the-full-path prompt; `h` jumps to a recently used parent directory
  (up to 8, newest first, auto-expiring after 3 days of not being picked
  again, shown with age/TTL); `/` filters the repo list by name; `?` opens
  a full keybinding cheatsheet. Both screens warn before applying if a
  selected path's project name already exists in the target workspace, or
  if the same path is already mounted under a different workspace.
- `a` on the manage screen: jump to the scan screen pre-loaded for the
  workspace under the cursor (same name so picks append instead of
  creating a new one, starting directory next to an existing project, same
  managed-worktree branch if applicable) — adding a project to an existing
  workspace no longer means retyping its name from scratch. `P` runs
  `orcan context worktree prune` in place and returns to the manage
  screen, instead of requiring a trip to the shell.
- `orcan context assert overview` — one line per configured workspace:
  composition (repo@branch) + how many accepted assertions currently match
  it, recomputed live. A glance across every workspace at once, e.g. to
  spot two that share a project but ended up with different context
  because they're on different branches.
- `orcan doctor`: new "Context" section listing every workspace's Stop
  hook status (enabled/disabled, informational either way — disabling is a
  valid deliberate choice) and, if enabled, the last recorded Reflection
  failure if there is one.

### Fixed

- `orcan context worktree create --force` (replacing an existing managed
  workspace) no longer leaves orphaned worktrees behind for projects that
  were dropped or renamed out of the new project list — those are now
  removed the same way `orcan context worktree remove` would. Unchanged
  projects are also no longer needlessly re-created (which previously made
  any `--force` replace that kept an existing project name fail outright).
- `orcan sync` seeds the Stop hook only when a workspace's
  `.claude/settings.json` doesn't exist yet — correct for a brand-new
  workspace, but if that file was created by any other path first (e.g.
  `init-workspace`'s missing-only template copy, or a workspace that
  predates the on-by-default change above), the hook silently never got
  added, with no signal. `orcan sync` and `orcan doctor` now report this
  explicitly instead of staying quiet.
- `orcan-context-reflect` model-call failures (timeout, non-zero exit) are
  now recorded (message + timestamp, cleared on the next successful run)
  into the same per-session `reflection-state.json`, instead of only
  reaching an async Stop hook's stderr that nothing reads — a hook that
  was on but silently failing every time looked identical to a healthy one.
- `claude_hook.py` (`orcan context hook enable|disable`) gives a clear
  error naming the failing path and the likely cause (a `.claude/settings.json`
  owned by a different UID than the one running the command — e.g. created
  from inside the orcan container) instead of a raw Python traceback on
  permission denied.

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
