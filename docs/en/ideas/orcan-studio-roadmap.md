# Studio server and container roadmap

The desktop application is maintained in the separate
[orcan-studio repository](https://github.com/aKyther/orcan-studio).
Tauri, the frontend, desktop tests and installer workflows live there.
See the [desktop documentation](https://github.com/aKyther/orcan-studio/blob/main/docs/orcan-studio-roadmap.md).

Orcan continues to own workspace and runtime management, the terminal cockpit,
and the `orcan studio …` JSON bridge used by the desktop locally, through WSL
or over SSH. The host-side bridge and its tests remain in this repository.
Installing Studio does not update the Orcan CLI or running containers.
