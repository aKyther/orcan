#!/usr/bin/env bash
# shellcheck shell=bash


orcan_plugin_redis_prepare() {
    export ORCAN_REDIS_ENABLED=1
}
orcan_plugin_redis_verify() {
    local attempt
    for attempt in {1..30}; do
        if orcan_run_selected exec -T orcan orcan-executor doctor >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    orcan_warn 'executor is not ready; inspect: orcan executor doctor'
    return 1
}
orcan_plugin_redis_report() {
    printf 'Background executor enabled; dashboard: %s\n' "$(orcan_executor_url)"
    printf 'Readiness: orcan executor doctor\n'
}
