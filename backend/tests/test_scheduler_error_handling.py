"""
Scheduler Error Handling Tests

Verifies:
- All scheduler exceptions produce consistent JSON error responses
- Status codes map correctly from exception classes
- Public endpoint sanitization strips internal details in production
- Retry-After header is set for rate limit errors
- 5xx errors log at ERROR level, 4xx at INFO
- The centralized handler catches all SchedulerError subclasses
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from exceptions import (
    SchedulerError,
    AppointmentNotFoundError,
    AppointmentConflictError,
    SlotUnavailableError,
    DuplicateBookingError,
    InvalidAppointmentStateError,
    BookingLinkNotFoundError,
    BookingLinkExpiredError,
    CapacityExceededError,
    CalendarSyncError,
    SchedulerRateLimitError,
    SchedulerValidationError,
    SchedulerPermissionError,
    SchedulerConfigNotFoundError,
    OptimisticLockError,
)


# =============================================================================
# Exception class tests
# =============================================================================

class TestSchedulerExceptionHierarchy:
    """Verify exception hierarchy, status codes, and error codes."""

    def test_all_scheduler_errors_inherit_from_scheduler_error(self):
        """All specific scheduler exceptions must subclass SchedulerError."""
        subclasses = [
            AppointmentNotFoundError(1),
            AppointmentConflictError(),
            SlotUnavailableError(),
            DuplicateBookingError(),
            InvalidAppointmentStateError("booked", "funded"),
            BookingLinkNotFoundError("test-slug"),
            BookingLinkExpiredError("test-slug"),
            CapacityExceededError(),
            CalendarSyncError("sync failed"),
            SchedulerRateLimitError(),
            SchedulerValidationError("bad input"),
            SchedulerPermissionError(),
            SchedulerConfigNotFoundError(),
            OptimisticLockError(),
        ]
        for exc in subclasses:
            assert isinstance(exc, SchedulerError), f"{type(exc).__name__} must inherit SchedulerError"

    def test_status_codes(self):
        """Each exception class carries the correct HTTP status code."""
        assert AppointmentNotFoundError(1).status_code == 404
        assert AppointmentConflictError().status_code == 409
        assert SlotUnavailableError().status_code == 409
        assert DuplicateBookingError().status_code == 409
        assert InvalidAppointmentStateError("a", "b").status_code == 422
        assert BookingLinkNotFoundError("slug").status_code == 404
        assert BookingLinkExpiredError("slug").status_code == 410
        assert CapacityExceededError().status_code == 429
        assert CalendarSyncError("fail").status_code == 502
        assert SchedulerRateLimitError().status_code == 429
        assert SchedulerValidationError("bad").status_code == 422
        assert SchedulerPermissionError().status_code == 403
        assert SchedulerConfigNotFoundError().status_code == 404
        assert OptimisticLockError().status_code == 409

    def test_error_codes(self):
        """Each exception carries a unique error code string."""
        assert AppointmentNotFoundError(1).code == "APPOINTMENT_NOT_FOUND"
        assert AppointmentConflictError().code == "APPOINTMENT_CONFLICT"
        assert SlotUnavailableError().code == "SLOT_UNAVAILABLE"
        assert DuplicateBookingError().code == "DUPLICATE_BOOKING"
        assert InvalidAppointmentStateError("a", "b").code == "INVALID_STATE_TRANSITION"
        assert BookingLinkNotFoundError("slug").code == "BOOKING_LINK_NOT_FOUND"
        assert BookingLinkExpiredError("slug").code == "BOOKING_LINK_EXPIRED"
        assert CapacityExceededError().code == "CAPACITY_EXCEEDED"
        assert CalendarSyncError("fail").code == "CALENDAR_SYNC_ERROR"
        assert SchedulerRateLimitError().code == "RATE_LIMIT_EXCEEDED"
        assert SchedulerValidationError("bad").code == "SCHEDULER_VALIDATION_ERROR"
        assert SchedulerPermissionError().code == "SCHEDULER_PERMISSION_DENIED"
        assert SchedulerConfigNotFoundError().code == "SCHEDULER_CONFIG_NOT_FOUND"
        assert OptimisticLockError().code == "CONCURRENT_MODIFICATION"

    def test_custom_message(self):
        """Exceptions preserve custom messages."""
        exc = AppointmentNotFoundError(42)
        assert "42" in exc.message

        exc = BookingLinkNotFoundError("my-link")
        assert "my-link" in exc.message

        exc = InvalidAppointmentStateError("booked", "funded", allowed=["cancelled", "completed"])
        assert "booked" in exc.message
        assert "funded" in exc.message
        assert "cancelled" in exc.message

    def test_details_dict(self):
        """Exceptions include structured details where applicable."""
        exc = DuplicateBookingError(attendee_email="test@example.com")
        assert exc.details["attendee_email"] == "test@example.com"

        exc = InvalidAppointmentStateError("booked", "funded", allowed=["cancelled"])
        assert exc.details["from"] == "booked"
        assert exc.details["to"] == "funded"
        assert exc.details["allowed"] == ["cancelled"]

        exc = CalendarSyncError("fail", provider="google")
        assert exc.details["provider"] == "google"

        exc = SchedulerRateLimitError(retry_after=60)
        assert exc.details["retry_after"] == 60

        exc = SchedulerValidationError("bad field", field="email")
        assert exc.details["field"] == "email"

    def test_base_scheduler_error_status_code_override(self):
        """SchedulerError accepts an explicit status_code override."""
        exc = SchedulerError("custom", status_code=418)
        assert exc.status_code == 418

    def test_base_scheduler_error_default_status_code(self):
        """SchedulerError defaults to 500 if no status_code is provided."""
        exc = SchedulerError("server error")
        assert exc.status_code == 500


# =============================================================================
# Centralized handler tests
# =============================================================================

class TestSchedulerErrorHandler:
    """Test the centralized exception handler response format."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI Request."""
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/scheduler/appointments"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.mark.asyncio
    async def test_response_format_4xx(self, mock_request):
        """4xx errors produce consistent JSON format."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = AppointmentNotFoundError(42)
        response = await scheduler_exception_handler(mock_request, exc)

        assert response.status_code == 404

        import json
        body = json.loads(response.body)

        assert body["success"] is False
        assert "error" in body
        assert body["error"]["code"] == "APPOINTMENT_NOT_FOUND"
        assert body["error"]["status"] == 404
        assert "42" in body["error"]["message"]
        assert "details" in body["error"]

    @pytest.mark.asyncio
    async def test_response_format_409(self, mock_request):
        """Conflict errors produce correct 409 response."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = AppointmentConflictError(conflicting_appointments=[10, 20])
        response = await scheduler_exception_handler(mock_request, exc)

        assert response.status_code == 409

        import json
        body = json.loads(response.body)

        assert body["success"] is False
        assert body["error"]["code"] == "APPOINTMENT_CONFLICT"
        assert body["error"]["details"]["conflicts"] == [10, 20]

    @pytest.mark.asyncio
    async def test_response_format_422(self, mock_request):
        """Validation errors produce correct 422 response with field info."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = SchedulerValidationError("Invalid email format", field="email")
        response = await scheduler_exception_handler(mock_request, exc)

        assert response.status_code == 422

        import json
        body = json.loads(response.body)

        assert body["error"]["code"] == "SCHEDULER_VALIDATION_ERROR"
        assert body["error"]["details"]["field"] == "email"

    @pytest.mark.asyncio
    async def test_rate_limit_retry_after_header(self, mock_request):
        """Rate limit errors include Retry-After header."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = SchedulerRateLimitError(retry_after=30)
        response = await scheduler_exception_handler(mock_request, exc)

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"

    @pytest.mark.asyncio
    async def test_5xx_no_retry_after_header(self, mock_request):
        """Non-rate-limit errors do not include Retry-After header."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = CalendarSyncError("External API failure", provider="google")
        response = await scheduler_exception_handler(mock_request, exc)

        assert response.status_code == 502
        # No Retry-After for non-rate-limit errors
        assert response.headers.get("Retry-After") is None

    @pytest.mark.asyncio
    async def test_public_endpoint_sanitization_in_production(self, mock_request):
        """Public endpoints get sanitized messages in production."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        mock_request.url.path = "/api/scheduler/public/book/my-slug/confirm"

        exc = SchedulerError("Internal database error with user details", status_code=500)

        with patch("middleware.scheduler_error_handler._is_production", return_value=True):
            response = await scheduler_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)

        # In production on public paths, message should be sanitized
        assert "database" not in body["error"]["message"].lower()
        # Details should be empty for public paths in production
        assert body["error"]["details"] == {}

    @pytest.mark.asyncio
    async def test_authenticated_endpoint_preserves_details(self, mock_request):
        """Authenticated endpoints preserve full error details."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        mock_request.url.path = "/api/scheduler/appointments/42"

        exc = SchedulerValidationError("Invalid field: status must be one of [booked, cancelled]", field="status")

        with patch("middleware.scheduler_error_handler._is_production", return_value=True):
            response = await scheduler_exception_handler(mock_request, exc)

        import json
        body = json.loads(response.body)

        # Authenticated endpoints keep the real message
        assert "status" in body["error"]["message"]
        assert body["error"]["details"]["field"] == "status"

    @pytest.mark.asyncio
    async def test_5xx_logged_at_error_level(self, mock_request):
        """5xx errors are logged at ERROR level."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = CalendarSyncError("External API failure")

        with patch("middleware.scheduler_error_handler.logger") as mock_logger:
            await scheduler_exception_handler(mock_request, exc)
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_4xx_logged_at_info_level(self, mock_request):
        """4xx errors are logged at INFO level."""
        from middleware.scheduler_error_handler import scheduler_exception_handler

        exc = AppointmentNotFoundError(42)

        with patch("middleware.scheduler_error_handler.logger") as mock_logger:
            await scheduler_exception_handler(mock_request, exc)
            mock_logger.info.assert_called_once()
            mock_logger.error.assert_not_called()


