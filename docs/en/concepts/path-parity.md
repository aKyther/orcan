---
description: Path parity — same absolute paths on host and in the Orcan container, and why nested Docker needs it.
---

# Path parity

## Problem

You run Docker **inside** the Orcan container (`make terminal-docker`). The daemon that creates nested containers is still the **host** daemon. Bind mounts are resolved on the host.

If the path inside Orcan were `/workspace/app` while the host checkout lived at `/home/you/code/app`, nested Compose would mount the wrong directory — or nothing.

## Why it hurts

Broken nested builds, empty volumes, and “it works on my laptop path but not in the agent container” bugs that are expensive to debug.

## How Orcan addresses it

**Path parity** means the same absolute path on the host and inside the Orcan container.

Example: host `/home/you/code/app` is mounted at `/home/you/code/app` in the container (not rewritten to `/workspace/app`).

Workspace UX still uses short symlinks under `/home/developer/workspaces/<name>/` for navigation. Parity mounts are for correctness with Docker-from-Docker. See [Mental Model](../ideas/mental-model.md).

## How it works

`make env` writes mounts into `.orcan/compose-projects.generated.yml`:

```yaml
# conceptual
volumes:
  - /absolute/path/to/app:/absolute/path/to/app
```

## Check (commands last)

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
