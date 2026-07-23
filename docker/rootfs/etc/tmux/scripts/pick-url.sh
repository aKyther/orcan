#!/usr/bin/env bash
# Pick an http(s) URL from the current pane and copy it (joins soft-wraps).
# Autodetect/click breaks when a long URL wraps; capture-pane -J keeps one match.
# ttyd-safe: display-menu (no fzf popup).
set -Eeuo pipefail

copy_url() {
    local url="$1"
    tmux set-buffer -b orcan-url "${url}"
    # OSC 52 when set-clipboard is on (browser / local paste).
    if ! printf '%s' "${url}" | tmux load-buffer -w - 2>/dev/null; then
        tmux set-buffer "${url}" 2>/dev/null || true
    fi
    tmux display-message " URL copied (${#url} chars) — paste: prefix ] "
}

if [[ "${1:-}" == "--copy" ]]; then
    shift
    if [[ -z "${1:-}" ]]; then
        tmux display-message ' pick-url: empty URL '
        exit 1
    fi
    copy_url "$1"
    exit 0
fi

pane_id="$(tmux display-message -p '#{pane_id}')"
tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

# -J joins soft-wrapped lines so one logical URL stays one match.
tmux capture-pane -t "${pane_id}" -J -p -S - -E - > "${tmp}"

mapfile -t urls < <(
    grep -oE 'https?://[^[:space:]<>"'\''\`\)\]\}]+' "${tmp}" \
        | sed -E 's/[.,;:!?'\''")\]\}]+$//' \
        | awk 'NF && !seen[$0]++'
)

if [[ "${#urls[@]}" -eq 0 ]]; then
    tmux display-message ' no http(s) URLs in this pane '
    exit 0
fi

if [[ "${#urls[@]}" -eq 1 ]]; then
    copy_url "${urls[0]}"
    exit 0
fi

menu_args=(-T "URLs in pane (copies to clipboard)")
keys=(a b c d e f g h i j k l m n o p q r s t u v w x y z)
limit="${#urls[@]}"
if (( limit > ${#keys[@]} )); then
    limit="${#keys[@]}"
fi

i=0
while (( i < limit )); do
    url="${urls[$i]}"
    label="${url}"
    if (( ${#label} > 72 )); then
        label="${label:0:34}…${label: -34}"
    fi
    qurl="$(printf '%q' "${url}")"
    menu_args+=("${label}" "${keys[$i]}" "run-shell -b '/etc/tmux/scripts/pick-url.sh --copy ${qurl}'")
    i=$((i + 1))
done

if (( ${#urls[@]} > limit )); then
    menu_args+=("… $(( ${#urls[@]} - limit )) more (scroll / re-run after fewer URLs)" "" "")
fi

tmux display-menu -t "${pane_id}" "${menu_args[@]}"
