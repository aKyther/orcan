# Orcan

Work on your project with an AI coding assistant in a separate environment.
Orcan connects your project folders and starts the tools you need. You choose
the assistant and sign into your own account.

## Start here

You need Docker with Compose v2, Git, Python 3, Bash and curl on your computer.
On Windows, use WSL2. See [Installation](docs/en/getting-started/installation.md)
for preparation and help.

Install Orcan in your terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

Open a new terminal, then check the installation:

```bash
orcan doctor
```

Next, follow **[Your first session](docs/en/getting-started/quickstart.md)** to
select a project, prepare your agent and start working.

## Find what you need

| I want to… | Read |
| --- | --- |
| Return to my project tomorrow | [Daily use](docs/en/guides/daily-use.md) |
| Fix a problem | [Troubleshooting](docs/en/guides/troubleshooting.md) |
| Understand workspaces | [Core Ideas](docs/en/ideas/core-ideas.md) |
| Change agents or tools | [Image profiles](docs/en/guides/image-profiles.md) |
| Use a browser, SSH or Git access | [Advanced workflows](docs/en/guides/workflows.md) |
| Look up a command | [CLI reference](docs/en/reference/cli.md) |

[Full documentation](https://akyther.github.io/orcan/latest/) ·
[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Status

Version **4.1.60**. Orcan is distributed as a CLI (`orcan`) with a terminal interface.
[Orcan Studio](https://github.com/aKyther/orcan-studio) is a separate desktop
application in development, with its own repository and documentation.

## License

[MIT](LICENSE).
