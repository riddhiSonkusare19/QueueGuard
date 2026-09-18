"""Core queueing logic, kept free of FastAPI/HTTP concerns so it can be
unit tested directly against a Redis client (real or fake)."""

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from app.config import settings

QUEUE_KEY_PREFIX = "queue"          # queue:{event_id}            -> ZSET of user_id -> join timestamp
ADMITTED_KEY_PREFIX = "admitted"    # admitted:{event_id}:{user_id} -> admission token (with TTL)
ACTIVE_EVENTS_KEY = "active_events"  # SET of event_ids that have ever had a join


class AlreadyAdmittedError(Exception):
    pass


def _queue_key(event_id: str) -> str:
    return f"{QUEUE_KEY_PREFIX}:{event_id}"


def _admitted_key(event_id: str, user_id: str) -> str:
    return f"{ADMITTED_KEY_PREFIX}:{event_id}:{user_id}"


@dataclass
class JoinResult:
    status: str          # "already_admitted" | "already_queued" | "queued"
    position: Optional[int] = None
    admission_token: Optional[str] = None


def join_queue(r, event_id: str, user_id: str) -> JoinResult:
    """Adds a user to the queue for an event, or reports their existing state.

    Idempotent: calling this again for a user already queued or already
    admitted returns their current state rather than erroring or re-queueing.
    """
    r.sadd(ACTIVE_EVENTS_KEY, event_id)

    token = r.get(_admitted_key(event_id, user_id))
    if token:
        return JoinResult(status="already_admitted", admission_token=token)

    key = _queue_key(event_id)
    existing_score = r.zscore(key, user_id)
    if existing_score is None:
        r.zadd(key, {user_id: time.time()})

    rank = r.zrank(key, user_id)
    position = (rank + 1) if rank is not None else None
    status = "already_queued" if existing_score is not None else "queued"
    return JoinResult(status=status, position=position)


@dataclass
class StatusResult:
    status: str          # "admitted" | "queued" | "not_found"
    position: Optional[int] = None
    admission_token: Optional[str] = None


def get_status(r, event_id: str, user_id: str) -> StatusResult:
    token = r.get(_admitted_key(event_id, user_id))
    if token:
        return StatusResult(status="admitted", admission_token=token)

    rank = r.zrank(_queue_key(event_id), user_id)
    if rank is None:
        return StatusResult(status="not_found")

    return StatusResult(status="queued", position=rank + 1)


def admit_next_batch(r, event_id: str, batch_size: Optional[int] = None) -> list[str]:
    """Pops the next `batch_size` users off the front of the queue and
    issues each of them an admission token. Returns the list of user_ids
    that were admitted in this call.
    """
    batch_size = batch_size or settings.ADMIT_BATCH_SIZE
    key = _queue_key(event_id)

    # Lowest score = earliest joiner = front of the queue.
    front = r.zrange(key, 0, batch_size - 1)
    admitted = []
    for user_id in front:
        token = str(uuid.uuid4())
        r.set(_admitted_key(event_id, user_id), token, ex=settings.TOKEN_TTL_SECONDS)
        r.zrem(key, user_id)
        admitted.append(user_id)

    return admitted


def queue_depth(r, event_id: str) -> int:
    return r.zcard(_queue_key(event_id))


def active_events(r) -> list[str]:
    return list(r.smembers(ACTIVE_EVENTS_KEY))
