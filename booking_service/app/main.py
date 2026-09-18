import logging

from fastapi import Depends, FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import Response

from app import booking_logic
from app.db import Booking, get_db, init_db
from app.messaging import publish_booking_event
from app.redis_client import get_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booking_service")

app = FastAPI(title="QueueGuard - Booking Service")

BOOKINGS_CONFIRMED = Counter("queueguard_bookings_confirmed_total", "Total confirmed bookings")
BOOKINGS_FAILED = Counter("queueguard_bookings_failed_total", "Total failed booking attempts", ["reason"])


class BookingRequest(BaseModel):
    user_id: str
    event_id: str
    admission_token: str


class BookingResponse(BaseModel):
    id: str
    event_id: str
    user_id: str
    status: str


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/bookings", response_model=BookingResponse, status_code=201)
def create_booking(req: BookingRequest, db: Session = Depends(get_db)):
    r = get_redis()
    try:
        booking = booking_logic.claim_slot(db, r, req.event_id, req.user_id, req.admission_token)
    except booking_logic.InvalidAdmissionTokenError:
        BOOKINGS_FAILED.labels(reason="invalid_admission_token").inc()
        raise HTTPException(status_code=403, detail="Invalid or missing admission token")
    except booking_logic.EventNotFoundError:
        BOOKINGS_FAILED.labels(reason="event_not_found").inc()
        raise HTTPException(status_code=404, detail="Event not found")
    except booking_logic.NoSlotsAvailableError:
        BOOKINGS_FAILED.labels(reason="no_slots_available").inc()
        raise HTTPException(status_code=409, detail="No slots remaining for this event")
    except booking_logic.PaymentFailedError as exc:
        BOOKINGS_FAILED.labels(reason="payment_failed").inc()
        raise HTTPException(status_code=402, detail=f"Payment failed: {exc}")

    BOOKINGS_CONFIRMED.inc()
    publish_booking_event(
        "booking.confirmed",
        {"booking_id": booking.id, "event_id": booking.event_id, "user_id": booking.user_id},
    )
    return BookingResponse(id=booking.id, event_id=booking.event_id, user_id=booking.user_id, status=booking.status)


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return BookingResponse(id=booking.id, event_id=booking.event_id, user_id=booking.user_id, status=booking.status)


@app.delete("/bookings/{booking_id}", response_model=BookingResponse)
def delete_booking(booking_id: str, db: Session = Depends(get_db)):
    try:
        booking = booking_logic.cancel_booking(db, booking_id)
    except booking_logic.EventNotFoundError:
        raise HTTPException(status_code=404, detail="Booking not found")

    publish_booking_event(
        "booking.cancelled",
        {"booking_id": booking.id, "event_id": booking.event_id, "user_id": booking.user_id},
    )
    return BookingResponse(id=booking.id, event_id=booking.event_id, user_id=booking.user_id, status=booking.status)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        get_redis().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dependency unavailable: {exc}")
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
