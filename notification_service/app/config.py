import os


class Settings:
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092"
)

    BOOKING_EVENTS_TOPIC: str = os.getenv(
    "BOOKING_EVENTS_TOPIC",
    "booking-events"
)

    KAFKA_CONSUMER_GROUP: str = os.getenv(
    "KAFKA_CONSUMER_GROUP",
    "notification-service"
)


settings = Settings()
