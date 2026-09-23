import json
import logging

from kafka import KafkaProducer

from app.config import settings

logger = logging.getLogger("booking_service.messaging")

producer = KafkaProducer(
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)


def publish_booking_event(event_type: str, payload: dict) -> None:
    """Publishes a booking event to Kafka for the Notification Service."""
    try:
        message = {"event_type": event_type, **payload}

        producer.send(
            settings.BOOKING_EVENTS_TOPIC,
            value=message,
        )

        producer.flush()

        logger.info(
            "published booking event %s to Kafka topic %s",
            event_type,
            settings.BOOKING_EVENTS_TOPIC,
        )

    except Exception:
        logger.exception("failed to publish booking event %s", event_type)