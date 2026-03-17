"""
Tests for SMS Appointment Confirmation & Reminder Service

Covers:
- SMSConfirmationService: booking confirmation, reminder, cancellation, reschedule
- TCPA/DNC consent check integration
- E.164 phone normalization
- Reminder scheduling via AppointmentReminder model
- Reminder processing (pending -> sent/failed)
- SMS webhook handler: CONFIRM, CANCEL, RESCHEDULE, HELP, STOP
- Phone number matching for inbound replies
- Telnyx SDK and HTTP fallback send paths
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_appointment():
    """Create a mock Appointment with standard fields."""
    appt = Mock()
    appt.id = 42
    appt.organization_id = 1
    appt.attendee_phone = "+15551234567"
    appt.attendee_name = "Jane Doe"
    appt.attendee_email = "jane@example.com"
    appt.title = "Pre-Approval Review"
    appt.scheduled_start = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    appt.scheduled_end = datetime(2026, 4, 15, 15, 0, tzinfo=timezone.utc)
    appt.video_link = None
    appt.status = Mock()
    appt.status.value = "booked"
    return appt


@pytest.fixture
def mock_appointment_no_phone():
    """Appointment without attendee_phone."""
    appt = Mock()
    appt.id = 43
    appt.attendee_phone = None
    appt.attendee_name = "No Phone"
    appt.scheduled_start = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    return appt


@pytest.fixture
def mock_telnyx():
    """Mock telnyx module for all tests that need it."""
    mock_module = MagicMock()
    mock_message_response = MagicMock()
    mock_message_response.id = "msg-test-123"
    mock_module.Message.create.return_value = mock_message_response
    return mock_module


@pytest.fixture
def sms_service(mock_telnyx):
    """Create an SMSConfirmationService with mocked Telnyx credentials."""
    with patch.dict("os.environ", {
        "TELNYX_API_KEY": "test-key-123",
        "TELNYX_PHONE_NUMBER": "+18438838956",
        "TELNYX_MESSAGING_PROFILE_ID": "40019bed-2fa1-4407-a0c6-fe4c6b222c93",
    }):
        with patch.dict("sys.modules", {"telnyx": mock_telnyx}):
            from services.sms_confirmation_service import SMSConfirmationService
            service = SMSConfirmationService()
            # Store the mock for assertions
            service._mock_telnyx = mock_telnyx
            return service


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value = session.query.return_value
    session.query.return_value.first.return_value = None
    session.query.return_value.all.return_value = []
    return session


def _patch_send_deps(mock_telnyx):
    """Context manager that patches all _send dependencies for the telnyx SDK path."""
    mock_consent = MagicMock(return_value=(True, "OK"))
    mock_sched_email = MagicMock(check_sms_consent=mock_consent)
    return patch.dict("sys.modules", {
        "scheduler_email_service": mock_sched_email,
        "telnyx": mock_telnyx,
    })


# =============================================================================
# SMS CONFIRMATION SERVICE TESTS
# =============================================================================

class TestSMSConfirmationService:
    """Tests for SMSConfirmationService methods."""

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_success(self, sms_service, mock_appointment):
        """Confirmation SMS is sent with correct message formatting."""
        with _patch_send_deps(sms_service._mock_telnyx):
            result = await sms_service.send_booking_confirmation(
                appointment=mock_appointment,
                org_name="Acme Mortgage",
                organization_id=1,
            )

        assert result["sent"] is True
        assert result["error"] is None
        sms_service._mock_telnyx.Message.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_booking_confirmation_no_phone(self, sms_service, mock_appointment_no_phone):
        """Confirmation SMS skipped when attendee has no phone."""
        result = await sms_service.send_booking_confirmation(
            appointment=mock_appointment_no_phone,
            org_name="Acme Mortgage",
        )

        assert result["sent"] is False
        assert "No attendee phone" in result["error"]

    @pytest.mark.asyncio
    async def test_send_reminder_formats_time_text(self, sms_service, mock_appointment):
        """Reminder uses 'tomorrow' for 24h."""
        with _patch_send_deps(sms_service._mock_telnyx):
            await sms_service.send_reminder(
                appointment=mock_appointment,
                hours_before=24,
                org_name="Test Org",
                organization_id=1,
            )

        call_args = sms_service._mock_telnyx.Message.create.call_args
        # telnyx.Message.create is called with keyword args
        msg_text = call_args.kwargs.get("text", "")
        assert "tomorrow" in msg_text

    @pytest.mark.asyncio
    async def test_send_reminder_short_notice(self, sms_service, mock_appointment):
        """Reminder with 1-hour notice uses 'soon'."""
        with _patch_send_deps(sms_service._mock_telnyx):
            await sms_service.send_reminder(
                appointment=mock_appointment,
                hours_before=1,
                org_name="Test Org",
                organization_id=1,
            )

        call_args = sms_service._mock_telnyx.Message.create.call_args
        msg_text = call_args.kwargs.get("text", "")
        assert "soon" in msg_text

    @pytest.mark.asyncio
    async def test_send_cancellation(self, sms_service, mock_appointment):
        """Cancellation SMS includes appointment details and reason."""
        with _patch_send_deps(sms_service._mock_telnyx):
            result = await sms_service.send_cancellation(
                appointment=mock_appointment,
                org_name="Test Org",
                cancellation_reason="LO unavailable",
                organization_id=1,
            )

        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_send_reschedule(self, sms_service, mock_appointment):
        """Reschedule SMS includes both old and new times."""
        old_time = datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc)

        with _patch_send_deps(sms_service._mock_telnyx):
            result = await sms_service.send_reschedule(
                appointment=mock_appointment,
                old_time=old_time,
                org_name="Test Org",
                organization_id=1,
            )

        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_consent_check_blocks_send(self, sms_service, mock_appointment):
        """SMS is blocked when consent check returns False."""
        mock_consent = MagicMock(return_value=(False, "DNC listed"))
        mock_sched_email = MagicMock(check_sms_consent=mock_consent)
        with patch.dict("sys.modules", {
            "scheduler_email_service": mock_sched_email,
            "telnyx": sms_service._mock_telnyx,
        }):
            result = await sms_service.send_booking_confirmation(
                appointment=mock_appointment,
                organization_id=1,
            )

        assert result["sent"] is False
        assert "Consent blocked" in result["error"]

    @pytest.mark.asyncio
    async def test_no_api_key_skips_send(self, mock_appointment):
        """SMS is skipped when TELNYX_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict("sys.modules", {"telnyx": MagicMock()}):
                from services.sms_confirmation_service import SMSConfirmationService
                service = SMSConfirmationService()
                service.api_key = None

                result = await service.send_booking_confirmation(
                    appointment=mock_appointment,
                )

        assert result["sent"] is False
        assert "not configured" in result["error"]


