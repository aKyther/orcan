# Devtool hygiene (always refreshed from skel — keep projects free of tool caches).
# shellcheck disable=SC1091
if [[ -f /etc/orcan/shell/devtools-env.sh ]]; then
    # shellcheck source=/etc/orcan/shell/devtools-env.sh
    . /etc/orcan/shell/devtools-env.sh
fi
