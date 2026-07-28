#!/usr/bin/env bash
# Install orcan CLI into the current user account.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
#   OR: bash install.sh
#
# Installs to:
#   ~/.local/share/orcan   (clone)
#   ~/.local/bin/orcan     (launcher)

set -Eeuo pipefail

REPO_URL="${ORCAN_REPO_URL:-https://github.com/aKyther/orcan.git}"
REPO_REF="${ORCAN_REPO_REF:-main}"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
BIN_HOME="${ORCAN_BIN_DIR:-${HOME}/.local/bin}"
INSTALL_DIR="${ORCAN_INSTALL_DIR:-${DATA_HOME}/orcan}"

bold=""
reset=""
if [[ -t 1 && -z "${ORCAN_NO_COLOR:-}" ]]; then
    bold=$'\033[1m'
    reset=$'\033[0m'
fi

info() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

need() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

info "${bold}orcan installer${reset}"
info ""

need bash
need git
need python3
if ! command -v docker >/dev/null 2>&1; then
    info "Warning: docker not found — install Docker Engine before: orcan up / orcan build"
else
    if ! docker compose version >/dev/null 2>&1; then
        info "Warning: docker compose v2 not found — required for orcan up / orcan build"
    fi
fi

mkdir -p "${BIN_HOME}" "${DATA_HOME}"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Updating existing install at ${INSTALL_DIR}…"
    git -C "${INSTALL_DIR}" fetch --tags --prune
    git -C "${INSTALL_DIR}" checkout "${REPO_REF}"
    git -C "${INSTALL_DIR}" pull --ff-only origin "${REPO_REF}" || true
else
    if [[ -e "${INSTALL_DIR}" ]]; then
        die "refusing to overwrite non-git path: ${INSTALL_DIR}"
    fi
    info "Cloning ${REPO_URL} (${REPO_REF}) → ${INSTALL_DIR}"
    git clone --branch "${REPO_REF}" --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
fi

chmod +x "${INSTALL_DIR}/bin/orcan" "${INSTALL_DIR}/cli/orcan.sh"

launcher="${BIN_HOME}/orcan"
cat > "${launcher}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
export ORCAN_ROOT="${INSTALL_DIR}"
exec bash "${INSTALL_DIR}/cli/orcan.sh" "\$@"
EOF
chmod +x "${launcher}"

info "Installed launcher: ${launcher}"

if [[ ":${PATH}:" != *":${BIN_HOME}:"* ]]; then
    info ""
    info "Add ${BIN_HOME} to your PATH, for example:"
    info "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    info "  # or for zsh:"
    info "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    info "Then open a new shell."
fi

mkdir -p "${XDG_CONFIG_HOME:-${HOME}/.config}/orcan/home"

info ""
info "${bold}Done.${reset} Host needs: bash, git, python3, docker compose"
info "Next:"
info "  orcan doctor"
info "  orcan init /absolute/path/to/your/repo"
info "  orcan build"
info "  orcan up"
info ""
info "Config home: ${XDG_CONFIG_HOME:-${HOME}/.config}/orcan/home"
info "Docs: https://akyther.github.io/orcan/latest/"
info "Note: orcan is Bash; sync/wizard/init use python3 on the host (stdlib only)."
