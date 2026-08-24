---
name: repository-analysis
description: >-
  Understand a repository before making large changes. Inspect structure,
  entry points, README, AGENTS.md, build system, and task-relevant files.
  Use when starting substantial work or when the codebase is unfamiliar.
---

# Repository analysis

Understand the mounted project before making large changes.

## Process

1. Inspect repository structure (top-level dirs and key config files).
2. Read `README.md` and `AGENTS.md` when present.
3. Identify entry points and the build system (`Makefile`, package manifests, CI config).
4. Locate files relevant to the current task.
5. Note constraints: tests, lint rules, deployment shape, existing patterns.
6. Stop when you have enough context to act — avoid unnecessary exploration.

## Rules

- Infer the stack from existing files only. Do not assume frameworks or languages.
- Do not generate documentation, analysis reports, or new Markdown files.
- Summarize findings briefly in your response if helpful; keep it in the conversation, not the repo.
