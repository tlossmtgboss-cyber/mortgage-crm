"""
Tests for scheduler utility modules:
  - routes/scheduler/error_responses.py
  - routes/scheduler/constants.py
"""

import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from routes.scheduler.error_responses import (
    scheduler_error,
    validation_error,
    not_found_error,
    conflict_error,
    rate_limit_error,
    internal_error,
    forbidden_error,
    unauthorized_error,
    service_unavailable_error,
    error_json_response,
    _build_error_body,
    _is_production,
    VALIDATION_ERROR,
    NOT_FOUND,
    CONFLICT,
    SLOT_UNAVAILABLE,
    FORBIDDEN,
    UNAUTHORIZED,
    RATE_LIMITED,
    INTERNAL_ERROR,
    SERVICE_UNAVAILABLE,
    INVALID_SECTION,
    IMPORT_ERROR,
    RESET_ERROR,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    MIN_APPOINTMENT_DURATION_MINUTES,
    MAX_APPOINTMENT_DURATION_MINUTES,
    ALLOWED_APPOINTMENT_DURATIONS,
    DEFAULT_BUFFER_BEFORE_MINUTES,
    DEFAULT_BUFFER_AFTER_MINUTES,
    DEFAULT_MIN_NOTICE_HOURS,
    DEFAULT_MAX_ADVANCE_DAYS,
    SLOT_GENERATION_MAX_DAYS,
    PUBLIC_BOOKING_RATE_LIMIT,
    PUBLIC_SLOTS_RATE_LIMIT,
    BOOKING_RATE_LIMIT_PER_EMAIL,
    BOOKING_RATE_LIMIT_PER_IP,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_BULK_OPERATION_SIZE,
    MAX_REMINDERS_PER_APPOINTMENT,
    DEFAULT_HOLD_TTL_SECONDS,
    DEFAULT_ORGANIZER_EMAIL,
    DEFAULT_TIMEZONE,
    CAN_SPAM_PHYSICAL_ADDRESS,
    NMLS_REGULATED_STATES,
    NOTIFICATION_LOOKBACK_HOURS,
    APPOINTMENT_REMINDER_WINDOW_MINUTES,
    NOTIFICATION_RECENCY_HOURS,
    NOTIFICATION_FETCH_LIMIT,
    DEMO_CREATE_RATE_LIMIT,
)


# ============================================================================
# error_responses.py tests
# ============================================================================


class TestErrorBodyShape:
    """Verify the standardized error body always has the required keys."""

    def test_build_error_body_has_required_keys(self):
        body = _build_error_body(error="Something failed", code="TEST_CODE")
        assert "error" in body
        assert "code" in body
        assert "timestamp" in body
        assert body["error"] == "Something failed"
        assert body["code"] == "TEST_CODE"

    def test_build_error_body_timestamp_is_iso_format(self):
        body = _build_error_body(error="msg", code="C")
        # Should parse without error; ISO 8601 with timezone info
        parsed = datetime.fromisoformat(body["timestamp"])
        assert parsed.tzinfo is not None

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", False)
    def test_detail_included_in_non_production(self):
        body = _build_error_body(error="msg", code="C", detail="secret trace")
        assert body.get("detail") == "secret trace"

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", True)
    def test_detail_suppressed_in_production(self):
        body = _build_error_body(error="msg", code="C", detail="secret trace")
        assert "detail" not in body


class TestConvenienceHelpers:
    """Each helper must raise HTTPException with the correct status code and error code."""

    def test_validation_error_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            validation_error("name is required")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == VALIDATION_ERROR
        assert exc_info.value.detail["error"] == "name is required"

    def test_not_found_error_raises_404(self):
        with pytest.raises(HTTPException) as exc_info:
            not_found_error("Appointment not found")
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == NOT_FOUND

    def test_conflict_error_raises_409(self):
        with pytest.raises(HTTPException) as exc_info:
            conflict_error("Time slot already booked")
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == CONFLICT

    def test_rate_limit_error_raises_429(self):
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_error()
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["code"] == RATE_LIMITED
        assert "Too many requests" in exc_info.value.detail["error"]

    def test_internal_error_raises_500(self):
        with pytest.raises(HTTPException) as exc_info:
            internal_error()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == INTERNAL_ERROR

    def test_forbidden_error_raises_403(self):
        with pytest.raises(HTTPException) as exc_info:
            forbidden_error()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == FORBIDDEN

    def test_unauthorized_error_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            unauthorized_error()
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == UNAUTHORIZED

    def test_service_unavailable_error_raises_503(self):
        with pytest.raises(HTTPException) as exc_info:
            service_unavailable_error()
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["code"] == SERVICE_UNAVAILABLE


