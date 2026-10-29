import logging

from celery import Celery
from redis.exceptions import RedisError

from .engine import run_job
from .events import publish_pending
from .settings import broker_url, queue_name

app = Celery("orcan_executor", broker=broker_url())
app.conf.update(
    task_default_queue=queue_name(),
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=False,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={
        "visibility_timeout": 86400,
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    },
    task_publish_retry=False,
)


def flush_events():
    try:
        publish_pending()
    except RedisError:
        logging.getLogger(__name__).warning(
            "Result stored locally; run orcan-executor recover to publish pending events"
        )


@app.task(name="orcan_executor.verify")
def verify(job_id: str):
    run_job(job_id, on_started=flush_events)
    flush_events()


# A Redis lease marks a worker that reached Celery's ready state. The separate
# heartbeat thread remains responsive while the solo worker waits for a build.
from threading import Event, Thread  # noqa: E402

from celery.signals import worker_ready, worker_shutdown  # noqa: E402

_heartbeat_stop = Event()


@worker_ready.connect
def announce_ready(**kwargs):
    def heartbeat():
        from .events import client

        while not _heartbeat_stop.is_set():
            try:
                client().set(queue_name() + ":worker-ready", "1", ex=45)
            except Exception:
                pass
            _heartbeat_stop.wait(10)

    _heartbeat_stop.clear()
    Thread(target=heartbeat, daemon=True, name="executor-readiness").start()


@worker_shutdown.connect
def announce_shutdown(**kwargs):
    _heartbeat_stop.set()
    try:
        from .events import client

        client().delete(queue_name() + ":worker-ready")
    except Exception:
        pass
