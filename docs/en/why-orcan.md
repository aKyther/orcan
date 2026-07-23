---
description: Why Orcan exists — the problem of fragmented repos and lost work context, and when not to use it.
---

# Why Orcan?

## The problem

You do not work in one repository.

You work across many. They often come from different organisations. Some depend on each other. Some need a specific version of a shared library. Each machine ends up with a slightly different mix of tools, logins, and “how we start the day” scripts.

After a few months, the hard part is not cloning a repo. The hard part is **recreating the full work context**: which checkouts belong together, where agents should start, what they should ignore, and which absolute paths Docker-from-Docker will still understand.

Without a shared description of that context, every developer (and every agent) rebuilds it by memory.

## Why that hurts

- Onboarding means guessing which five repos matter for “customer A”.
- Agents index the wrong trees or miss the shared library sitting next to the app.
- Nested Docker binds break when the container path is not the host path.
- Toolchains and CLI logins scatter across host homes and one-off containers.

Commands alone do not fix that. You need a **named context** you can recreate.

## What Orcan is for

Orcan is a **work-context orchestrator**.

It does not replace Git. It does not pick AI models. It describes **which projects form one workspace**, mounts them with **path parity**, seeds a small **context pack** agents can read, and opens a **browser terminal** (tmux + zsh) where Cursor CLI (`agent`) and Claude Code (`claude`) run inside Docker.

The product idea is simple: **projects are parts; the workspace is the context.**

## Life without Orcan

You keep a personal list of paths. You open five terminals. You hope `docker compose` inside a container still sees `/home/you/...`. You paste the same ignores into every checkout. You explain the layout to each new agent from scratch.

## Life with Orcan

You write one JSON config: workspaces and absolute project paths. `make env` materialises mounts and runtime files. You open one browser terminal, pick a workspace, and both you and the agents share the same layout and the same starter instructions.

## When to use it

- Several related git checkouts (often multi-org) form one daily job.
- You want coding agents in an isolated Docker environment.
- You need Docker-from-Docker with correct bind paths (path parity).
- You want a repeatable “session” per customer or product line.

## When not to use it

- One small repo and a normal local IDE is enough.
- You do not want Docker on the host.
- You need a product that **routes or pins models** — that stays with each CLI.
- You want a hosted SaaS image registry — Orcan is **clone + `make build`**.

## Design stance (non-goals)

Orcan deliberately does **not**:

- choose or abstract models across `agent` / `claude`
- auto-route prompts between CLIs
- rewrite every mounted git checkout on every start

Those boundaries keep the tool small: **orchestrate context, not cognition.**

## Next

1. [Core Ideas](ideas/core-ideas.md) — Project, Workspace, Context  
2. [Mental Model](ideas/mental-model.md) — how the pieces relate  
3. [Quick Start](getting-started/quickstart.md) — when you are ready to run
