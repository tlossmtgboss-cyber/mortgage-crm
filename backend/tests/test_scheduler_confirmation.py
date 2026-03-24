"""
Tests for scheduler confirmation endpoints.

Covers:
  - GET  /public/confirmation/{appointment_id}        View appointment details via token
  - GET  /public/confirmation/{appointment_id}/ics     Download ICS calendar file
  - POST /public/confirm/{appointment_id}/cancel       Cancel from confirmation link
  - POST /public/confirm/{appointment_id}/reschedule   Reschedule from confirmation link
  - Token validation: expired token, invalid token, wrong appointment
  - Cancel edge cases: already cancelled, past appointment, wrong email
  - Reschedule edge cases: conflict, past time, same time
  - Rate limiting on public endpoints
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Module under test + patch target prefix
# ---------------------------------------------------------------------------

_MOD = "routes.scheduler.confirmation"


# ---------------------------------------------------------------------------
# Helpers & Mocks
# ---------------------------------------------------------------------------

# A fixed test secret key for generating/verifying tokens
TEST_SECRET_KEY = "test-secret-key-for-confirmation-tests"


def _make_token(appointment_id: int, email: str = "borrower@test.com",
                expired: bool = False, wrong_appt_id: int = None,
                purpose: str = "confirmation"):
    """Generate a real JWT token for tests using the test secret key."""
    import jwt as pyjwt
    exp = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=48))
    payload = {
        "appt_id": wrong_appt_id if wrong_appt_id is not None else appointment_id,
        "email": email,
        "purpose": purpose,
        "exp": exp,
    }
    return pyjwt.encode(payload, TEST_SECRET_KEY, algorithm="HS256")


class MockAppointment:
    """Mock appointment ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.organization_id = kwargs.get("organization_id", 1)
        self.title = kwargs.get("title", "Mortgage Consultation")
        self.description = kwargs.get("description", "Discuss refinance options")
        self.status = kwargs.get("status", "booked")
        self.meeting_type = kwargs.get("meeting_type", None)
        self.meeting_mode = kwargs.get("meeting_mode", None)
        self.appointment_type_id = kwargs.get("appointment_type_id", None)
        self.scheduled_start = kwargs.get(
            "scheduled_start",
            datetime(2026, 4, 10, 14, 0),  # future date
        )
        self.scheduled_end = kwargs.get(
            "scheduled_end",
            datetime(2026, 4, 10, 14, 30),
        )
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.timezone = kwargs.get("timezone", "America/New_York")
        self.location = kwargs.get("location", None)
        self.video_link = kwargs.get("video_link", "https://meet.example.com/abc")
        self.phone_number = kwargs.get("phone_number", None)
        self.attendee_name = kwargs.get("attendee_name", "Jane Borrower")
        self.attendee_email = kwargs.get("attendee_email", "borrower@test.com")
        self.assigned_user_id = kwargs.get("assigned_user_id", 10)
        self.cancelled_at = kwargs.get("cancelled_at", None)
        self.cancellation_reason = kwargs.get("cancellation_reason", None)
        self.status_changed_at = kwargs.get("status_changed_at", None)
        self.updated_at = kwargs.get("updated_at", None)
        self.reschedule_count = kwargs.get("reschedule_count", 0)


def _mock_db_with_appointment(appointment):
    """Create a MagicMock db session that returns the given appointment on query."""
    db = MagicMock()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.first.return_value = appointment
    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock
    return db


