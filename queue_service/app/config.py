import os


class Settings:
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # How many users get admitted from the queue per admission cycle.
    ADMIT_BATCH_SIZE: int = int(os.getenv("ADMIT_BATCH_SIZE", "5"))

    # How often the background admitter runs, in seconds.
    ADMIT_INTERVAL_SECONDS: float = float(os.getenv("ADMIT_INTERVAL_SECONDS", "5"))

    # How long an admission token stays valid before it expires.
    TOKEN_TTL_SECONDS: int = int(os.getenv("TOKEN_TTL_SECONDS", "300"))


settings = Settings()
