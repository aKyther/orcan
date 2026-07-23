# Devtool hygiene: keep caches out of project checkouts (see /etc/orcan/shell/devtools-env.sh).
# shellcheck disable=SC1091
if [[ -f /etc/orcan/shell/devtools-env.sh ]]; then
    # shellcheck source=/etc/orcan/shell/devtools-env.sh
    . /etc/orcan/shell/devtools-env.sh
fi
