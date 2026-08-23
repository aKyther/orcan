#!/usr/bin/env bash
# shellcheck shell=bash
# Move existing project checkouts under the managed root (ORCAN_PROJECTS_ROOT)
# so future project add/remove doesn't need its own Compose bind mount —
# see scripts/repository/migrate_projects.py and docs/en/ideas/mental-model.md.

orcan_cmd_migrate() {
    local yes=0
    local no_symlink=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes | -y)
                yes=1
                shift
                ;;
            --no-symlink)
                no_symlink=1
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan migrate [--yes] [--no-symlink]

  Move every configured project currently outside the managed root
  (ORCAN_PROJECTS_ROOT, default ~/.config/orcan/sandbox) under it, and
  update orcan.config.json in place.

  Default is a dry-run (prints the plan only). Pass --yes to actually move.
  A compat symlink is left at each old path unless --no-symlink is given.

  Why: a project path outside the managed root needs its own Compose bind
  mount, so adding a sibling project can still force a container recreate.
  Moving it here once removes that project from ever needing one again.

  After migrating: orcan sync (then orcan up if the container isn't running).
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1 (try: orcan migrate --help)"
                ;;
        esac
    done

    orcan_require_python
    orcan_load_env

    local -a args=(--root "${ORCAN_HOME}")
    if (( yes )); then
        args+=(--yes)
    fi
    if (( no_symlink )); then
        args+=(--no-symlink)
    fi

    ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
        ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT:-}" \
        orcan_host_python "${ORCAN_SCRIPTS}/migrate_projects.py" "${args[@]}"
}
