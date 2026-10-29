"""Read-only local dashboard: SQLite snapshot plus event-driven Redis Stream updates."""

import asyncio
import base64
import json
import os
import re
import secrets
from pathlib import Path

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from redis.exceptions import RedisError

from . import store
from .settings import broker_url, state_dir, stream_name

app = FastAPI(title="Orcan executor", docs_url=None, redoc_url=None)


@app.middleware("http")
async def terminal_credentials(request: Request, call_next):
    credential = os.environ.get("TTYD_CREDENTIAL", "")
    if credential:
        header = request.headers.get("authorization", "")
        try:
            scheme, encoded = header.split(" ", 1)
            supplied = base64.b64decode(encoded, validate=True).decode()
            valid = scheme.lower() == "basic" and secrets.compare_digest(
                supplied.encode(), credential.encode()
            )
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Orcan"'})
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(Path(__file__).with_name("dashboard.html").read_text())


@app.get("/api/board")
def board():
    return store.board()


def artifact(job_id: str, name: str) -> Path:
    try:
        job = store.get(job_id)
    except ValueError:
        raise HTTPException(404, "Unknown job") from None
    if not job["report"]:
        raise HTTPException(404, "Report not available yet")
    path = (Path(job["report"]).parent / name).resolve()
    if not path.is_relative_to(state_dir()) or not path.is_file():
        raise HTTPException(404, "Artifact not available")
    return path


@app.get("/api/jobs/{job_id}/report")
def report(job_id: str):
    return FileResponse(artifact(job_id, "report.json"), media_type="application/json")


@app.get("/api/jobs/{job_id}/log")
def log(job_id: str):
    return FileResponse(
        artifact(job_id, "output.log"), media_type="text/plain", filename=job_id + ".log"
    )


async def frames(request: Request):
    connection = redis.Redis.from_url(broker_url(), decode_responses=True, socket_connect_timeout=3)
    try:
        try:
            previous = request.headers.get("last-event-id", "")
            if re.fullmatch(r"[0-9]+-[0-9]+", previous):
                cursor = previous
            else:
                latest = await connection.xrevrange(stream_name(), count=1)
                cursor = latest[0][0] if latest else "0-0"
        except RedisError:
            snapshot = await asyncio.to_thread(store.board)
            yield (
                "event: snapshot\ndata: " + json.dumps({**snapshot, "redis_online": False}) + "\n\n"
            )
            return
        snapshot = await asyncio.to_thread(store.board)
        yield (
            f"id: {cursor}\nevent: snapshot\ndata: "
            + json.dumps({**snapshot, "redis_online": True})
            + "\n\n"
        )
        while not await request.is_disconnected():
            # Blocking Redis read, with SSE keepalive on an otherwise quiet connection.
            batches = await connection.xread({stream_name(): cursor}, count=50, block=15000)
            if not batches:
                yield ": keepalive\n\n"
                continue
            for _, messages in batches:
                cursor = messages[-1][0]
            snapshot = await asyncio.to_thread(store.board)
            yield (
                f"id: {cursor}\nevent: snapshot\ndata: "
                + json.dumps({**snapshot, "redis_online": True})
                + "\n\n"
            )
    except RedisError:
        yield 'event: disconnected\ndata: {"redis_online":false}\n\n'
    finally:
        await connection.aclose()


@app.get("/api/events")
async def event_stream(request: Request):
    return StreamingResponse(
        frames(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
