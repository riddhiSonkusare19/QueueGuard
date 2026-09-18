"""Core booking logic: admission-token verification, slot claiming under
a distributed lock, and a simulated payment step. Kept free of FastAPI
so it can be unit tested against fakeredis and an in-memory sqlite db.
"""

import random
import time
from dataclasses import dataclass

from app.config import settings
from app.db import Booking, Event
from app.distributed_lock import distributed_lock


class InvalidAdmissionTokenError(Exception):
    pass


class NoSlotsAvailableError(Exception):
    pass


class PaymentFailedError(Exception):
    pass


class EventNotFoundError(Exception):
    pass


def _admitted_key(event_id: str, user_id: str) -> str:
    # Must match the key format the Queue Service writes to - the two
    # services agree on this key shape as their integration contract.
    return f"admitted:{event_id}:{user_id}"


def verify_admission_token(r, event_id: str, user_id: str, token: str) -> bool:
    stored = r.get(_admitted_key(event_id, user_id))
    return stored is not None and stored == token


@dataclass
class PaymentResult:
    success: bool
    reason: str | None = None


def simulate_payment(user_id: str) -> PaymentResult:
    """Simulates a payment gateway. No real gateway is connected - this
    exists purely so the team can demo retries, timeouts, and failure
    handling without needing a real payments integration."""
    if settings.PAYMENT_LATENCY_SECONDS > 0:
        time.sleep(settings.PAYMENT_LATENCY_SECONDS)

    if random.random() < settings.PAYMENT_FAILURE_RATE:
        return PaymentResult(success=False, reason="simulated_payment_decline")

    return PaymentResult(success=True)


def claim_slot(db, r, event_id: str, user_id: str, admission_token: str) -> Booking:
    """The heart of the reliability story: verifies the user was actually
    admitted from the queue, then claims a slot under a distributed lock
    so two users admitted in the same batch can never claim the same
    last slot.
    """
    if not verify_admission_token(r, event_id, user_id, admission_token):
        raise InvalidAdmissionTokenError(
            f"user {user_id} does not hold a valid admission token for event {event_id}"
        )

    lock_key = f"lock:slot:{event_id}"
    with distributed_lock(r, lock_key, settings.LOCK_TTL_SECONDS, settings.LOCK_ACQUIRE_TIMEOUT_SECONDS):
        event = db.query(Event).filter(Event.id == event_id).with_for_update().first()
        if event is None:
            raise EventNotFoundError(f"event {event_id} does not exist")

        if event.total_slots <= 0:
            raise NoSlotsAvailableError(f"no slots remaining for event {event_id}")

        payment = simulate_payment(user_id)
        if not payment.success:
            raise PaymentFailedError(payment.reason or "payment_failed")

        event.total_slots -= 1
        booking = Booking(event_id=event_id, user_id=user_id, status="confirmed")
        db.add(booking)
        db.commit()
        db.refresh(booking)

    return booking


def cancel_booking(db, booking_id: str) -> Booking:
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise EventNotFoundError(f"booking {booking_id} does not exist")

    if booking.status == "confirmed":
        event = db.query(Event).filter(Event.id == booking.event_id).first()
        if event is not None:
            event.total_slots += 1

    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return booking
