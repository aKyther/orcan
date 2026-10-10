set -Eeuo pipefail
kit=$(mktemp -d)
trap 'rm -rf "$kit"' EXIT
orcan bundle create --output "$kit/bundle" "$@" >&2
tar -C "$kit/bundle" -czf - .
