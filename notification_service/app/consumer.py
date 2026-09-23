"""Kafka consumer for the Notification Service."""

import logging
import time

from kafka import KafkaConsumer

from app.config import settings
from app.handler import UnknownEventTypeError, process_and_log

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification_service.consumer")


def run_forever():
    while True:
        consumer = None

        try:
            consumer = KafkaConsumer(
                settings.BOOKING_EVENTS_TOPIC,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                value_deserializer=lambda value: value,
            )

            logger.info(
                "connected to Kafka, listening on topic '%s'",
                settings.BOOKING_EVENTS_TOPIC,
            )

            for message in consumer:
                try:
                    process_and_log(message.value)

                    consumer.commit()

                except (UnknownEventTypeError, ValueError):
                    logger.warning(
                        "dropping unprocessable message: %s",
                        message.value,
                    )

                    consumer.commit()

                except Exception:
                    logger.exception(
                        "failed to process message, will retry"
                    )

        except Exception:
            logger.exception(
                "Kafka not reachable, retrying in %ss",
                settings.RECONNECT_DELAY_SECONDS,
            )

            time.sleep(settings.RECONNECT_DELAY_SECONDS)

        except KeyboardInterrupt:
            logger.info("shutting down")
            break

        finally:
            if consumer:
                consumer.close()


if __name__ == "__main__":
    run_forever()