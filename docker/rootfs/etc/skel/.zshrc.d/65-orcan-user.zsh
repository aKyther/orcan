# User overlays from $ORCAN_DATA/dotfiles (host) → ~/.config/orcan/dotfiles
# Image defaults stay in /etc and /opt; put personal tweaks under the bind.
# shellcheck shell=bash
ORCAN_DOTFILES="${ORCAN_DOTFILES:-${HOME}/.config/orcan/dotfiles}"

if [[ -r "${ORCAN_DOTFILES}/aliases.sh" ]]; then
    # shellcheck source=/dev/null
    . "${ORCAN_DOTFILES}/aliases.sh"
fi

if [[ -d "${ORCAN_DOTFILES}/zshrc.d" ]]; then
    for f in "${ORCAN_DOTFILES}/zshrc.d"/*.zsh(N); do
        [[ -r "${f}" ]] && . "${f}"
    done
fi
