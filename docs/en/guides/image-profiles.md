# Image profiles and agent context

Choose image contents in the existing JSON configuration. No second YAML file or
host YAML dependency is needed. A build profile is explicit configuration, just
like the existing `--agent` flags:

```json
{
  "build": {
    "agents": ["codex"],
    "tools": {"go": false, "rust": false}
  },
  "workspaces": []
}
```

```sh
orcan build --plan
orcan build
orcan up --with-redis
```

`--plan` prints the resolved selection without Docker or a generated environment.
CLI `--agent NAME` and `--all-agents` override the configured agent list, while
keeping the configured tool choices. Without CLI agents or `build.agents`, the
build refuses to guess. Unknown agents, tool names and non-boolean tool values
are rejected before Docker runs. Go and Rust default to enabled for compatibility.
An explicit `false` keeps their files out of the resulting runtime image layers;
Orcan does not copy them into the image and delete them in a later layer.
BuildKit may still fetch the referenced source stages. Actual size and download
savings depend on Docker's layer cache and the selected toolchain versions.

This first tool selection supports **Go and Rust**. Node/npm, Python/uv and the
other existing base tools remain installed. Agents and Orcan helpers can depend
on them; they are not advertised as individually removable yet. User-mounted
caches and manually installed binaries are preserved. Selection changes require
a new image build and container recreation; `sync` alone cannot remove software
from an existing container. This changes no model/provider routing.

## Files follow the installed agents

The built image's `/etc/orcan/agents.json` is authoritative for context generation.
It records the actual selected clients, not a planned future configuration.

| Image selection | Generated context |
| --- | --- |
| Any agent | Shared workspace `AGENTS.md` and workspace manifest |
| Claude | `CLAUDE.md`, `.claudeignore`, `.claude/settings.json`, Claude home defaults/hooks |
| Cursor | `.cursorignore`, `.cursorindexingignore`, `.cursor/rules/`, Cursor home defaults/hooks |
| Both | Both sets |
| Codex/Gemini/Copilot without Claude/Cursor | Shared context; no Claude/Cursor files |

Startup and runtime reconcile apply this selection to all existing and future
workspaces. Host `sync` reads the target image manifest without running its
entrypoint; without an available manifest, it creates shared context only. The
running container reconciles against its own actual image. Old images without
a baked manifest use the installed CLI binaries as a compatibility fallback.

When a client is disabled, Orcan removes only unchanged workspace defaults it
owns. A small `.orcan/agent-context.json` records their hashes. Identical legacy
defaults can also be recognized. Custom files, modified ignores, custom Cursor
rules, and symlinks are preserved. Existing user home settings are not deleted.
`CLAUDE.md` is removed only when it still matches the generated workspace context.
Project repositories are never automatically rewritten at container startup.

To seed a project explicitly, run `orcan-init-project PATH` inside Orcan or
`orcan seed` from the host. The initializer uses image templates and the same
agent selection, so Claude-only images do not need a Cursor home directory.
`cursor-init-project` remains a compatibility spelling. Existing project files
are preserved unless the user explicitly selects the initializer's `--force`
option, which makes backups. Context-status hints request only active clients'
files. An agent already in a conversation should reread workspace instructions
after switching images.