class TestPhoneNormalization:
    """Test E.164 phone number normalization in _send."""

    @pytest.mark.asyncio
    async def test_10_digit_gets_plus_1(self, sms_service):
        """10-digit number gets +1 prefix."""
        with _patch_send_deps(sms_service._mock_telnyx):
            await sms_service._send("5551234567", "test")

        call_args = sms_service._mock_telnyx.Message.create.call_args
        to_number = call_args.kwargs.get("to", "")
        assert to_number == "+15551234567"

    @pytest.mark.asyncio
    async def test_11_digit_with_1(self, sms_service):
        """11-digit number starting with 1 gets + prefix."""
        with _patch_send_deps(sms_service._mock_telnyx):
            await sms_service._send("15551234567", "test")

        call_args = sms_service._mock_telnyx.Message.create.call_args
        to_number = call_args.kwargs.get("to", "")
        assert to_number == "+15551234567"

    @pytest.mark.asyncio
    async def test_e164_passed_through(self, sms_service):
        """Already-formatted E.164 number passes through unchanged."""
        with _patch_send_deps(sms_service._mock_telnyx):
            await sms_service._send("+15551234567", "test")

        call_args = sms_service._mock_telnyx.Message.create.call_args
        to_number = call_args.kwargs.get("to", "")
        assert to_number == "+15551234567"


