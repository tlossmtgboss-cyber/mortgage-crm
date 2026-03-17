"""
API Versioning Infrastructure Tests - Perennia AI

Tests for the full V2 API versioning stack:
- APIVersionMiddleware: version negotiation, unsupported versions, sunset
- V2 response schemas: ProblemDetail, CursorPage, V2Envelope
- Sparse fieldsets: validate_sparse_fields, apply_sparse_fields
- Cursor pagination: encode/decode cursors
- Deprecation service: decorator, registry, notices endpoint
- V2 Scheduler routes: CRUD, pagination, fieldsets, includes, error format

30+ tests organized by component.
"""

import base64
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# SCHEMA TESTS
# =============================================================================


class TestProblemDetail:
    """RFC 7807 Problem Details schema tests."""

    def test_not_found(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.not_found("Appointment 42 not found")
        assert problem.status == 404
        assert problem.title == "Resource Not Found"
        assert "42" in problem.detail
        assert "not-found" in problem.type

    def test_bad_request(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.bad_request(
            "Invalid field name",
            errors=[{"field": "foo", "message": "unknown field"}],
        )
        assert problem.status == 400
        assert problem.title == "Bad Request"
        assert len(problem.errors) == 1

    def test_unsupported_version(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.unsupported_version("v99 not supported")
        assert problem.status == 400
        assert "unsupported-version" in problem.type

    def test_validation_error(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.validation_error(
            "Validation failed",
            errors=[{"field": "email", "message": "invalid"}],
        )
        assert problem.status == 422
        assert len(problem.errors) == 1

    def test_internal_error(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.internal_error()
        assert problem.status == 500
        assert problem.detail == "An unexpected error occurred"

    def test_problem_detail_with_instance(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.not_found(
            "Not found",
            instance="/api/v2/scheduler/appointments/999",
        )
        assert problem.instance == "/api/v2/scheduler/appointments/999"

    def test_serialization_excludes_none(self):
        from schemas.api_v2 import ProblemDetail

        problem = ProblemDetail.not_found("Not found")
        data = problem.model_dump(exclude_none=True)
        assert "errors" not in data
        assert "instance" not in data
        assert data["status"] == 404


class TestCursorPagination:
    """Cursor encode/decode and CursorPage tests."""

    def test_encode_decode_roundtrip(self):
        from schemas.api_v2 import decode_cursor, encode_cursor

        values = {"id": 42, "created_at": "2026-03-12T10:00:00"}
        cursor = encode_cursor(values)
        assert isinstance(cursor, str)
        decoded = decode_cursor(cursor)
        assert decoded["id"] == 42

    def test_decode_invalid_cursor(self):
        from schemas.api_v2 import decode_cursor

        with pytest.raises(ValueError, match="Invalid cursor"):
            decode_cursor("not-valid-base64!!!")

    def test_encode_with_datetime(self):
        from schemas.api_v2 import decode_cursor, encode_cursor

        values = {"id": 1, "ts": datetime(2026, 3, 12, 10, 0, 0)}
        cursor = encode_cursor(values)
        decoded = decode_cursor(cursor)
        assert decoded["id"] == 1
        assert "2026-03-12" in decoded["ts"]

    def test_cursor_page_defaults(self):
        from schemas.api_v2 import CursorPage

        page = CursorPage(data=[])
        assert page.data == []
        assert page.has_more is False
        assert page.cursor.next is None
        assert page.cursor.prev is None
        assert page.total_count is None

    def test_cursor_page_with_data(self):
        from schemas.api_v2 import CursorInfo, CursorPage

        page = CursorPage(
            data=[{"id": 1}, {"id": 2}],
            cursor=CursorInfo(next="abc", prev=None),
            has_more=True,
            total_count=10,
        )
        assert len(page.data) == 2
        assert page.has_more is True
        assert page.cursor.next == "abc"
        assert page.total_count == 10


class TestSparseFieldsets:
    """Field selection utilities tests."""

    def test_validate_valid_fields(self):
        from schemas.api_v2 import validate_sparse_fields

        result = validate_sparse_fields("id,title,status")
        assert result == {"id", "title", "status"}

    def test_validate_none_returns_none(self):
        from schemas.api_v2 import validate_sparse_fields

        assert validate_sparse_fields(None) is None
        assert validate_sparse_fields("") is None

    def test_validate_unknown_field_raises(self):
        from schemas.api_v2 import validate_sparse_fields

        with pytest.raises(ValueError, match="Unknown fields"):
            validate_sparse_fields("id,nonexistent_field")

    def test_validate_with_whitespace(self):
        from schemas.api_v2 import validate_sparse_fields

        result = validate_sparse_fields("id , title , status")
        assert result == {"id", "title", "status"}

    def test_apply_sparse_fields_filters(self):
        from schemas.api_v2 import apply_sparse_fields

        item = {"id": 1, "title": "Test", "status": "booked", "description": "desc"}
        filtered = apply_sparse_fields(item, {"title", "status"})
        assert set(filtered.keys()) == {"id", "title", "status"}

    def test_apply_sparse_fields_always_includes_id(self):
        from schemas.api_v2 import apply_sparse_fields

        item = {"id": 1, "title": "Test"}
        filtered = apply_sparse_fields(item, {"title"})
        assert "id" in filtered

    def test_apply_sparse_fields_none_returns_all(self):
        from schemas.api_v2 import apply_sparse_fields

        item = {"id": 1, "title": "Test", "status": "booked"}
        result = apply_sparse_fields(item, None)
        assert result == item

    def test_validate_custom_allowed_set(self):
        from schemas.api_v2 import validate_sparse_fields

        result = validate_sparse_fields("a,b", allowed={"a", "b", "c"})
        assert result == {"a", "b"}


class TestV2Envelope:
    """V2 response envelope tests."""

    def test_envelope_defaults(self):
        from schemas.api_v2 import V2Envelope

        env = V2Envelope(data={"id": 1})
        assert env.data == {"id": 1}
        assert env.meta.api_version == "2.0"
        assert env.included is None

    def test_envelope_with_included(self):
        from schemas.api_v2 import V2Envelope

        env = V2Envelope(
            data={"id": 1},
            included={"attendees": [{"name": "John"}]},
        )
        assert env.included["attendees"][0]["name"] == "John"

    def test_envelope_serialization(self):
        from schemas.api_v2 import V2Envelope, V2Meta

        env = V2Envelope(
            data={"id": 1, "title": "Test"},
            meta=V2Meta(api_version="2.0", deprecated=False),
        )
        data = env.model_dump(exclude_none=True)
        assert data["data"]["id"] == 1
        assert data["meta"]["api_version"] == "2.0"
        assert "included" not in data


class TestV2AppointmentSchemas:
    """V2 appointment request/response schema tests."""

    def test_create_request_valid(self):
        from schemas.api_v2 import V2AppointmentCreateRequest

        req = V2AppointmentCreateRequest(
            title="Test Meeting",
            scheduled_start="2026-03-15T10:00:00-05:00",
            duration_minutes=30,
        )
        assert req.title == "Test Meeting"
        assert req.meeting_mode == "video"

    def test_create_request_requires_timezone(self):
        from schemas.api_v2 import V2AppointmentCreateRequest

        with pytest.raises(Exception, match="timezone"):
            V2AppointmentCreateRequest(
                title="Test",
                scheduled_start="2026-03-15T10:00:00",  # no timezone
            )

    def test_create_request_rejects_invalid_datetime(self):
        from schemas.api_v2 import V2AppointmentCreateRequest

        with pytest.raises(Exception):
            V2AppointmentCreateRequest(
                title="Test",
                scheduled_start="not-a-date",
            )

    def test_update_request_partial(self):
        from schemas.api_v2 import V2AppointmentUpdateRequest

        req = V2AppointmentUpdateRequest(title="Updated Title")
        data = req.model_dump(exclude_unset=True)
        assert data == {"title": "Updated Title"}

    def test_update_request_timezone_validation(self):
        from schemas.api_v2 import V2AppointmentUpdateRequest

        # With timezone should pass
        req = V2AppointmentUpdateRequest(
            scheduled_start="2026-04-01T14:00:00+00:00"
        )
        assert req.scheduled_start is not None

        # Without timezone should fail
        with pytest.raises(Exception, match="timezone"):
            V2AppointmentUpdateRequest(
                scheduled_start="2026-04-01T14:00:00"
            )


# =============================================================================
# MIDDLEWARE TESTS
# =============================================================================


class TestAPIVersionMiddleware:
    """Tests for the API version negotiation middleware."""

    def _make_request(self, path="/api/v1/test", accept=None):
        """Create a mock Request."""
        request = MagicMock()
        request.url.path = path
        request.method = "GET"
        request.headers = {}
        if accept:
            request.headers["accept"] = accept
        request.state = MagicMock()
        return request

    def test_version_from_path_v1(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        request = self._make_request("/api/v1/scheduler/appointments")
        version, source = mw._negotiate_version(request)
        assert version == 1
        assert source == "path"

    def test_version_from_path_v2(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        request = self._make_request("/api/v2/scheduler/appointments")
        version, source = mw._negotiate_version(request)
        assert version == 2
        assert source == "path"

    def test_version_from_accept_header(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        request = self._make_request(
            "/scheduler/appointments",
            accept="application/vnd.perennia.v2+json",
        )
        version, source = mw._negotiate_version(request)
        assert version == 2
        assert source == "accept"

    def test_default_version_fallback(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        request = self._make_request("/health")
        version, source = mw._negotiate_version(request)
        assert version == 1
        assert source == "default"

    def test_path_takes_priority_over_accept(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        # Path says v1, accept says v2 -> path wins
        request = self._make_request(
            "/api/v1/scheduler/appointments",
            accept="application/vnd.perennia.v2+json",
        )
        version, source = mw._negotiate_version(request)
        assert version == 1
        assert source == "path"

    def test_unsupported_version_detected(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock(), supported_versions={1, 2})
        request = self._make_request("/api/v99/test")
        version, source = mw._negotiate_version(request)
        assert version == 99
        assert version not in mw.supported_versions

    def test_sunset_endpoint_detected(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(
            app=MagicMock(),
            sunset_endpoints={"/api/v0/old"},
        )
        assert mw._is_sunset_endpoint("/api/v0/old") is True
        assert mw._is_sunset_endpoint("/api/v0/old/sub") is True
        assert mw._is_sunset_endpoint("/api/v1/new") is False

    def test_gone_response_format(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        response = mw._create_gone_response("/api/v0/test")
        assert response.status_code == 410
        body = json.loads(response.body)
        assert body["status"] == 410
        assert "sunset" in body["type"].lower() or "sunset" in body["title"].lower()

    def test_unsupported_version_response_format(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        response = mw._create_unsupported_version_response(99)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["status"] == 400
        assert "v99" in body["detail"]

    def test_deprecation_headers_added(self):
        from middleware.api_versioning import APIVersionMiddleware

        deprecated = {
            "/api/v1/old": {
                "deprecation_date": date(2026, 1, 1),
                "sunset_date": date(2026, 6, 1),
                "replacement": "/api/v2/new",
            },
        }
        mw = APIVersionMiddleware(
            app=MagicMock(),
            deprecated_endpoints=deprecated,
        )
        response = MagicMock()
        response.headers = {}
        mw._add_deprecation_headers(response, "/api/v1/old")
        assert "Deprecation" in response.headers
        assert "Sunset" in response.headers
        assert "Link" in response.headers
        assert "/api/v2/new" in response.headers["Link"]

    def test_no_deprecation_headers_for_non_deprecated(self):
        from middleware.api_versioning import APIVersionMiddleware

        mw = APIVersionMiddleware(app=MagicMock())
        response = MagicMock()
        response.headers = {}
        mw._add_deprecation_headers(response, "/api/v2/new")
        assert "Deprecation" not in response.headers


class TestVersionUsageTracking:
    """Tests for version usage statistics tracking."""

    def test_usage_stats_structure(self):
        from middleware.api_versioning import (
            get_version_usage_stats,
            reset_version_usage_stats,
        )

        reset_version_usage_stats()
        stats = get_version_usage_stats()
        assert "by_version" in stats
        assert "by_endpoint" in stats

    def test_reset_clears_counters(self):
        from middleware.api_versioning import (
            _version_usage,
            get_version_usage_stats,
            reset_version_usage_stats,
        )

        _version_usage[1] = 100
        reset_version_usage_stats()
        stats = get_version_usage_stats()
        assert stats["by_version"] == {}


# =============================================================================
# DEPRECATION SERVICE TESTS
# =============================================================================


class TestDeprecationService:
    """Tests for the API deprecation tracking service."""

    def setup_method(self):
        from services.api_deprecation import clear_deprecation_registry
        clear_deprecation_registry()

    def test_register_deprecation(self):
        from services.api_deprecation import (
            get_deprecation_notices,
            register_deprecation,
        )

        register_deprecation(
            path="/api/v1/old",
            method="GET",
            deprecation_date="2026-01-01",
            sunset_date="2026-09-01",
            replacement="/api/v2/new",
        )
        notices = get_deprecation_notices()
        assert len(notices) == 1
        assert notices[0]["path"] == "/api/v1/old"
        assert notices[0]["sunset_date"] == "2026-09-01"
        assert notices[0]["replacement"] == "/api/v2/new"

    def test_multiple_notices(self):
        from services.api_deprecation import (
            get_deprecation_notices,
            register_deprecation,
        )

        register_deprecation("/a", "GET", "2026-01-01", "2026-09-01")
        register_deprecation("/b", "POST", "2026-02-01", "2026-10-01")
        notices = get_deprecation_notices()
        assert len(notices) == 2

    def test_clear_registry(self):
        from services.api_deprecation import (
            clear_deprecation_registry,
            get_deprecation_notices,
            register_deprecation,
        )

        register_deprecation("/a", "GET", "2026-01-01", "2026-09-01")
        clear_deprecation_registry()
        assert len(get_deprecation_notices()) == 0

    def test_deprecated_endpoint_decorator_metadata(self):
        from services.api_deprecation import deprecated_endpoint

        @deprecated_endpoint(sunset_date="2026-09-01", replacement="/api/v2/new")
        async def my_endpoint():
            return {"ok": True}

        assert hasattr(my_endpoint, "_deprecation_info")
        info = my_endpoint._deprecation_info
        assert info["sunset_date"] == "2026-09-01"
        assert info["replacement"] == "/api/v2/new"

    @pytest.mark.asyncio
    async def test_deprecation_notices_endpoint_returns_list(self):
        """Test the deprecation notices endpoint handler directly."""
        from services.api_deprecation import (
            list_deprecation_notices,
            register_deprecation,
        )

        register_deprecation(
            "/api/v1/test", "GET", "2026-01-01", "2026-06-01",
            replacement="/api/v2/test",
        )
        result = await list_deprecation_notices()
        assert "deprecation_notices" in result
        assert result["total"] == 1
        assert result["deprecation_notices"][0]["replacement"] == "/api/v2/test"


# =============================================================================
# V2 SCHEDULER ROUTE TESTS (unit-level with mocks)
# =============================================================================


class _FakeAppointment:
    """Mock appointment object for route handler tests."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.uuid = kwargs.get("uuid", "abc-123")
        self.title = kwargs.get("title", "Test Meeting")
        self.description = kwargs.get("description", "A test meeting")
        self.status = kwargs.get("status", "booked")
        self.meeting_type = kwargs.get("meeting_type", "discovery_call")
        self.meeting_mode = kwargs.get("meeting_mode", "video")
        self.scheduled_start = kwargs.get(
            "scheduled_start",
            datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        self.scheduled_end = kwargs.get(
            "scheduled_end",
            datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.timezone = kwargs.get("timezone", "America/Chicago")
        self.attendee_name = kwargs.get("attendee_name", "John Doe")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.attendee_phone = kwargs.get("attendee_phone", None)
        self.attendee_notes = kwargs.get("attendee_notes", None)
        self.lead_id = kwargs.get("lead_id", None)
        self.loan_id = kwargs.get("loan_id", None)
        self.contact_id = kwargs.get("contact_id", None)
        self.assigned_user_id = kwargs.get("assigned_user_id", 1)
        self.location = kwargs.get("location", None)
        self.video_link = kwargs.get("video_link", "https://meet.example.com/abc")
        self.cancellation_reason = kwargs.get("cancellation_reason", None)
        self.internal_notes = kwargs.get("internal_notes", None)
        self.meeting_notes = kwargs.get("meeting_notes", None)
        self.booked_by_ai = kwargs.get("booked_by_ai", False)
        self.no_show_risk_score = kwargs.get("no_show_risk_score", None)
        self.created_at = kwargs.get(
            "created_at",
            datetime(2026, 3, 10, 8, 0, 0, tzinfo=timezone.utc),
        )
        self.updated_at = kwargs.get("updated_at", None)
        self.organization_id = kwargs.get("organization_id", 1)
        self.appointment_type_id = kwargs.get("appointment_type_id", None)
        self.user_id = kwargs.get("user_id", 1)


class TestV2SchedulerHelpers:
    """Unit tests for V2 scheduler route helper functions."""

    def test_format_datetime_with_tz(self):
        from routes.api_v2.scheduler_v2 import _format_datetime

        dt = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = _format_datetime(dt)
        assert "2026-03-15" in result
        assert "+00:00" in result or "Z" in result

    def test_format_datetime_naive_assumes_utc(self):
        from routes.api_v2.scheduler_v2 import _format_datetime

        dt = datetime(2026, 3, 15, 10, 0, 0)
        result = _format_datetime(dt)
        assert "+00:00" in result

    def test_format_datetime_none(self):
        from routes.api_v2.scheduler_v2 import _format_datetime

        assert _format_datetime(None) is None

    def test_format_datetime_string_passthrough(self):
        from routes.api_v2.scheduler_v2 import _format_datetime

        assert _format_datetime("2026-03-15T10:00:00Z") == "2026-03-15T10:00:00Z"

    def test_appointment_to_dict(self):
        from routes.api_v2.scheduler_v2 import _appointment_to_dict

        appt = _FakeAppointment(id=42, title="My Meeting")
        result = _appointment_to_dict(appt)
        assert result["id"] == 42
        assert result["title"] == "My Meeting"
        assert "2026-03-15" in result["scheduled_start"]

    def test_build_included_attendees(self):
        from routes.api_v2.scheduler_v2 import _build_included

        appt = _FakeAppointment(attendee_name="Jane", attendee_email="jane@test.com")
        included = _build_included(appt, {"attendees"})
        assert "attendees" in included
        assert included["attendees"][0]["name"] == "Jane"

    def test_build_included_meeting(self):
        from routes.api_v2.scheduler_v2 import _build_included

        appt = _FakeAppointment(video_link="https://meet.example.com")
        included = _build_included(appt, {"meeting"})
        assert "meeting" in included
        assert included["meeting"][0]["video_link"] == "https://meet.example.com"

    def test_build_included_empty(self):
        from routes.api_v2.scheduler_v2 import _build_included

        appt = _FakeAppointment()
        result = _build_included(appt, set())
        assert result is None

    def test_parse_include_valid(self):
        from routes.api_v2.scheduler_v2 import _parse_include

        result = _parse_include("attendees,meeting")
        assert result == {"attendees", "meeting"}

    def test_parse_include_none(self):
        from routes.api_v2.scheduler_v2 import _parse_include

        assert _parse_include(None) == set()
        assert _parse_include("") == set()

    def test_parse_include_invalid_raises(self):
        from routes.api_v2.scheduler_v2 import _parse_include

        with pytest.raises(ValueError, match="Unknown include"):
            _parse_include("attendees,invalid_resource")


# =============================================================================
# BACKWARDS COMPATIBILITY TESTS
# =============================================================================


class TestBackwardsCompatibility:
    """Ensure old middleware names still work."""

    def test_old_class_name_alias(self):
        from middleware.api_versioning import APIVersioningMiddleware

        # Should be an alias of the new class
        assert APIVersioningMiddleware is not None

    def test_deprecate_endpoint_function(self):
        from middleware.api_versioning import (
            DEPRECATED_ENDPOINTS,
            deprecate_endpoint,
        )

        # Clear first
        DEPRECATED_ENDPOINTS.clear()
        deprecate_endpoint(
            "/api/v1/old-test",
            deprecation_date=date(2026, 1, 1),
            sunset_date=date(2026, 7, 1),
            replacement="/api/v2/new-test",
        )
        assert "/api/v1/old-test" in DEPRECATED_ENDPOINTS
        info = DEPRECATED_ENDPOINTS["/api/v1/old-test"]
        assert info["replacement"] == "/api/v2/new-test"
        # Clean up
        DEPRECATED_ENDPOINTS.clear()

    def test_sunset_endpoint_function(self):
        from middleware.api_versioning import SUNSET_ENDPOINTS, sunset_endpoint

        SUNSET_ENDPOINTS.clear()
        sunset_endpoint("/api/v0/dead")
        assert "/api/v0/dead" in SUNSET_ENDPOINTS
        SUNSET_ENDPOINTS.clear()

    def test_current_api_version_constant(self):
        from middleware.api_versioning import CURRENT_API_VERSION

        assert CURRENT_API_VERSION == "1.0"


# =============================================================================
# INTEGRATION-STYLE ROUTE TESTS
# =============================================================================


class TestV2RouterInit:
    """Tests for the V2 router aggregator."""

    def test_router_has_prefix(self):
        from routes.api_v2 import router

        assert router.prefix == "/api/v2"

    def test_scheduler_routes_included(self):
        from routes.api_v2 import router

        # Collect all route paths
        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)
            # Check sub-routers
            if hasattr(route, "routes"):
                for sub in route.routes:
                    if hasattr(sub, "path"):
                        paths.add(sub.path)
        # The scheduler router is included at /scheduler prefix
        # so routes will appear as /scheduler/appointments, etc.
        assert any("appointments" in p for p in paths)


class TestV2EndpointDiscovery:
    """Verify that V2 endpoints are properly registered."""

    def test_list_appointments_route_exists(self):
        from routes.api_v2.scheduler_v2 import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        # Router has prefix /scheduler so paths are /scheduler/appointments
        assert "/scheduler/appointments" in paths

    def test_get_appointment_route_exists(self):
        from routes.api_v2.scheduler_v2 import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert "/scheduler/appointments/{appointment_id}" in paths

    def test_search_route_exists(self):
        from routes.api_v2.scheduler_v2 import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert "/scheduler/appointments/search" in paths

    def test_all_methods_covered(self):
        from routes.api_v2.scheduler_v2 import router

        methods = set()
        for route in router.routes:
            if hasattr(route, "methods"):
                methods.update(route.methods)
        assert "GET" in methods
        assert "POST" in methods
        assert "PATCH" in methods or "PUT" in methods
        assert "DELETE" in methods
