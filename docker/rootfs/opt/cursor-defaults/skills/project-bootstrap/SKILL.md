---
name: project-bootstrap
description: >-
  Prepare a mounted project for Cursor/Claude by creating missing AGENTS.md,
  ignore files, Claude settings, and small project rules. Use when the user
  asks to bootstrap, initialize, or set up agent config in a project.
---

# Project bootstrap

Prepare the project at `${PROJECT_DIR}` (or another path the user names) for Cursor and Claude Code.

## Steps

1. Inspect the repository structure and key config files.
2. Detect the main language and tools from existing files only.
3. Check for existing files (`AGENTS.md`, `.cursorignore`, `.cursorindexingignore`, `.claudeignore`, `.claude/settings.json`, `.cursor/rules/`).
4. Create **missing** files only. Use templates from `${HOME}/.cursor/templates/` when present.
5. Keep project rules specific to this repository — not language/framework globals.
6. Never overwrite existing files without explicit user approval.
7. Summarize created and skipped files. Do not add analysis or progress Markdown.

## Suggested outputs

| File | Purpose |
| --- | --- |
| `AGENTS.md` | Agent instructions for this repo |
| `.cursorignore` | Block secrets and junk from Cursor |
| `.cursorindexingignore` | Reduce Cursor indexing noise (includes `.env`) |
| `.claudeignore` | Claude Code discovery exclusions |
| `.claude/settings.json` | Claude `permissions.deny` for `.env` / keys |
| `.cursor/rules/*.mdc` | Short project-specific rules |

## Rules

- Do not invent a stack that the repo does not use.
- Do not add secrets or real credentials.
- Prefer `cursor-init-project` for file copies when the user wants a quick scaffold.
- Ask before `--force` style overwrites.
