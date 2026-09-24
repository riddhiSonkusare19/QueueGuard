"""Core booking logic.

Handles:
- admission-token verification
- event/slot lookup
- slot claiming under a distributed lock
- simulated payment
- booking cancellation
"""

import random
import time
from dataclasses import dataclass

from app.config import settings
from app.db import Booking, Event, Slot
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
    # Must match the key format used by Queue Service.
    return f"admitted:{event_id}:{user_id}"


def verify_admission_token(r, event_id: str, user_id: str, token: str) -> bool:
    stored = r.get(_admitted_key(event_id, user_id))
    return stored is not None and stored == token


@dataclass
class PaymentResult:
    success: bool
    reason: str | None = None


def simulate_payment(user_id: str) -> PaymentResult:
    """Simulate a payment gateway."""

    if settings.PAYMENT_LATENCY_SECONDS > 0:
        time.sleep(settings.PAYMENT_LATENCY_SECONDS)

    if random.random() < settings.PAYMENT_FAILURE_RATE:
        return PaymentResult(
            success=False,
            reason="simulated_payment_decline",
        )

    return PaymentResult(success=True)


def claim_slot(
    db,
    r,
    event_id: str,
    user_id: str,
    admission_token: str,
) -> Booking:
    """Verify admission and claim one available slot for the event."""

    # 1. Verify that the user was admitted by the Queue Service.
    if not verify_admission_token(
        r,
        event_id,
        user_id,
        admission_token,
    ):
        raise InvalidAdmissionTokenError(
            f"user {user_id} does not hold a valid admission token "
            f"for event {event_id}"
        )

    # 2. Lock the event while selecting and booking a slot.
    lock_key = f"lock:slot:{event_id}"

    with distributed_lock(
        r,
        lock_key,
        settings.LOCK_TTL_SECONDS,
        settings.LOCK_ACQUIRE_TIMEOUT_SECONDS,
    ):
        # 3. Verify the event exists.
        event = (
            db.query(Event)
            .filter(Event.id == event_id)
            .with_for_update()
            .first()
        )

        if event is None:
            raise EventNotFoundError(
                f"event {event_id} does not exist"
            )

        # 4. Find an available slot belonging to this event.
        slot = (
            db.query(Slot)
            .filter(
                Slot.event_id == event_id,
                Slot.status == "available",
            )
            .with_for_update()
            .first()
        )

        if slot is None:
            raise NoSlotsAvailableError(
                f"no slots remaining for event {event_id}"
            )

        # 5. Simulate payment before confirming the booking.
        payment = simulate_payment(user_id)

        if not payment.success:
            raise PaymentFailedError(
                payment.reason or "payment_failed"
            )

        # 6. Mark the selected slot as booked.
        slot.status = "booked"

        # 7. Keep the event counter consistent.
        if event.total_slots > 0:
            event.total_slots -= 1

        # 8. Create booking using slot_id.
        booking = Booking(
            slot_id=slot.id,
            user_id=user_id,
            status="confirmed",
        )

        db.add(booking)

        # 9. Persist everything atomically.
        db.commit()
        db.refresh(booking)

    return booking


def cancel_booking(db, booking_id: str) -> Booking:
    """Cancel a booking and make its slot available again."""

    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id)
        .first()
    )

    if booking is None:
        raise EventNotFoundError(
            f"booking {booking_id} does not exist"
        )

    if booking.status == "confirmed":
        slot = (
            db.query(Slot)
            .filter(Slot.id == booking.slot_id)
            .first()
        )

        if slot is not None and slot.status == "booked":
            slot.status = "available"

            event = (
                db.query(Event)
                .filter(Event.id == slot.event_id)
                .first()
            )

            if event is not None:
                event.total_slots += 1

        # The current database CHECK constraint does not allow
        # "cancelled", so use "failed" for a non-active booking.
        booking.status = "failed"

    db.commit()
    db.refresh(booking)

    return booking