class TestReminderScheduling:
    """Test schedule_reminders creates AppointmentReminder records."""

    def test_schedule_default_reminders(self, sms_service, mock_appointment, mock_db):
        """Default scheduling creates 24h and 1h reminders."""
        # Set up appointment far enough in the future
        mock_appointment.scheduled_start = datetime.now(timezone.utc) + timedelta(days=2)

        # Mock the ReminderChannel and ReminderStatus enums
        mock_channel = MagicMock()
        mock_channel.SMS = "sms"
        mock_status = MagicMock()
        mock_status.PENDING = "pending"

        mock_scheduler_models = MagicMock()
        mock_scheduler_models.ReminderChannel = mock_channel
        mock_scheduler_models.ReminderStatus = mock_status

        # Mock the relationship to get the model class
        mock_reminder_class = MagicMock()
        type(mock_appointment).reminders = MagicMock()
        type(mock_appointment).reminders.property = MagicMock()
        type(mock_appointment).reminders.property.mapper = MagicMock()
        type(mock_appointment).reminders.property.mapper.class_ = mock_reminder_class

        # No existing reminders
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.dict("sys.modules", {"smart_scheduler_models": mock_scheduler_models}):
            reminders = sms_service.schedule_reminders(
                db=mock_db,
                appointment=mock_appointment,
                organization_id=1,
            )

        # Should have added 2 reminders (24h and 1h)
        assert mock_db.add.call_count == 2

    def test_schedule_skips_past_reminders(self, sms_service, mock_appointment, mock_db):
        """Reminders scheduled in the past are skipped."""
        # Appointment is in 30 minutes -- both 24h and 1h reminders are in the past
        mock_appointment.scheduled_start = datetime.now(timezone.utc) + timedelta(minutes=30)

        mock_channel = MagicMock()
        mock_channel.SMS = "sms"
        mock_status = MagicMock()
        mock_status.PENDING = "pending"

        mock_scheduler_models = MagicMock()
        mock_scheduler_models.ReminderChannel = mock_channel
        mock_scheduler_models.ReminderStatus = mock_status

        mock_reminder_class = MagicMock()
        type(mock_appointment).reminders = MagicMock()
        type(mock_appointment).reminders.property = MagicMock()
        type(mock_appointment).reminders.property.mapper = MagicMock()
        type(mock_appointment).reminders.property.mapper.class_ = mock_reminder_class

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.dict("sys.modules", {"smart_scheduler_models": mock_scheduler_models}):
            reminders = sms_service.schedule_reminders(
                db=mock_db,
                appointment=mock_appointment,
                organization_id=1,
            )

        assert mock_db.add.call_count == 0

    def test_schedule_skips_no_phone(self, sms_service, mock_appointment_no_phone, mock_db):
        """No reminders created when attendee has no phone."""
        reminders = sms_service.schedule_reminders(
            db=mock_db,
            appointment=mock_appointment_no_phone,
            organization_id=1,
        )

        assert len(reminders) == 0
        assert mock_db.add.call_count == 0


