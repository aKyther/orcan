#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_doctor() {
    local fail=0
    local pass=0

    check() {
        local label="$1"
        local ok="$2"
        local detail="${3:-}"
        if [[ "${ok}" == "1" ]]; then
            printf '  %s%-4s%s %s' "${ORCAN_CLR_GREEN}" "ok" "${ORCAN_CLR_RESET}" "${label}"
            ((pass++)) || true
        else
            printf '  %s%-4s%s %s' "${ORCAN_CLR_RED}" "FAIL" "${ORCAN_CLR_RESET}" "${label}"
            ((fail++)) || true
        fi
        if [[ -n "${detail}" ]]; then
            printf ' %s(%s)%s' "${ORCAN_CLR_DIM}" "${detail}" "${ORCAN_CLR_RESET}"
        fi
        printf '\n'
    }

    printf '%s%sorcan doctor%s\n\n' "${ORCAN_CLR_BOLD}" "" "${ORCAN_CLR_RESET}"
    printf 'Paths\n'
    check "ORCAN_ROOT" "$([[ -d ${ORCAN_ROOT} && -f ${ORCAN_ROOT}/cli/orcan.sh ]] && echo 1 || echo 0)" "${ORCAN_ROOT}"
    check "ORCAN_HOME" "$([[ -d ${ORCAN_HOME} ]] && echo 1 || echo 0)" "${ORCAN_HOME}"
    check "ORCAN_DATA" "$([[ -d ${ORCAN_DATA} ]] && echo 1 || echo 0)" "${ORCAN_DATA}"
    check "config file" "$([[ -f ${ORCAN_CONFIG_FILE} ]] && echo 1 || echo 0)" "${ORCAN_CONFIG_FILE}"
    check ".env" "$([[ -f ${ORCAN_ENV_FILE} ]] && echo 1 || echo 0)" "${ORCAN_ENV_FILE}"

    printf '\nDependencies\n'
    check "bash" "$(orcan_have bash && echo 1 || echo 0)" "${BASH_VERSION:-}"
    check "git" "$(orcan_have git && echo 1 || echo 0)"
    check "python3" "$(orcan_have python3 && echo 1 || echo 0)"
    check "docker" "$(orcan_have docker && echo 1 || echo 0)"
    if orcan_have docker && docker compose version >/dev/null 2>&1; then
        check "docker compose" "1" "$(docker compose version --short 2>/dev/null || true)"
    else
        check "docker compose" "0"
    fi

    printf '\nEnvironment\n'
    if [[ -f "${ORCAN_ENV_FILE}" ]]; then
        orcan_load_env
        local projects="${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}"
        local runtime="${ORCAN_CONFIG_HOST:-${ORCAN_RUNTIME_DIR}/runtime-config.json}"
        check "compose mounts" "$([[ -f ${projects} ]] && echo 1 || echo 0)" "${projects}"
        local git_name="${GIT_AUTHOR_NAME:-}"
        local git_email="${GIT_AUTHOR_EMAIL:-}"
        if [[ -n "${git_name}" && -n "${git_email}" ]]; then
            check "git identity" "1" "${git_name} <${git_email}>"
        else
            check "git identity" "0" "set host git user.name/email, then: orcan sync"
        fi
        local git_overlay="${ORCAN_COMPOSE_GIT:-${ORCAN_RUNTIME_DIR}/compose-git.generated.yml}"
        if [[ -f "${git_overlay}" ]]; then
            check "git overlay (up --with-git)" "1" "${git_overlay}"
        else
            check "git overlay (up --with-git)" "1" "created on demand by: orcan up --with-git"
        fi
        if [[ -d "${HOME}/.ssh" ]]; then
            check "host ~/.ssh" "1" "${HOME}/.ssh"
        else
            check "host ~/.ssh" "0" "needed for: orcan up --with-git"
        fi
        check "runtime config" "$([[ -f ${runtime} ]] && echo 1 || echo 0)" "${runtime}"
        if [[ -f "${ORCAN_CONFIG_FILE}" && -f "${runtime}" ]]; then
            if [[ "${ORCAN_CONFIG_FILE}" -nt "${runtime}" ]]; then
                check "config freshness" "0" "config newer than runtime — run: orcan sync"
            else
                check "config freshness" "1"
            fi
        fi
    else
        check "generated runtime" "0" "run: orcan sync"
    fi

    printf '\nContext\n'
    if [[ -f "${ORCAN_HOME}/workspaces/index.json" ]]; then
        local hook_lines
        hook_lines="$(ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/claude_hook.py" \
            status --all --home "${ORCAN_HOME}" 2>/dev/null)"
        if [[ -n "${hook_lines}" ]]; then
            while IFS= read -r line; do
                local hook_status ws_name
                hook_status="$(awk '{print $1}' <<<"${line}")"
                ws_name="$(awk '{print $2}' <<<"${line}")"
                [[ -z "${ws_name}" ]] && continue
                if [[ "${hook_status}" == "enabled" ]]; then
                    check "context hook: ${ws_name}" "1"
                else
                    # Informational, not a failure: this is also the steady
                    # state after a deliberate `orcan context hook disable`,
                    # which is indistinguishable from "never got seeded" —
                    # both just mean the hook isn't in settings.json today.
                    check "context hook: ${ws_name}" "1" "disabled — enable: orcan context hook enable ${ws_name}"
                fi
            done <<<"${hook_lines}"
        else
            check "context hook" "1" "no workspaces yet — run: orcan init"
        fi
    else
        check "context hook" "1" "no workspace manifest yet — run: orcan sync"
    fi

    if [[ -S /var/run/docker.sock ]]; then
        check "docker.sock" "1" "/var/run/docker.sock"
    else
        check "docker.sock" "0" "needed for: orcan up --with-docker"
    fi

    local local_bin="${HOME}/.local/bin"
    if [[ ":${PATH}:" == *":${local_bin}:"* ]]; then
        check "~/.local/bin on PATH" "1"
    else
        check "~/.local/bin on PATH" "0" "open a new shell or: export PATH=\"\$HOME/.local/bin:\$PATH\" (install.sh updates shell rc)"
    fi
    if orcan_have orcan; then
        check "orcan on PATH" "1" "$(command -v orcan)"
    else
        check "orcan on PATH" "0" "run install.sh or link bin/orcan"
    fi

    printf '\n'
    orcan_maybe_hint_update

    if (( fail > 0 )); then
        orcan_error "${fail} check(s) failed, ${pass} passed"
        return 1
    fi
    orcan_ok "all ${pass} checks passed"
    return 0
}
