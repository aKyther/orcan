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
                -h | --help | "")
                    printf 'usage: orcan context worktree create --repo PATH --branch NAME [--workspace NAME --project NAME]\n'
                    printf '       orcan context worktree remove --path PATH [--force]\n'
                    printf '       orcan context worktree remove --workspace NAME [--force]\n'
                    printf '  Managed paths: \$ORCAN_DATA/worktrees/<workspace>/<project>\n'
                    ;;
                *)
                    orcan_usage_error "usage: orcan context worktree <create|remove>"
                    ;;
            esac
            ;;
        add)
            orcan_context_add "$@"
            ;;
        assert)
            orcan_context_assert "$@"
            ;;
        hook)
            orcan_context_hook "$@"
            ;;
        *)
            orcan_usage_error "usage: orcan context <show|add|worktrees|worktree|assert|hook> (wizard moved to: orcan init)"
            ;;
    esac
}

orcan_context_hook() {
    local action="${1:-}"
    shift || true

    case "${action}" in
        enable | disable | status) ;;
        -h | --help | "")
            printf 'usage: orcan context hook <enable|disable|status> [PATH ...] [--all] [--dry-run]\n'
            printf '  Toggle the optional Claude Code Stop hook (orcan-context-reflect) in a\n'
            printf "  project's .claude/settings.json. Takes effect immediately — no orcan sync.\n"
            printf '  PATH: one or more project directories (default: current directory)\n'
            printf '  --all: every project in %s\n' "${ORCAN_CONFIG_FILE}"
            printf '\n'
            printf '  Claude-only by design: Cursor CLI has no reliably wired stop-hook here\n'
            printf '  to fire this. Cursor still benefits — it reads the same CONTEXT-\n'
            printf '  ASSERTIONS.md (via AGENTS.md) that this hook helps populate, automatically,\n'
            printf '  once orcan sync compiles it.\n'
            return 0
            ;;
        *)
            orcan_usage_error "usage: orcan context hook <enable|disable|status>"
            ;;
    esac

    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/claude_hook.py" \
        "${action}" "$@" --config "${ORCAN_CONFIG_FILE}"
}

orcan_context_assert() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        propose | list | show | accept | reject | retire | select | root)
            ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
                orcan_host_python "${ORCAN_SCRIPTS}/context_assertions.py" "${sub}" "$@"
            ;;
        -h | --help | "")
            cat <<'EOF'
usage: orcan context assert <command> [arguments]

  propose --project PATH (--file PATH|-|--text STRING) --justification TEXT
          [--title T] [--kind rule|fact|hint|policy] [applicability flags]
                          Reflection: draft a candidate (status: proposed)
  list --project PATH [--status proposed|accepted|rejected|retired]
                          List assertions anchored to a project
  show --project PATH ID
                          Print one assertion (full record)
  accept --project PATH ID [--edit-content PATH] [--edit-justification TEXT]
         [--override-applicability [applicability flags]]
                          Review Gate: proposed -> accepted (never automatic)
  reject --project PATH ID
                          Review Gate: proposed -> rejected
  retire --project PATH ID
                          accepted -> retired
  select --workspace NAME --project PATH [--project PATH ...] [--limit N]
                          Applicability Layer preview — what `orcan sync`
                          would compile into CONTEXT-ASSERTIONS.md
  root                    Print $ORCAN_DATA/context

  Applicability flags (propose / accept --override-applicability):
    --workspace NAME (repeatable)          --repo-all-of NAME (repeatable)
    --repo-any-of NAME (repeatable)        --repo-none-of NAME (repeatable)
    --branch GLOB (repeatable)             --valid-from / --valid-until YYYY-MM-DD

Store: $ORCAN_DATA/context/<project-id>/ (git-versioned, one repo per anchor).
Anchoring is organisational only — it never decides when an assertion
applies; the applicability predicate does. Agents never read this store
directly — only the compiled CONTEXT-ASSERTIONS.md in each workspace's
context pack (RFC-0001: Context Assertions / Applicability Layer).
EOF
            ;;
        *)
            orcan_usage_error "usage: orcan context assert <propose|list|show|accept|reject|retire|select|root>"
            ;;
    esac
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
                printf '  Default: managed under \$ORCAN_DATA/worktrees/<workspace>/<project>\n'
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
