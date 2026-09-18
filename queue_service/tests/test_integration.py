"""Integration tests: exercise the real FastAPI app talking to a real
Redis instance (as started by docker-compose). These are automatically
skipped if Redis isn't reachable, so unit tests still run in isolation.

Run with: docker compose up -d redis
          REDIS_HOST=localhost pytest tests/test_integration.py -m integration
"""

import os

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def _redis_available() -> bool:
    try:
        redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(not _redis_available(), reason="Redis is not reachable")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _flush_redis():
    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.flushdb()
    yield
    r.flushdb()


@requires_redis
def test_join_then_status_round_trip(client):
    join_resp = client.post("/queue/join", json={"user_id": "alice", "event_id": "concert-1"})
    assert join_resp.status_code == 200
    assert join_resp.json()["position"] == 1

    status_resp = client.get("/queue/status/concert-1/alice")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "queued"


@requires_redis
def test_status_for_never_joined_user_is_404(client):
    resp = client.get("/queue/status/concert-1/nobody")
    assert resp.status_code == 404


@requires_redis
def test_full_flow_join_admit_status_becomes_admitted(client):
    client.post("/queue/join", json={"user_id": "alice", "event_id": "concert-1"})

    admit_resp = client.post("/queue/admit-batch/concert-1", params={"batch_size": 1})
    assert admit_resp.status_code == 200
    assert "alice" in admit_resp.json()["admitted"]

    status_resp = client.get("/queue/status/concert-1/alice")
    assert status_resp.json()["status"] == "admitted"
    assert status_resp.json()["admission_token"]


@requires_redis
def test_health_endpoints(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


@requires_redis
def test_metrics_endpoint_exposes_queue_depth(client):
    client.post("/queue/join", json={"user_id": "alice", "event_id": "concert-1"})
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "queueguard_queue_depth" in resp.text