def _mock_request():
    """Create a minimal mock Request object."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.url = MagicMock()
    req.url.path = "/public/confirmation/100"
    return req


# ---------------------------------------------------------------------------
# GET /public/confirmation/{appointment_id} - View confirmation details
# ---------------------------------------------------------------------------

class TestGetConfirmationDetails:
    """Tests for GET /public/confirmation/{appointment_id}."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_appointment_details(self):
        """Valid token returns full appointment confirmation page data."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock(), "AppointmentType": MagicMock()}), \
             patch(f"{_MOD}.generate_reschedule_url", return_value="https://app.perenniaai.com/reschedule/tok"), \
             patch(f"{_MOD}.generate_ics_content", return_value="BEGIN:VCALENDAR..."):
            # Patch the User query to avoid importing real DB models
            with patch(f"database.models.core.User", create=True):
                result = await get_confirmation_details(request, 100, token=token, db=db)

        assert "appointment" in result
        assert result["appointment"]["id"] == 100
        assert result["appointment"]["title"] == "Mortgage Consultation"
        assert result["appointment"]["attendee_name"] == "Jane Borrower"
        assert "calendar_links" in result
        assert "preparation" in result
        assert "actions" in result

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self):
        """Expired JWT token is rejected with 401."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100, expired=True)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """A garbled or malformed token is rejected with 401."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token="not.a.valid.token", db=db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_appointment_id_in_token_returns_403(self):
        """Token minted for appointment 999 should not access appointment 100."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment(id=100)
        db = _mock_db_with_appointment(appt)
        # Token was generated for appointment 999
        token = _make_token(100, wrong_appt_id=999)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_email_in_token_returns_403(self):
        """Token email must match appointment attendee_email (SEC-001)."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment(attendee_email="real@borrower.com")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100, email="attacker@evil.com")
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_appointment_not_found_returns_404(self):
        """Non-existent appointment returns 404."""
        from routes.scheduler.confirmation import get_confirmation_details

        db = _mock_db_with_appointment(None)  # no appointment found
        token = _make_token(999)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 999, token=token, db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancelled_appointment_returns_410(self):
        """Token for a cancelled appointment is implicitly revoked (410 Gone)."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment(status="cancelled")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 410


# ---------------------------------------------------------------------------
# POST /public/confirm/{appointment_id}/cancel
# ---------------------------------------------------------------------------

class TestPublicCancelAppointment:
    """Tests for POST /public/confirm/{appointment_id}/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_happy_path(self):
        """Valid cancel request marks appointment as cancelled."""
        from routes.scheduler.confirmation import public_cancel_appointment, ConfirmationCancelRequest

        appt = MockAppointment(status="booked")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()
        body = ConfirmationCancelRequest(reason="Schedule conflict")

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock(), "AppointmentStatusHistory": None}), \
             patch(f"{_MOD}._audit_log"), \
             patch(f"{_MOD}._convert_utc_to_user_tz", return_value=datetime(2026, 4, 10, 10, 0)), \
             patch(f"{_MOD}._sanitize_text", side_effect=lambda x: x):
            # Patch the email sender and User import
            with patch(f"database.models.core.User", create=True):
                result = await public_cancel_appointment(request, 100, body=body, token=token, db=db)

        assert result["status"] == "ok"
        assert result["appointment_id"] == 100
        assert "cancelled_at" in result
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_returns_410(self):
        """Cancelling an already-cancelled appointment returns 410 (token revoked)."""
        from routes.scheduler.confirmation import public_cancel_appointment, ConfirmationCancelRequest

        appt = MockAppointment(status="cancelled")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_cancel_appointment(request, 100, body=None, token=token, db=db)
            assert exc_info.value.status_code == 410

    @pytest.mark.asyncio
    async def test_cancel_past_appointment_returns_409(self):
        """Cannot cancel an appointment that has already started."""
        from routes.scheduler.confirmation import public_cancel_appointment, ConfirmationCancelRequest

        past_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        appt = MockAppointment(
            status="booked",
            scheduled_start=past_start,
            scheduled_end=past_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_cancel_appointment(request, 100, body=None, token=token, db=db)
            assert exc_info.value.status_code == 409
            assert "already started" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_cancel_wrong_email_returns_403(self):
        """Token email mismatch blocks cancellation (SEC-001)."""
        from routes.scheduler.confirmation import public_cancel_appointment

        appt = MockAppointment(status="booked", attendee_email="real@borrower.com")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100, email="hacker@evil.com")
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_cancel_appointment(request, 100, body=None, token=token, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cancel_non_actionable_status_returns_409(self):
        """Completed or no-show appointments cannot be cancelled."""
        from routes.scheduler.confirmation import public_cancel_appointment

        appt = MockAppointment(status="completed")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_cancel_appointment(request, 100, body=None, token=token, db=db)
            assert exc_info.value.status_code == 409
            assert "completed" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# POST /public/confirm/{appointment_id}/reschedule
# ---------------------------------------------------------------------------

class TestPublicRescheduleAppointment:
    """Tests for POST /public/confirm/{appointment_id}/reschedule."""

    @pytest.mark.asyncio
    async def test_reschedule_happy_path(self):
        """Valid reschedule moves appointment to new time."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        future_start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
        appt = MockAppointment(
            status="booked",
            scheduled_start=future_start,
            scheduled_end=future_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        new_time = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        body = ConfirmationRescheduleRequest(
            slot_time=new_time.isoformat(),
            reason="Need a different day",
        )

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock(), "AppointmentStatusHistory": None}), \
             patch(f"{_MOD}._audit_log"), \
             patch(f"{_MOD}._sanitize_text", side_effect=lambda x: x), \
             patch(f"{_MOD}._check_appointment_conflict", new_callable=AsyncMock):
            result = await public_reschedule_appointment(request, 100, body=body, token=token, db=db)

        assert result["status"] == "ok"
        assert result["message"] == "Appointment rescheduled successfully"
        assert result["appointment_id"] == 100
        assert result["duration_minutes"] == 30
        assert result["reschedule_count"] == 1
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reschedule_past_time_returns_400(self):
        """Cannot reschedule to a past time."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        future_start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
        appt = MockAppointment(
            status="booked",
            scheduled_start=future_start,
            scheduled_end=future_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0)
        body = ConfirmationRescheduleRequest(slot_time=past_time.isoformat())

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}), \
             patch(f"{_MOD}._sanitize_text", side_effect=lambda x: x):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 400
            assert "past" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reschedule_same_time_returns_400(self):
        """Rescheduling to the exact same time is a no-op and returns 400."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        # The scheduled_start is stored as naive UTC in the DB
        fixed_start = datetime(2026, 5, 1, 14, 0, 0)
        appt = MockAppointment(
            status="booked",
            scheduled_start=fixed_start,
            scheduled_end=fixed_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        # Provide the same time in UTC-aware ISO format
        body = ConfirmationRescheduleRequest(
            slot_time=fixed_start.replace(tzinfo=timezone.utc).isoformat(),
        )

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}), \
             patch(f"{_MOD}._sanitize_text", side_effect=lambda x: x):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 400
            assert "same" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reschedule_conflict_returns_409(self):
        """Conflict with an existing appointment returns 409."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        future_start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
        appt = MockAppointment(
            status="booked",
            scheduled_start=future_start,
            scheduled_end=future_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        new_time = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        body = ConfirmationRescheduleRequest(slot_time=new_time.isoformat())

        # _check_appointment_conflict raises 409 when conflict found
        conflict_error = HTTPException(status_code=409, detail="Time slot conflicts with existing appointment")

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}), \
             patch(f"{_MOD}._sanitize_text", side_effect=lambda x: x), \
             patch(f"{_MOD}._check_appointment_conflict", new_callable=AsyncMock, side_effect=conflict_error):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 409
            assert "conflict" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reschedule_invalid_datetime_format_returns_400(self):
        """Malformed slot_time returns 400."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        future_start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5)
        appt = MockAppointment(
            status="booked",
            scheduled_start=future_start,
            scheduled_end=future_start + timedelta(minutes=30),
        )
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        body = ConfirmationRescheduleRequest(slot_time="not-a-date")

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 400
            assert "datetime" in exc_info.value.detail.lower() or "iso" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reschedule_already_cancelled_returns_410(self):
        """Rescheduling a cancelled appointment returns 410 (token revoked)."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        appt = MockAppointment(status="cancelled")
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        new_time = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        body = ConfirmationRescheduleRequest(slot_time=new_time.isoformat())

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 410


