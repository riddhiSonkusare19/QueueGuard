import json

import pytest

from app.handler import UnknownEventTypeError, handle_message_body, render_notification


def test_render_notification_for_confirmed_booking():
    event = {"event_type": "booking.confirmed", "booking_id": "b1", "event_id": "concert-1", "user_id": "alice"}
    message = render_notification(event)
    assert "alice" in message
    assert "b1" in message
    assert "concert-1" in message


def test_render_notification_for_cancelled_booking():
    event = {"event_type": "booking.cancelled", "booking_id": "b1", "event_id": "concert-1", "user_id": "alice"}
    message = render_notification(event)
    assert "cancelled" in message.lower()


def test_render_notification_raises_for_unknown_event_type():
    event = {"event_type": "booking.teleported", "booking_id": "b1", "event_id": "concert-1", "user_id": "alice"}
    with pytest.raises(UnknownEventTypeError):
        render_notification(event)


def test_handle_message_body_parses_json_and_renders():
    body = json.dumps(
        {"event_type": "booking.confirmed", "booking_id": "b2", "event_id": "concert-2", "user_id": "bob"}
    ).encode()
    message = handle_message_body(body)
    assert "bob" in message


def test_handle_message_body_raises_on_malformed_json():
    with pytest.raises(json.JSONDecodeError):
        handle_message_body(b"not json")
