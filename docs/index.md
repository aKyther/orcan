# Cursor CLI Dev Container

This project gives you an isolated Docker environment for **Cursor CLI** and a full developer toolchain.

## What this project is

A ready-to-run container image and Compose setup where:

* your chosen project is mounted at `/workspace`
* Cursor CLI and common tools are already installed
* the host stays free of global language toolchains
* optional Docker socket access is an explicit choice

## Who should use it

* Developers who use Cursor CLI on Linux or WSL
* Teams that want the same toolchain for every machine
* Anyone who wants clearer boundaries between agent work and the host OS

## Project goals

1. Keep the host clean.
2. Give Cursor a complete toolbox.
3. Make everyday commands short (`make build`, `make shell`).
4. Be honest about security limits.

## Start here

| Page | Content |
| --- | --- |
| [Getting started](getting-started.md) | First successful run |
| [Installation](installation.md) | Requirements and setup |
| [Docker](docker.md) | Image, Compose, volumes, users |
| [Makefile](makefile.md) | Every Make command |
| [Cursor](cursor.md) | Global profile, image defaults, project init |
| [Security](security.md) | What is and is not isolated |
| [Development](development.md) | Repository vs container layout |
| [FAQ](faq.md) | Common questions |
| [Troubleshooting](troubleshooting.md) | Fixes for common failures |

!!! tip

    If you only want to try it once, open [Getting started](getting-started.md).
