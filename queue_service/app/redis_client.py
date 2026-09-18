import redis

from app.config import settings


def get_redis() -> redis.Redis:
    """Returns a Redis client. Kept as a thin factory so tests can
    swap in fakeredis without touching the rest of the app."""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
    )
