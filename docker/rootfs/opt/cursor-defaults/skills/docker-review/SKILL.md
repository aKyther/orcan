---
name: docker-review
description: >-
  Review Dockerfile, Compose, Makefile, entrypoints, UID/GID mapping,
  volumes, Docker socket access, and image hygiene. Use when the user
  asks for a Docker or container environment review.
---

# Docker review

Review container-related files in the current project.

## Scope

Inspect when present:

- `Dockerfile` / Containerfiles
- Compose files
- `Makefile` Docker targets
- Entrypoint and init scripts
- UID/GID mapping
- Named volumes and bind mounts
- Docker socket access
- Non-root execution
- Image size and multi-stage builds
- BuildKit cache usage
- `amd64` / `arm64` compatibility notes

## Review checklist

1. Is the runtime user non-root?
2. Are secrets absent from image layers?
3. Is the Docker socket optional and documented?
4. Do bind mounts stay limited to the project?
5. Do `down`/`clean` targets avoid deleting volumes by default?
6. Are APT installs using `--no-install-recommends` where applicable?
7. Is cache used without breaking reproducibility goals?

## Report format

Use the **final-review** skill for the closing report.
Label findings as **Verified**, **Assumption**, or **Not checked** when reviewing Docker files.

## Rules

- Do not claim a build passed unless `docker build` / `make build` ran.
- Do not recommend `--privileged` or mounting `/`, `/home`, or `/etc`.
- Treat textual agent rules as guidance, not isolation.
