"""RabbitMQ consumer for the Notification Service.

Demonstrates message persistence and recovery: if this service is
down when a booking event is published, the message waits durably in
the queue and is delivered as soon as the service reconnects.
"""

import logging
import time

import pika

from app.config import settings
from app.handler import UnknownEventTypeError, process_and_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification_service.consumer")


def _on_message(channel, method, properties, body):
    try:
        process_and_log(body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except (UnknownEventTypeError, ValueError):
        # Malformed or unrecognized message - don't requeue it forever,
        # just drop it (a real system would dead-letter it instead).
        logger.warning("dropping unprocessable message: %s", body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("failed to process message, requeueing")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def run_forever():
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
            channel = connection.channel()
            channel.queue_declare(queue=settings.BOOKING_EVENTS_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=settings.BOOKING_EVENTS_QUEUE, on_message_callback=_on_message)

            logger.info("connected to RabbitMQ, listening on '%s'", settings.BOOKING_EVENTS_QUEUE)
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            logger.warning(
                "RabbitMQ not reachable, retrying in %ss", settings.RECONNECT_DELAY_SECONDS
            )
            time.sleep(settings.RECONNECT_DELAY_SECONDS)
        except KeyboardInterrupt:
            logger.info("shutting down")
            break


if __name__ == "__main__":
    run_forever()
