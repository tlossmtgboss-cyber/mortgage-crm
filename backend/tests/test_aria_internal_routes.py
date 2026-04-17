# backend/tests/test_aria_internal_routes.py
import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

from main import app
from database import get_db


def _mock_db():
    """Yield a mock DB session that returns no results for any query."""
    db = MagicMock()
    # .query(...).filter(...).first() returns None
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    try:
        yield db
    finally:
        pass


app.dependency_overrides[get_db] = _mock_db

client = TestClient(app)
HEADERS = {"X-Internal-API-Key": "test-internal-key"}


def test_internal_lead_lookup_requires_api_key():
    resp = client.post("/internal/aria/lead-lookup", json={"phone": "+18435551234"})
    assert resp.status_code == 403


def test_internal_lead_lookup_with_valid_key():
    resp = client.post(
        "/internal/aria/lead-lookup",
        json={"phone": "+18435551234"},
        headers=HEADERS,
    )
    # Should return 200 even if no lead found (empty result, not error)
    assert resp.status_code == 200
    data = resp.json()
    assert "lead" in data


def test_internal_tool_execute_unknown_tool():
    resp = client.post(
        "/internal/aria/tool/execute",
        json={"tool_name": "nonexistent_tool_xyz", "params": {}},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") is not None
