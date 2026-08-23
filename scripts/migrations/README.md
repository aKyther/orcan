# Migrations

One-off scripts for breaking changes to orcan's **host-side** layout
(`~/.config/orcan/...`) that need existing installs to move data by hand.
Not run automatically by anything — `orcan` never migrates data for you
(see `AGENTS.md` / `CLAUDE.md` on config staying plain JSON with no hidden
magic). Each entry here is announced in `CHANGELOG.md` under the release
that introduced the breaking change, with a pointer to the script name.

## When to add one

Only for changes that move or rename existing **user data** on the host
(config, workspace meta, generated state) — not for new features, and not
for changes that only affect a fresh install. If `orcan sync` can just
regenerate whatever changed, you don't need a migration script; only add
one when data would otherwise be silently orphaned or lost.

## Conventions

- Name: `<short-slug>.sh` describing the change (e.g. `flatten-orcan-home.sh`),
  not a sequential number — these are independent and opt-in, not a chain
  that must run in order.
- Safe to run more than once: check before every move (source exists,
  destination doesn't already have real content) and skip rather than
  overwrite. Never delete data — only `mv` it to its new home.
- Runs on the **host**, stdlib bash only (same constraint as the rest of
  `scripts/repository/` — no assumptions about what's installed).
- Print what it did (and what it deliberately left behind, and why).
- Keep it here — do not delete after use. The next person hitting the same
  breaking change (or reading the CHANGELOG entry) needs to find it.

## Current scripts

- `flatten-orcan-home.sh` — `~/.config/orcan/home/...` → flat
  `~/.config/orcan/...` layout (see `CHANGELOG.md` `[Unreleased]`,
  "Breaking: flattened `~/.config/orcan/`").
- `consolidate-container-data.sh` — host `$ORCAN_DATA` cache/history layout
  for the flatter container home (`cache/` single bind, `history/` instead of
  `shell-history/` / flat `npm|pnpm|cargo|go`). See `CHANGELOG.md`
  `[Unreleased]`, "Breaking: container home layout".
- `move-worktrees-into-sandbox.sh` — legacy `$ORCAN_DATA/worktrees` or
  `$ORCAN_PROJECTS_ROOT/worktrees` → `$ORCAN_PROJECTS_ROOT/.worktrees`
  (default under `sandbox/`). Dot-dir keeps managed branch checkouts
  separate from live project clones. See `CHANGELOG.md` `[Unreleased]`.
  (`move-worktrees-into-space.sh` is a compatibility wrapper.)
- `rename-space-to-sandbox.sh` — `$ORCAN_DATA/space` →
  `$ORCAN_DATA/sandbox` (default `ORCAN_PROJECTS_ROOT`). See
  `CHANGELOG.md` `[Unreleased]`, "Breaking: managed projects root renamed
  `space/` → `sandbox/`".
