"""Integration test: publishes a real message to RabbitMQ and confirms
the consumer picks it up and processes it.

Run with: docker compose up -d rabbitmq
          pytest tests/test_integration.py -m integration
"""

import json
import os
import threading
import time

import pika
import pytest

pytestmark = pytest.mark.integration

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
TEST_QUEUE = "booking_events_test"


def _rabbitmq_available() -> bool:
    try:
        conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        conn.close()
        return True
    except Exception:
        return False


requires_rabbitmq = pytest.mark.skipif(not _rabbitmq_available(), reason="RabbitMQ is not reachable")


@requires_rabbitmq
def test_published_message_is_consumed_and_processed(caplog):
    from app.handler import process_and_log

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=TEST_QUEUE, durable=False)
    channel.queue_purge(queue=TEST_QUEUE)

    message = {"event_type": "booking.confirmed", "booking_id": "b1", "event_id": "concert-1", "user_id": "alice"}
    channel.basic_publish(exchange="", routing_key=TEST_QUEUE, body=json.dumps(message))
    connection.close()

    # Consume once, directly - proves the wire format round-trips cleanly
    # end to end through a real broker, without needing the full
    # reconnect-loop consumer running in a background thread.
    consume_connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    consume_channel = consume_connection.channel()

    received = {}

    def on_message(ch, method, properties, body):
        received["body"] = body
        ch.basic_ack(delivery_tag=method.delivery_tag)
        ch.stop_consuming()

    consume_channel.basic_consume(queue=TEST_QUEUE, on_message_callback=on_message)

    timer = threading.Timer(5, consume_channel.stop_consuming)
    timer.start()
    consume_channel.start_consuming()
    timer.cancel()

    consume_connection.close()

    assert "body" in received
    with caplog.at_level("INFO"):
        process_and_log(received["body"])
    assert any("alice" in record.message for record in caplog.records)
