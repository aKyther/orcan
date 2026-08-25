# Documentation style guide

Rules for people and agents editing Orcan docs under `docs/en/` and `docs/pl/`.

## Story first

Lead the reader: **problem → why it hurts → how Orcan helps → how it works → example → commands (last)**.

Never open a conceptual page with “run this command” unless the page is Quick Start or Reference and the idea was already taught.

Preferred public arc (nav tabs + order):

```text
Home → Get started (Installation first) → Understand → Guides → Reference → Develop
```

Installation is a top-level Get started tab — do not bury it under a deeper section.

## Site theme (MkDocs)

Docs chrome uses the same **navy / cyan** tokens as [Terminal UI](en/guides/terminal-ui.md):

- CSS: `docs/assets/stylesheets/orcan.css`
- Favicon: `docs/assets/images/favicon.svg`
- Fonts: IBM Plex Sans / IBM Plex Mono (`mkdocs.yml` `theme.font`)
- `mkdocs.yml`: `primary` / `accent` = `custom`; tabs = Home / Get started / Understand / Guides / Reference / Develop
- Header: docs **version dropdown** (`orcan-version.js`, reads `versions.json` from Pages) + SemVer chip → Changelog

Do not reintroduce Material stock indigo. Keep light-mode accents darker teal for contrast.

## Agent-facing public index

- `docs/llms.txt` — curated [llms.txt](https://llmstxt.org/) map for external agents (regenerate: `make docs-llms`).
- Live workspace agents still prefer the **context pack** (`AGENTS.md`, …) over `llms.txt`.

## When to add a page

- Prefer extending an existing page over creating a new one.
- New page only when the topic has a clear audience and nav slot.
- Mirror every new English page in Polish (`docs/pl/…` same relative path).
- Register the page once in `mkdocs.yml` `nav` (English titles; Polish via `nav_translations`).

## File and heading names

- Paths: `kebab-case.md`.
- One H1 per page (= nav title).
- Prefer this shape for how-to pages:

  1. Short intro (or YAML `description`) — include *why*
  2. Before you start (optional)
  3. Steps
  4. Expected result
  5. Common problems
  6. See also

For idea pages: problem / hurt / solution / example / trade-offs / next.

## Define terms before use

Do not use **Workspace**, **Context**, **Project**, **path parity**, **context pack**, or **manifest** on a page without a plain definition nearby — or a link to [Core Ideas](en/ideas/core-ideas.md) / [Mental Model](en/ideas/mental-model.md).

## Language level

- User-facing docs: B1–B2 English / clear Polish.
- Short paragraphs. Prefer tables for commands and options.
- No marketing fluff. No invented features or Make targets.
- Product name is **Orcan** only (technical ids: `orcan`, `ORCAN_*`). Do not invent or use other product names in docs.

## Examples

- Use absolute paths in examples (`/absolute/path/to/…`).
- Prefer multi-repo / multi-org stories over single-path demos when teaching ideas.
- Only document commands that exist (`make help`, container binaries under `docker/rootfs/usr/local/bin/`).
- Prefer fenced bash blocks with copy-friendly commands.
- Translate comments inside code blocks when the page language is Polish.
- In command signatures, `|` inside `[…]` means **pick one** (mutually exclusive options) — documentation notation, not a literal shell pipeline. Example: `[--with-docker | --with-network NAME]`, `[--with-ttyd | --with-ttyd-auth USER:PASS]`.

## Tabs and admonitions

- Tabs (`=== "…"`): use for mutually exclusive choices (e.g. full vs Claude-only image).
- `!!! note` — rituals users overlook (`orcan sync` before `terminal*`).
- `!!! tip` — shortcuts and cross-links.
- `!!! warning` — security, destructive targets (`clean-data`), ttyd without auth.

## Mermaid

- Use Mermaid for relationships, journeys, and architecture when ASCII is hard to scan.
- Every diagram needs a short **caption** in prose under it.
- Keep node labels short; avoid secrets or host-specific real usernames.
- ASCII remains fine for tiny sketches.

## EN ↔ PL

- Same relative path and section structure.
- Same external URLs (GitHub, Pages). Prefer Pages links with `/latest/` (or `/dev/` when documenting unreleased docs).
- Update both languages in the same PR when behaviour or narrative changes.
- `nav_translations` in `mkdocs.yml` must cover every English nav label.

## Linking

- Inside one language tree: relative Markdown links.
- Do not link `docs/en/…` from Polish pages (or the reverse).
- After renaming a page, update nav, both languages, and greppable references.

## Version numbers

- Source of truth: `cockpit/pyproject.toml` → `version = "X.Y.Z"`.
- Root `VERSION` is a synced mirror for CLI/image scripts (`orcan build` tags).
- `make bump-*` updates pyproject + `cockpit/uv.lock` package stanza + `VERSION` +
  `mkdocs.yml` `extra.orcan_version`, README Status, and Home Status.
- Enforced by `make test-host` (`tests/host/test_version.py`).

## Makefile reference

- Document every Make target that has a `##` help string.
- When adding a target, update `docs/en/reference/makefile.md` and `docs/pl/reference/makefile.md`.
- Keep a two-sentence “when you need this page” intro on Reference pages.

## Social / community links

- Header icons: GitHub, Issues, Releases.
- Re-enable GitHub Discussions in `mkdocs.yml` `extra.social` only after Discussions are turned on for `aKyther/orcan`.

## Checklist before merge

- [ ] EN + PL updated (or N/A)
- [ ] `nav` / `nav_translations` if new page
- [ ] Terms defined or linked before use
- [ ] Diagrams have captions
- [ ] No dead relative links
- [ ] `make docs-check`
- [ ] User-visible change noted in `CHANGELOG.md` when appropriate

## See also

- [Development overview](https://akyther.github.io/orcan/latest/development/overview/)
- [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md)
