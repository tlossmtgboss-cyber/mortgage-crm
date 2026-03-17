"""
Tests for the standard API response envelope (schemas/response.py).

Validates:
- APIResponse model (ok, fail, paginated class methods)
- PaginationParams (offset, limit properties)
- JSONResponse helpers (success_response, error_response, paginated_response)
- Dict-based helpers (envelope, envelope_error, envelope_page)
- Integration with scheduler routes (envelope shape consistency)
"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.response import (
    APIResponse,
    PaginationParams,
    success_response,
    error_response,
    paginated_response,
    envelope,
    envelope_error,
    envelope_page,
)


# =============================================================================
# APIResponse Model Tests
# =============================================================================

class TestAPIResponse:
    """Tests for the APIResponse Pydantic model."""

    def test_ok_with_data(self):
        resp = APIResponse.ok(data={"id": 1, "name": "test"})
        assert resp.success is True
        assert resp.data == {"id": 1, "name": "test"}
        assert resp.message is None
        assert resp.errors is None
        assert resp.meta is None

    def test_ok_with_message(self):
        resp = APIResponse.ok(data={"id": 1}, message="Created successfully")
        assert resp.success is True
        assert resp.message == "Created successfully"

    def test_ok_with_meta(self):
        resp = APIResponse.ok(data=[], meta={"total": 42})
        assert resp.success is True
        assert resp.meta == {"total": 42}

    def test_ok_with_none_data(self):
        resp = APIResponse.ok()
        assert resp.success is True
        assert resp.data is None

    def test_fail_basic(self):
        resp = APIResponse.fail(message="Something went wrong")
        assert resp.success is False
        assert resp.message == "Something went wrong"
        assert resp.data is None

    def test_fail_with_errors(self):
        errors = [
            {"field": "email", "message": "Invalid email format"},
            {"field": "phone", "message": "Phone is required"},
        ]
        resp = APIResponse.fail(message="Validation failed", errors=errors)
        assert resp.success is False
        assert len(resp.errors) == 2
        assert resp.errors[0]["field"] == "email"

    def test_paginated(self):
        resp = APIResponse.paginated(
            data=[{"id": 1}, {"id": 2}],
            total=100,
            page=2,
            page_size=25,
        )
        assert resp.success is True
        assert resp.data == [{"id": 1}, {"id": 2}]
        assert resp.meta["total"] == 100
        assert resp.meta["page"] == 2
        assert resp.meta["page_size"] == 25
        assert resp.meta["total_pages"] == 4

    def test_paginated_total_pages_calculation(self):
        """total_pages = ceil(total / page_size)"""
        resp = APIResponse.paginated(data=[], total=101, page=1, page_size=25)
        assert resp.meta["total_pages"] == 5  # ceil(101/25) = 5

    def test_paginated_zero_page_size(self):
        """Edge case: page_size=0 should not divide by zero."""
        resp = APIResponse.paginated(data=[], total=10, page=1, page_size=0)
        assert resp.meta["total_pages"] == 0

    def test_paginated_with_message(self):
        resp = APIResponse.paginated(
            data=[], total=0, page=1, page_size=25, message="No results found"
        )
        assert resp.message == "No results found"

    def test_model_dump(self):
        """Ensure model_dump() produces serializable dict."""
        resp = APIResponse.ok(data={"id": 1}, message="OK")
        d = resp.model_dump()
        assert d["success"] is True
        assert d["data"] == {"id": 1}
        assert d["message"] == "OK"
        assert d["errors"] is None
        assert d["meta"] is None


# =============================================================================
# PaginationParams Tests
# =============================================================================

class TestPaginationParams:
    """Tests for PaginationParams query model."""

    def test_defaults(self):
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 25

    def test_offset_page_1(self):
        params = PaginationParams(page=1, page_size=25)
        assert params.offset == 0
        assert params.limit == 25

    def test_offset_page_3(self):
        params = PaginationParams(page=3, page_size=10)
        assert params.offset == 20
        assert params.limit == 10

    def test_custom_page_size(self):
        params = PaginationParams(page=1, page_size=50)
        assert params.limit == 50
        assert params.offset == 0


# =============================================================================
# JSONResponse Helper Tests
# =============================================================================

class TestJSONResponseHelpers:
    """Tests for success_response, error_response, paginated_response."""

    def test_success_response_default_status(self):
        resp = success_response(data={"id": 1})
        assert resp.status_code == 200
        body = json.loads(resp.body.decode())
        assert body["success"] is True
        assert body["data"] == {"id": 1}

    def test_success_response_custom_status(self):
        resp = success_response(data={"id": 1}, message="Created", status_code=201)
        assert resp.status_code == 201
        body = json.loads(resp.body.decode())
        assert body["message"] == "Created"

    def test_success_response_with_meta(self):
        resp = success_response(data=[], meta={"total": 5})
        body = json.loads(resp.body.decode())
        assert body["meta"]["total"] == 5

    def test_error_response_default_status(self):
        resp = error_response("Bad request")
        assert resp.status_code == 400
        body = json.loads(resp.body.decode())
        assert body["success"] is False
        assert body["message"] == "Bad request"

    def test_error_response_custom_status(self):
        resp = error_response("Not found", status_code=404)
        assert resp.status_code == 404

    def test_error_response_with_errors(self):
        resp = error_response(
            "Validation failed",
            errors=[{"field": "name", "message": "required"}],
        )
        body = json.loads(resp.body.decode())
        assert body["errors"][0]["field"] == "name"

    def test_paginated_response(self):
        resp = paginated_response(
            data=[{"id": 1}],
            total=50,
            page=2,
            page_size=10,
        )
        assert resp.status_code == 200
        body = json.loads(resp.body.decode())
        assert body["success"] is True
        assert body["data"] == [{"id": 1}]
        assert body["meta"]["total"] == 50
        assert body["meta"]["page"] == 2
        assert body["meta"]["total_pages"] == 5


# =============================================================================
# Dict-based Helper Tests (envelope, envelope_error, envelope_page)
# =============================================================================

class TestDictHelpers:
    """Tests for dict-based envelope helpers used in scheduler routes."""

    def test_envelope_basic(self):
        result = envelope(data={"id": 1})
        assert result["success"] is True
        assert result["data"] == {"id": 1}
        assert result["message"] is None
        assert result["errors"] is None
        assert result["meta"] is None

    def test_envelope_with_message(self):
        result = envelope(data={"id": 1}, message="Created")
        assert result["message"] == "Created"

    def test_envelope_with_meta(self):
        result = envelope(data=[], meta={"total": 10})
        assert result["meta"]["total"] == 10

    def test_envelope_message_only(self):
        """Some endpoints return just a message with no data."""
        result = envelope(message="Deleted successfully")
        assert result["success"] is True
        assert result["data"] is None
        assert result["message"] == "Deleted successfully"

    def test_envelope_error_basic(self):
        result = envelope_error("Something went wrong")
        assert result["success"] is False
        assert result["data"] is None
        assert result["message"] == "Something went wrong"
        assert result["errors"] is None

    def test_envelope_error_with_errors(self):
        result = envelope_error(
            "Validation failed",
            errors=[{"field": "email", "message": "invalid"}],
        )
        assert result["errors"][0]["field"] == "email"

    def test_envelope_page(self):
        result = envelope_page(
            data=[{"id": 1}, {"id": 2}],
            total=100,
            page=1,
            page_size=25,
        )
        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["meta"]["total"] == 100
        assert result["meta"]["page"] == 1
        assert result["meta"]["page_size"] == 25
        assert result["meta"]["total_pages"] == 4

    def test_envelope_page_empty(self):
        result = envelope_page(data=[], total=0, page=1, page_size=25)
        assert result["data"] == []
        assert result["meta"]["total"] == 0
        assert result["meta"]["total_pages"] == 0

    def test_envelope_page_with_message(self):
        result = envelope_page(
            data=[], total=0, page=1, page_size=25, message="No records"
        )
        assert result["message"] == "No records"

    def test_envelope_page_total_pages_rounding(self):
        """26 items / 25 per page = 2 pages."""
        result = envelope_page(data=[], total=26, page=1, page_size=25)
        assert result["meta"]["total_pages"] == 2

    def test_envelope_page_exact_division(self):
        """50 items / 25 per page = 2 pages exactly."""
        result = envelope_page(data=[], total=50, page=1, page_size=25)
        assert result["meta"]["total_pages"] == 2


# =============================================================================
# Shape Consistency Tests
# =============================================================================

class TestShapeConsistency:
    """Verify that all envelope variants produce the same top-level keys."""

    EXPECTED_KEYS = {"success", "data", "message", "errors", "meta"}

    def test_envelope_keys(self):
        assert set(envelope(data={}).keys()) == self.EXPECTED_KEYS

    def test_envelope_error_keys(self):
        assert set(envelope_error("err").keys()) == self.EXPECTED_KEYS

    def test_envelope_page_keys(self):
        assert set(envelope_page([], 0, 1, 25).keys()) == self.EXPECTED_KEYS

    def test_api_response_ok_keys(self):
        d = APIResponse.ok(data={}).model_dump()
        assert set(d.keys()) == self.EXPECTED_KEYS

    def test_api_response_fail_keys(self):
        d = APIResponse.fail(message="err").model_dump()
        assert set(d.keys()) == self.EXPECTED_KEYS

    def test_json_success_response_keys(self):
        resp = success_response(data={})
        body = json.loads(resp.body.decode())
        assert set(body.keys()) == self.EXPECTED_KEYS

    def test_json_error_response_keys(self):
        resp = error_response("err")
        body = json.loads(resp.body.decode())
        assert set(body.keys()) == self.EXPECTED_KEYS

    def test_json_paginated_response_keys(self):
        resp = paginated_response(data=[], total=0, page=1, page_size=25)
        body = json.loads(resp.body.decode())
        assert set(body.keys()) == self.EXPECTED_KEYS


# =============================================================================
# Serialization Edge Cases
# =============================================================================

class TestSerializationEdgeCases:
    """Test that various data types serialize correctly through the envelope."""

    def test_list_data(self):
        result = envelope(data=[1, 2, 3])
        assert result["data"] == [1, 2, 3]

    def test_nested_dict_data(self):
        result = envelope(data={"nested": {"deep": True}})
        assert result["data"]["nested"]["deep"] is True

    def test_none_data(self):
        result = envelope()
        assert result["data"] is None

    def test_string_data(self):
        result = envelope(data="simple string")
        assert result["data"] == "simple string"

    def test_boolean_data(self):
        result = envelope(data=True)
        assert result["data"] is True

    def test_empty_list_data(self):
        result = envelope(data=[])
        assert result["data"] == []

    def test_empty_dict_data(self):
        result = envelope(data={})
        assert result["data"] == {}
