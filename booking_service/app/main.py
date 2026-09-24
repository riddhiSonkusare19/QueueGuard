import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from starlette.responses import Response

from app import booking_logic
from app.booking_logic import SlotNotFound, SlotUnavailable
from app.config import settings
from app.db import Booking, Slot, get_db, init_db
from app.messaging import publish_booking_event
from app.redis_client import get_redis
from app.schemas import BookingCreate, BookingOut, ErrorOut, SlotOut

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("booking_service")


# ---------------------------------------------------------------------------
# Application lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Booking service started")
    yield
    logger.info("Booking service shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="QueueGuard - Booking Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
BOOKINGS_CONFIRMED = Counter(
    "queueguard_bookings_confirmed_total",
    "Total number of confirmed bookings",
)
BOOKINGS_CANCELLED = Counter(
    "queueguard_bookings_cancelled_total",
    "Total number of cancelled bookings",
)
BOOKING_ERRORS = Counter(
    "queueguard_booking_errors_total",
    "Total number of booking errors",
    ["reason"],
)
REQUEST_LATENCY = Histogram(
    "queueguard_request_latency_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)


# ---------------------------------------------------------------------------
# Health / metrics
# ---------------------------------------------------------------------------
@app.get("/health", tags=["system"])
def health():
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/metrics", tags=["system"])
def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/db/ping", tags=["system"])
def db_ping(db: Session = Depends(get_db)):
    """Check DB and Redis connectivity."""
    db.execute(text("SELECT 1"))
    try:
        get_redis().ping()
        redis_status = "ok"
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        redis_status = "unavailable"
    return {"db": "ok", "redis": redis_status}


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------
@app.get("/slots", response_model=list[SlotOut], tags=["slots"])
def list_slots(db: Session = Depends(get_db)):
    """List all slots with live remaining capacity."""
    slots = db.query(Slot).order_by(Slot.start_time).all()
    result = []
    for slot in slots:
        confirmed = (
            db.query(func.count(Booking.id))
            .filter(Booking.slot_id == slot.id, Booking.status == "confirmed")
            .scalar()
            or 0
        )
        result.append(
            SlotOut(
                id=slot.id,
                resource=slot.resource,
                start_time=slot.start_time,
                end_time=slot.end_time,
                capacity=slot.capacity,
                remaining=max(slot.capacity - confirmed, 0),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
@app.post(
    "/bookings",
    response_model=BookingOut,
    responses={
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
        500: {"model": ErrorOut},
    },
    tags=["bookings"],
)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    """
    Create a booking for a slot.

    Returns:
        - 200: booking created (or existing idempotent booking returned)
        - 404: slot not found
        - 409: slot unavailable / already booked by this user
        - 500: unexpected error
    """
    redis = get_redis()
    with REQUEST_LATENCY.labels(endpoint="create_booking").time():
        try:
            booking = booking_logic.create_booking(
                db=db,
                redis=redis,
                slot_id=payload.slot_id,
                user_id=payload.user_id,
            )
        except SlotNotFound as exc:
            BOOKING_ERRORS.labels(reason="slot_not_found").inc()
            raise HTTPException(status_code=404, detail=str(exc))
        except SlotUnavailable as exc:
            BOOKING_ERRORS.labels(reason="slot_unavailable").inc()
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception:
            BOOKING_ERRORS.labels(reason="internal").inc()
            logger.exception("Booking failed")
            raise HTTPException(status_code=500, detail="Internal error")

    BOOKINGS_CONFIRMED.inc()
    publish_booking_event(
        {
            "type": "confirmed",
            "booking_id": booking.id,
            "slot_id": booking.slot_id,
            "user_id": booking.user_id,
        }
    )
    return booking


@app.delete(
    "/bookings/{booking_id}",
    response_model=BookingOut,
    responses={404: {"model": ErrorOut}},
    tags=["bookings"],
)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    """Cancel an existing booking."""
    redis = get_redis()
    with REQUEST_LATENCY.labels(endpoint="cancel_booking").time():
        try:
            booking = booking_logic.cancel_booking(db, redis, booking_id)
        except SlotNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    BOOKINGS_CANCELLED.inc()
    publish_booking_event(
        {
            "type": "cancelled",
            "booking_id": booking.id,
            "slot_id": booking.slot_id,
            "user_id": booking.user_id,
        }
    )
    return booking


@app.get(
    "/bookings/{booking_id}",
    response_model=BookingOut,
    responses={404: {"model": ErrorOut}},
    tags=["bookings"],
)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    """Fetch a single booking by ID."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@app.get(
    "/users/{user_id}/bookings",
    response_model=list[BookingOut],
    tags=["bookings"],
)
def list_user_bookings(user_id: str, db: Session = Depends(get_db)):
    """List all bookings for a given user, newest first."""
    return (
        db.query(Booking)
        .filter(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Dev convenience: seed a slot (remove in production)
# ---------------------------------------------------------------------------
@app.post("/_dev/seed-slot", tags=["dev"], include_in_schema=False)
def seed_slot(db: Session = Depends(get_db)):
    """Create a demo slot for local testing. Do not expose in production."""
    from datetime import datetime, timedelta

    slot = Slot(
        resource="room-A",
        start_time=datetime.utcnow() + timedelta(hours=1),
        end_time=datetime.utcnow() + timedelta(hours=2),
        capacity=3,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return {"slot_id": slot.id}