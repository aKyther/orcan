#!/usr/bin/env bash
# Common bootstrap for every orcan command.
# shellcheck shell=bash

set -Eeuo pipefail

_ORCAN_LIB_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=log.sh
source "${_ORCAN_LIB_DIR}/log.sh"
# shellcheck source=paths.sh
source "${_ORCAN_LIB_DIR}/paths.sh"
# shellcheck source=deps.sh
source "${_ORCAN_LIB_DIR}/deps.sh"
# shellcheck source=compose.sh
source "${_ORCAN_LIB_DIR}/compose.sh"
# shellcheck source=git.sh
source "${_ORCAN_LIB_DIR}/git.sh"
# shellcheck source=image.sh
source "${_ORCAN_LIB_DIR}/image.sh"
# shellcheck source=runtime.sh
source "${_ORCAN_LIB_DIR}/runtime.sh"

orcan_log_init
orcan_paths_init
