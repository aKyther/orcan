# Path parity

## What this means

**Path parity** = the same absolute path on the host and inside the Orcan container.

Example: host path `/home/you/code/app` is mounted at `/home/you/code/app` in the container (not at `/workspace/app`).

## Why it matters

When you run Docker **inside** Orcan (`make terminal-docker`), the **host** Docker daemon resolves bind mounts. If paths differed, nested Compose would bind the wrong directories.

## How Orcan does it

`make env` writes mounts into `.orcan/compose-projects.generated.yml`:

```yaml
# conceptual
volumes:
  - /absolute/path/to/app:/absolute/path/to/app
```

Workspace UX still uses short symlinks under `/home/developer/workspaces/<name>/`.

## Check

```bash
make path-check
```

Integration test (needs Docker socket):

```bash
make test-path-parity
```

## Common mistakes

| Mistake | Result |
| --- | --- |
| Relative `projects[].path` | Rejected or broken mounts |
| Assuming `/workspace` | Old pattern — not used |
| Editing generated Compose by hand | Overwritten by `make env` |
