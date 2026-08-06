#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_help() {
    cat <<'EOF'
orcan — work-context orchestrator for coding agents

Usage:
  orcan <command> [arguments]

Commands:
  init [PATH]              No PATH: interactive config wizard (create or edit)
                           PATH: non-interactive scaffold (scripts/CI)
                           Either way: scaffold/wizard + sync + show
  sync                     Materialise .env + .orcan/* for Compose
  context show             List workspaces
  context add PATH         Add a project (optional --workspace NAME)
  context add --from-worktree REPO SELECTOR
                           Add an existing git worktree as a project
  context worktrees [REPO] List git worktrees for a repo (default: cwd)
  context worktree create  Create a worktree (+ optional managed path) and pin it
  context worktree remove  Remove a managed worktree (--path or --workspace)
  context assert propose|list|show|accept|reject|retire|select
                           Context Assertions: propose/review candidates for
                           CONTEXT-ASSERTIONS.md, compiled by `orcan sync`
                           (orcan context assert --help for details)
  context hook enable|disable|status [WORKSPACE ...] [--all]
                           Toggle the optional Claude Code Stop hook
                           (batched Reflection drafting) in the workspace's
                           generated root — needs `orcan sync` at least once
  up [--with-docker] [--with-git]
                           Start browser terminal
                           --with-docker: mount Docker socket
                           --with-git: mount host ~/.ssh (+ agent) for push/pull
  down                     Stop containers
  build [--claude|--cursor] [--force]
                           Both agents → orcan:latest + orcan:<VERSION>.
                           --claude/--cursor → orcan:<VERSION>-claude|cursor (no pull)
  pull                     Pull both-agents orcan:<VERSION> → orcan:latest
  publish                  Manual push of both-agents orcan:latest (maintainers)
  url                      Print http://localhost:<port>
  logs                     Follow container logs
  enter [--launcher|--shell|--tmux [SESSION]]
                           Local terminal into the running container
                           (default: agent-launcher; alias: go-in)
  update [--release|--main] Checkout newest release tag (default) or main
  doctor                   Host / config health report
  uninstall [--purge-data] Remove CLI (and optionally ORCAN_DATA)
  version                  Print version
  help                     Show this help

Optional:
  seed [--all] [--dry-run] Copy templates into git checkouts (rarely needed;
                           workspace pack is enough — see docs)

Ritual:
  orcan init                 # interactive wizard (or: orcan init /path/to/repo)
  orcan build && orcan up
  # after config edits: orcan init && orcan down && orcan up

Install home:  ORCAN_ROOT (clone)
User config:   ORCAN_HOME (default ~/.config/orcan/home)
Tool data:     ORCAN_DATA (default ~/.config/orcan)

Host deps:     bash, git, python3 (sync/wizard), docker compose
               (orcan doctor checks these)
EOF
}
