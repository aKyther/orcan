import json
import time

import redis

from . import store
from .metrics import model_result
from .settings import broker_url, retention_seconds, stream_name


def client():
    return redis.Redis.from_url(
        broker_url(), decode_responses=True, socket_connect_timeout=3, socket_timeout=5
    )


def publish_pending(replay: bool = False) -> int:
    published = 0
    connection = client()
    for event in store.unpublished(replay):
        connection.xadd(
            stream_name(), {"payload": event["payload"]}, maxlen=10000, approximate=False
        )
        connection.xtrim(
            stream_name(),
            minid=str(int((time.time() - retention_seconds()) * 1000)) + "-0",
            approximate=False,
        )
        connection.expire(stream_name(), retention_seconds())
        store.mark_published(event["id"])
        published += 1
    return published


def listen(after: str = "0-0", job_id: str | None = None, timeout: float | None = None):
    """Blocking Redis Stream reads; after=0-0 replays history, explicit IDs allow resuming."""
    connection = stream_client()
    deadline = time.monotonic() + timeout if timeout is not None else None
    cursor = after
    while True:
        remaining = deadline - time.monotonic() if deadline is not None else None
        if remaining is not None and remaining <= 0:
            return
        block = max(1, int(remaining * 1000)) if remaining is not None else 0
        batches = connection.xread({stream_name(): cursor}, count=50, block=block)
        if not batches:
            return
        for _, messages in batches:
            for message_id, fields in messages:
                cursor = message_id
                payload = json.loads(fields["payload"])
                payload["stream_id"] = message_id
                if payload.get("status") in store.TERMINAL and (
                    job_id is None or payload["job_id"] == job_id
                ):
                    yield model_result(payload)


def stream_client():
    return redis.Redis.from_url(broker_url(), decode_responses=True, socket_connect_timeout=3)
