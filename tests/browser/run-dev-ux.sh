#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
PLAYWRIGHT_IMAGE="${ORCAN_PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.55.0-noble}"
URL="${ORCAN_DEV_UX_URL:-$("${ROOT_DIR}/scripts/dev/orcan-preview" url)}"
UPDATE="${1:-}"

docker info >/dev/null 2>&1 || { printf 'Error: Docker daemon unavailable\n' >&2; exit 1; }
"${ROOT_DIR}/scripts/dev/orcan-preview" doctor >/dev/null
mkdir -p "${ROOT_DIR}/.orcan-dev-ux/artifacts/playwright"

args=(test --config=/work/tests/browser/playwright.config.js)
if [[ "${ORCAN_A11Y_ONLY:-}" == 1 ]]; then
    args+=(dev-a11y.spec.js)
else
    args+=(dev-ux.spec.js)
fi
[[ "${UPDATE}" != "--update" ]] || args+=(--update-snapshots)
[[ -z "${UPDATE}" || "${UPDATE}" == "--update" ]] || { printf 'Usage: %s [--update]\n' "$0" >&2; exit 2; }

docker run --rm --network host \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp/playwright-home \
    -e "ORCAN_DEV_UX_URL=${URL}" \
    -v "${ROOT_DIR}:/work" -w /work \
    "${PLAYWRIGHT_IMAGE}" \
    bash -lc "mkdir -p \"\$HOME\" /work/.orcan-dev-ux/playwright-node && \
        npm install --silent --no-save --no-package-lock \
            --prefix /work/.orcan-dev-ux/playwright-node @playwright/test@1.55.0 @axe-core/playwright@4.10.2 && \
        NODE_PATH=/work/.orcan-dev-ux/playwright-node/node_modules \
            /work/.orcan-dev-ux/playwright-node/node_modules/.bin/playwright ${args[*]}"
