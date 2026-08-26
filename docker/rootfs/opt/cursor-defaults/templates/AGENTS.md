# AGENTS.md

## Purpose

Short instructions for coding agents working in this repository.
**Keep `AGENTS.md` and `CLAUDE.md` identical** (Cursor loads `AGENTS.md`; Claude Code loads `CLAUDE.md`).

Replace project-specific sections below with real setup and checks.

## Behavioral guidelines

Bias toward caution over speed on non-trivial work. Adapted from
[andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills).

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs. State assumptions; ask when unclear; present alternatives instead of silently picking one.

### 2. Simplicity First

Minimum code that solves the problem. No speculative features, abstractions, or configurability. If 200 lines could be 50, rewrite.

### 3. Surgical Changes

Touch only what you must. Don't drive-by refactor. Match existing style. Clean up only orphans **your** change created.

### 4. Goal-Driven Execution

Define verifiable success criteria and loop until checked (tests, `make`, lint). Prefer "make X pass" over "make it work".

## When stuck

- Don't assume something is broken — check logs/output first.
- Fix one root cause at a time; don't guess-fix in a loop.
- Genuinely blocked? Say so and ask — don't silently pick an interpretation.

## Setup

```bash
# Document install and run commands here
```

## Python (orcan)

Prefer **`uv`** / **`uvx`** for dependencies and one-shot tools. Do not `pip install` into the system Python.

```bash
uv init
uv add requests
uv run pytest
uvx ruff check .
```

## Checks

```bash
# Document test and lint commands here
```

## Project rules

- Work only inside this repository.
- Do not commit secrets or `.env` files.
- Respect `.cursorignore` / `.claudeignore` when present; do not read secrets.
- Run available checks before claiming success; label what you did not run.
- This runs in a container (Docker-from-Docker) — host tools/paths outside the mounted project may not exist. Ask rather than assume.

## Do not

- Create `PLAN.md`, `TODO.md`, `SUMMARY.md`, or similar note files unless asked.
- Run destructive Docker cleanup without approval.
- Overwrite user configuration without approval.
- Invent tools or commands that are not in the environment.
- Force-push, `git reset --hard`, or rewrite history without approval.