# =============================================================================
# Handler registration test
# =============================================================================

class TestHandlerRegistration:
    """Test the handler registration function."""

    def test_register_scheduler_error_handlers(self):
        """Handler registration adds SchedulerError handler to FastAPI app."""
        from middleware.scheduler_error_handler import register_scheduler_error_handlers

        mock_app = MagicMock()
        register_scheduler_error_handlers(mock_app)

        mock_app.add_exception_handler.assert_called_once()
        # First arg should be SchedulerError class
        call_args = mock_app.add_exception_handler.call_args
        assert call_args[0][0] is SchedulerError


# =============================================================================
# Public path detection tests
# =============================================================================

class TestPublicPathDetection:
    """Test _is_public_path helper."""

    def test_public_book_path(self):
        from middleware.scheduler_error_handler import _is_public_path
        request = MagicMock()
        request.url.path = "/api/scheduler/public/book/my-slug/confirm"
        assert _is_public_path(request) is True

    def test_authenticated_path(self):
        from middleware.scheduler_error_handler import _is_public_path
        request = MagicMock()
        request.url.path = "/api/scheduler/appointments/42"
        assert _is_public_path(request) is False

    def test_book_in_path(self):
        from middleware.scheduler_error_handler import _is_public_path
        request = MagicMock()
        request.url.path = "/book/my-slug"
        assert _is_public_path(request) is True
