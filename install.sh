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
CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}/orcan"

bold=""
dim=""
reset=""
if [[ -t 1 && -z "${ORCAN_NO_COLOR:-}" ]]; then
    bold=$'\033[1m'
    dim=$'\033[2m'
    reset=$'\033[0m'
fi

info() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

step() {
    local n="$1"
    shift
    info ""
    info "${bold}── ${n}. $*${reset}"
}

ok() { info "  ✓ $*"; }
note() { info "  ${dim}$*${reset}"; }

need() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# Persist ~/.local/bin on PATH in shell rc (idempotent). Skip with ORCAN_SKIP_PATH=1.
ensure_path_rc() {
    local rc="$1"
    local marker="# orcan CLI — keep ${BIN_HOME} on PATH"
    [[ -n "${rc}" ]] || return 1
    mkdir -p "$(dirname "${rc}")"
    touch "${rc}"
    if grep -Fq "${marker}" "${rc}" 2>/dev/null; then
        note "already configured: ${rc}"
        return 0
    fi
    {
        printf '\n%s\n' "${marker}"
        printf 'export PATH="%s:$PATH"\n' "${BIN_HOME}"
    } >> "${rc}"
    ok "appended PATH export to ${rc}"
    return 0
}

info "${bold}orcan installer${reset}"
info "${dim}Install clone: ${INSTALL_DIR}${reset}"
info "${dim}Launcher:      ${BIN_HOME}/orcan${reset}"
info "${dim}Git ref:       ${REPO_REF}${reset}"

step 1 "Check host tools"
need bash
ok "bash $(bash --version 2>/dev/null | head -1 | sed 's/^GNU bash, //' || echo ok)"
need git
ok "git $(git --version 2>/dev/null | awk '{print $3}' || echo ok)"
need python3
ok "python3 $(python3 --version 2>/dev/null | awk '{print $2}' || echo ok)"
if ! command -v docker >/dev/null 2>&1; then
    info "  ! docker not found — install Docker Engine before: orcan up / orcan build"
else
    ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo present)"
    if ! docker compose version >/dev/null 2>&1; then
        info "  ! docker compose v2 not found — required for orcan up / orcan build"
    else
        ok "docker compose $(docker compose version --short 2>/dev/null || echo ok)"
    fi
fi

step 2 "Prepare directories"
mkdir -p "${BIN_HOME}" "${DATA_HOME}" "${CONFIG_HOME}"
ok "bin:    ${BIN_HOME}"
ok "data:   ${INSTALL_DIR%/*}"
ok "config: ${CONFIG_HOME}"

step 3 "Install or update source"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    note "existing install found — fetching ${REPO_REF}"
    git -C "${INSTALL_DIR}" fetch --tags --prune
    git -C "${INSTALL_DIR}" checkout "${REPO_REF}"
    git -C "${INSTALL_DIR}" pull --ff-only origin "${REPO_REF}" || true
    ok "updated ${INSTALL_DIR}"
else
    if [[ -e "${INSTALL_DIR}" ]]; then
        die "refusing to overwrite non-git path: ${INSTALL_DIR}"
    fi
    note "cloning ${REPO_URL} (${REPO_REF})"
    git clone --branch "${REPO_REF}" --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
    ok "cloned → ${INSTALL_DIR}"
fi
chmod +x "${INSTALL_DIR}/bin/orcan" "${INSTALL_DIR}/cli/orcan.sh"
ok "scripts executable"

step 4 "Install launcher"
launcher="${BIN_HOME}/orcan"
cat > "${launcher}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
export ORCAN_ROOT="${INSTALL_DIR}"
exec bash "${INSTALL_DIR}/cli/orcan.sh" "\$@"
EOF
chmod +x "${launcher}"
ok "wrote ${launcher}"

step 5 "Ensure PATH"
if [[ -n "${ORCAN_SKIP_PATH:-}" ]]; then
    note "ORCAN_SKIP_PATH set — skipping shell rc"
elif [[ ":${PATH}:" == *":${BIN_HOME}:"* ]]; then
    ok "current PATH already includes ${BIN_HOME}"
    shell_name="$(basename "${SHELL:-bash}")"
    case "${shell_name}" in
        zsh) ensure_path_rc "${HOME}/.zshrc" || true ;;
        bash)
            ensure_path_rc "${HOME}/.bashrc" || true
            [[ -f "${HOME}/.bash_profile" ]] && ensure_path_rc "${HOME}/.bash_profile" || true
            ;;
        *)
            ensure_path_rc "${HOME}/.zshrc" || true
            ensure_path_rc "${HOME}/.bashrc" || true
            ;;
    esac
else
    note "adding ${BIN_HOME} to your shell rc so new terminals find orcan"
    shell_name="$(basename "${SHELL:-bash}")"
    case "${shell_name}" in
        zsh)
            ensure_path_rc "${HOME}/.zshrc"
            ;;
        bash)
            ensure_path_rc "${HOME}/.bashrc"
            if [[ -f "${HOME}/.bash_profile" ]]; then
                ensure_path_rc "${HOME}/.bash_profile"
            fi
            ;;
        *)
            ensure_path_rc "${HOME}/.zshrc" || true
            ensure_path_rc "${HOME}/.bashrc" || true
            ;;
    esac
    export PATH="${BIN_HOME}:${PATH}"
    info ""
    info "  This terminal still needs PATH once (curl|bash cannot change the parent shell):"
    info "    export PATH=\"${BIN_HOME}:\$PATH\""
    info "  Or: source ~/.zshrc   /   source ~/.bashrc"
    info "  New shells will already have it."
fi

info ""
info "${bold}Done.${reset} Host needs: bash, git, python3, docker compose"
info ""
info "Next:"
info "  orcan doctor"
info "  orcan init /absolute/path/to/your/repo"
info "  orcan build"
info "  orcan up"
info ""
info "Config home: ${CONFIG_HOME}"
info "Docs: https://akyther.github.io/orcan/latest/"
info "Note: orcan is Bash; sync/init use python3 on the host (stdlib only)."