class TestSchedulerErrorCustomStatus:
    """scheduler_error() should accept any HTTP status code."""

    def test_custom_status_code(self):
        with pytest.raises(HTTPException) as exc_info:
            scheduler_error(418, "TEAPOT", "I'm a teapot")
        assert exc_info.value.status_code == 418
        assert exc_info.value.detail["code"] == "TEAPOT"
        assert exc_info.value.detail["error"] == "I'm a teapot"

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", False)
    def test_custom_status_with_detail_non_prod(self):
        with pytest.raises(HTTPException) as exc_info:
            scheduler_error(422, "UNPROCESSABLE", "Bad data", detail="field X was null")
        assert exc_info.value.detail.get("detail") == "field X was null"

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", True)
    def test_custom_status_detail_hidden_in_prod(self):
        with pytest.raises(HTTPException) as exc_info:
            scheduler_error(422, "UNPROCESSABLE", "Bad data", detail="field X was null")
        assert "detail" not in exc_info.value.detail


class TestErrorJsonResponse:
    """error_json_response returns a JSONResponse rather than raising."""

    def test_returns_json_response(self):
        resp = error_json_response(400, VALIDATION_ERROR, "bad input")
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 400

    def test_response_body_has_expected_shape(self):
        resp = error_json_response(404, NOT_FOUND, "gone")
        assert resp.body is not None
        # JSONResponse serializes body bytes; decode to verify keys
        import json
        body = json.loads(resp.body.decode())
        assert body["code"] == NOT_FOUND
        assert body["error"] == "gone"
        assert "timestamp" in body


class TestPIISanitization:
    """Error helpers should not leak PII from the detail field in production."""

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", True)
    def test_no_pii_leakage_in_production_validation(self):
        with pytest.raises(HTTPException) as exc_info:
            validation_error(
                "Invalid email",
                detail="Borrower john.doe@example.com failed regex"
            )
        body = exc_info.value.detail
        assert "john.doe@example.com" not in str(body)
        assert "detail" not in body

    @patch("routes.scheduler.error_responses._IS_PRODUCTION", True)
    def test_no_pii_leakage_in_production_internal(self):
        with pytest.raises(HTTPException) as exc_info:
            internal_error(
                detail="DB traceback: SSN=123-45-6789 exposed"
            )
        body = exc_info.value.detail
        assert "123-45-6789" not in str(body)
        assert "detail" not in body


class TestErrorCodes:
    """All error code constants should be non-empty strings."""

    @pytest.mark.parametrize("code_value,code_name", [
        (VALIDATION_ERROR, "VALIDATION_ERROR"),
        (NOT_FOUND, "NOT_FOUND"),
        (CONFLICT, "CONFLICT"),
        (SLOT_UNAVAILABLE, "SLOT_UNAVAILABLE"),
        (FORBIDDEN, "FORBIDDEN"),
        (UNAUTHORIZED, "UNAUTHORIZED"),
        (RATE_LIMITED, "RATE_LIMITED"),
        (INTERNAL_ERROR, "INTERNAL_ERROR"),
        (SERVICE_UNAVAILABLE, "SERVICE_UNAVAILABLE"),
        (INVALID_SECTION, "INVALID_SECTION"),
        (IMPORT_ERROR, "IMPORT_ERROR"),
        (RESET_ERROR, "RESET_ERROR"),
    ])
    def test_error_code_is_nonempty_string(self, code_value, code_name):
        assert isinstance(code_value, str), f"{code_name} should be a string"
        assert len(code_value) > 0, f"{code_name} should not be empty"


# ============================================================================
# constants.py tests
# ============================================================================


