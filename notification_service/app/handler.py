"""Turns a raw booking event message into a simulated notification.
Kept separate from the RabbitMQ connection plumbing so this logic can
be unit tested with plain dicts - no broker required.
"""

import json
import logging

logger = logging.getLogger("notification_service")

TEMPLATES = {
    "booking.confirmed": "Hey {user_id}, your spot for event {event_id} is confirmed! Booking ID: {booking_id}",
    "booking.cancelled": "Hey {user_id}, your booking {booking_id} for event {event_id} has been cancelled.",
}


class UnknownEventTypeError(Exception):
    pass


def render_notification(event: dict) -> str:
    event_type = event.get("event_type")
    template = TEMPLATES.get(event_type)
    if template is None:
        raise UnknownEventTypeError(f"no notification template for event type '{event_type}'")
    return template.format(**event)


def handle_message_body(body: bytes) -> str:
    """Parses a raw message body and returns the rendered notification
    text. Raises on malformed JSON or unknown event types so the caller
    can decide whether to ack, retry, or dead-letter the message."""
    event = json.loads(body)
    return render_notification(event)


def process_and_log(body: bytes) -> None:
    """The actual side effect: simulate sending the notification by
    logging it. In a real system this is where an email/SMS/push
    provider call would go."""
    message = handle_message_body(body)
    logger.info("NOTIFICATION SENT: %s", message)
