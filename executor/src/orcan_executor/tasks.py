import logging

from celery import Celery
from redis.exceptions import RedisError

from . import store
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
    task_reject_on_worker_lost=True,
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


@app.task(name="orcan_executor.verify", bind=True)
def verify(self, job_id: str):
    result = run_job(job_id, on_started=flush_events)
    if result is None and store.get(job_id)["status"] == "queued":
        # Global capacity admission is atomic in SQLite. Do not occupy an execution
        # slot while waiting, or classify capacity pressure as a failed procedure.
        raise self.retry(countdown=3, max_retries=None)
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
                client().set(app.conf.task_default_queue + ":worker-ready", "1", ex=45)
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

        client().delete(app.conf.task_default_queue + ":worker-ready")
    except Exception:
        pass
