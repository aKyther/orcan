#!/usr/bin/env bash
# Start one resolved selection of bundled plugins.
# shellcheck shell=bash
source "${ORCAN_ROOT}/cli/lib/plugins.sh"

orcan_cmd_up() {
    if [[ " $* " == *" --help "* || " $* " == *" -h "* ]]; then
        printf 'usage: orcan up --resume [--web-terminal-auth USER:PASS]\n'
        printf '       orcan up [--web-terminal | --web-terminal-auth USER:PASS] [--docker-socket | --network NAME] [--with-ssh] [--github [--github-hostname HOST]] [--gitlab [--gitlab-hostname HOST]]\n'
        printf '  --with-redis: enable local background executor, Redis and dashboard (separate port, same ttyd host)\n'
        printf '  default: start the plugins enabled in orcan settings\n'
        printf '  --web-terminal | --web-terminal-auth USER:PASS: pick one (| = mutually exclusive)\n'
        printf '  --web-terminal: publish browser terminal, no password prompt\n'
        printf '  --web-terminal-auth USER:PASS: publish browser terminal with HTTP basic auth\n'
        printf '  --docker-socket | --network NAME: pick one (| = mutually exclusive)\n'
        printf '  --docker-socket: mount /var/run/docker.sock (DinD)\n'
        printf '  --with-ssh: mount host ~/.ssh (+ agent) for push/pull (key exposure risk)\n'
        printf '  --network NAME: join an existing Docker network\n'
        printf '  --github: provide GitHub authentication (GH_TOKEN or gh auth login)\n'
        printf '  --github-hostname HOST: GitHub host (default: github.com; Enterprise Server uses GH_ENTERPRISE_TOKEN)\n'
        printf '  --gitlab: provide GitLab authentication (GITLAB_TOKEN or saved glab login)\n'
        printf '  --gitlab-hostname HOST: GitLab host (default: gitlab.com)\n'
        printf '  Compatibility aliases: --ssh, --with-git, --with-docker, --with-network, --with-ttyd, --with-ttyd-auth\n'
        printf '  --resume: restart with the flags of the last orcan up (kept across orcan down)\n'
        printf '  --docker-socket and --with-ssh expose credentials/capabilities to agents inside the container.\n'
        printf '  Plugin defaults: orcan settings; temporary overrides: --with NAME | --without NAME\n'
        return 0
    fi
    local with_redis=0 with_docker=0 with_git=0 with_github=0 with_gitlab=0 with_network=0 with_ttyd=0
    local with_ttyd_opt=0 with_ttyd_auth=0 resume=0
    local github_hostname="" gitlab_hostname="" network_name="" ttyd_credential="" git_overlay=""
    local ORCAN_REDIS_ENABLED=0 ORCAN_GITHUB_TOKEN="" ORCAN_GITLAB_TOKEN=""
    local ORCAN_ACTIVE_PLUGINS="" ORCAN_PLUGINS_JSON="" resolved
    export ORCAN_REDIS_ENABLED ORCAN_GITHUB_TOKEN ORCAN_GITLAB_TOKEN ORCAN_ACTIVE_PLUGINS ORCAN_PLUGINS_JSON
    # Resolve before host authentication and before any container lifecycle action.
    # Disable tracing across the transient auth argument and generated shell values.
    local traced=0
    if [[ $- == *x* ]]; then traced=1; set +x; fi
    if ! resolved="$(orcan_host_python "${ORCAN_SCRIPTS}/plugin-plan.py" \
        --config "${CONFIG:-${ORCAN_CONFIG_FILE:-${ORCAN_HOME}/orcan.config.json}}" \
        --last-up "$(orcan_last_up_file)" -- "$@")"; then
        if ((traced)); then set -x; fi
        return 2
    fi
    orcan_require_docker
    orcan_require_generated
    orcan_load_config
    eval "${resolved}"
    if ((traced)); then set -x; fi
    ORCAN_REDIS_ENABLED="${with_redis}"
    orcan_maybe_hint_upgrade
    orcan_plugins_run prepare || return
    # Preparation failures leave the current container running.
    orcan_compose_ttyd_down_all_variants
    orcan_info "starting container (plugins: ${ORCAN_ACTIVE_PLUGINS})"
    orcan_run_selected up -d || return
    orcan_plugins_run verify || return
    orcan_write_up_state "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${network_name}" "${with_github}" "${github_hostname}" "${with_gitlab}" "${gitlab_hostname}" "${with_redis}"
    orcan_write_last_up "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_ttyd_auth}" "${network_name}" "${with_github}" "${github_hostname}" "${with_gitlab}" "${gitlab_hostname}" "${with_redis}"
    orcan_plugins_run report || return
    if ((!with_ttyd)); then orcan_ok "container ready — local access: orcan enter"; fi
        printf 'Stop with: orcan down\n'
}
