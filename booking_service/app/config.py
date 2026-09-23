import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard",
    )

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092",
    )

    BOOKING_EVENTS_TOPIC: str = os.getenv(
        "BOOKING_EVENTS_TOPIC",
        "booking-events",
    )

    LOCK_TTL_SECONDS: int = int(os.getenv("LOCK_TTL_SECONDS", "5"))
    LOCK_ACQUIRE_TIMEOUT_SECONDS: float = float(
        os.getenv("LOCK_ACQUIRE_TIMEOUT_SECONDS", "5")
    )

    PAYMENT_FAILURE_RATE: float = float(
        os.getenv("PAYMENT_FAILURE_RATE", "0.0")
    )

    PAYMENT_LATENCY_SECONDS: float = float(
        os.getenv("PAYMENT_LATENCY_SECONDS", "0.0")
    )


settings = Settings()