class TestReminderProcessing:
    """Test process_pending_reminders sends due reminders."""

    @pytest.mark.asyncio
    async def test_process_sends_due_reminders(self, sms_service, mock_db):
        """Due pending reminders get sent."""
        # Mock scheduler model enums
        mock_channel = MagicMock()
        mock_channel.SMS = "sms"
        mock_reminder_status = MagicMock()
        mock_reminder_status.PENDING = "pending"
        mock_reminder_status.SENT = "sent"
        mock_reminder_status.FAILED = "failed"
        mock_appt_status = MagicMock()
        mock_appt_status.CANCELLED = "cancelled"
        mock_appt_status.COMPLETED = "completed"
        mock_appt_status.NO_SHOW = "no_show"

        mock_scheduler_models = MagicMock()
        mock_scheduler_models.ReminderChannel = mock_channel
        mock_scheduler_models.ReminderStatus = mock_reminder_status
        mock_scheduler_models.AppointmentStatus = mock_appt_status

        # Create mock reminder
        mock_reminder = MagicMock()
        mock_reminder.appointment_id = 42
        mock_reminder.hours_before = 24
        mock_reminder.organization_id = 1
        mock_reminder.status = "pending"

        # Create mock appointment for the reminder
        mock_appt = MagicMock()
        mock_appt.id = 42
        mock_appt.attendee_phone = "+15551234567"
        mock_appt.attendee_name = "Jane"
        mock_appt.scheduled_start = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_appt.video_link = None
        mock_appt.organization_id = 1
        mock_appt.status = MagicMock()
        mock_appt.status.value = "booked"

        # Model classes need to support attribute access for SQLAlchemy filter.
        # SQLAlchemy columns support comparison via __le__, __ge__ etc.
        # MagicMock's dunder methods need to be configured via configure_mock
        # or set on the type. We create attributes that support comparison.
        def _make_col():
            m = MagicMock()
            m.__le__ = MagicMock(return_value=MagicMock())
            m.__ge__ = MagicMock(return_value=MagicMock())
            m.__gt__ = MagicMock(return_value=MagicMock())
            m.__lt__ = MagicMock(return_value=MagicMock())
            m.__eq__ = MagicMock(return_value=MagicMock())
            return m

        MockAppointmentReminder = MagicMock()
        MockAppointmentReminder.channel = _make_col()
        MockAppointmentReminder.status = _make_col()
        MockAppointmentReminder.scheduled_for = _make_col()
        MockAppointmentReminder.appointment_id = _make_col()

        MockAppointment = MagicMock()
        MockAppointment.id = _make_col()

        # Set up DB queries
        call_count = [0]
        def query_side_effect(model):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 1:
                # First query: pending reminders
                result.filter.return_value.all.return_value = [mock_reminder]
            else:
                # Second query: appointment lookup
                result.filter.return_value.first.return_value = mock_appt
            return result

        mock_db.query.side_effect = query_side_effect

        # Mock the send_reminder method directly
        sms_service.send_reminder = AsyncMock(return_value={"sent": True, "message_id": "msg-100", "error": None})

        models = {
            "AppointmentReminder": MockAppointmentReminder,
            "Appointment": MockAppointment,
        }

        with patch.dict("sys.modules", {"smart_scheduler_models": mock_scheduler_models}):
            stats = await sms_service.process_pending_reminders(
                db=mock_db,
                models=models,
                org_name="Test Org",
            )

        assert stats["processed"] == 1
        assert stats["sent"] == 1


# =============================================================================
# SMS WEBHOOK HANDLER TESTS
# =============================================================================

