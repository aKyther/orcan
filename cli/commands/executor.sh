#!/usr/bin/env bash
# shellcheck shell=bash
orcan_cmd_executor() {
    case "${1:-help}" in
        help|-h|--help)
            cat <<'EOF'
Orcan background executor (optional --with-redis module)

Enable: orcan up --with-redis
Host commands: orcan executor COMMAND ...
Inside Orcan:  orcan-executor COMMAND ...

  help / --help             This guide; no running container required
  url                       Dashboard URL (same ttyd host, separate port; default 8765)
  doctor                    Check module, broker and worker readiness
  init --repo PATH --kind python|java|scala|custom
                            Scaffold project procedures; review and commit them
  profiles --repo PATH      List procedures from the committed snapshot
  submit --repo PATH --sha HEAD --profile selected --test SELECTOR --task TASK
                            Queue a committed snapshot; return job ID and SHA
  result JOB                Read the small result once it is available
  status [--failures]        Bounded list of retained jobs
  artifacts JOB             List full report and JUnit XML files, 50 per page
  logs JOB [--artifact report.json] --offset 0 --limit 4000
                            Consume long diagnostics in bounded chunks
  listen --after STREAM_ID  Completion JSONL; separate controller process only
  recover [--job JOB]        Recover delivery after a broker/worker interruption

Use long or small approved checks without flooding the agent with successful logs.
Default completed-result retention: 1 hour. Never block an interactive agent on
listen or poll status repeatedly. Full suites require an explicit scope choice.
No manual uv, Celery or Uvicorn setup is needed in the built Orcan image.
Guide: docs/en/guides/background-executor.md
EOF
            return 0
            ;;
        url)
            orcan_load_env
            printf '%s\n' "$(orcan_executor_url)"
            return 0
            ;;
    esac
    local container
    container="$(orcan_require_running_container)" || return
    docker exec -i "${container}" orcan-executor "$@"
}
