# Roadmap

Optional hardening and publishing ideas. None of these are required to use the project today.

| Idea | Why |
| --- | --- |
| Pin tool and base image versions | Reproducible builds over time |
| Verify SHA256 of downloaded binaries | Stronger supply-chain checks |
| CI builds for `amd64` and `arm64` | Catch arch-specific breakages early |
| Scan images with Trivy | Find known CVEs before publish |
| Publish to GHCR | Share a prebuilt image |
| Slim language variants | Smaller images for focused stacks |
| Optional SSH agent forwarding | Safer than mounting `~/.ssh` |
| Image smoke tests in CI | Fail fast when a tool disappears |
| Dependabot or Renovate | Keep base images and actions current |