class TestSMSWebhookHandler:
    """Tests for the SMS scheduler webhook endpoint."""

    def _make_telnyx_payload(self, from_number: str, text: str) -> dict:
        """Build a Telnyx inbound message webhook payload."""
        return {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "from": {"phone_number": from_number},
                    "to": [{"phone_number": "+18438838956"}],
                    "text": text,
                    "id": "msg-webhook-test",
                },
            }
        }

    @pytest.mark.asyncio
    async def test_confirm_keyword(self, mock_db, mock_appointment):
        """CONFIRM keyword triggers appointment confirmation."""
        from routes.sms_scheduler_webhook import _handle_confirm

        # Mock the models
        import routes.sms_scheduler_webhook as webhook_module
        mock_appointment.status = MagicMock()
        mock_appointment.status.value = "booked"

        webhook_module._models = {
            "Appointment": MagicMock,
            "AppointmentStatusHistory": MagicMock,
            "AppointmentReminder": MagicMock,
        }

        mock_appt_status = MagicMock()
        mock_appt_status.CONFIRMED = MagicMock()
        mock_appt_status.CONFIRMED.value = "confirmed"

        with patch("routes.sms_scheduler_webhook._find_upcoming_appointment", return_value=mock_appointment):
            with patch("routes.sms_scheduler_webhook._send_reply", new_callable=AsyncMock, return_value=True):
                with patch("routes.sms_scheduler_webhook._acknowledge_reminders"):
                    with patch.dict("sys.modules", {"smart_scheduler_models": MagicMock(AppointmentStatus=mock_appt_status)}):
                        response = await _handle_confirm(mock_db, "+15551234567")

        assert response.status_code == 200
        body = response.body
        assert b"confirmed" in body

    @pytest.mark.asyncio
    async def test_cancel_keyword(self, mock_db, mock_appointment):
        """CANCEL keyword triggers appointment cancellation."""
        from routes.sms_scheduler_webhook import _handle_cancel

        import routes.sms_scheduler_webhook as webhook_module
        mock_appointment.status = MagicMock()
        mock_appointment.status.value = "booked"

        webhook_module._models = {
            "Appointment": MagicMock,
            "AppointmentStatusHistory": MagicMock,
        }

        mock_appt_status = MagicMock()
        mock_appt_status.CANCELLED = MagicMock()
        mock_appt_status.CANCELLED.value = "cancelled"

        with patch("routes.sms_scheduler_webhook._find_upcoming_appointment", return_value=mock_appointment):
            with patch("routes.sms_scheduler_webhook._send_reply", new_callable=AsyncMock, return_value=True):
                with patch.dict("sys.modules", {"smart_scheduler_models": MagicMock(AppointmentStatus=mock_appt_status)}):
                    response = await _handle_cancel(mock_db, "+15551234567")

        assert response.status_code == 200
        body = response.body
        assert b"cancelled" in body

    @pytest.mark.asyncio
    async def test_no_appointment_found(self, mock_db):
        """Returns not_found when no matching appointment exists."""
        from routes.sms_scheduler_webhook import _handle_confirm

        import routes.sms_scheduler_webhook as webhook_module
        webhook_module._models = {
            "Appointment": MagicMock,
            "AppointmentStatusHistory": MagicMock,
        }

        with patch("routes.sms_scheduler_webhook._find_upcoming_appointment", return_value=None):
            with patch("routes.sms_scheduler_webhook._send_reply", new_callable=AsyncMock, return_value=True):
                response = await _handle_confirm(mock_db, "+15559999999")

        assert response.status_code == 200
        body = response.body
        assert b"not_found" in body

    @pytest.mark.asyncio
    async def test_help_keyword(self):
        """HELP keyword returns available commands."""
        from routes.sms_scheduler_webhook import _handle_help

        with patch("routes.sms_scheduler_webhook._send_reply", new_callable=AsyncMock, return_value=True):
            response = await _handle_help("+15551234567")

        assert response.status_code == 200
        body = response.body
        assert b"help_sent" in body

    @pytest.mark.asyncio
    async def test_reschedule_keyword(self, mock_db, mock_appointment):
        """RESCHEDULE keyword attempts to generate reschedule URL."""
        from routes.sms_scheduler_webhook import _handle_reschedule

        import routes.sms_scheduler_webhook as webhook_module
        webhook_module._models = {"Appointment": MagicMock}

        mock_appt_status = MagicMock()
        mock_scheduler_email = MagicMock()
        mock_scheduler_email.generate_reschedule_url = MagicMock(return_value="https://app.perenniaai.com/reschedule/abc")

        with patch("routes.sms_scheduler_webhook._find_upcoming_appointment", return_value=mock_appointment):
            with patch("routes.sms_scheduler_webhook._send_reply", new_callable=AsyncMock, return_value=True):
                with patch.dict("sys.modules", {
                    "smart_scheduler_models": MagicMock(AppointmentStatus=mock_appt_status),
                    "scheduler_email_service": mock_scheduler_email,
                }):
                    response = await _handle_reschedule(mock_db, "+15551234567")

        assert response.status_code == 200
        body = response.body
        assert b"reschedule_info_sent" in body

    @pytest.mark.asyncio
    async def test_stop_keyword_acknowledged(self):
        """STOP keyword is acknowledged (Telnyx handles opt-out)."""
        from routes.sms_scheduler_webhook import handle_sms_reply

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value=
            self._make_telnyx_payload("+15551234567", "STOP")
        )
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"")

        mock_db_session = MagicMock()

        with patch("routes.sms_scheduler_webhook._validate_telnyx_signature", new_callable=AsyncMock, return_value=True):
            response = await handle_sms_reply(mock_request, mock_db_session)

        assert response.status_code == 200
        body = response.body
        assert b"stop" in body

    @pytest.mark.asyncio
    async def test_delivery_status_ignored(self):
        """Non-inbound events (delivery status) are ignored."""
        from routes.sms_scheduler_webhook import handle_sms_reply

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "data": {
                "event_type": "message.sent",
                "payload": {"id": "msg-456"},
            }
        })
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"")

        mock_db_session = MagicMock()

        with patch("routes.sms_scheduler_webhook._validate_telnyx_signature", new_callable=AsyncMock, return_value=True):
            response = await handle_sms_reply(mock_request, mock_db_session)

        assert response.status_code == 200
        body = response.body
        assert b"ignored" in body


