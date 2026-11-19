import logging
import random

from celery import Celery
from redis.exceptions import RedisError

from . import store
from .engine import run_job
from .events import publish_pending
from .settings import broker_url, queue_name, visibility_timeout

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
        "visibility_timeout": visibility_timeout(),
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


@app.task(name="orcan_executor.verify", bind=True, max_retries=None)
def verify(self, job_id: str):
    result = run_job(job_id, on_started=flush_events)
    job = store.get(job_id)
    if result is None and job["status"] == "queued":
        # Global capacity admission is atomic in SQLite. Do not occupy an execution
        # slot while waiting, or classify capacity pressure as a failed procedure.
        # None on retry() means "use the task default", not unlimited retries.
        # Set the unlimited admission budget on the task itself.
        ceiling = min(60, 3 * 2 ** min(self.request.retries, 5))
        delay = random.uniform(ceiling / 2, ceiling)
        logging.getLogger(__name__).warning(
            "Job %s awaiting admission (%s); retry %s in %.1fs; procedure not started",
            job_id,
            job.get("admission_reason") or "execution_lock",
            self.request.retries + 1,
            delay,
        )
        raise self.retry(countdown=delay)
    flush_events()


# A Redis lease marks a worker that reached Celery's ready state. The separate
# heartbeat thread remains responsive while the solo worker waits for a build.
from threading import Event, Thread  # noqa: E402

from celery.signals import worker_ready, worker_shutdown  # noqa: E402

_heartbeat_stop = Event()


def readiness_key():
    from .readiness import worker_lease

    return worker_lease(app.conf.task_default_queue, app.conf.get("orcan_worker_slot", 1))


@worker_ready.connect
def announce_ready(**kwargs):
    def heartbeat():
        from .events import client

        while not _heartbeat_stop.is_set():
            try:
                with client() as connection:
                    connection.set(readiness_key(), store.now(), ex=45)
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

        with client() as connection:
            connection.delete(readiness_key())
    except Exception:
        pass
