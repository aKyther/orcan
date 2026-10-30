#!/usr/bin/env bash
# shellcheck shell=bash
orcan_cmd_executor() {
    case "${1:-help}" in
        help|-h|--help)
            cat <<'EOF'
Orcan background executor plugin (enabled by --with-redis)

Enable: orcan up --with-redis
Host commands: orcan executor COMMAND ...
Inside Orcan:  orcan-executor COMMAND ...

  help / --help             This guide; no running container required
  url                       Dashboard URL (same ttyd host, separate port; default 8765)
  doctor [--lane LANE]       Check broker and the matching local worker lease/lock
  settings                  Effective queue/parallel limits, timeout and retention
  diagnostics               Sanitized Redis/AOF, publication and execution-lock health
  overview                  Bounded task overview used by the cockpit
  init --repo PATH --kind python|java|scala|custom
                            Scaffold project procedures; review and commit them
  profiles --repo PATH      List procedures from the committed snapshot
  submit --repo PATH --sha HEAD --profile selected --test SELECTOR --task TASK
                            Queue a committed snapshot; return job ID and SHA
  submit ... --replace-pending GROUP
                            Replace matching owned pending ancestor checks; never running jobs
  submit ... --notify-codex-thread UUID
                            Opt in to a compact message in that local Codex session
  notify JOB --codex-thread UUID
                            Attach a session to an already submitted job
  deliveries [--job JOB]     Notification states: queued is not consumed
  ack JOB [--codex-thread UUID]
                            Confirm consumption; does not accept code or test outcome
  stats [--hours N]         Payload bytes, reductions, timings; model tokens unavailable
  history [--hours N]       Compact history; default last 3 hours
  result JOB                Read the small result once it is available
  status [--failures]        Bounded list of retained jobs
  artifacts JOB             List full report and JUnit XML files, 50 per page
  logs JOB [--artifact report.json] --offset 0 --limit 4000
                            Consume long diagnostics in bounded chunks
  listen --after STREAM_ID  Completion JSONL; separate controller process only
  recover [--job JOB]        Guarded recovery; refuses active execution and completed jobs

Use reviewed profiles for heavy builds, analysis, generation, reports and tests.
Default detailed-result retention: 1 hour; compact history: 30 days / 10000 expired entries. Never block an interactive agent on
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
