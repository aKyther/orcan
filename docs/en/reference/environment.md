# Process environment

Persistent configuration lives in `orcan.config.json`. Orcan does not read or write
`.env`. The host CLI resolves JSON settings and passes process variables to Compose;
Compose's automatic dotenv loading is disabled. Workspace manifests describe the
resolved context for agents and tools.

For field names and migration, see [Configuration](../getting-started/configuration.md#upgrade-from-dotenv-configuration).

## Host locations and authentication

| Variable | Role |
| --- | --- |
| `ORCAN_HOME` | Locate the configuration directory; default `~/.config/orcan` |
| `ORCAN_CONFIG_FILE` | Select a JSON configuration file |
| `ORCAN_DATA` / `ORCAN_PROJECTS_ROOT` | Fallback paths when `data_root` / `projects_root` are absent in JSON |
| `COMPOSE_PROJECT_NAME` / `ORCAN_INSTANCE` | Internal runtime naming; prefer `orcan --instance NAME` |
| `TTYD_CREDENTIAL` | Temporary process-only browser authentication; never persisted |
| `SSH_AUTH_SOCK` | Optional host SSH agent forwarded with `--with-ssh` |

UID/GID, the Docker socket group and global Git identity are detected from the host.
Resource, ttyd and executor variables are internal translations of JSON fields;
setting a stale `CPUS` or `TTYD_HOST_PORT` in the shell cannot override JSON.

The managed project root defaults to the data root's `sandbox/`. Changing its JSON
path does not move repositories. `orcan uninstall --purge-data` preserves project
checkouts. Review paths before moving existing data.

For the experimental offline classifier, `INSTALL_ACTIONS_ML=1` is an image build
argument. It does not configure coding-agent models. See [Offline actions](../guides/offline-actions.md).

## Optional GitHub access

`orcan up --github [--github-hostname HOST]` reads host authentication only when
requested. `GH_TOKEN` takes precedence over `GITHUB_TOKEN` for `github.com` and
`*.ghe.com`. `GH_ENTERPRISE_TOKEN` takes precedence over `GITHUB_ENTERPRISE_TOKEN`
for a GitHub Enterprise Server hostname. A saved `gh auth login` for the selected
host is the fallback. The container receives `GH_HOST` and the selected token
variable; the other token variables are cleared. `ORCAN_GITHUB_TOKEN` is an
internal, temporary Compose interpolation variable, not a persisted setting.
See [GitHub access](cli.md#github-access) for examples and token visibility.

## Optional GitLab access

`orcan up --gitlab [--gitlab-hostname HOST]` defaults to `gitlab.com`.
`GITLAB_TOKEN` takes precedence over `GITLAB_ACCESS_TOKEN`, then `OAUTH_TOKEN`.
The saved `glab` login for the exact hostname is the fallback. The container
receives `GITLAB_HOST` and `GITLAB_TOKEN`; alternative token variables and
`CI_JOB_TOKEN` are cleared, and `GLAB_ENABLE_CI_AUTOLOGIN` is disabled for this
access mode. `ORCAN_GITLAB_TOKEN` is internal and temporary, not persisted.
See [GitLab access](cli.md#gitlab-access).
