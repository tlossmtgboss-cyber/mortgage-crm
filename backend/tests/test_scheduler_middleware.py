"""
Tests for scheduler middleware, API versioning, and exception handling.

Covers:
  - SchedulerTimingMiddleware (X-Scheduler-Duration-Ms header, slow request logging)
  - SchedulerAPIVersionMiddleware (X-API-Version negotiation)
  - CURRENT_API_VERSION / SUPPORTED_API_VERSIONS constants
  - ENDPOINT_VERSIONS registry
  - deprecated_endpoint decorator (Deprecation, Sunset, Link headers)
  - Scheduler exception hierarchy and handler
  - SchedulerErrorResponse / SchedulerSuccessResponse models
"""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request
from starlette.responses import Response, JSONResponse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Tests: API Version Constants and Registry
# ---------------------------------------------------------------------------

class TestAPIVersionConstants:
    """Tests for version constants and endpoint registry."""

    def test_current_version_is_in_supported(self):
        """CURRENT_API_VERSION must appear in SUPPORTED_API_VERSIONS."""
        from routes.scheduler.middleware import CURRENT_API_VERSION, SUPPORTED_API_VERSIONS

        assert CURRENT_API_VERSION in SUPPORTED_API_VERSIONS

    def test_supported_versions_ordered(self):
        """SUPPORTED_API_VERSIONS should be in chronological order."""
        from routes.scheduler.middleware import SUPPORTED_API_VERSIONS

        assert len(SUPPORTED_API_VERSIONS) >= 2
        assert SUPPORTED_API_VERSIONS == sorted(SUPPORTED_API_VERSIONS)

    def test_endpoint_versions_have_required_keys(self):
        """Every ENDPOINT_VERSIONS entry should have 'introduced' and 'current'."""
        from routes.scheduler.middleware import ENDPOINT_VERSIONS

        assert len(ENDPOINT_VERSIONS) > 0
        for path, meta in ENDPOINT_VERSIONS.items():
            assert "introduced" in meta, f"{path} missing 'introduced'"
            assert "current" in meta, f"{path} missing 'current'"

    def test_endpoint_introduced_not_after_current(self):
        """The 'introduced' version should not be later than 'current'."""
        from routes.scheduler.middleware import ENDPOINT_VERSIONS

        for path, meta in ENDPOINT_VERSIONS.items():
            assert meta["introduced"] <= meta["current"], (
                f"{path}: introduced={meta['introduced']} > current={meta['current']}"
            )


# ---------------------------------------------------------------------------
# Tests: API Version Middleware
# ---------------------------------------------------------------------------

class TestAPIVersionMiddleware:
    """Tests for SchedulerAPIVersionMiddleware dispatch logic."""

    @pytest.mark.asyncio
    async def test_default_version_when_no_header(self):
        """When no version header is sent, default to CURRENT_API_VERSION."""
        from routes.scheduler.middleware import (
            scheduler_api_version_middleware, CURRENT_API_VERSION,
        )

        request = MagicMock(spec=Request)
        request.headers = {}
        request.state = MagicMock()

        response = MagicMock(spec=Response)
        response.headers = {}

        async def call_next(req):
            return response

        result = await scheduler_api_version_middleware(request, call_next)
        assert request.state.api_version == CURRENT_API_VERSION
        assert result.headers["X-API-Version"] == CURRENT_API_VERSION

    @pytest.mark.asyncio
    async def test_x_api_version_header_takes_precedence(self):
        """X-API-Version header should take precedence over Accept-Version."""
        from routes.scheduler.middleware import scheduler_api_version_middleware

        request = MagicMock(spec=Request)
        request.headers = {
            "X-API-Version": "2025-06",
            "Accept-Version": "2025-12",
        }
        request.state = MagicMock()

        response = MagicMock(spec=Response)
        response.headers = {}

        async def call_next(req):
            return response

        result = await scheduler_api_version_middleware(request, call_next)
        assert request.state.api_version == "2025-06"
        assert result.headers["X-API-Version"] == "2025-06"

    @pytest.mark.asyncio
    async def test_accept_version_fallback(self):
        """Accept-Version is used when X-API-Version is absent."""
        from routes.scheduler.middleware import scheduler_api_version_middleware

        request = MagicMock(spec=Request)
        request.headers = {"Accept-Version": "2025-12"}
        request.state = MagicMock()

        response = MagicMock(spec=Response)
        response.headers = {}

        async def call_next(req):
            return response

        result = await scheduler_api_version_middleware(request, call_next)
        assert request.state.api_version == "2025-12"


