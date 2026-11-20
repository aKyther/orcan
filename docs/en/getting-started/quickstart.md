---
description: Open your first project in Orcan and start a conversation with a coding agent.
tags:
  - guide
---

# First session

This guide takes you from an installed Orcan to a conversation with an agent in
one project. You do not need to learn Docker commands or edit configuration files.

## Before you start

Complete [Installation](installation.md) first. You need Docker running, Orcan
installed, a project folder on your computer, and an account for the agent you
choose. Orcan does not include an AI subscription or sign you in automatically.

A **project** is the folder containing your code. A **workspace** is a named group
of projects; start with just one. Orcan runs the tools in a **container**, a separate
running environment. Your connected project files remain on your computer.
Changes made by an agent affect those files too.

## Where to type commands

Open your computer's terminal. On Windows, use the terminal of your WSL2 Linux
distribution, rather than PowerShell. This is the **host terminal**.

Copy one code block at a time, press Enter, and wait for the command to finish.
Do not continue if it reports an error: use [Troubleshooting](../guides/troubleshooting.md).
Commands in steps 1–4 run in this host terminal.

## 1. Choose your project

```bash
orcan init
```

Follow the prompts to name a workspace and select your project folder. Enter the
full folder path, for example `/home/alex/projects/my-app`. Replace this example
with your own path; keep quotes around paths containing spaces when using shell
commands. A folder's Properties or your file manager can help you find its path.

For your first session, use the existing folder. Leave the advanced **worktree**
option off; it creates a separate checkout and is optional.

**Expected result:** Orcan saves your choices. This step does not start anything.

## 2. Apply your choices

```bash
orcan sync
```

**Expected result:** Orcan prepares the files needed to connect your project.
Repeat this step whenever you change your workspace configuration.

## 3. Prepare your agent

Choose **one** example below for the agent account you already use:

=== "Codex"

    ```bash
    orcan build --agent codex
    ```

=== "Claude Code"

    ```bash
    orcan build --agent claude
    ```

=== "Cursor CLI"

    ```bash
    orcan build --agent cursor
    ```

This prepares an **image**, the reusable package of tools used to start Orcan.
The first preparation can take several minutes or longer, depending on your
connection and computer. Wait until the command finishes successfully.
You do not need to repeat it each day.

Other clients and tool choices are covered in [Image profiles](../guides/image-profiles.md).

## 4. Start and open Orcan

```bash
orcan up
```

When it finishes, open the working environment:

```bash
orcan enter
```

**Expected result:** the Orcan terminal interface, called **Cockpit**, opens.
Select your workspace if prompted. Press **F4** to open the workspace picker
and **F1** for keyboard help.

## 5. Open the project and talk to your agent

You are now **inside Orcan**. The center terminal accepts shell commands.
List the workspace folders:

```bash
ls
```

Open your project's folder using the name shown, for example:

```bash
cd my-app
```

Then type the command for the agent you prepared: `codex`, `claude`, or `agent`
(Cursor CLI). Follow that agent's sign-in instructions. The agent may ask you to
open a browser or approve access to the project. Login and billing belong to the
agent provider; Orcan does not manage them.

Start with a small request, such as:

> Explain what this project does and how to run it. Do not change files yet.

**Expected result:** your agent responds about the selected project.

## Finish and come back later

Use Cockpit's **Exit** button to return to your host terminal. This leaves the
container and terminal sessions running. Stopping the container ends its running
processes; it does not delete your project files.

See [Daily use](../guides/daily-use.md) for returning tomorrow, stopping Orcan,
and switching projects.

## Git inside the container

If you only need to open your project and talk to an agent, the steps above are
enough. To send or receive Git changes over SSH, host SSH access is an additional
choice: see [Git access](../guides/workflows.md#scenario-git-pushpull-from-inside-the-container).

## Common problems

| What you see | Next step |
| --- | --- |
| `orcan: command not found` | Open a new terminal; see [command not found](../guides/troubleshooting.md#orcan-command-not-found) |
| Docker is unavailable | Start Docker; see [Docker problems](../guides/troubleshooting.md#docker-is-not-running-or-access-is-denied) |
| No project in the picker | See [missing projects](../guides/troubleshooting.md#launcher-is-empty-wrong-projects) |
| Agent command not found | See [missing agent](../guides/troubleshooting.md#agent-or-claude-missing) |
| Agent asks for login | Follow its sign-in instructions; see [login help](../guides/troubleshooting.md#the-agent-asks-me-to-sign-in) |
