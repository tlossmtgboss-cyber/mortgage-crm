"""
Integration tests for call queue statistics service (CQ-001, CQ-002).

Validates the stub fallbacks behave deterministically when the database
layer is unavailable, and that wait-time estimates compose with queue depth.
"""
from __future__ import annotations

from unittest import mock

from services import call_queue_stats


def test_get_queue_depth_returns_int_with_stub_fallback():
    """When SessionLocal is unavailable the service must degrade to 0."""
    with mock.patch.object(call_queue_stats, "_safe_session", return_value=None):
        depth = call_queue_stats.get_queue_depth()
        assert isinstance(depth, int)
        assert depth == 0


def test_get_wait_time_estimate_uses_queue_depth_and_handle_time():
    """estimated_wait_seconds = depth * avg_handle_seconds."""
    with mock.patch.object(call_queue_stats, "get_queue_depth", return_value=4):
        out = call_queue_stats.get_wait_time_estimate(avg_handle_seconds=120)

    assert out["queue_depth"] == 4
    assert out["avg_handle_seconds"] == 120
    assert out["estimated_wait_seconds"] == 480  # 4 * 120
    assert out["estimated_wait_minutes"] == 8.0


def test_get_queue_position_handles_missing_db():
    """When DB isn't wired the service must return a stable shape."""
    with mock.patch.object(call_queue_stats, "_safe_session", return_value=None):
        out = call_queue_stats.get_queue_position("call-xyz")

    assert out["call_id"] == "call-xyz"
    assert out["position"] == 0
    assert out["in_queue"] is False
    assert out["queue_depth"] == 0
