import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

from app.config import settings
from app.redis_client import get_redis
from app import queue_logic


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("queue_service")


app = FastAPI(title="QueueGuard - Queue Service")


# ---------------------------------------------------------
# CORS
# Allows the QueueGuard frontend to call this API
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------

QUEUE_DEPTH_GAUGE = Gauge(
    "queueguard_queue_depth",
    "Number of users currently waiting in the queue",
    ["event_id"],
)


# ---------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------

class JoinRequest(BaseModel):
    user_id: str
    event_id: str


class JoinResponse(BaseModel):
    status: str
    position: int | None = None
    admission_token: str | None = None


class StatusResponse(BaseModel):
    status: str
    position: int | None = None
    admission_token: str | None = None


# ---------------------------------------------------------
# Queue endpoints
# ---------------------------------------------------------

@app.post("/queue/join", response_model=JoinResponse)
def join(req: JoinRequest):
    r = get_redis()

    result = queue_logic.join_queue(
        r,
        req.event_id,
        req.user_id,
    )

    return JoinResponse(**result.__dict__)


@app.get(
    "/queue/status/{event_id}/{user_id}",
    response_model=StatusResponse,
)
def status(event_id: str, user_id: str):
    r = get_redis()

    result = queue_logic.get_status(
        r,
        event_id,
        user_id,
    )

    if result.status == "not_found":
        raise HTTPException(
            status_code=404,
            detail="User is not in this queue",
        )

    return StatusResponse(**result.__dict__)


@app.post("/queue/admit-batch/{event_id}")
def admit_batch(
    event_id: str,
    batch_size: int | None = None,
):
    """
    Manually trigger an admission cycle for one event.

    Normally the background task handles admission automatically.
    This endpoint is useful for tests, demos, and manual intervention.
    """

    r = get_redis()

    admitted = queue_logic.admit_next_batch(
        r,
        event_id,
        batch_size,
    )

    return {
        "event_id": event_id,
        "admitted": admitted,
        "count": len(admitted),
    }


@app.get("/queue/depth/{event_id}")
def depth(event_id: str):
    r = get_redis()

    return {
        "event_id": event_id,
        "depth": queue_logic.queue_depth(
            r,
            event_id,
        ),
    }


# ---------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------

@app.get("/health/live")
def live():
    return {
        "status": "ok"
    }


@app.get("/health/ready")
def ready():
    try:
        get_redis().ping()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"redis unavailable: {exc}",
        )

    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# Prometheus metrics endpoint
# ---------------------------------------------------------

@app.get("/metrics")
def metrics():
    r = get_redis()

    for event_id in queue_logic.active_events(r):
        QUEUE_DEPTH_GAUGE.labels(
            event_id=event_id
        ).set(
            queue_logic.queue_depth(
                r,
                event_id,
            )
        )

    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------
# Background queue admission
# ---------------------------------------------------------

async def _background_admitter():
    """
    Periodically admits the next batch of users
    for every active event.

    This makes the queue automatically drain.
    """

    while True:
        try:
            r = get_redis()

            for event_id in queue_logic.active_events(r):

                admitted = queue_logic.admit_next_batch(
                    r,
                    event_id,
                )

                if admitted:
                    logger.info(
                        "admitted %s users for event %s",
                        len(admitted),
                        event_id,
                    )

        except Exception:
            logger.exception(
                "background admitter iteration failed"
            )

        await asyncio.sleep(
            settings.ADMIT_INTERVAL_SECONDS
        )


# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------

@app.on_event("startup")
async def start_background_admitter():
    asyncio.create_task(
        _background_admitter()
    )