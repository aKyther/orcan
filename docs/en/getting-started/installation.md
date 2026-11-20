---
description: Prepare your computer, install Orcan and check that it is ready.
tags:
  - guide
---

# Installation

Install Orcan once on the computer where your project files will live. After
installation, [Your first session](quickstart.md) walks through selecting a
project and starting your agent.

## 1. Prepare your computer

A **terminal** is the application where you type commands. A **host** is the
computer running Orcan and Docker.

=== "Linux"

    Open your Terminal application. Install Docker Engine with Compose v2, Git,
    Python 3, Bash and curl using your distribution's installation instructions.
    Start Docker before continuing.

=== "Windows (WSL2)"

    Use a WSL2 Linux distribution and a Docker setup available inside it, such as
    Docker Desktop with WSL integration enabled for that distribution.
    Open the Linux distribution's terminal and run all Orcan commands there.
    Install Git, Python 3, Bash and curl inside that distribution too.
    Use Linux project paths in Orcan, not `C:\…` paths.

=== "macOS"

    Open Terminal. Install and start Docker Desktop (with Compose v2), and make
    sure Git, Python 3, Bash and curl are available in that terminal.

Official prerequisite instructions:
[Docker Engine](https://docs.docker.com/engine/install/),
[Docker Desktop](https://docs.docker.com/desktop/),
[WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install).
If setting up these tools is unfamiliar, ask someone to help prepare them before
continuing. The Orcan installer does not install Docker for you.

Check the tools, one command at a time:

```bash
docker version
docker compose version
git --version
python3 --version
bash --version
curl --version
```

**Expected result:** each command reports its version. `docker version` must
reach the Docker server too. If it reports an error, see
[Docker problems](../guides/troubleshooting.md#docker-is-not-running-or-access-is-denied).

## 2. Install Orcan

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

This downloads and runs Orcan's installer from its GitHub repository. It installs
the `orcan` launcher under `~/.local/bin` and adds that folder to your shell's
command search path. It does not configure your project or start a container.

When the installer finishes, **open a new terminal** (your Linux terminal on
Windows). This lets it find the newly installed command.

## 3. Check the installation

```bash
orcan doctor
```

The report checks prerequisites and the current Orcan setup. Before your first
session, configuration, image or runtime items may still be missing. The next
guide creates them; fix prerequisite errors first.

If `orcan` is not found, see
[command not found](../guides/troubleshooting.md#orcan-command-not-found).

## Next: open your project

Continue with **[Your first session](quickstart.md)**. It is the single guide for
configuration, image preparation, startup and agent sign-in.

For removal instructions, see [Uninstall](../guides/workflows.md#uninstall).
