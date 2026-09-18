"""Integration tests: real Postgres + real Redis + the actual FastAPI app.

Run with: docker compose up -d postgres redis rabbitmq
          pytest tests/test_integration.py -m integration
"""

import os

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard"
)


def _dependencies_available() -> bool:
    try:
        redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1).ping()
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 1})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_deps = pytest.mark.skipif(not _dependencies_available(), reason="Postgres/Redis not reachable")


@pytest.fixture
def client():
    from app.db import Base, init_db, make_engine
    from app.main import app

    engine = make_engine(DATABASE_URL)
    init_db(engine)

    with TestClient(app) as c:
        yield c

    # clean slate between tests
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def _flush_redis():
    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.flushdb()
    yield
    r.flushdb()


def _seed_event(event_id="concert-1", slots=3):
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    from app.db import Event

    session.merge(Event(id=event_id, name="Integration Test Event", total_slots=slots))
    session.commit()
    session.close()


def _admit_user(event_id, user_id, token="integration-token"):
    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.set(f"admitted:{event_id}:{user_id}", token, ex=300)
    return token


@requires_deps
def test_create_booking_end_to_end(client):
    _seed_event("concert-1", slots=3)
    token = _admit_user("concert-1", "alice")

    resp = client.post(
        "/bookings", json={"user_id": "alice", "event_id": "concert-1", "admission_token": token}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["user_id"] == "alice"

    get_resp = client.get(f"/bookings/{body['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "confirmed"


@requires_deps
def test_booking_without_admission_token_is_rejected(client):
    _seed_event("concert-1", slots=3)

    resp = client.post(
        "/bookings", json={"user_id": "alice", "event_id": "concert-1", "admission_token": "fake"}
    )
    assert resp.status_code == 403


@requires_deps
def test_booking_fails_when_event_sold_out(client):
    _seed_event("concert-1", slots=0)
    token = _admit_user("concert-1", "alice")

    resp = client.post(
        "/bookings", json={"user_id": "alice", "event_id": "concert-1", "admission_token": token}
    )
    assert resp.status_code == 409


@requires_deps
def test_cancel_booking_returns_slot(client):
    _seed_event("concert-1", slots=1)
    token = _admit_user("concert-1", "alice")

    create_resp = client.post(
        "/bookings", json={"user_id": "alice", "event_id": "concert-1", "admission_token": token}
    )
    booking_id = create_resp.json()["id"]

    cancel_resp = client.delete(f"/bookings/{booking_id}")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # slot should be available again
    token2 = _admit_user("concert-1", "bob")
    second_resp = client.post(
        "/bookings", json={"user_id": "bob", "event_id": "concert-1", "admission_token": token2}
    )
    assert second_resp.status_code == 201


@requires_deps
def test_health_endpoints(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
