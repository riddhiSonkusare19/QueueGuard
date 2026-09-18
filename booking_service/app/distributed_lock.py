"""A minimal distributed lock built directly on SET NX/EX.

This is the mechanism that prevents two users admitted from the queue
at the same moment from claiming the same slot. Deliberately simple
(no Lua unlock script, no reentrancy) so it's easy to explain and to
unit test against fakeredis.
"""

import time
import uuid
from contextlib import contextmanager


class LockAcquisitionError(Exception):
    """Raised when the lock could not be acquired within the timeout."""


def acquire_lock(r, key: str, ttl_seconds: int, timeout_seconds: float, poll_interval: float = 0.05) -> str:
    token = str(uuid.uuid4())
    deadline = time.time() + timeout_seconds

    while True:
        if r.set(key, token, nx=True, ex=ttl_seconds):
            return token
        if time.time() >= deadline:
            raise LockAcquisitionError(f"could not acquire lock '{key}' within {timeout_seconds}s")
        time.sleep(poll_interval)


def release_lock(r, key: str, token: str) -> bool:
    """Only releases the lock if we're still the holder (token matches) -
    otherwise we might delete a lock some other process legitimately
    acquired after ours expired."""
    current = r.get(key)
    if current == token:
        r.delete(key)
        return True
    return False


@contextmanager
def distributed_lock(r, key: str, ttl_seconds: int, timeout_seconds: float):
    token = acquire_lock(r, key, ttl_seconds, timeout_seconds)
    try:
        yield
    finally:
        release_lock(r, key, token)
