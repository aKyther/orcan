#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_help() {
    cat <<'EOF'
orcan — work-context orchestrator for coding agents

Usage:
  orcan <command> [arguments]

Commands:
  init [PATH]              No PATH: TUI to create/edit workspaces (default)
                           --cli: old sequential prompt wizard instead
                           PATH: non-interactive scaffold (scripts/CI)
                           Either way: scaffold/wizard + sync + show
  sync [--prune-orphans]   Materialise .env + mounts/* for Compose; live
                           reconcile into a running container. --prune-orphans
                           also kills orphaned tmux sessions (default: report
                           only, never kill one that might have an active agent)
  migrate [--yes]          Move projects under managed root (dry-run by default)
  settings                 Edit tool settings (tmux windows/prefix, ttyd
                           port/font) — separate from workspaces/projects
  context show             List workspaces
  context add PATH         Add a project (optional --workspace NAME)
  context add --from-worktree REPO SELECTOR
                           Add an existing git worktree as a project
  context tui              TUI: pick folder → multi-select repos → workspace
                           (+ optional shared-branch worktrees); see --help
  context worktrees [REPO] List git worktrees for a repo (default: cwd)
  context worktree create  Create a worktree (+ optional managed path) and pin it
  context worktree remove  Remove a managed worktree (--path or --workspace)
  context worktree prune   Reconcile worktrees/registry.json against disk
                           (+ config); dry-run by default, --force to clean
  context assert propose|list|show|accept|reject|retire|select
                           Context Assertions: propose/review candidates for
                           CONTEXT-ASSERTIONS.md, compiled by `orcan sync`
                           (orcan context assert --help for details)
  context hook enable|disable|status [WORKSPACE ...] [--all]
                           Toggle the Claude Code Stop hook (batched
                           Reflection drafting) in the workspace's generated
                           root — on by default since first `orcan sync`;
                           opting out (disable) sticks across later syncs
  up [--with-ttyd] [--with-docker | --with-network NAME] [--with-git]
                           Start container (local: orcan enter; --with-ttyd: browser)
                           | = pick one (docker vs network)
  down                     Stop containers
  build [--claude|--cursor|--codex] [--force]
                           All agents → orcan:latest + orcan:<VERSION>.
                           --claude/--cursor/--codex → orcan:<VERSION>-claude|cursor|codex (no pull)
  pull                     Pull all-agents orcan:<VERSION> → orcan:latest
  publish                  Manual push of all-agents orcan:latest (maintainers)
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
User config:   ORCAN_HOME (default ~/.config/orcan)
Tool data:     ORCAN_DATA (default ~/.config/orcan — same root as ORCAN_HOME)

Host deps:     bash, git, python3 (sync/wizard), docker compose
               (orcan doctor checks these)
EOF
}
