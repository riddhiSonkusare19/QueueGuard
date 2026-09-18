"""Unit tests: pure logic, no network, no real Redis. Uses fakeredis
so these run fast and don't depend on docker-compose being up."""

import fakeredis
import pytest

from app import queue_logic


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def test_join_queue_first_time_returns_position_one(r):
    result = queue_logic.join_queue(r, "concert-1", "alice")
    assert result.status == "queued"
    assert result.position == 1


def test_join_queue_is_idempotent(r):
    first = queue_logic.join_queue(r, "concert-1", "alice")
    second = queue_logic.join_queue(r, "concert-1", "alice")
    assert first.position == second.position
    assert second.status == "already_queued"


def test_join_queue_preserves_arrival_order(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    queue_logic.join_queue(r, "concert-1", "bob")
    queue_logic.join_queue(r, "concert-1", "carol")

    assert queue_logic.get_status(r, "concert-1", "alice").position == 1
    assert queue_logic.get_status(r, "concert-1", "bob").position == 2
    assert queue_logic.get_status(r, "concert-1", "carol").position == 3


def test_status_for_unknown_user_is_not_found(r):
    result = queue_logic.get_status(r, "concert-1", "ghost")
    assert result.status == "not_found"


def test_admit_next_batch_admits_front_of_queue_in_order(r):
    for name in ["alice", "bob", "carol", "dave"]:
        queue_logic.join_queue(r, "concert-1", name)

    admitted = queue_logic.admit_next_batch(r, "concert-1", batch_size=2)

    assert admitted == ["alice", "bob"]
    # Admitted users are removed from the queue...
    assert queue_logic.get_status(r, "concert-1", "alice").status == "admitted"
    # ...and the remaining users shift up.
    assert queue_logic.get_status(r, "concert-1", "carol").position == 1
    assert queue_logic.get_status(r, "concert-1", "dave").position == 2


def test_admitted_user_receives_a_token(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    admitted = queue_logic.admit_next_batch(r, "concert-1", batch_size=1)
    assert admitted == ["alice"]

    status = queue_logic.get_status(r, "concert-1", "alice")
    assert status.status == "admitted"
    assert status.admission_token is not None
    assert len(status.admission_token) > 0


def test_join_after_admission_returns_existing_token_not_a_new_queue_entry(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    queue_logic.admit_next_batch(r, "concert-1", batch_size=1)

    result = queue_logic.join_queue(r, "concert-1", "alice")
    assert result.status == "already_admitted"
    assert result.admission_token is not None


def test_admit_batch_never_admits_more_than_available(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    admitted = queue_logic.admit_next_batch(r, "concert-1", batch_size=10)
    assert admitted == ["alice"]


def test_admit_batch_on_empty_queue_admits_nobody(r):
    admitted = queue_logic.admit_next_batch(r, "concert-1", batch_size=5)
    assert admitted == []


def test_queue_depth_reflects_current_size(r):
    assert queue_logic.queue_depth(r, "concert-1") == 0
    queue_logic.join_queue(r, "concert-1", "alice")
    queue_logic.join_queue(r, "concert-1", "bob")
    assert queue_logic.queue_depth(r, "concert-1") == 2
    queue_logic.admit_next_batch(r, "concert-1", batch_size=1)
    assert queue_logic.queue_depth(r, "concert-1") == 1


def test_events_are_isolated_from_each_other(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    queue_logic.join_queue(r, "concert-2", "bob")

    assert queue_logic.get_status(r, "concert-1", "bob").status == "not_found"
    assert queue_logic.get_status(r, "concert-2", "alice").status == "not_found"


def test_active_events_tracks_every_event_seen(r):
    queue_logic.join_queue(r, "concert-1", "alice")
    queue_logic.join_queue(r, "concert-2", "bob")
    assert set(queue_logic.active_events(r)) == {"concert-1", "concert-2"}
