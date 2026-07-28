# User overlays from $ORCAN_DATA/dotfiles (host) → ~/.config/orcan/dotfiles
# shellcheck shell=bash
ORCAN_DOTFILES="${ORCAN_DOTFILES:-${HOME}/.config/orcan/dotfiles}"

if [[ -r "${ORCAN_DOTFILES}/aliases.sh" ]]; then
    # shellcheck source=/dev/null
    . "${ORCAN_DOTFILES}/aliases.sh"
fi

if [[ -d "${ORCAN_DOTFILES}/bashrc.d" ]]; then
    for f in "${ORCAN_DOTFILES}/bashrc.d"/*.sh; do
        [[ -r "${f}" ]] && . "${f}"
    done
fi
