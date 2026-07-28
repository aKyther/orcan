# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/aKyther/orcan/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/aKyther/orcan/releases/tag/v0.2.1
[0.2.0]: https://github.com/aKyther/orcan/releases/tag/v0.2.0
[0.1.1]: https://github.com/aKyther/orcan/releases/tag/v0.1.1
[0.1.0]: https://github.com/aKyther/orcan/releases/tag/v0.1.0
