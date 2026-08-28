---
description: Orcan — work-context orchestrator for coding agents across many repositories.
tags:
  - concept
---

# Orcan

<div class="orcan-hero" markdown>

Orcan orchestrates **work context** for coding agents: which repositories belong together, how they are mounted, and how you enter that environment in Docker.

It does **not** choose models — Cursor CLI (`agent`) and Claude Code (`claude`) keep their own accounts.

<span class="orcan-version">Version **3.1.0**</span>

</div>

## Start here

<div class="grid cards" markdown>

-   :material-download-outline: __Install__

    ---

    Put `orcan` on your PATH, then sync and build.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-lightbulb-outline: __Understand__

    ---

    Why Orcan exists, Project / Workspace / Context, and the mental model.

    [:octicons-arrow-right-24: Why Orcan?](why-orcan.md)

    [:octicons-arrow-right-24: Core Ideas](ideas/core-ideas.md)

-   :material-map-search-outline: __Find a change__

    ---

    Matrix of *what you want to change* → *where in the repo* → *which doc*.

    [:octicons-arrow-right-24: Change map](change-map.md)

-   :material-book-search-outline: __Look up__

    ---

    CLI flags, env vars, Compose, security — after you know the story.

    [:octicons-arrow-right-24: CLI reference](reference/cli.md)

    [:octicons-arrow-right-24: FAQ](faq.md)

</div>

## Three words

| Term | Meaning |
| --- | --- |
| **Project** | One checkout — an absolute path on disk |
| **Workspace** | A named set of projects that belong together + one tmux session |
| **Context** | The reproducible environment: mounts, instructions, ignores, entry path |

Configuration describes those relationships. `orcan sync` and Docker apply them. Agents and humans share the same layout.

## Try it

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
orcan doctor
orcan init /absolute/path/to/your-repo
orcan sync && orcan build && orcan up
# local: orcan enter
```

Full steps: [Installation](getting-started/installation.md) · [Quick Start](getting-started/quickstart.md).

!!! note
    Config changes always need `orcan sync` before recreate (`orcan down && orcan up`). Rebuild the image only when Dockerfile or agent install inputs change.

## See also

- [Mental Model](ideas/mental-model.md) — how the pieces relate  
- [Architecture](architecture.md)  
- [Changelog](changelog.md) · [GitHub](https://github.com/aKyther/orcan)
