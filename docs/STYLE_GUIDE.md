# Documentation style guide

Rules for people and agents editing Orcan documentation under `docs/en/`.

## Story first

Lead the reader: **problem → why it hurts → how Orcan helps → how it works → example → commands (last)**.

Never open a conceptual page with “run this command” unless the page is Quick Start or Reference and the idea was already taught.

Preferred public arc (nav tabs + order):

```text
Home → Get started (Installation first) → Understand → Guides → Reference → Develop
```

Installation is a top-level Get started tab — do not bury it under a deeper section.

## Site theme (MkDocs)

Docs chrome has its own accessible documentation palette. The terminal and
Cockpit use **Warm Graphite / Amber**; see [Terminal UI](en/guides/terminal-ui.md).

- CSS: `docs/en/assets/stylesheets/orcan.css`
- Favicon: `docs/en/assets/images/favicon.svg`
- Fonts: IBM Plex Sans / IBM Plex Mono (`mkdocs.yml` `theme.font`)
- `mkdocs.yml`: `primary` / `accent` = `custom`; tabs = Home / Get started / Understand / Guides / Reference / Develop
- Header: docs **version dropdown** (`orcan-version.js`, reads `versions.json` from Pages) + SemVer chip → Changelog

Do not reintroduce Material stock indigo. Keep light-mode accents darker teal for contrast.

## Agent-facing public index

- `docs/en/llms.txt` — curated [llms.txt](https://llmstxt.org/) map for external agents
  (regenerate: `make docs-llms`). Must stay **opinionated**: source priority,
  what to pay attention to, and explicit non-goals / “do not invent” — not only
  a link dump.
- Live workspace agents still prefer the **context pack** (`AGENTS.md`, …) over
  `llms.txt`.
- Edit the generator `scripts/repository/generate-llms-txt.py`, not the output
  by hand (docs-check regenerates it).

## When to add a page

- Prefer extending an existing page over creating a new one.
- New page only when the topic has a clear audience and nav slot.
- Register each new page in `mkdocs.yml` `nav`.

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

- User-facing docs: clear B1–B2 English.
- Short paragraphs. Prefer tables for commands and options.
- No marketing fluff. No invented features or Make targets.
- Product name is **Orcan** only (technical ids: `orcan`, `ORCAN_*`). Do not invent or use other product names in docs.

## Examples

- Use absolute paths in examples (`/absolute/path/to/…`).
- Prefer multi-repo / multi-org stories over single-path demos when teaching ideas.
- Only document commands that exist (`make help`, container binaries under `docker/rootfs/usr/local/bin/`).
- Prefer fenced bash blocks with copy-friendly commands.
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

## Linking

- Use relative Markdown links inside `docs/en/`.
- After renaming a page, update nav and greppable references.

## Version numbers

- Source of truth: `cockpit/pyproject.toml` → `version = "X.Y.Z"`.
- Root `VERSION` is a synced mirror for CLI/image scripts (`orcan build` tags).
- `make bump-*` updates pyproject + `cockpit/uv.lock` package stanza + `VERSION` +
  `mkdocs.yml` `extra.orcan_version`, README Status, and Home Status.
- Enforced by `make test-host` (`tests/host/test_version.py`).

## Makefile reference

- Document every Make target that has a `##` help string.
- When adding a target, update `docs/en/reference/makefile.md`.
- Keep a two-sentence “when you need this page” intro on Reference pages.

## Social / community links

- Header icons: GitHub, Issues, Releases.
- Re-enable GitHub Discussions in `mkdocs.yml` `extra.social` only after Discussions are turned on for `aKyther/orcan`.

## Checklist before merge

- [ ] English documentation updated (or N/A)
- [ ] `nav` if new page
- [ ] Terms defined or linked before use
- [ ] Diagrams have captions
- [ ] No dead relative links
- [ ] `make docs-check`
- [ ] User-visible change noted in `CHANGELOG.md` when appropriate

## See also

- [Development overview](https://akyther.github.io/orcan/latest/development/overview/)
- [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md)
