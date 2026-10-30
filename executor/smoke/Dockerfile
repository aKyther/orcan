# Isolated integration fixture: never retag or restart the user's Orcan image.
FROM orcan:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends redis-server && rm -rf /var/lib/apt/lists/*
COPY executor/ /opt/orcan-executor-src/
RUN cd /opt/orcan-executor-src && UV_PYTHON_INSTALL_DIR=/opt/python UV_PROJECT_ENVIRONMENT=/opt/orcan-executor/venv uv sync --locked --python 3.12 && chmod -R a+rX /opt/python /opt/orcan-executor /opt/orcan-executor-src
COPY docker/rootfs/etc/orcan/supervisor.d/ /etc/orcan/supervisor.d/
COPY docker/rootfs/etc/orcan/supervisord.conf /etc/orcan/supervisord.conf
COPY docker/rootfs/usr/local/bin/orcan-supervisord docker/rootfs/usr/local/bin/orcan-executor docker/rootfs/usr/local/bin/orcan-executor-redis /usr/local/bin/
# Only the test notification service resolves Codex to a fake transport.
COPY executor/smoke/fake_codex.py /opt/orcan-smoke-bin/codex
RUN chmod 755 /opt/orcan-smoke-bin/codex && printf '\nenvironment=PATH="/opt/orcan-smoke-bin:%%(ENV_PATH)s"\n' >> /etc/orcan/supervisor.d/executor-notifications.conf
USER developer
ENTRYPOINT []
CMD ["orcan-supervisord"]
