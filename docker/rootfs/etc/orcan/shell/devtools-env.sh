# Keep tool caches and bytecode out of mounted project trees.
# Caches go under $HOME/.cache (Compose bind: $ORCAN_DATA/cache).
# Sourced by docker-entrypoint and /etc/profile.d/orcan-devtools.sh.
# Override any variable explicitly if you need the default tool behaviour.

# Python: no __pycache__ / .pyc beside sources; unbuffered logs for agents
if [[ -z "${PYTHONDONTWRITEBYTECODE+x}" ]]; then
    export PYTHONDONTWRITEBYTECODE=1
fi
if [[ -z "${PYTHONUNBUFFERED+x}" ]]; then
    export PYTHONUNBUFFERED=1
fi

export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"

# Linters / typecheckers / package managers → shared host cache volume
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-${XDG_CACHE_HOME}/ruff}"
export MYPY_CACHE_DIR="${MYPY_CACHE_DIR:-${XDG_CACHE_HOME}/mypy}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${XDG_CACHE_HOME}/pip}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME}/uv}"
export PRE_COMMIT_HOME="${PRE_COMMIT_HOME:-${XDG_CACHE_HOME}/pre-commit}"
export YARN_CACHE_FOLDER="${YARN_CACHE_FOLDER:-${XDG_CACHE_HOME}/yarn}"
export npm_config_cache="${npm_config_cache:-${XDG_CACHE_HOME}/npm}"
export PNPM_HOME="${PNPM_HOME:-${XDG_CACHE_HOME}/pnpm}"
export CARGO_HOME="${CARGO_HOME:-${XDG_CACHE_HOME}/cargo}"
export GOPATH="${GOPATH:-${XDG_CACHE_HOME}/go}"
export GOCACHE="${GOCACHE:-${XDG_CACHE_HOME}/go-build}"
export GOMODCACHE="${GOMODCACHE:-${GOPATH}/pkg/mod}"
export TURBO_CACHE_DIR="${TURBO_CACHE_DIR:-${XDG_CACHE_HOME}/turbo}"

# Shell history under $HOME (Compose bind: $ORCAN_DATA/history)
export HISTFILE="${HISTFILE:-${HOME}/.local/share/orcan/history/.zsh_history}"

# pytest: do not create .pytest_cache/ inside repos (append if user already set opts)
_orcan_pytest_no_cache="-p no:cacheprovider"
if [[ -z "${PYTEST_ADDOPTS:-}" ]]; then
    export PYTEST_ADDOPTS="${_orcan_pytest_no_cache}"
elif [[ "${PYTEST_ADDOPTS}" != *no:cacheprovider* ]]; then
    export PYTEST_ADDOPTS="${PYTEST_ADDOPTS} ${_orcan_pytest_no_cache}"
fi
unset _orcan_pytest_no_cache
