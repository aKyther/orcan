# Docker image filesystem

Files under `rootfs/` are copied into the container image.

Their paths match the final container layout.

```text
docker/rootfs/
├── etc/
│   ├── profile.d/cursor-dev-path.sh
│   ├── skel/
│   │   ├── .bashrc.d/50-cursor-dev.sh
│   │   ├── .tmux.conf
│   │   └── .vimrc
│   └── ssh/sshd_config.d/cursor.conf
├── opt/
│   └── cursor-defaults/     → /opt/cursor-defaults
└── usr/
    └── local/
        └── bin/
            ├── docker-entrypoint
            ├── init-cursor-home
            ├── cursor-init-project
            └── cursor-sshd
```

## Rules

* Edit container files here, not in the repository root.
* Do not mix these assets with this repository's own `.cursor/` rules.
* `/opt/cursor-defaults` is immutable product config for the container user.
* Runtime writable state lives in `${HOME}/.cursor` (named volume).

## Build

The Dockerfile copies this tree with:

```dockerfile
COPY docker/rootfs/ /
```

Then sets permissions on binaries and `/opt/cursor-defaults`.
