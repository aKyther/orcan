# Context orchestration

**cind** is an **environment and context orchestrator**. It decides *where* you work and *what* coding agents can see. Cursor CLI (`agent`) and Claude Code (`claude`) are **pluggable tools** inside that environment. **Models are out of scope** for cind configuration — each CLI / account chooses its own model.

## Product boundary

| cind owns | cind does not own |
| --- | --- |
| Which repos are in a session (workspaces, mounts, path parity) | Which model a CLI dials |
| What agents should see (ignore files, deny rules, `AGENTS.md` / `CLAUDE.md`) | Prompt engineering for a specific model |
| How you enter work (launcher, tmux session per workspace) | Provider keys beyond auth under `$CIND_DATA` |
| Docker isolation and optional host socket | Picking a “better” model |

Agent selection (`agent` vs `claude`, aliases like `agy` / `ccy`) is a **lower layer** — convenient slots, not the product core.

```text
cind.config.yaml  →  mounts + workspace roots
                  →  context pack (manifest, instructions, ignores)
                  →  tmux / launcher
                  →  agent | claude   (their models stay theirs)
```

## Context unit = workspace

A workspace is the primary **context unit**: one root, one tmux session, one or more project checkouts. See [Virtual workspace](workspace.md).

### Canonical context pack

`init-workspace` maintains this set at the workspace root (no separate pack format):

| File | Role | Update policy |
| --- | --- | --- |
| `.manifest.json` | Paths and symlinks (source of truth) | Every start |
| `AGENTS.md` / `CLAUDE.md` | Behaviour for both CLIs | Every start |
| `.cursorignore` | Cursor read exclusions | Missing-only |
| `.cursorindexingignore` | Cursor index exclusions | Missing-only |
| `.claudeignore` | Claude discovery exclusions | Missing-only |
| `.claude/settings.json` | Claude `permissions.deny` for secrets | Missing-only |
| `.cursor/rules/` | Lasting Cursor rules | Missing-only seed |
| `.cind/session-brief.md` | Optional shared handoff (goal / done / constraints) | **On demand only** |

Agents should read: **`AGENTS.md` → `.manifest.json` → (if present) `.cind/session-brief.md` → project files after `cd`**.

### Per-repo context

cind **does not** auto-modify mounted git checkouts. Workspace ignores do not rewrite `backend/.env` protection inside a project.

Ritual after `make config-wizard` or any config edit:

```bash
make env
make init-project-all          # missing-only ignores/templates in every projects[].path
make down && make terminal-docker
```

Dry-run: `make init-project-all-dry-run`. Inside the container: `cind-init-projects` / `cind-context-status`.

Launcher keys: `s` = context status, `i` = init hint. Menu lines show compact flags (`brief`, `init:backend`, …).

### Session brief (handoff)

Shared scratch for `agent` and `claude` in the same workspace — not a task queue and not model config:

```bash
# inside the container, from the workspace root (or with CIND_WORKSPACE_ROOT set)
cind-session-brief   # alias: brief
```

Creates `.cind/session-brief.md` if missing. When present, tmux status-right shows **brief**, and `AGENTS.md` requires agents to read it before coding.

### Context status

```bash
cind-context-status              # all workspaces
cind-context-status gotibooks    # by name
cind-context-status              # uses $CIND_WORKSPACE_ROOT when set
```

## Non-goals

cind will **not**:

- UI or flags for choosing / pinning models
- An `AgentProvider` abstraction over `agent` / `claude`
- Auto-routing prompts between CLIs
- Shared RAG / memory outside workspace files
- A task orchestrator (brief → CLI → result queue) — that would be a separate product on top of this contract

## Related

- [Virtual workspace](workspace.md)
- [Cursor defaults and project init](../cursor.md)
- [Security](../security.md)
- [Makefile](../makefile.md)
