#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_context() {
    local sub="${1:-show}"
    shift || true
    orcan_require_python

    case "${sub}" in
        show)
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-show.py" "$@"
            orcan_load_env
            if [[ -f "${ORCAN_ENV_FILE}" ]]; then
                printf '\n'
                printf 'Orchestrator home:      %s\n' "${ORCAN_HOME}"
                printf 'Install root:           %s\n' "${ORCAN_ROOT}"
                printf 'Workspace (container):  %s (%s)\n' \
                    "${WORKSPACE_ROOT:-${CONTAINER_PROJECT_DIR:-}}" "${WORKSPACE_NAME:-}"
                printf 'Runtime config:         %s\n' "${ORCAN_CONFIG_HOST:-${ORCAN_RUNTIME_DIR}/runtime-config.json}"
                printf 'Compose project mounts: %s\n' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}"
                if [[ -f "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}" ]]; then
                    grep -E '^[[:space:]]+- ' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}" \
                        | sed 's/^/  /' || true
                fi
                printf 'Path parity:            enabled\n'
            fi
            ;;
        wizard)
            orcan_die "moved: run 'orcan init' instead (no PATH → interactive wizard; run again anytime to add more)"
            ;;
        worktrees)
            local repo="${1:-${PWD}}"
            if [[ "${repo}" != /* ]]; then
                repo="$(cd -- "${repo}" 2>/dev/null && pwd)" || orcan_die "not a directory: ${1:-${PWD}}"
            fi
            orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" list --repo "${repo}"
            ;;
        worktree)
            local wsub="${1:-}"
            shift || true
            case "${wsub}" in
                create)
                    orcan_context_worktree_create "$@"
                    ;;
                remove)
                    orcan_context_worktree_remove "$@"
                    ;;
                prune)
                    orcan_context_worktree_prune "$@"
                    ;;
                -h | --help | "")
                    printf 'usage: orcan context worktree create --repo PATH --branch NAME [--workspace NAME --project NAME]\n'
                    printf '       orcan context worktree remove --path PATH [--force]\n'
                    printf '       orcan context worktree remove --workspace NAME [--force]\n'
                    printf '       orcan context worktree prune [--force] [--no-config]\n'
                    printf '  Managed paths: \$ORCAN_PROJECTS_ROOT/.worktrees/<workspace>/<project>\n'
                    ;;
                *)
                    orcan_usage_error "usage: orcan context worktree <create|remove|prune>"
                    ;;
            esac
            ;;
        add)
            orcan_context_add "$@"
            ;;
        tui)
            orcan_context_tui "$@"
            ;;
        recent)
            local limit="10" ws_filter=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --limit) limit="${2:-10}"; shift 2 ;;
                    --workspace) ws_filter="${2:-}"; shift 2 ;;
                    *) orcan_usage_error "usage: orcan context recent [--limit N] [--workspace NAME]" ;;
                esac
            done
            local -a args=(--data "${ORCAN_DATA:-${HOME}/.config/orcan}" recent --limit "${limit}")
            if [[ -n "${ws_filter}" ]]; then
                args+=(--workspace "${ws_filter}")
            fi
            orcan_host_python "${ORCAN_SCRIPTS}/history.py" "${args[@]}"
            ;;
        *)
            orcan_usage_error "usage: orcan context <show|add|tui|worktrees|worktree|recent> (wizard moved to: orcan init)"
            ;;
    esac
}

orcan_context_tui() {
    case "${1:-}" in
        -h | --help)
            cat <<'EOF'
usage: orcan context tui [options]

Interactive TUI. `orcan init` (no path) opens this: if workspaces already
exist it starts on the manage screen, otherwise (or via `n`) the scan
screen — point at a parent folder → multi-select git repos or plain
directories → create/update a workspace. Optional: one branch name →
managed worktree per selected git repo (plain directories are always
mounted as-is, no worktree).

Scan screen keys:
  Tab review · Space pick · Enter apply (or open when empty) ·
  l/→ open · u/← up · h recent picks · a/A all/clear · / filter · e browse ·
  D depth 1↔2 · w name · t all mount/worktree · b branch · q quit
  In Tab review: b toggles the highlighted git project mount↔worktree
  (selection preview: right column if wide, compact bar if narrow)

Manage screen keys (shown when a config already exists):
  j/k move · ←/→ collapse/expand · Enter toggle · r rename ·
  p change path · a add project (jump to
  scan, pre-filled) · d delete project · W delete workspace ·
  n new workspace (scan folder) · s save · q quit

Options:
  --dir PATH           Parent directory to scan (default: last used / cwd)
  --workspace NAME     Workspace name (default: parent folder name)
  --branch NAME        Create managed worktrees on this branch for all
  --select a,b         Pre-select (or use with --yes)
  --yes                Non-interactive (needs --dir and --select)
  --force              Replace existing workspace / projects
  --sync               Run orcan sync after writing config
  --depth N            Scan depth (default 1 = children only; 2 = grandchildren)

Examples:
  orcan context tui
  orcan context tui --dir /home/you/code/acme --sync
  orcan context tui --yes --dir ~/code/acme --select api,web --branch feature/s1 --sync
EOF
            return 0
            ;;
    esac
    ORCAN_HOME="${ORCAN_HOME}" ORCAN_ROOT="${ORCAN_ROOT}" ORCAN_DATA="${ORCAN_DATA:-}" \
        orcan_host_python "${ORCAN_SCRIPTS}/context_tui.py" "$@"
}


orcan_context_add() {
    local path=""
    local workspace=""
    local force=""
    local from_worktree=""
    local selector=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --from-worktree)
                from_worktree="${2:-}"
                shift 2 || orcan_usage_error "--from-worktree needs a repo path"
                ;;
            --workspace)
                workspace="${2:-}"
                shift 2 || orcan_usage_error "--workspace needs a value"
                ;;
            --force)
                force=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan context add /absolute/path/to/repo [--workspace NAME] [--force]\n'
                printf '       orcan context add --from-worktree /abs/repo [branch|index|path] [--workspace NAME] [--force]\n'
                return 0
                ;;
            *)
                if [[ -n "${from_worktree}" && -z "${selector}" && "$1" != --* ]]; then
                    selector="$1"
                    shift
                elif [[ -z "${path}" && -z "${from_worktree}" ]]; then
                    path="$1"
                    shift
                else
                    orcan_usage_error "unknown argument: $1"
                fi
                ;;
        esac
    done

    if [[ -n "${from_worktree}" ]]; then
        if [[ "${from_worktree}" != /* ]]; then
            orcan_usage_error "--from-worktree needs an absolute repo path"
        fi
        if [[ -z "${selector}" ]]; then
            orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" list --repo "${from_worktree}"
            orcan_usage_error "usage: orcan context add --from-worktree /abs/repo <branch|index|path>"
        fi
        path="$(
            orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" resolve \
                --repo "${from_worktree}" "${selector}"
        )" || orcan_die "could not resolve worktree ${selector}"
        orcan_info "using worktree: ${path}"
    fi

    if [[ -z "${path}" || "${path}" != /* ]]; then
        orcan_usage_error "usage: orcan context add /absolute/path/to/repo [--workspace NAME]"
    fi
    local args=(--project-dir "${path}" --config "${ORCAN_CONFIG_FILE}")
    if [[ -n "${workspace}" ]]; then
        args+=(--workspace "${workspace}")
    fi
    if [[ -n "${force}" ]]; then
        args+=(--force)
    fi
    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
        "${ORCAN_SCRIPTS}/config-scaffold.py" "${args[@]}"
    orcan_info "run: orcan sync"
}

orcan_context_worktree_create() {
    local repo=""
    local branch=""
    local path=""
    local workspace=""
    local project=""
    local force=""
    local start_point="HEAD"
    local managed=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo)
                repo="${2:-}"
                shift 2 || orcan_usage_error "--repo needs a value"
                ;;
            --branch)
                branch="${2:-}"
                shift 2 || orcan_usage_error "--branch needs a value"
                ;;
            --path)
                path="${2:-}"
                shift 2 || orcan_usage_error "--path needs a value"
                ;;
            --workspace)
                workspace="${2:-}"
                shift 2 || orcan_usage_error "--workspace needs a value"
                ;;
            --project)
                project="${2:-}"
                shift 2 || orcan_usage_error "--project needs a value"
                ;;
            --managed)
                managed=1
                shift
                ;;
            --start-point)
                start_point="${2:-}"
                shift 2 || orcan_usage_error "--start-point needs a value"
                ;;
            --force)
                force=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan context worktree create --repo PATH --branch NAME \\\n'
                printf '         [--workspace NAME --project NAME | --path PATH] [--force]\n'
                printf '  Default: managed under \$ORCAN_PROJECTS_ROOT/.worktrees/<workspace>/<project>\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    if [[ -z "${repo}" || "${repo}" != /* ]]; then
        orcan_usage_error "--repo must be an absolute path"
    fi
    if [[ -z "${branch}" ]]; then
        orcan_usage_error "--branch is required"
    fi
    # Prefer managed layout when workspace is set (project defaults to repo basename).
    if [[ -n "${workspace}" && -z "${path}" ]]; then
        managed=1
        if [[ -z "${project}" ]]; then
            project="$(basename "${repo}")"
        fi
    fi
    if (( managed )) && [[ -z "${workspace}" || -z "${project}" ]]; then
        orcan_usage_error "--managed needs --workspace and --project (or omit --path and pass --workspace)"
    fi

    local create_args=(
        create --repo "${repo}" --branch "${branch}" --start-point "${start_point}"
    )
    if [[ -n "${path}" ]]; then
        if [[ "${path}" != /* ]]; then
            orcan_usage_error "--path must be absolute"
        fi
        create_args+=(--path "${path}")
    fi
    if (( managed )); then
        create_args+=(--managed --workspace "${workspace}" --project "${project}")
    fi

    local out wt_path
    out="$(
        ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
            orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" "${create_args[@]}"
    )" || orcan_die "worktree create failed"
    printf '%s\n' "${out}"
    wt_path="$(printf '%s\n' "${out}" | tail -1)"
    if [[ -z "${wt_path}" || "${wt_path}" != /* ]]; then
        orcan_die "could not parse created worktree path"
    fi

    local args=(--project-dir "${wt_path}" --config "${ORCAN_CONFIG_FILE}")
    if [[ -n "${workspace}" ]]; then
        args+=(--workspace "${workspace}")
    fi
    if [[ -n "${force}" ]]; then
        args+=(--force)
    fi
    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
        "${ORCAN_SCRIPTS}/config-scaffold.py" "${args[@]}"
    orcan_info "run: orcan sync"
}

orcan_context_worktree_remove() {
    local path=""
    local workspace=""
    local force=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --path)
                path="${2:-}"
                shift 2 || orcan_usage_error "--path needs a value"
                ;;
            --workspace)
                workspace="${2:-}"
                shift 2 || orcan_usage_error "--workspace needs a value"
                ;;
            --force)
                force=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan context worktree remove --path PATH [--force]\n'
                printf '       orcan context worktree remove --workspace NAME [--force]\n'
                printf '  --workspace removes all managed worktrees for that workspace\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    if [[ -n "${workspace}" ]]; then
        if [[ -n "${path}" ]]; then
            orcan_usage_error "use either --path or --workspace, not both"
        fi
        local rm_args=(remove --config "${ORCAN_CONFIG_FILE}" --workspace "${workspace}")
        if [[ -n "${force}" ]]; then
            rm_args+=(--force)
        fi
        ORCAN_HOME="${ORCAN_HOME}" ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
            orcan_host_python "${ORCAN_SCRIPTS}/managed_workspace.py" "${rm_args[@]}"
        return
    fi

    if [[ -z "${path}" || "${path}" != /* ]]; then
        orcan_usage_error "--path must be an absolute managed worktree path (or pass --workspace)"
    fi
    local rm_args=(remove --path "${path}")
    if [[ -n "${force}" ]]; then
        rm_args+=(--force)
    fi
    ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
        orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" "${rm_args[@]}"
}

orcan_context_worktree_prune() {
    local force=""
    local config="${ORCAN_CONFIG_FILE}"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)
                force=1
                shift
                ;;
            --no-config)
                config=""
                shift
                ;;
            -h | --help)
                printf 'usage: orcan context worktree prune [--force] [--no-config]\n'
                printf '  Reconciles $ORCAN_PROJECTS_ROOT/.worktrees/registry.json against disk\n'
                printf '  (and orcan.config.json, unless --no-config). Dry-run by default;\n'
                printf '  --force removes orphan directories / config-stale worktrees.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    local prune_args=(prune)
    if [[ -n "${config}" && -f "${config}" ]]; then
        prune_args+=(--config "${config}")
    fi
    if [[ -n "${force}" ]]; then
        prune_args+=(--force)
    fi
    ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
        orcan_host_python "${ORCAN_SCRIPTS}/git_worktrees.py" "${prune_args[@]}"
}
