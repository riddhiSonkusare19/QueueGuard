import os


class Settings:
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    BOOKING_EVENTS_QUEUE: str = os.getenv("BOOKING_EVENTS_QUEUE", "booking_events")
    RECONNECT_DELAY_SECONDS: float = float(os.getenv("RECONNECT_DELAY_SECONDS", "3"))


settings = Settings()
