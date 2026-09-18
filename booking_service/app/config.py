import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard"
    )

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    BOOKING_EVENTS_QUEUE: str = os.getenv("BOOKING_EVENTS_QUEUE", "booking_events")

    # How long a slot-claim lock is held before it auto-expires (safety net
    # in case a process dies mid-claim and never releases it).
    LOCK_TTL_SECONDS: int = int(os.getenv("LOCK_TTL_SECONDS", "5"))
    LOCK_ACQUIRE_TIMEOUT_SECONDS: float = float(os.getenv("LOCK_ACQUIRE_TIMEOUT_SECONDS", "5"))

    # Simulated payment failure rate, 0.0-1.0. Lets the team demo retries /
    # failure handling without a real payment gateway.
    PAYMENT_FAILURE_RATE: float = float(os.getenv("PAYMENT_FAILURE_RATE", "0.0"))
    PAYMENT_LATENCY_SECONDS: float = float(os.getenv("PAYMENT_LATENCY_SECONDS", "0.0"))


settings = Settings()
