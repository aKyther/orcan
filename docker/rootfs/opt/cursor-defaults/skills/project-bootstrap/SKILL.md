---
name: project-bootstrap
description: >-
  Prepare a mounted project for Cursor by creating missing AGENTS.md,
  ignore files, and small project rules. Use when the user asks to
  bootstrap, initialize, or set up Cursor config in /workspace.
---

# Project bootstrap

Prepare the project at `/workspace` (or another path the user names) for Cursor.

## Steps

1. Inspect the repository structure and key config files.
2. Detect the main language and tools from existing files only.
3. Check for existing Cursor files (`AGENTS.md`, `.cursorignore`, `.cursorindexingignore`, `.cursor/rules/`).
4. Create **missing** files only. Use templates from `${HOME}/.cursor/templates/` when present.
5. Keep project rules specific to this repository — not language/framework globals.
6. Never overwrite existing files without explicit user approval.
7. Summarize created and skipped files. Do not add analysis or progress Markdown.

## Suggested outputs

| File | Purpose |
| --- | --- |
| `AGENTS.md` | Agent instructions for this repo |
| `.cursorignore` | Block secrets and junk from the agent |
| `.cursorindexingignore` | Reduce indexing noise |
| `.cursor/rules/*.mdc` | Short project-specific rules |

## Rules

- Do not invent a stack that the repo does not use.
- Do not add secrets or real credentials.
- Prefer `cursor-init-project` for file copies when the user wants a quick scaffold.
- Ask before `--force` style overwrites.
