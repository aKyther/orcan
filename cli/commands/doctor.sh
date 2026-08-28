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
                check "config freshness" "0" "orcan.config.json newer than mounts/* — run: orcan sync (no rebuild needed)"
            else
                check "config freshness" "1"
            fi
        fi
    else
        check "generated runtime" "0" "run: orcan sync (creates .env + mounts/* for orcan up)"
    fi

    # v2.0 renamed space/ → sandbox/. If .env still points at space/, the next
    # `orcan up` bind-mounts a missing host path and Docker creates it root:root.
    orcan_load_env 2>/dev/null || true
    local space_dir="${ORCAN_DATA%/}/space"
    local space_stat="" space_uid="" space_owner=""
    local projects_root="${ORCAN_PROJECTS_ROOT:-}"
    if [[ -d "${space_dir}" ]]; then
        if space_stat="$(stat -c '%u %U:%G' "${space_dir}" 2>/dev/null)"; then
            :
        else
            space_stat="$(stat -f '%u %Su:%Sg' "${space_dir}" 2>/dev/null || printf 'unknown unknown')"
        fi
        space_uid="${space_stat%% *}"
        space_owner="${space_stat#* }"
        if [[ "${space_uid}" == "0" ]]; then
            check "legacy space/ dir" "0" \
                "${space_dir} is ${space_owner} — Docker recreated a missing bind after space→sandbox. orcan down; empty: sudo rmdir; else: bash ${ORCAN_ROOT}/scripts/migrations/rename-space-to-sandbox.sh"
        else
            check "legacy space/ dir" "0" \
                "${space_dir} leftover (owner ${space_owner}) — bash ${ORCAN_ROOT}/scripts/migrations/rename-space-to-sandbox.sh"
        fi
    elif [[ -n "${projects_root}" && "${projects_root}" == "${space_dir}" ]]; then
        check "legacy space/ path" "0" \
            "ORCAN_PROJECTS_ROOT still ${projects_root} — next orcan up recreates it as root:root. Point .env at ${ORCAN_DATA%/}/sandbox; bash ${ORCAN_ROOT}/scripts/migrations/rename-space-to-sandbox.sh"
    else
        check "legacy space/ dir" "1" "absent (v2 default is sandbox/)"
    fi

    printf '\nRuntime\n'
    if orcan_have docker; then
        orcan_load_env 2>/dev/null || true
        local cname image_local
        cname="$(orcan_container_name)"
        if orcan_container_is_running "${cname}"; then
            check "container ${cname}" "1" "running"
            check "last up flags" "1" "$(orcan_up_state_summary)"
            if orcan_ttyd_is_active; then
                check "browser terminal (ttyd)" "1" "$(orcan_terminal_url | tr -d '\n')"
            else
                check "browser terminal (ttyd)" "1" "off — orcan up --with-ttyd (local: orcan enter)"
            fi
            # Supervisord (post rebuild): status line + whether durable log dir exists.
            local sup_line=""
            sup_line="$(docker exec -u developer "${cname}" bash -lc '
                if command -v supervisorctl >/dev/null 2>&1 \
                    && [[ -f ~/.local/share/orcan/history/supervisor/supervisord.conf ]]; then
                    supervisorctl -c ~/.local/share/orcan/history/supervisor/supervisord.conf status 2>/dev/null \
                        | tr "\n" "; " | head -c 200
                elif command -v orcan-supervisord >/dev/null 2>&1; then
                    echo "image has orcan-supervisord but process not running — recreate after build"
                else
                    echo "image predates supervisord — orcan build && orcan down && orcan up"
                fi
            ' 2>/dev/null || true)"
            if [[ -n "${sup_line}" ]]; then
                if [[ "${sup_line}" == *"RUNNING"* ]]; then
                    check "supervisord" "1" "${sup_line}"
                elif [[ "${sup_line}" == *"predates"* ]] || [[ "${sup_line}" == *"not running"* ]]; then
                    check "supervisord" "1" "${sup_line}"
                else
                    check "supervisord" "1" "${sup_line}"
                fi
            fi
        else
            check "container ${cname}" "0" "not running — orcan up"
        fi
        image_local="${IMAGE_LOCAL:-orcan:latest}"
        if docker image inspect "${image_local}" >/dev/null 2>&1; then
            check "image ${image_local}" "1"
        else
            check "image ${image_local}" "0" "run: orcan build"
        fi
    else
        check "docker daemon" "0" "needed for: orcan up"
    fi

    printf '\nWorkspace mapping\n'
    local runtime_cfg="${ORCAN_CONFIG_HOST:-${ORCAN_RUNTIME_DIR}/runtime-config.json}"
    if [[ -f "${runtime_cfg}" ]]; then
        local audit_container="" audit_level audit_label audit_detail
        if orcan_have docker; then
            orcan_load_env 2>/dev/null || true
            local audit_cname
            audit_cname="$(orcan_container_name 2>/dev/null || true)"
            if [[ -n "${audit_cname}" ]] && orcan_container_is_running "${audit_cname}"; then
                audit_container="${audit_cname}"
            fi
        fi
        while IFS=$'\t' read -r audit_level audit_label audit_detail; do
            [[ -z "${audit_level}" ]] && continue
            case "${audit_level}" in
                ok) check "${audit_label}" "1" "${audit_detail}" ;;
                warn) check "${audit_label}" "1" "WARN: ${audit_detail}" ;;
                fail) check "${audit_label}" "0" "${audit_detail}" ;;
            esac
        done < <(
            ORCAN_HOME="${ORCAN_HOME}" \
                ORCAN_DATA="${ORCAN_DATA:-}" \
                ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT:-}" \
                ORCAN_COMPOSE_PROJECTS="${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}" \
                orcan_host_python "${ORCAN_SCRIPTS}/workspace-audit.py" \
                    --home "${ORCAN_HOME}" \
                    --container "${audit_container}" \
                    --format doctor 2>/dev/null
        )
    else
        check "workspace mapping" "1" "no runtime config — run: orcan sync"
    fi

    printf '\nContext\n'
    if [[ -f "${ORCAN_HOME}/workspaces/index.json" ]]; then
        local hook_lines
        hook_lines="$(ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/claude_hook.py" \
            status --all --home "${ORCAN_HOME}" 2>/dev/null)"
        if [[ -n "${hook_lines}" ]]; then
            while IFS= read -r line; do
                local hook_status ws_name ws_meta reflection_state last_error
                hook_status="$(awk '{print $1}' <<<"${line}")"
                ws_name="$(awk '{print $2}' <<<"${line}")"
                ws_meta="$(awk '{print $3}' <<<"${line}")"
                [[ -z "${ws_name}" ]] && continue
                if [[ "${hook_status}" == "enabled" ]]; then
                    # A hook that's on but silently failing every reflection
                    # (model call erroring/timing out) looks identical to a
                    # healthy one otherwise — it's an async Stop hook, so its
                    # stderr is never seen. Surface the last recorded failure.
                    reflection_state="${ws_meta}/.orcan/reflection-state.json"
                    last_error=""
                    if [[ -f "${reflection_state}" ]]; then
                        last_error="$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
