# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Container devtool hygiene: no `__pycache__` / `.pyc` in projects; ruff/mypy/pip/uv/pytest (and related) caches under `$HOME/.cache` (`$ORCAN_DATA/cache` on the host)
- Persist Claude Code login across restarts: `CLAUDE_CONFIG_DIR` → mounted `~/.claude`, chown that volume, migrate legacy `~/.claude.json`
- tmux: prefix `u` picks/copies http(s) URLs with soft-wrap joined (`capture-pane -J`); enable OSC 8 `hyperlinks` terminal-features

### Fixed

- Claude deny templates: drop obsolete `Write(path)` rules (use `Edit` only; removes startup warnings)

### Changed

- Docs: remove historical product-name migration notes; **Orcan** is the only documented product name
- Docs storytelling rewrite: Why Orcan / Core Ideas / Mental Model; Home and Architecture narrative-first; Reference last in nav
- tmux status bar at bottom (tabs above, metrics below); metric icons instead of text labels; Starship separates path and git with `│`

### Fixed

- Docs mike deploy: re-sync `gh-pages` before push + retry; serialize CI `dev` and Release on concurrency group `docs-gh-pages`

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

[Unreleased]: https://github.com/aKyther/orcan/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/aKyther/orcan/releases/tag/v0.1.1
[0.1.0]: https://github.com/aKyther/orcan/releases/tag/v0.1.0
