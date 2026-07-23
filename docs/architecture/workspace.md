# Virtual workspace architecture

A **workspace** is the primary **context unit** in orcan: one directory under `/home/developer/workspaces/<name>`, one tmux session, one or more mounted repos, and a [context pack](context.md#canonical-context-pack).

orcan orchestrates that context. `agent` / `claude` are tools inside it; **models stay outside** orcan config.

## Model

```text
Host (orcan repo, automatic)              Container (always)
──────────────────────────────────    ─────────────────────────────────────
.orcan/workspaces/              →    /home/developer/workspaces/
  gotibooks/                              gotibooks/
    .cursor/rules/                          .cursor/rules/
    .manifest.json, AGENTS.md, …            context pack
    backend/  → symlink                     backend/   → /home/you/.../backend (parity)
    frontend/                               frontend/  → /home/you/.../frontend (parity)
  other/                                  other/
```

One Compose bind mounts the whole `.orcan/workspaces/` tree (not one bind per workspace). Each workspace is a subdirectory — project symlinks stay only under that subdirectory.

| Concept | Path / meaning |
| --- | --- |
| Workspace (context unit) | tmux session name = `workspaces[].name` |
| Workspace root | Always `/home/developer/workspaces/<name>` in the container |
| Host persistence | Auto: `<orcan-repo>/.orcan/workspaces/<name>/` (not in JSON) |
| `projects[]` | Path parity mount + symlink as subdirectory under workspace root |
| tmux tabs | `tab-1`, `tab-2`, `tab-3` (shells in the same workspace; configurable) |

You do **not** set container paths in JSON — orcan handles parity mounts and symlinks.

## Path parity + symlinks

Every `projects[].path` is bind-mounted at the **same absolute path** on host and in the container. That keeps `docker compose` bind mounts working when you use the host Docker socket.

Under the workspace root, `init-workspace` creates symlinks:

```text
/home/developer/workspaces/gotibooks/backend → /home/you/gotibooks/backend
```

Agents start in the workspace root and `cd` into project subdirectories.

## One tmux session per workspace

- ttyd launcher lists **workspaces**.
- Choosing a workspace attaches **one** tmux session.
- Default layout: **three tabs** — `tab-1`, `tab-2`, `tab-3` (all in this workspace root). These are **not** other workspaces. Rename or add windows with normal tmux commands.
- Second workspace = second **tmux session** (launcher → pick again after detach, or `prefix s` / `prefix w`).
- Project repos appear as subdirectories under the workspace root (symlinks).
- Agent and shell start in the **workspace root**; projects are subdirectories.

## Configuration

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace id — directory under `/home/developer/workspaces/` and tmux session name |
| `projects[].name` | Symlink name under workspace root |
| `projects[].path` | Host absolute path (parity mount) |

No `alias`, no `default_project`, no `default_workspace`, no `mount_mode`, no per-workspace `tmux`.

## Workspace-level Cursor rules

On the host, edit `<orcan-repo>/.orcan/workspaces/<name>/.cursor/rules/` (created by `make env`). Inside the container the same files appear under `/home/developer/workspaces/<name>/.cursor/rules/`.

## Context pack (agents)

On container start, `init-workspace` maintains the canonical **context pack** at the workspace root:

| File | Role | Policy |
| --- | --- | --- |
| `.manifest.json` | Machine-readable projects / paths | Every start |
| `AGENTS.md` | Agent instructions | Every start |
| `CLAUDE.md` | Same content for Claude Code | Every start |
| `.cursorignore` | Cursor agent exclusions | Missing-only |
| `.cursorindexingignore` | Cursor index exclusions | Missing-only |
| `.claudeignore` | Claude discovery exclusions | Missing-only |
| `.claude/settings.json` | Claude `permissions.deny` for secrets | Missing-only |
| `.cursor/rules/workspace-context.mdc` | Cursor rule seed | Missing-only |
| `README.workspace.md` | Short human map | Every start |
| `.orcan/session-brief.md` | Optional shared handoff | **On demand** (`orcan-session-brief`) |

Agents should read **`AGENTS.md` → `.manifest.json` → session brief (if any) → project `AGENTS.md`**.

Ignore files at the workspace root help when the agent starts there. They do **not** rewrite files inside each project checkout (orcan does not auto-modify mounted repos). For per-repo `.env` protection:

```bash
make config-wizard   # or hand-edit / config-scaffold
make env
make init-project-all        # every projects[].path in config
make down && make terminal-docker
```

Check pack health: `orcan-context-status` (alias `ctx`; launcher key `s`). Session brief shows as **brief** in tmux status-right when `.orcan/session-brief.md` exists.

Global layers: Cursor `~/.cursor/cli-config.json` deny rules; Claude `~/.claude/settings.json` deny rules (seeded additively by `init-ai-statusline`).

Do not treat workspace root as a git root.

Custom lasting rules: edit `.cursor/rules/` under `<orcan-repo>/.orcan/workspaces/<name>/` (not the generated `AGENTS.md`). Customize ignore files in the same tree — they are missing-only and will not be overwritten on restart.

Full product boundary and non-goals: [Context orchestration](context.md).

See also: [Path parity](../path-parity.md), [Cursor](../cursor.md#what-belongs-in-the-mounted-project).
