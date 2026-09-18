"""Unit tests: fakeredis + in-memory sqlite, no docker-compose required.

The concurrency test is the important one - it proves the distributed
lock actually prevents two admitted users from claiming the same last
slot, which is the entire reliability point of the Booking Service.
"""

import threading

import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import booking_logic
from app.config import settings
from app.db import Base, Event


@pytest.fixture
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def _admit(r, event_id, user_id, token="test-token"):
    r.set(f"admitted:{event_id}:{user_id}", token, ex=300)
    return token


def test_claim_slot_rejects_missing_admission_token(db, r):
    db.add(Event(id="concert-1", name="Test Concert", total_slots=5))
    db.commit()

    with pytest.raises(booking_logic.InvalidAdmissionTokenError):
        booking_logic.claim_slot(db, r, "concert-1", "alice", "bogus-token")


def test_claim_slot_succeeds_with_valid_token_and_available_slot(db, r):
    db.add(Event(id="concert-1", name="Test Concert", total_slots=5))
    db.commit()
    token = _admit(r, "concert-1", "alice")

    booking = booking_logic.claim_slot(db, r, "concert-1", "alice", token)

    assert booking.status == "confirmed"
    assert booking.user_id == "alice"

    refreshed = db.query(Event).filter(Event.id == "concert-1").first()
    assert refreshed.total_slots == 4


def test_claim_slot_fails_when_no_slots_remain(db, r):
    db.add(Event(id="concert-1", name="Test Concert", total_slots=0))
    db.commit()
    token = _admit(r, "concert-1", "alice")

    with pytest.raises(booking_logic.NoSlotsAvailableError):
        booking_logic.claim_slot(db, r, "concert-1", "alice", token)


def test_claim_slot_fails_for_unknown_event(db, r):
    token = _admit(r, "no-such-event", "alice")
    with pytest.raises(booking_logic.EventNotFoundError):
        booking_logic.claim_slot(db, r, "no-such-event", "alice", token)


def test_claim_slot_rolls_back_slot_count_on_payment_failure(db, r, monkeypatch):
    db.add(Event(id="concert-1", name="Test Concert", total_slots=5))
    db.commit()
    token = _admit(r, "concert-1", "alice")

    monkeypatch.setattr(
        booking_logic, "simulate_payment", lambda user_id: booking_logic.PaymentResult(success=False, reason="declined")
    )

    with pytest.raises(booking_logic.PaymentFailedError):
        booking_logic.claim_slot(db, r, "concert-1", "alice", token)

    refreshed = db.query(Event).filter(Event.id == "concert-1").first()
    assert refreshed.total_slots == 5  # untouched - failure happened before decrement


def test_cancel_booking_returns_slot_to_pool(db, r):
    db.add(Event(id="concert-1", name="Test Concert", total_slots=5))
    db.commit()
    token = _admit(r, "concert-1", "alice")
    booking = booking_logic.claim_slot(db, r, "concert-1", "alice", token)

    booking_logic.cancel_booking(db, booking.id)

    refreshed = db.query(Event).filter(Event.id == "concert-1").first()
    assert refreshed.total_slots == 5
    assert db.query(booking.__class__).filter_by(id=booking.id).first().status == "cancelled"


def test_two_admitted_users_racing_for_the_last_slot_only_one_wins(db_session_factory, r):
    """The signature test for this project: two users are both admitted
    from the queue at the same moment, but only one slot remains. The
    distributed lock must ensure exactly one of them gets it - never
    both, never neither."""
    setup_session = db_session_factory()
    setup_session.add(Event(id="concert-1", name="Test Concert", total_slots=1))
    setup_session.commit()
    setup_session.close()

    token_a = _admit(r, "concert-1", "alice")
    token_b = _admit(r, "concert-1", "bob")

    results = {}

    def attempt(user_id, token):
        session = db_session_factory()
        try:
            booking = booking_logic.claim_slot(session, r, "concert-1", user_id, token)
            results[user_id] = ("success", booking.id)
        except booking_logic.NoSlotsAvailableError:
            results[user_id] = ("no_slots", None)
        finally:
            session.close()

    t1 = threading.Thread(target=attempt, args=("alice", token_a))
    t2 = threading.Thread(target=attempt, args=("bob", token_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    outcomes = [v[0] for v in results.values()]
    assert outcomes.count("success") == 1
    assert outcomes.count("no_slots") == 1

    verify_session = db_session_factory()
    final_event = verify_session.query(Event).filter(Event.id == "concert-1").first()
    assert final_event.total_slots == 0
    verify_session.close()


def test_distributed_lock_helper_prevents_concurrent_section(r):
    from app.distributed_lock import distributed_lock

    counter = {"value": 0}
    errors = []

    def critical_section():
        try:
            with distributed_lock(r, "lock:test", ttl_seconds=5, timeout_seconds=2):
                current = counter["value"]
                counter["value"] = current + 1
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=critical_section) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert counter["value"] == 10
