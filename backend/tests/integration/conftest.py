"""
Integration tests conftest.

Provides:
  * `integration_db_url` env-gate fixture
  * `requires_db` marker that skips when no DB is configured
  * `sqlite_session` lightweight in-memory session for model-shape tests

Heavier fixtures (real Postgres, full app) are inherited from
`backend/tests/conftest.py` automatically.
"""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timezone, timedelta


def _has_real_db() -> bool:
    """Return True if a Postgres URL is configured for integration tests."""
    url = os.getenv("TEST_DATABASE_URL", "")
    return url.startswith("postgresql://") and "localhost" not in url or (
        # Also allow CI local Postgres
        url.startswith("postgresql://test:")
    )


requires_real_db = pytest.mark.skipif(
    not _has_real_db(),
    reason="Real Postgres TEST_DATABASE_URL not configured",
)


@pytest.fixture
def now_utc():
    return datetime.now(timezone.utc)


@pytest.fixture
def business_hours_window(now_utc):
    """Returns (start, end) tuple spanning a 9am-5pm business window."""
    start = now_utc.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=8)
    return (start, end)