# ---------------------------------------------------------------------------
# GET /public/confirmation/{appointment_id}/ics - ICS download
# ---------------------------------------------------------------------------

class TestDownloadIcsFile:
    """Tests for GET /public/confirmation/{appointment_id}/ics."""

    @pytest.mark.asyncio
    async def test_ics_download_happy_path(self):
        """Valid token returns ICS content with correct headers."""
        from routes.scheduler.confirmation import download_ics_file

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}), \
             patch(f"{_MOD}.generate_ics_content", return_value="BEGIN:VCALENDAR\nEND:VCALENDAR"):
            with patch(f"database.models.core.User", create=True):
                response = await download_ics_file(request, 100, token=token, db=db)

        assert response.body == b"BEGIN:VCALENDAR\nEND:VCALENDAR"
        assert response.media_type == "text/calendar"
        assert "appointment-100.ics" in response.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_ics_download_expired_token_returns_401(self):
        """Expired token on ICS download returns 401."""
        from routes.scheduler.confirmation import download_ics_file

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100, expired=True)
        request = _mock_request()

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await download_ics_file(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting on public endpoints
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Tests for rate limiting on public confirmation endpoints."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforced_on_get_confirmation(self):
        """Rate limiter is called with max_requests=30 for GET confirmation."""
        from routes.scheduler.confirmation import get_confirmation_details

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        rate_limit_mock = AsyncMock(
            side_effect=HTTPException(status_code=429, detail="Too many requests")
        )

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", rate_limit_mock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await get_confirmation_details(request, 100, token=token, db=db)
            assert exc_info.value.status_code == 429

        rate_limit_mock.assert_called_once_with(request, max_requests=30)

    @pytest.mark.asyncio
    async def test_rate_limit_enforced_on_cancel(self):
        """Rate limiter is called with max_requests=10 for cancel endpoint."""
        from routes.scheduler.confirmation import public_cancel_appointment

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        rate_limit_mock = AsyncMock(
            side_effect=HTTPException(status_code=429, detail="Too many requests")
        )

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", rate_limit_mock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_cancel_appointment(request, 100, body=None, token=token, db=db)
            assert exc_info.value.status_code == 429

        rate_limit_mock.assert_called_once_with(request, max_requests=10)

    @pytest.mark.asyncio
    async def test_rate_limit_enforced_on_reschedule(self):
        """Rate limiter is called with max_requests=10 for reschedule endpoint."""
        from routes.scheduler.confirmation import public_reschedule_appointment, ConfirmationRescheduleRequest

        appt = MockAppointment()
        db = _mock_db_with_appointment(appt)
        token = _make_token(100)
        request = _mock_request()

        new_time = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        body = ConfirmationRescheduleRequest(slot_time=new_time.isoformat())

        rate_limit_mock = AsyncMock(
            side_effect=HTTPException(status_code=429, detail="Too many requests")
        )

        with patch(f"{_MOD}.SECRET_KEY", TEST_SECRET_KEY), \
             patch(f"{_MOD}._check_rate_limit", rate_limit_mock), \
             patch(f"{_MOD}.get_models", return_value={"Appointment": MagicMock()}):
            with pytest.raises(HTTPException) as exc_info:
                await public_reschedule_appointment(request, 100, body=body, token=token, db=db)
            assert exc_info.value.status_code == 429

        rate_limit_mock.assert_called_once_with(request, max_requests=10)


# ---------------------------------------------------------------------------
# Helper / utility function tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_mask_email_public(self):
        """Email masking shows only first 2 chars of local part."""
        from routes.scheduler.confirmation import _mask_email_public

        assert _mask_email_public("timothy@example.com") == "ti***@example.com"
        assert _mask_email_public("ab@example.com") == "ab***@example.com"
        assert _mask_email_public("x@example.com") == "x***@example.com"
        assert _mask_email_public(None) is None
        assert _mask_email_public("") is None
        assert _mask_email_public("no-at-sign") is None

    def test_mask_phone_public(self):
        """Phone masking shows only last 4 digits."""
        from routes.scheduler.confirmation import _mask_phone_public

        assert _mask_phone_public("+1 (555) 123-4567") == "***-***-4567"
        assert _mask_phone_public("5551234567") == "***-***-4567"
        assert _mask_phone_public(None) is None
        assert _mask_phone_public("123") is None  # too short

    def test_sanitize_ics_description_strips_html(self):
        """ICS description sanitizer strips HTML tags."""
        from routes.scheduler.confirmation import _sanitize_ics_description

        assert _sanitize_ics_description("<b>Bold</b> text") == "Bold text"
        assert _sanitize_ics_description('<script>alert("xss")</script>') == 'alert("xss")'
        assert _sanitize_ics_description("") == ""
        assert _sanitize_ics_description(None) == ""

    def test_sanitize_ics_description_truncates_long_content(self):
        """ICS description is truncated to max length."""
        from routes.scheduler.confirmation import _sanitize_ics_description, _ICS_DESCRIPTION_MAX_LENGTH

        long_text = "A" * (_ICS_DESCRIPTION_MAX_LENGTH + 500)
        result = _sanitize_ics_description(long_text)
        assert len(result) == _ICS_DESCRIPTION_MAX_LENGTH + 3  # +3 for "..."
        assert result.endswith("...")
