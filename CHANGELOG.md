# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `docs-mike.sh`: put `.venv-docs/bin` on `PATH` so `mike` can find `mkdocs` in CI

### Added

- Docs style guide (`docs/STYLE_GUIDE.md`)
- `orcan.config.schema.json` for editor / tooling validation
- FAQ and workflows: uninstall, bug report, contribute
- Mermaid runtime diagram; OG/meta descriptions; image-variant tabs

### Changed

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

[Unreleased]: https://github.com/aKyther/orcan/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aKyther/orcan/releases/tag/v0.1.0
