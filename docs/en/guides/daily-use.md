---
description: Return to your project, switch workspaces, leave a session, and stop Orcan.
tags:
  - guide
---

# Daily use

Use this page after your [first session](../getting-started/quickstart.md).
A **workspace** groups your project folders. Cockpit is Orcan's terminal
interface for opening those workspaces and working with your agent.

## Return to your work

Open your computer's terminal (your WSL2 Linux terminal on Windows). Run:

```bash
orcan up
orcan enter
```

You do not need to repeat installation, configuration or image preparation each
day. If you changed the configuration, run `orcan sync` before starting.

Select your workspace if prompted. If your agent is still running, continue in
its terminal. If it has stopped, open your project folder and launch it again
with `codex`, `claude`, or `agent`, depending on what you installed. Conversation
resume options belong to that agent; opening Orcan does not guarantee that the
agent resumes a previous conversation.

## Switch workspaces or open another project

Press **F4**, choose a workspace, then select it. To move into one of its project
folders, use `pwd` to check where you are, `ls` to see folder names and
`cd folder-name` to open one. Replace `folder-name` with the label you chose;
if you are already in a project folder, `cd ..` returns to its parent folder.

To connect an additional project, leave Cockpit using **Exit**. In the host
terminal, run `orcan init --cli` and follow the questions to edit your workspace
and add the folder. Save your choices, then run `orcan sync`.
If Orcan reports that the new path needs a container recreation, finish active
work before running `orcan down` followed by `orcan up` and `orcan enter`.
See [Workspaces](../concepts/workspaces.md) for more choices.

## Leave without stopping work

Click **Exit** in Cockpit's top bar. This returns to the host terminal while the
container and its terminal sessions keep running. Use `orcan enter` to return.

Closing a browser tab disconnects that view; it does not stop the container.
Turning off the computer or stopping Docker interrupts running work.

## Stop Orcan

Finish or save active work first. In the host terminal:

```bash
orcan down
```

This removes the running container and ends its processes. Your project files,
configuration and saved agent data remain. Run `orcan up` and `orcan enter` next
time; launch your agent again if needed.

## Find your files

Orcan connects the project folder you selected during setup. Changes inside that
folder are visible on your computer too. Keep project work there; do not rely on
arbitrary files elsewhere inside the container surviving its removal.

To review configured folder paths, run `orcan context show` in the host terminal.
Orcan's default configuration and saved tool data live under `~/.config/orcan/`.

## Cache space

Orcan checks supported tool caches hourly and lets each tool remove stale data
safely. This keeps useful downloads available for later work. It does not delete
all cache every hour or promise a fixed disk size.
See [Automatic cache maintenance](orcan-flow.md#automatic-cache-maintenance)
for retention periods, status and how to disable it.

## Get help

| Need | Where to go |
| --- | --- |
| Keyboard shortcuts | Press **F1** in Cockpit |
| Command overview | Run `orcan help` in the host terminal |
| Help for a command | For example, `orcan enter --help` |
| Something is broken | [Troubleshooting](troubleshooting.md) |
| Browser, SSH, Git or advanced workflows | [Advanced workflows](workflows.md) |
| Change installed agents or tools | [Image profiles](image-profiles.md) |
