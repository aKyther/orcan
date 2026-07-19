# Toolchain PATH for login shells (Docker ENV PATH is reset by /etc/profile).
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${HOME}/.local/share/pnpm:${HOME}/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH}"
