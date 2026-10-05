#!/usr/bin/env bash
# Install only the host Orcan CLI from an offline kit. It never imports config,
# projects, sandbox data, credentials, or Docker images.
set -Eeuo pipefail

kit_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
install_dir="${ORCAN_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/orcan}"
bin_dir="${ORCAN_BIN_DIR:-$HOME/.local/bin}"
runtime="$kit_dir/orcan-runtime.tar.gz"

test -f "$runtime" || { echo "missing orcan-runtime.tar.gz" >&2; exit 2; }
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
printf 'Installed Orcan CLI at %s (no configuration, projects, sandbox data, or secrets were copied).\n' "$install_dir"
printf 'Use: export PATH="%s:\$PATH"\n' "$bin_dir"
