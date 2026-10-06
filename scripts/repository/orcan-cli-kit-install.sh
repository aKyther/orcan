#!/usr/bin/env bash
# Install only the host Orcan CLI from an offline kit. It never imports config,
# projects, sandbox data, credentials, or Docker images.
set -Eeuo pipefail

kit_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
install_dir="${ORCAN_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/orcan}"
bin_dir="${ORCAN_BIN_DIR:-$HOME/.local/bin}"
runtime="$kit_dir/orcan-runtime.tar.gz"

test -f "$runtime" || { echo "missing orcan-runtime.tar.gz" >&2; exit 2; }

ensure_path_rc() {
    local rc="$1"
    local marker="# orcan CLI — keep ${bin_dir} on PATH"
    [[ -n "${rc}" ]] || return 1
    mkdir -p "$(dirname -- "${rc}")"
    touch "${rc}"
    grep -Fq "${marker}" "${rc}" 2>/dev/null && return 0
    {
        printf '\n%s\n' "${marker}"
        printf 'export PATH="%s:$PATH"\n' "${bin_dir}"
    } >> "${rc}"
}

ensure_user_path() {
    ensure_path_rc "${HOME}/.profile" || true
    case "$(basename "${SHELL:-sh}")" in
        zsh) ensure_path_rc "${HOME}/.zshrc" || true ;;
        bash) ensure_path_rc "${HOME}/.bashrc" || true ;;
        sh) ;;
        *)
            ensure_path_rc "${HOME}/.bashrc" || true
            ensure_path_rc "${HOME}/.zshrc" || true
            ;;
    esac
}
if command -v sha256sum >/dev/null 2>&1 && [[ -f "$kit_dir/manifest.json" ]]; then
    expected="$(python3 -c 'import json,sys; print(next(x["sha256"] for x in json.load(open(sys.argv[1]))["artifacts"] if x["name"] == "orcan-runtime.tar.gz"))' "$kit_dir/manifest.json")"
    actual="$(sha256sum "$runtime" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || { echo "runtime checksum mismatch" >&2; exit 2; }
fi
mkdir -p "$bin_dir" "$(dirname -- "$install_dir")"
staging="${install_dir}.staging.$$"
rm -rf -- "$staging"
mkdir -p "$staging"
tar -xzf "$runtime" -C "$staging"
test -f "$staging/cli/orcan.sh" || { echo "invalid Orcan runtime archive" >&2; exit 2; }
rm -rf -- "$install_dir"
mv -- "$staging" "$install_dir"
cat > "$bin_dir/orcan" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
export ORCAN_ROOT="$install_dir"
exec bash "$install_dir/cli/orcan.sh" "\$@"
EOF
chmod +x "$bin_dir/orcan"
ensure_user_path
export PATH="${bin_dir}:${PATH}"
printf 'Installed Orcan CLI at %s (no configuration, projects, sandbox data, or secrets were copied).\n' "$install_dir"
printf 'Added %s to your login and interactive shell PATH. New terminals will find `orcan`.\n' "$bin_dir"