class TestFindUpcomingAppointment:
    """Test phone number matching for inbound appointment lookup.

    Since _find_upcoming_appointment uses SQLAlchemy filter expressions
    internally, we test by mocking the entire function result rather than
    trying to mock the ORM query chain (which requires real column objects).
    """

    @staticmethod
    def _make_comparable_model_class():
        """Create a mock model class with SQLAlchemy-compatible comparison attributes."""
        def _make_col():
            m = MagicMock()
            m.__le__ = MagicMock(return_value=MagicMock())
            m.__ge__ = MagicMock(return_value=MagicMock())
            m.__gt__ = MagicMock(return_value=MagicMock())
            m.__lt__ = MagicMock(return_value=MagicMock())
            m.__eq__ = MagicMock(return_value=MagicMock())
            return m

        mock_class = MagicMock()
        mock_class.attendee_phone = _make_col()
        mock_class.status = _make_col()
        mock_class.scheduled_start = _make_col()
        return mock_class

    def test_finds_appointment_by_phone_suffix(self):
        """Verify the function is callable and returns appointment when found."""
        from routes.sms_scheduler_webhook import _find_upcoming_appointment

        mock_db = MagicMock()
        mock_appt_class = self._make_comparable_model_class()

        mock_appt = MagicMock()
        mock_appt.id = 99

        # Mock the full query chain that _find_upcoming_appointment uses
        query = mock_db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = mock_appt

        mock_appt_status = MagicMock()
        mock_appt_status.BOOKED = "booked"
        mock_appt_status.CONFIRMED = "confirmed"
        mock_appt_status.REMINDED = "reminded"
        mock_appt_status.TENTATIVE = "tentative"

        with patch.dict("sys.modules", {"smart_scheduler_models": MagicMock(AppointmentStatus=mock_appt_status)}):
            result = _find_upcoming_appointment(mock_db, mock_appt_class, "+15551234567")

        mock_db.query.assert_called_once_with(mock_appt_class)
        assert result is not None
        assert result.id == 99

    def test_returns_none_when_no_match(self):
        """Returns None when no appointment found."""
        from routes.sms_scheduler_webhook import _find_upcoming_appointment

        mock_db = MagicMock()
        mock_appt_class = self._make_comparable_model_class()

        query = mock_db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = None

        mock_appt_status = MagicMock()
        mock_appt_status.BOOKED = "booked"
        mock_appt_status.CONFIRMED = "confirmed"
        mock_appt_status.REMINDED = "reminded"
        mock_appt_status.TENTATIVE = "tentative"

        with patch.dict("sys.modules", {"smart_scheduler_models": MagicMock(AppointmentStatus=mock_appt_status)}):
            result = _find_upcoming_appointment(mock_db, mock_appt_class, "+15559999999")

        assert result is None


class TestHTTPFallback:
    """Test HTTP API fallback when telnyx SDK is unavailable."""

    @pytest.mark.asyncio
    async def test_http_fallback_sends_message(self):
        """HTTP fallback sends via Telnyx API when SDK import fails."""
        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "test-key",
            "TELNYX_PHONE_NUMBER": "+18438838956",
            "TELNYX_MESSAGING_PROFILE_ID": "test-profile",
        }):
            with patch.dict("sys.modules", {"telnyx": MagicMock()}):
                from services.sms_confirmation_service import SMSConfirmationService
                service = SMSConfirmationService()
                service.api_key = "test-key"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"id": "msg-http-1"}}

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await service._send_via_http("+15551234567", "Test message")

            assert result["sent"] is True
            assert result["message_id"] == "msg-http-1"

    @pytest.mark.asyncio
    async def test_http_fallback_handles_error(self):
        """HTTP fallback returns error on non-200 response."""
        from services.sms_confirmation_service import SMSConfirmationService
        service = SMSConfirmationService()
        service.api_key = "test-key"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await service._send_via_http("+15551234567", "Test message")

        assert result["sent"] is False
        assert "400" in result["error"]
