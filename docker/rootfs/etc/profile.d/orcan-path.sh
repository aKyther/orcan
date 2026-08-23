# Toolchain PATH for login shells (Docker ENV PATH is reset by /etc/profile).
# Cargo / pnpm / Go homes live under ~/.cache (see devtools-env.sh / Compose).
_orcan_cargo_bin="${CARGO_HOME:-${HOME}/.cache/cargo}/bin"
_orcan_pnpm_home="${PNPM_HOME:-${HOME}/.cache/pnpm}"
_orcan_gopath_bin="${GOPATH:-${HOME}/.cache/go}/bin"
export PATH="${HOME}/.local/bin:${_orcan_cargo_bin}:${_orcan_pnpm_home}:${_orcan_gopath_bin}:/usr/local/go/bin:/usr/local/cargo/bin:${PATH}"
unset _orcan_cargo_bin _orcan_pnpm_home _orcan_gopath_bin
