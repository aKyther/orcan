# Documentation style guide

Rules for people and agents editing Orcan docs under `docs/en/` and `docs/pl/`.

## When to add a page

- Prefer extending an existing page over creating a new one.
- New page only when the topic has a clear audience and nav slot.
- Mirror every new English page in Polish (`docs/pl/…` same relative path).
- Register the page once in `mkdocs.yml` `nav` (English titles; Polish via `nav_translations`).

## File and heading names

- Paths: `kebab-case.md`.
- One H1 per page (= nav title).
- Prefer this shape for how-to pages:

  1. Short intro (or YAML `description`)
  2. Before you start (optional)
  3. Steps
  4. Expected result
  5. Common problems
  6. See also

## Language level

- User-facing docs: B1–B2 English / clear Polish.
- Short paragraphs. Prefer tables for commands and options.
- No marketing fluff. No invented features or Make targets.
- Product name is **Orcan**. Do not reintroduce Sint, Orkan, or cind as product names (migration notes only).

## Examples

- Use absolute paths in examples (`/absolute/path/to/…`).
- Only document commands that exist (`make help`, container binaries under `docker/rootfs/usr/local/bin/`).
- Prefer fenced bash blocks with copy-friendly commands.
- Translate comments inside code blocks when the page language is Polish.

## Tabs and admonitions

- Tabs (`=== "…"`): use for mutually exclusive choices (e.g. full vs Claude-only image).
- `!!! note` — rituals users overlook (`make env` before `terminal*`).
- `!!! tip` — shortcuts and cross-links.
- `!!! warning` — security, destructive targets (`clean-data`), ttyd without auth.

## Mermaid

- Use Mermaid for runtime / data-flow diagrams when ASCII is hard to scan.
- Keep node labels short; avoid secrets or host-specific paths.
- ASCII remains fine for tiny sketches.

## EN ↔ PL

- Same relative path and section structure.
- Same external URLs (GitHub, Pages). Prefer Pages links with `/latest/` (or `/dev/` when documenting unreleased docs).
- Update both languages in the same PR when behaviour changes.
- `nav_translations` in `mkdocs.yml` must cover every English nav label.

## Linking

- Inside one language tree: relative Markdown links (`../guides/workflows.md`).
- Do not link `docs/en/…` from Polish pages (or the reverse).
- After renaming a page, update nav, both languages, and greppable references (`api.md` → `interface.md` style).

## Version numbers

- Source of truth: root `VERSION`.
- `make bump-*` updates `mkdocs.yml` `extra.orcan_version`, README Status, and Home Status.
- Enforced by `make test-host` (`tests/host/test_version.py`).

## Makefile reference

- Document every Make target that has a `##` help string.
- When adding a target, update `docs/en/reference/makefile.md` and `docs/pl/reference/makefile.md`.

## Social / community links

- Header icons: GitHub, Issues, Releases.
- Re-enable GitHub Discussions in `mkdocs.yml` `extra.social` only after Discussions are turned on for `aKyther/orcan`.

## Checklist before merge

- [ ] EN + PL updated (or N/A)
- [ ] `nav` / `nav_translations` if new page
- [ ] No dead relative links
- [ ] `make docs-check`
- [ ] User-visible change noted in `CHANGELOG.md` when appropriate

## See also

- [Development overview](https://akyther.github.io/orcan/latest/development/overview/)
- [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md)
