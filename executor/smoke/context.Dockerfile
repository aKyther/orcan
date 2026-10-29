FROM orcan:latest
USER root
COPY docker/rootfs/usr/local/lib/orcan/ /usr/local/lib/orcan/
COPY docker/rootfs/usr/local/bin/docker-entrypoint docker/rootfs/usr/local/bin/orcan-agent-enabled docker/rootfs/usr/local/bin/orcan-init-project docker/rootfs/usr/local/bin/cursor-init-project docker/rootfs/usr/local/bin/init-ai-statusline docker/rootfs/usr/local/bin/init-claude-home docker/rootfs/usr/local/bin/init-cursor-home /usr/local/bin/
COPY docker/rootfs/opt/cursor-defaults/ /opt/cursor-defaults/
USER developer
ENTRYPOINT []
