#!/usr/bin/env bash
# shellcheck shell=bash


orcan_plugin_redis_prepare() {
    export ORCAN_REDIS_ENABLED=1
}
orcan_plugin_redis_report() {
    printf 'Background executor enabled; dashboard: %s\n' "$(orcan_executor_url)"
    printf 'Readiness: orcan executor doctor\n'
}