# ---------------------------------------------------------------------------
# Tests: Timing Middleware
# ---------------------------------------------------------------------------

class TestTimingMiddleware:
    """Tests for SchedulerTimingMiddleware / scheduler_timing_middleware."""

    @pytest.mark.asyncio
    async def test_timing_header_added(self):
        """X-Scheduler-Duration-Ms header should be present on every response."""
        from routes.scheduler.middleware import scheduler_timing_middleware

        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/api/v1/scheduler/appointments"

        response = MagicMock(spec=Response)
        response.headers = {}

        async def call_next(req):
            return response

        result = await scheduler_timing_middleware(request, call_next)
        assert "X-Scheduler-Duration-Ms" in result.headers

    @pytest.mark.asyncio
    async def test_slow_request_is_logged(self):
        """Requests over the threshold should trigger a warning log."""
        from routes.scheduler.middleware import scheduler_timing_middleware

        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/api/v1/scheduler/appointments"

        response = MagicMock(spec=Response)
        response.headers = {}

        async def slow_call_next(req):
            # Simulate a slow request (> 1000ms threshold)
            time.sleep(0.01)  # 10ms -- we'll patch the threshold
            return response

        with patch("routes.scheduler.middleware._SLOW_REQUEST_THRESHOLD_MS", 0):
            with patch("routes.scheduler.middleware.logger") as mock_logger:
                await scheduler_timing_middleware(request, slow_call_next)
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args[0]
                assert "Slow scheduler request" in call_args[0]


# ---------------------------------------------------------------------------
# Tests: Scheduler Exception Hierarchy
# ---------------------------------------------------------------------------

class TestSchedulerExceptions:
    """Tests for scheduler exception classes and handler."""

    def test_slot_unavailable_error(self):
        """SlotUnavailableError should have 409 status and correct code."""
        from routes.scheduler.middleware import SlotUnavailableError

        exc = SlotUnavailableError()
        assert exc.status_code == 409
        assert exc.code == "SLOT_UNAVAILABLE"

    def test_booking_rate_limit_error(self):
        """BookingRateLimitError should have 429 status."""
        from routes.scheduler.middleware import BookingRateLimitError

        exc = BookingRateLimitError()
        assert exc.status_code == 429
        assert exc.code == "RATE_LIMITED"

    def test_calendar_conflict_error(self):
        """CalendarConflictError should have 409 status."""
        from routes.scheduler.middleware import CalendarConflictError

        exc = CalendarConflictError("Double-booked")
        assert exc.status_code == 409
        assert "Double-booked" in exc.message

    def test_config_error(self):
        """SchedulerConfigError should have 500 status."""
        from routes.scheduler.middleware import SchedulerConfigError

        exc = SchedulerConfigError("Missing timezone")
        assert exc.status_code == 500
        assert exc.code == "CONFIG_ERROR"

    @pytest.mark.asyncio
    async def test_exception_handler_returns_json(self):
        """scheduler_exception_handler should return a JSONResponse with correct status."""
        from routes.scheduler.middleware import (
            scheduler_exception_handler, SlotUnavailableError,
        )

        exc = SlotUnavailableError("Slot taken")
        request = MagicMock(spec=Request)

        response = await scheduler_exception_handler(request, exc)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 409

    def test_scheduler_exception_inherits_perennia(self):
        """SchedulerException should inherit from PerenniaError."""
        from routes.scheduler.middleware import SchedulerException
        from exceptions import PerenniaError

        exc = SchedulerException("test", code="TEST", status_code=400)
        assert isinstance(exc, PerenniaError)


# ---------------------------------------------------------------------------
# Tests: Deprecation Decorator
# ---------------------------------------------------------------------------

class TestDeprecatedEndpoint:
    """Tests for the deprecated_endpoint decorator."""

    @pytest.mark.asyncio
    async def test_deprecated_adds_headers_to_dict_response(self):
        """Decorator should add Deprecation and Sunset headers when handler returns dict."""
        from routes.scheduler.middleware import deprecated_endpoint

        @deprecated_endpoint(sunset_date="2026-09-01", replacement="/api/v1/new")
        async def handler(request):
            return {"data": "ok"}

        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/old"
        request.state = MagicMock()
        request.state.user = None

        result = await handler(request=request)
        assert isinstance(result, JSONResponse)
        assert result.headers.get("Deprecation") == "true"
        assert "Sep 2026" in result.headers.get("Sunset", "")
        assert 'rel="successor-version"' in result.headers.get("Link", "")