errs = sorted(
    (v.get("last_error_at", ""), v.get("last_error", ""))
    for v in data.values() if isinstance(v, dict) and v.get("last_error")
)
if errs:
    print(errs[-1][1][:120])
' "${reflection_state}" 2>/dev/null)"
                    fi
                    if [[ -n "${last_error}" ]]; then
                        check "context hook: ${ws_name}" "0" "last reflection failed: ${last_error}"
                    else
                        check "context hook: ${ws_name}" "1"
                    fi
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

    local auto_json="${ORCAN_DATA}/history/supervisor/automation.json"
    if [[ -f "${auto_json}" ]]; then
        local auto_summary
        auto_summary="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("unreadable")
    raise SystemExit(0)
enabled = d.get("enabled", True)
paused = bool(d.get("paused"))
if not enabled:
    print("disabled (cockpit [o] to enable)")
elif paused:
    print("paused (cockpit [p] to resume)")
else:
    print("running")
' "${auto_json}" 2>/dev/null || echo "unreadable")"
        if [[ "${auto_summary}" == disabled* ]]; then
            check "context automation" "1" "${auto_summary}"
        elif [[ "${auto_summary}" == paused* ]]; then
            check "context automation" "1" "${auto_summary}"
        elif [[ "${auto_summary}" == running ]]; then
            check "context automation" "1" "${auto_summary}"
        else
            check "context automation" "0" "${auto_summary}"
        fi
    else
        check "context automation" "1" "running (default; no automation.json yet)"
    fi

    if orcan_have docker; then
        local cname_mc model_line model_ok model_detail
        cname_mc="$(orcan_container_name)"
        if orcan_container_is_running "${cname_mc}"; then
            model_line="$(docker exec -u developer "${cname_mc}" orcan-context-model-check --quick 2>&1 || true)"
            model_ok="0"
            [[ "${model_line}" == recap-model:\ ok* ]] && model_ok="1"
            model_detail="${model_line#recap-model: ok — }"
            [[ "${model_ok}" == "0" ]] && model_detail="${model_line#recap-model: FAIL — }"
            check "recap model (claude haiku)" "${model_ok}" "${model_detail}"
        fi
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
    orcan_maybe_hint_upgrade

    if (( fail > 0 )); then
        orcan_error "${fail} check(s) failed, ${pass} passed"
        return 1
    fi
    orcan_ok "all ${pass} checks passed"
    return 0
}