class TestDurationConstants:
    """Duration-related constants must be positive and sensible."""

    def test_default_duration_is_positive_and_bounded(self):
        assert isinstance(DEFAULT_APPOINTMENT_DURATION_MINUTES, int)
        assert DEFAULT_APPOINTMENT_DURATION_MINUTES > 0
        assert DEFAULT_APPOINTMENT_DURATION_MINUTES < 480

    def test_min_duration_less_than_max(self):
        assert MIN_APPOINTMENT_DURATION_MINUTES < MAX_APPOINTMENT_DURATION_MINUTES

    def test_default_within_min_max_range(self):
        assert MIN_APPOINTMENT_DURATION_MINUTES <= DEFAULT_APPOINTMENT_DURATION_MINUTES <= MAX_APPOINTMENT_DURATION_MINUTES

    def test_allowed_durations_is_sorted_list_of_positive_ints(self):
        assert isinstance(ALLOWED_APPOINTMENT_DURATIONS, list)
        assert len(ALLOWED_APPOINTMENT_DURATIONS) > 0
        assert all(isinstance(d, int) and d > 0 for d in ALLOWED_APPOINTMENT_DURATIONS)
        assert ALLOWED_APPOINTMENT_DURATIONS == sorted(ALLOWED_APPOINTMENT_DURATIONS)

    def test_default_duration_in_allowed_list(self):
        assert DEFAULT_APPOINTMENT_DURATION_MINUTES in ALLOWED_APPOINTMENT_DURATIONS


class TestBufferAndTimingConstants:
    """Buffer and timing window constants must be non-negative."""

    def test_buffer_minutes_are_non_negative(self):
        assert DEFAULT_BUFFER_BEFORE_MINUTES >= 0
        assert DEFAULT_BUFFER_AFTER_MINUTES >= 0

    def test_notice_and_advance_days_positive(self):
        assert DEFAULT_MIN_NOTICE_HOURS > 0
        assert DEFAULT_MAX_ADVANCE_DAYS > 0
        assert SLOT_GENERATION_MAX_DAYS > 0

    def test_notification_windows_positive(self):
        assert NOTIFICATION_LOOKBACK_HOURS > 0
        assert APPOINTMENT_REMINDER_WINDOW_MINUTES > 0
        assert NOTIFICATION_RECENCY_HOURS > 0


class TestRateLimitConstants:
    """Rate limit constants must be positive integers."""

    @pytest.mark.parametrize("value,name", [
        (PUBLIC_BOOKING_RATE_LIMIT, "PUBLIC_BOOKING_RATE_LIMIT"),
        (PUBLIC_SLOTS_RATE_LIMIT, "PUBLIC_SLOTS_RATE_LIMIT"),
        (BOOKING_RATE_LIMIT_PER_EMAIL, "BOOKING_RATE_LIMIT_PER_EMAIL"),
        (BOOKING_RATE_LIMIT_PER_IP, "BOOKING_RATE_LIMIT_PER_IP"),
        (DEMO_CREATE_RATE_LIMIT, "DEMO_CREATE_RATE_LIMIT"),
    ])
    def test_rate_limit_is_positive_int(self, value, name):
        assert isinstance(value, int), f"{name} should be int"
        assert value > 0, f"{name} should be positive"


class TestPaginationConstants:
    """Pagination constants must form a valid range."""

    def test_default_page_size_within_max(self):
        assert 0 < DEFAULT_PAGE_SIZE <= MAX_PAGE_SIZE

    def test_max_page_size_positive(self):
        assert MAX_PAGE_SIZE > 0

    def test_bulk_operation_size_positive(self):
        assert MAX_BULK_OPERATION_SIZE > 0

    def test_notification_fetch_limit_positive(self):
        assert NOTIFICATION_FETCH_LIMIT > 0


class TestMiscConstants:
    """Other scheduler constants."""

    def test_max_reminders_positive(self):
        assert MAX_REMINDERS_PER_APPOINTMENT > 0

    def test_hold_ttl_positive(self):
        assert DEFAULT_HOLD_TTL_SECONDS > 0

    def test_organizer_email_is_string(self):
        assert isinstance(DEFAULT_ORGANIZER_EMAIL, str)
        assert "@" in DEFAULT_ORGANIZER_EMAIL

    def test_default_timezone_is_string(self):
        assert isinstance(DEFAULT_TIMEZONE, str)
        assert len(DEFAULT_TIMEZONE) > 0

    def test_can_spam_address_is_nonempty_string(self):
        assert isinstance(CAN_SPAM_PHYSICAL_ADDRESS, str)
        assert len(CAN_SPAM_PHYSICAL_ADDRESS) > 0

    def test_nmls_regulated_states_is_set_of_two_letter_codes(self):
        assert isinstance(NMLS_REGULATED_STATES, set)
        assert len(NMLS_REGULATED_STATES) > 0
        for code in NMLS_REGULATED_STATES:
            assert isinstance(code, str)
            assert len(code) == 2
            assert code == code.upper()

    def test_nmls_includes_major_states(self):
        for state in ("CA", "TX", "NY", "FL", "IL"):
            assert state in NMLS_REGULATED_STATES
