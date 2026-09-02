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
  sync --context [--watch|--once] [--interval N]
                           Spike: import inbox/decisions + compile
                           CONTEXT-ASSERTIONS.md only (host; no apply-config).
                           --watch polls; --once syncs when drops changed
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
  up [--with-ttyd | --with-ttyd-auth USER:PASS] [--with-docker | --with-network NAME] [--with-git]
                           Start container (local: orcan enter; browser: pick ttyd or ttyd-auth)
                           | = pick one (ttyd vs ttyd-auth; docker vs network)
  down                     Stop containers
  build [--claude|--cursor|--codex] [--force]
                           All agents → orcan:latest + orcan:<VERSION>.
                           --claude/--cursor/--codex → orcan:<VERSION>-claude|cursor|codex (no pull)
  pull                     Pull all-agents orcan:<VERSION> → orcan:latest
  publish                  Manual push of all-agents orcan:latest (maintainers)
  url                      Print http://localhost:<port>
  logs [docker|supervisor|context-scan]
                           Follow container logs (default) or show durable supervisord / scanner logs
  enter [--launcher|--shell|--tmux [SESSION]]
                           Local terminal into the running container
                           (default: agent-launcher; alias: go-in)
  update                   Dev channel: fast-forward to origin/main
  upgrade [--to VERSION]   Release channel: newest release tag (default), or pin VERSION
  downgrade [--to VERSION] Previous SemVer release, or pin an older VERSION
  doctor                   Host / config / container health (supervisord, context automation, recap model when running)
  uninstall [--purge-data] [--purge-images]
                           Remove Orcan; data/images are opt-in, projects are always kept
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
