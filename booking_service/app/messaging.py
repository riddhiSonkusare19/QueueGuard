import json
import logging

import pika

from app.config import settings

logger = logging.getLogger("booking_service.messaging")


def publish_booking_event(event_type: str, payload: dict) -> None:
    """Publishes a booking event to RabbitMQ for the Notification Service
    to pick up. Failures here are logged but never block the booking
    response - a lost notification shouldn't fail a confirmed booking."""
    try:
        connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue=settings.BOOKING_EVENTS_QUEUE, durable=True)

        message = {"event_type": event_type, **payload}
        channel.basic_publish(
            exchange="",
            routing_key=settings.BOOKING_EVENTS_QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        connection.close()
    except Exception:
        logger.exception("failed to publish booking event %s", event_type)
