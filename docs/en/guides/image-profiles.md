# Image profiles and agent context

Choose image contents in the Agents and image section of `orcan settings`, or edit
`build.agents` and `build.tools` in the existing JSON configuration. No second YAML file or
host YAML dependency is needed. A build profile is explicit configuration, just
like the existing `--agent` flags:

```json
{
  "build": {
    "agents": [
      {"name": "codex", "version": "latest"},
      {"name": "claude", "version": "stable"}
    ],
    "tools": [
      {"name": "go", "image": "golang:1.27-bookworm"},
      {"name": "rust", "image": "rust:1-bookworm"}
    ]
  },
  "workspaces": []
}
```

Both selections are lists of named objects. `tools: []` omits both optional
toolchains. A configured build profile installs only the listed optional tools;
old CLI-only builds without a build profile keep Go/Rust for compatibility.
Short names such as `"codex"` remain accepted as shorthand for default sources.

```sh
orcan build --plan                     # reads build from orcan.config.json
orcan build
orcan build --config /path/image.json --plan
orcan build --config /path/image.json
```

`--config` selects the build section only; it does not replace workspace/runtime
configuration. `--plan` needs neither Docker nor generated environment files.
CLI `--agent NAME` / `--all-agents` override which agents are selected, retaining
version/source settings for matching configured names. Unknown names, malformed
sources, ambiguous versions and conflicting duplicates fail before Docker runs.

## Build once, start when ready

The daily flow is `orcan settings`, optional `orcan up --plan`, then `orcan up`.
Use plain `orcan build` when you want to prepare the selected image in advance.
Both commands use the same image fingerprint and completion receipt. An unchanged
image is reused. `orcan build --force` runs the build again with Docker cache;
`--no-cache` also refreshes installation steps. Compatibility agent flags remain
available for one build and do not rewrite the selection saved in settings.

`orcan build --plan` includes a computed `requirements` report. The startup plan
shows the same agent requirements plus those of enabled plugins. This report is
not a JSON configuration section to copy back into `build`.

The standard image supplies required runtimes: for example, npm-based agent CLIs
need Node and npm even when optional Go and Rust toolchains are disabled. Python
packages for cockpit and executor use their committed uv lockfiles. Selecting a
plugin enables its services/access; it does not install a second copy of its
base-image components. Arbitrary apt/pip package lists are not supported settings.
In the settings image page, Space toggles Go/Rust and Enter edits the enabled
source image. Review shows the selected image reference before saving.

## Versions and sources

- Codex, Gemini and Copilot use their npm packages. Set `version` to `latest` or
  an exact published version. Optional `source` supports `type: npm`, a package
  name and an HTTPS registry, for example an explicitly selected package mirror.
- Claude uses its native installer with `latest`, `stable` or an exact published
  version. Cursor uses its current installer for `latest`, or the official
  architecture-specific archive for an exact CLI release identifier.
- Custom native installer URLs require HTTPS and a 64-character `sha256` checksum.
  A mismatch stops before executing the downloaded installer. Custom Cursor
  archives also need a checksum and the Cursor CLI package layout. Installer
  links are explicit build inputs, never arbitrary shell expressions.
- Go/Rust accept a complete `image` reference, including a registry/tag or digest.
  Alternatively use `version` as the official image tag. Do not specify both.
  The source must retain the official `/usr/local/go` or `/usr/local/cargo` and
  `/usr/local/rustup` layout and be compatible with the runtime architecture.

The resolved requested profile is baked at `/etc/orcan/build-profile.json`.
`latest` and image tags are mutable. Docker can reuse a cached installation;
use `--no-cache` when deliberately refreshing floating inputs. Agent-managed
updaters can also change their own runtime versions. This is selection and
installation pinning, not a promise that every future runtime is immutable.

An omitted tool's files are never copied into a runtime layer and deleted later.
BuildKit can still fetch referenced source stages; downloads and savings depend
on the cache and image versions. This first optional-tool set is **Go and Rust**.
Node/npm, Python/uv and other existing base tools remain required. User-mounted
caches/manual installations are preserved. Selection changes need a new image
and recreated container; `sync` cannot remove installed software. No model/provider
routing is involved. See [Orcan flow](orcan-flow.md) for runtime plugins and memory.

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

### Claude installer HTTP 403 during an image build

The public Claude bootstrap URL may return HTTP 403 to non-interactive Python
clients. For the built-in Claude installer only, Orcan then requests the bootstrap
from Anthropic's official `downloads.claude.ai` host. It keeps native installation
and the selected version; it does not switch to npm or disable TLS checks. A custom
URL, any checksum-pinned source, another agent or a different HTTP status does not
activate this fallback. If the official downloads host also fails, the build stops.
An error in `install_agent.py claude` precedes the Dockerfile's npm-cache cleanup;
the cleanup command shown in the failed RUN block is not the failing download.

The [settings TUI](settings.md) preserves pinned versions and custom sources while
selecting other agents. Saving selection takes effect on the next `orcan up`, which builds when needed.
Use `orcan build` to build explicitly before starting. Saving does not install or start a client. `orcan up --plan` previews requested image contents
and startup integrations without inspecting or modifying the installed image.
