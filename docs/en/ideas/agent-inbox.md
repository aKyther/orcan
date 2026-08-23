---
description: Agent inbox — a filesystem task queue that hands a small, structured manifest from a discussion agent to an execution agent, instead of a full transcript.
---

# Agent inbox

The **agent inbox** is a filesystem queue under `<workspace_root>/.orcan/tasks/` that
hands a small, structured **task manifest** from a discussion/planning agent to an
execution agent. It never hands over the discussion agent's own transcript.

## The problem it solves

A planning conversation in one agent session often ends with "now go implement
this." The easiest way to hand that off is pasting the whole transcript into
another session — but that burns context on back-and-forth that was never a
decision, and it gives the execution agent no way to tell "we settled this" from
"we were still arguing about this."

## How it works

A task is a JSON file that moves through a fixed set of states, mirroring the
propose → review → accept pattern already used by
[Context Assertions](context-assertions.md):

```mermaid
flowchart LR
  propose[propose] -->|policy=draft| proposals[proposals/]
  propose -->|policy=approve, default| proposals
  proposals -->|human approve| inbox[inbox/]
  propose -->|policy=auto| inbox
  inbox -->|claim, atomic| processing[processing/]
  processing --> done[done/]
  processing --> review[review/]
  processing --> failed[failed/]
```

- **`draft`** — stays in `proposals/` only; nothing ever picks it up.
- **`approve`** (default) — sits in `proposals/` until a human runs `approve`.
- **`auto`** — written straight to `inbox/`, claimable immediately.

`orcan-inbox` (in-container CLI) covers the whole lifecycle:

```bash
orcan-inbox propose --title "Add retry to fetch()" \
  --goal "Network calls should retry once on timeout" \
  --file src/fetch.ts --acceptance "Existing tests still pass"
orcan-inbox approve task-abc123
orcan-inbox watch --executor claude   # claim + run one task at a time
```

`claim` is an atomic rename (`inbox/<id>.json` → `processing/<id>.json`), so two
workers racing for the same task never both get it — the loser just gets an
`OSError` and moves on. An **executor** then turns the manifest into a prompt
(`build_prompt()` renders only the known fields: goal, context, decisions,
constraints, files, acceptance, risks — an arbitrary `transcript` field on the
task is silently dropped, not leaked into the prompt) and runs it — `claude -p`,
`codex exec`, or a plain shell command, depending on `execution.executor`.

## Trade-offs

- **Default is human-gated.** `approve` is the default policy — a task sits in
  `proposals/` until a person runs `approve`. `auto` is opt-in per task.
- **The shell executor is real command execution.** `execution.executor: shell`
  runs `execution.command` directly. Combined with `policy: auto`, a task is
  claimed and executed with no human step in between — the same trust
  boundary trade-off as the rest of Orcan (see
  [Security](../reference/security.md)), not a sandboxed evaluation.
- **Not signed.** Like the Context Assertions inbox, task JSON is plain,
  unsigned files. Anything that can write into `.orcan/tasks/inbox/` can
  queue work for whichever executor is watching it.
- **One workspace, one queue.** There is no cross-workspace routing — a task
  proposed in workspace A is only ever claimable by a watcher pointed at
  workspace A's `.orcan/tasks/`.

## Next

- [Security](../reference/security.md) — trust model and the `auto` + `shell`
  combination specifically
- [Context Assertions](context-assertions.md) — the propose/review pattern this
  reuses
- [Mental Model](mental-model.md)
