# Security policy

Orcan's intended threat model — what it isolates and what it deliberately does
not — is documented at [docs/en/reference/security.md](docs/en/reference/security.md)
([Polish](docs/pl/reference/security.md)). Read that first: some things listed
below as "risk" are known, intentional trade-offs (e.g. `orcan up
--with-docker`), not bugs.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.

Use [GitHub Security Advisories](https://github.com/aKyther/orcan/security/advisories/new)
for this repository to report privately. Include:

- Affected version (`VERSION` file / `orcan version`)
- Steps to reproduce
- Impact (what an attacker gains)

We aim to acknowledge reports within a few days.

## Supported versions

Only the latest tagged release is supported. There is no long-term-support
branch.
