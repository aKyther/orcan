#!/usr/bin/env bash
# Run host-side unit tests (no Docker image build required).
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

export PYTHONPATH="${ROOT_DIR}/scripts/repository:${ROOT_DIR}/cockpit/src${PYTHONPATH:+:$PYTHONPATH}"

if ! command -v uv >/dev/null 2>&1; then
    printf 'Host tests require uv. Install uv, then rerun make test-host.\n' >&2
    exit 1
fi

coverage=0
if [[ "${1:-}" == --coverage ]]; then
    coverage=1
    shift
fi
selection=()
case "${ORCAN_TEST_MODE:-all}" in
    all) ;;
    fast) selection=(-m 'not integration') ;;
    integration) selection=(-m integration) ;;
    *) printf 'Unknown ORCAN_TEST_MODE: use all, fast or integration\n' >&2; exit 2 ;;
esac
uv_python=(uv run --no-project --with-requirements requirements-test.txt python -m)
printf '==> host tests (%s, pytest via uv)\n' "${ORCAN_TEST_MODE:-all}"
if (( coverage )); then
    export COVERAGE_PROCESS_START="${ROOT_DIR}/.coveragerc"
    export ORCAN_COVERAGE_ROOT="${ROOT_DIR}"
    export COVERAGE_FILE="${ROOT_DIR}/.coverage"
    export PYTHONPATH="${ROOT_DIR}/tests/host/coverage_bootstrap:${PYTHONPATH}"
    "${uv_python[@]}" coverage erase
    "${uv_python[@]}" coverage run \
        -m pytest -q "${selection[@]}" "$@"
    unset COVERAGE_PROCESS_START ORCAN_COVERAGE_ROOT
    "${uv_python[@]}" coverage combine
    "${uv_python[@]}" coverage report --show-missing --skip-empty
else
    "${uv_python[@]}" pytest -q "${selection[@]}" "$@"
fi

printf '==> release.sh check\n'
./scripts/repository/release.sh check

printf 'Host tests OK\n'
