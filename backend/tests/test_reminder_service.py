"""
Tests for the Appointment Reminder System

Covers:
  - ReminderTemplate model and defaults seeding
  - ReminderLog model
  - ReminderService: template rendering, scheduling, cancellation, rescheduling
  - TCPA SMS consent checking
  - Rate limiting (max 3 per appointment)
  - Batch processing
  - Route endpoints (CRUD, log, test)
  - Edge cases (missing data, past reminders, unknown channels)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, PropertyMock
from types import SimpleNamespace


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock DB session."""
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.order_by.return_value = session
    session.limit.return_value = session
    session.all.return_value = []
    session.first.return_value = None
    session.count.return_value = 0
    session.scalar.return_value = 0
    session.flush.return_value = None
    session.add.return_value = None
    return session


@pytest.fixture
def sample_appointment():
    """Create a sample appointment object."""
    appt = SimpleNamespace(
        id=1,
        organization_id=100,
        appointment_type_id=10,
        assigned_user_id=5,
        meeting_type=SimpleNamespace(value="discovery_call"),
        scheduled_start=datetime.now(timezone.utc) + timedelta(hours=25),
        scheduled_end=datetime.now(timezone.utc) + timedelta(hours=25, minutes=30),
        timezone="America/Chicago",
        attendee_name="Jane Doe",
        attendee_email="jane@example.com",
        attendee_phone="+15551234567",
        location="Video Call",
        video_link="https://meet.example.com/abc",
        title="Discovery Call",
    )
    return appt


@pytest.fixture
def sample_template():
    """Create a sample ReminderTemplate-like object."""
    return SimpleNamespace(
        id=1,
        organization_id=100,
        name="24-Hour Email Reminder",
        channel="email",
        timing_minutes=1440,
        subject_template="Reminder: {appointment_type} tomorrow at {time}",
        body_template="Hi {client_name}, you have a {appointment_type} at {time} with {lo_name}.",
        is_active=True,
        appointment_type_id=None,
    )


@pytest.fixture
def sample_user():
    """Create a sample user object."""
    return SimpleNamespace(
        id=5,
        first_name="John",
        last_name="Smith",
        email="john@example.com",
    )


# ============================================================================
# Template Rendering Tests
# ============================================================================

class TestTemplateRendering:
    """Tests for ReminderService.render_template()."""

    def test_render_all_variables(self):
        from services.reminder_service import ReminderService

        template = "Hi {client_name}, your {appointment_type} is on {date} at {time} with {lo_name}."
        variables = {
            "client_name": "Jane",
            "appointment_type": "Discovery Call",
            "date": "March 15, 2026",
            "time": "2:00 PM",
            "lo_name": "John Smith",
        }
        result = ReminderService.render_template(template, variables)
        assert result == "Hi Jane, your Discovery Call is on March 15, 2026 at 2:00 PM with John Smith."

    def test_render_missing_variable_preserved(self):
        from services.reminder_service import ReminderService

        template = "Hello {client_name}, {unknown_var} is here."
        variables = {"client_name": "Jane"}
        result = ReminderService.render_template(template, variables)
        assert "{unknown_var}" in result
        assert "Jane" in result

    def test_render_empty_template(self):
        from services.reminder_service import ReminderService

        assert ReminderService.render_template("", {"key": "val"}) == ""
        assert ReminderService.render_template(None, {"key": "val"}) == ""

    def test_render_no_variables_in_template(self):
        from services.reminder_service import ReminderService

        result = ReminderService.render_template("Plain text with no vars", {})
        assert result == "Plain text with no vars"

    def test_render_multiple_occurrences(self):
        from services.reminder_service import ReminderService

        template = "{client_name} says hi to {client_name}"
        result = ReminderService.render_template(template, {"client_name": "Jane"})
        assert result == "Jane says hi to Jane"

    def test_render_url_variables(self):
        from services.reminder_service import ReminderService

        template = "Cancel: {cancel_url}\nReschedule: {reschedule_url}"
        variables = {
            "cancel_url": "https://app.perenniaai.com/cancel/123",
            "reschedule_url": "https://app.perenniaai.com/reschedule/123",
        }
        result = ReminderService.render_template(template, variables)
        assert "https://app.perenniaai.com/cancel/123" in result
        assert "https://app.perenniaai.com/reschedule/123" in result

    def test_render_special_characters_in_values(self):
        from services.reminder_service import ReminderService

        template = "Hi {client_name}"
        result = ReminderService.render_template(template, {"client_name": "O'Brien & Co."})
        assert result == "Hi O'Brien & Co."


# ============================================================================
# Model Tests
# ============================================================================

class TestReminderModels:
    """Tests for the ReminderTemplate and ReminderLog SQLAlchemy models."""

    def test_reminder_template_has_required_columns(self):
        from database.models.reminder_config import ReminderTemplate

        columns = {c.name for c in ReminderTemplate.__table__.columns}
        required = {
            "id", "organization_id", "name", "channel", "timing_minutes",
            "subject_template", "body_template", "is_active", "appointment_type_id",
            "created_at", "updated_at",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_reminder_log_has_required_columns(self):
        from database.models.reminder_config import ReminderLog

        columns = {c.name for c in ReminderLog.__table__.columns}
        required = {
            "id", "appointment_id", "template_id", "channel", "sent_at",
            "status", "error_message", "external_id",
            "recipient_email", "recipient_phone",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_reminder_template_tablename(self):
        from database.models.reminder_config import ReminderTemplate

        assert ReminderTemplate.__tablename__ == "reminder_templates"

    def test_reminder_log_tablename(self):
        from database.models.reminder_config import ReminderLog

        assert ReminderLog.__tablename__ == "reminder_logs"


# ============================================================================
# Default Template Seeding Tests
# ============================================================================

class TestDefaultTemplateSeeding:
    """Tests for seed_default_templates()."""

    def test_default_templates_structure(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES

        assert len(DEFAULT_REMINDER_TEMPLATES) == 3

        channels = {t["channel"] for t in DEFAULT_REMINDER_TEMPLATES}
        assert "email" in channels
        assert "sms" in channels

        timings = {t["timing_minutes"] for t in DEFAULT_REMINDER_TEMPLATES}
        assert 1440 in timings  # 24hr
        assert 60 in timings    # 1hr
        assert 15 in timings    # 15min

    def test_default_templates_have_body(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES

        for tmpl in DEFAULT_REMINDER_TEMPLATES:
            assert tmpl["body_template"], f"Template {tmpl['name']} has empty body"
            assert len(tmpl["body_template"]) > 10

    def test_default_templates_contain_variables(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES

        for tmpl in DEFAULT_REMINDER_TEMPLATES:
            # Every template should reference at least client_name or appointment_type
            body = tmpl["body_template"]
            assert "{" in body and "}" in body, f"Template {tmpl['name']} has no variables"

    def test_seed_default_templates_idempotent(self, mock_db):
        """Seed function should skip already-existing templates."""
        from database.models.reminder_config import seed_default_templates

        # Simulate all templates already exist
        mock_db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=1)

        result = seed_default_templates(mock_db, organization_id=100)
        assert result == []  # Nothing created

    def test_seed_creates_templates_when_missing(self, mock_db):
        """Seed function should create templates when they don't exist."""
        from database.models.reminder_config import seed_default_templates

        # Simulate no templates exist
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = seed_default_templates(mock_db, organization_id=100)
        assert len(result) == 3
        assert mock_db.add.call_count == 3


# ============================================================================
# ReminderService Core Tests
# ============================================================================

class TestReminderServiceSchedule:
    """Tests for schedule_reminders()."""

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_schedule_reminders_creates_entries(self, mock_get_models, mock_get_reminder, mock_db, sample_appointment, sample_template):
        from services.reminder_service import ReminderService

        # Setup mocks
        MockAppointment = MagicMock()
        MockAppointmentReminder = MagicMock()
        mock_get_models.return_value = {
            "Appointment": MockAppointment,
            "AppointmentReminder": MockAppointmentReminder,
        }

        MockReminderTemplate = MagicMock()
        MockReminderLog = MagicMock()
        mock_get_reminder.return_value = (MockReminderTemplate, MockReminderLog)

        # Appointment query returns our sample
        mock_db.query.return_value.filter.return_value.first.return_value = sample_appointment
        # Templates query returns one active template
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_template]

        service = ReminderService(mock_db)

        with patch("smart_scheduler_models.ReminderChannel") as MockChannel, \
             patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockChannel.EMAIL = "email"
            MockChannel.SMS = "sms"
            MockStatus.PENDING = "pending"

            result = service.schedule_reminders(appointment_id=1)

        assert len(result) >= 1
        assert mock_db.add.called

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_schedule_skips_past_reminders(self, mock_get_models, mock_get_reminder, mock_db):
        """Reminders scheduled before now should not be created."""
        from services.reminder_service import ReminderService

        # Appointment starting 5 minutes from now
        past_appt = SimpleNamespace(
            id=2,
            organization_id=100,
            appointment_type_id=None,
            scheduled_start=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        # Template with 1440 min (24hr) timing -- would be in the past
        template = SimpleNamespace(
            id=1,
            organization_id=100,
            name="Test",
            channel="email",
            timing_minutes=1440,
            appointment_type_id=None,
            is_active=True,
        )

        MockAppointment = MagicMock()
        MockAppointmentReminder = MagicMock()
        mock_get_models.return_value = {
            "Appointment": MockAppointment,
            "AppointmentReminder": MockAppointmentReminder,
        }
        mock_get_reminder.return_value = (MagicMock(), MagicMock())

        mock_db.query.return_value.filter.return_value.first.return_value = past_appt
        mock_db.query.return_value.filter.return_value.all.return_value = [template]

        service = ReminderService(mock_db)
        result = service.schedule_reminders(appointment_id=2)
        assert len(result) == 0  # Nothing created, all in the past

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_schedule_no_appointment_found(self, mock_get_models, mock_get_reminder, mock_db):
        from services.reminder_service import ReminderService

        MockAppointment = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointment, "AppointmentReminder": MagicMock()}
        mock_get_reminder.return_value = (MagicMock(), MagicMock())
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ReminderService(mock_db)
        result = service.schedule_reminders(appointment_id=999)
        assert result == []


class TestReminderServiceCancel:
    """Tests for cancel_reminders()."""

    @patch("services.reminder_service.ReminderService._get_models")
    def test_cancel_reminders(self, mock_get_models, mock_db):
        from services.reminder_service import ReminderService

        MockReminder = MagicMock()
        mock_get_models.return_value = {"AppointmentReminder": MockReminder}

        mock_db.query.return_value.filter.return_value.update.return_value = 3

        service = ReminderService(mock_db)

        with patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.FAILED = "failed"
            result = service.cancel_reminders(appointment_id=1)

        assert result == 3


class TestReminderServiceReschedule:
    """Tests for reschedule_reminders()."""

    def test_reschedule_calls_cancel_then_schedule(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)

        with patch.object(service, "cancel_reminders", return_value=2) as mock_cancel, \
             patch.object(service, "schedule_reminders", return_value=[{"template_id": 1}]) as mock_schedule:
            result = service.reschedule_reminders(appointment_id=1)

        mock_cancel.assert_called_once_with(1)
        mock_schedule.assert_called_once_with(1)
        assert len(result) == 1


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class TestRateLimiting:
    """Tests for the max 3 reminders per appointment limit."""

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    def test_rate_limit_not_exceeded(self, mock_get_reminder, mock_db):
        from services.reminder_service import ReminderService

        MockReminderLog = MagicMock()
        mock_get_reminder.return_value = (MagicMock(), MockReminderLog)

        # 2 reminders already sent
        mock_db.query.return_value.filter.return_value.scalar.return_value = 2

        service = ReminderService(mock_db)
        assert service._check_rate_limit(appointment_id=1) is True

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    def test_rate_limit_exceeded(self, mock_get_reminder, mock_db):
        from services.reminder_service import ReminderService

        MockReminderLog = MagicMock()
        mock_get_reminder.return_value = (MagicMock(), MockReminderLog)

        # 3 reminders already sent (at limit)
        mock_db.query.return_value.filter.return_value.scalar.return_value = 3

        service = ReminderService(mock_db)
        assert service._check_rate_limit(appointment_id=1) is False

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    def test_rate_limit_zero_sent(self, mock_get_reminder, mock_db):
        from services.reminder_service import ReminderService

        MockReminderLog = MagicMock()
        mock_get_reminder.return_value = (MagicMock(), MockReminderLog)

        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        service = ReminderService(mock_db)
        assert service._check_rate_limit(appointment_id=1) is True


# ============================================================================
# TCPA Consent Tests
# ============================================================================

class TestTCPAConsent:
    """Tests for SMS consent checking."""

    def test_no_phone_returns_false(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)
        assert service._check_sms_consent("", 100) is False
        assert service._check_sms_consent(None, 100) is False

    @patch("database.models.tcpa_consent.TCPAConsent")
    def test_consent_found(self, MockTCPA, mock_db):
        from services.reminder_service import ReminderService

        mock_db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=1, is_active=True)

        service = ReminderService(mock_db)
        assert service._check_sms_consent("+15551234567", 100) is True

    @patch("database.models.tcpa_consent.TCPAConsent")
    def test_consent_not_found(self, MockTCPA, mock_db):
        from services.reminder_service import ReminderService

        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ReminderService(mock_db)
        assert service._check_sms_consent("+15551234567", 100) is False

    def test_consent_check_graceful_on_import_error(self, mock_db):
        """If TCPAConsent table doesn't exist, should return True (graceful degradation)."""
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)
        mock_db.query.side_effect = Exception("relation does not exist")

        # Should not raise, should return True
        result = service._check_sms_consent("+15551234567", 100)
        assert result is True


# ============================================================================
# Send Tests
# ============================================================================

class TestReminderSend:
    """Tests for send_reminder() and transport helpers."""

    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_send_reminder_appointment_not_found(self, mock_get_models, mock_get_reminder, mock_db):
        from services.reminder_service import ReminderService

        MockAppointment = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointment}
        mock_get_reminder.return_value = (MagicMock(), MagicMock())
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ReminderService(mock_db)
        result = service.send_reminder(appointment_id=999, template_id=1)
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("services.reminder_service.ReminderService._send_email")
    @patch("services.reminder_service.ReminderService._check_rate_limit")
    @patch("services.reminder_service.ReminderService._build_variables")
    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_send_email_success(self, mock_get_models, mock_get_reminder, mock_build_vars, mock_rate, mock_send_email, mock_db, sample_appointment, sample_template):
        from services.reminder_service import ReminderService

        MockAppointment = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointment}

        MockReminderTemplate = MagicMock()
        MockReminderLog = MagicMock
        mock_get_reminder.return_value = (MockReminderTemplate, type("ReminderLog", (), {
            "__init__": lambda self, **kw: [setattr(self, k, v) for k, v in kw.items()],
        }))

        # First call returns appointment, second returns template
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_appointment,
            sample_template,
        ]

        mock_rate.return_value = True
        mock_build_vars.return_value = {"client_name": "Jane", "appointment_type": "Test"}
        mock_send_email.return_value = {"success": True, "message_id": "abc123"}

        service = ReminderService(mock_db)
        result = service.send_reminder(appointment_id=1, template_id=1)

        assert result["success"] is True
        mock_send_email.assert_called_once()

    @patch("services.reminder_service.ReminderService._check_rate_limit")
    @patch("services.reminder_service.ReminderService._get_reminder_models")
    @patch("services.reminder_service.ReminderService._get_models")
    def test_send_rate_limited(self, mock_get_models, mock_get_reminder, mock_rate, mock_db, sample_appointment, sample_template):
        from services.reminder_service import ReminderService

        MockAppointment = MagicMock()
        mock_get_models.return_value = {"Appointment": MockAppointment}

        MockReminderLog = type("ReminderLog", (), {
            "__init__": lambda self, **kw: [setattr(self, k, v) for k, v in kw.items()],
        })
        mock_get_reminder.return_value = (MagicMock(), MockReminderLog)

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_appointment,
            sample_template,
        ]

        mock_rate.return_value = False  # Rate limited

        service = ReminderService(mock_db)
        result = service.send_reminder(appointment_id=1, template_id=1)

        assert result["success"] is False
        assert "Rate limit" in result["error"]

    def test_send_email_static_no_recipient(self):
        from services.reminder_service import ReminderService

        result = ReminderService._send_email("", "Subject", "Body")
        assert result["success"] is False
        assert "No recipient" in result["error"]

    def test_send_sms_static_no_recipient(self):
        from services.reminder_service import ReminderService

        result = ReminderService._send_sms("", "Body")
        assert result["success"] is False
        assert "No recipient" in result["error"]


# ============================================================================
# Build Variables Tests
# ============================================================================

class TestBuildVariables:
    """Tests for _build_variables()."""

    @patch("services.reminder_service.ReminderService._get_models")
    def test_build_variables_basic(self, mock_get_models, mock_db, sample_appointment, sample_user):
        from services.reminder_service import ReminderService

        MockAppointmentType = MagicMock()
        appt_type_instance = SimpleNamespace(type_name="Discovery Call")
        mock_get_models.return_value = {"AppointmentType": MockAppointmentType}
        mock_db.query.return_value.filter.return_value.first.return_value = appt_type_instance

        service = ReminderService(mock_db)
        variables = service._build_variables(sample_appointment, assigned_user=sample_user)

        assert variables["client_name"] == "Jane Doe"
        assert variables["lo_name"] == "John Smith"
        assert "cancel_url" in variables
        assert "reschedule_url" in variables
        assert variables["location"] == "Video Call"

    @patch("services.reminder_service.ReminderService._get_models")
    def test_build_variables_missing_attendee(self, mock_get_models, mock_db):
        from services.reminder_service import ReminderService

        mock_get_models.return_value = {"AppointmentType": MagicMock()}

        appt = SimpleNamespace(
            id=1, organization_id=100, appointment_type_id=None,
            assigned_user_id=None, meeting_type=None,
            scheduled_start=datetime.now(timezone.utc),
            timezone="America/Chicago",
            attendee_name=None, location=None, video_link=None,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = ReminderService(mock_db)
        variables = service._build_variables(appt)

        assert variables["client_name"] == "there"  # Fallback
        assert variables["appointment_type"] == "Appointment"  # Default


# ============================================================================
# Batch Processing Tests
# ============================================================================

class TestBatchProcessing:
    """Tests for process_pending_batch()."""

    def test_batch_no_pending(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)

        with patch.object(service, "get_pending_reminders", return_value=[]):
            result = service.process_pending_batch(batch_size=50)

        assert result["processed"] == 0
        assert result["sent"] == 0

    def test_batch_with_pending_success(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)

        pending_reminder = SimpleNamespace(
            id=1, appointment_id=1, message_template="5",
            status=None, failure_reason=None, sent_at=None, failed_at=None,
        )

        with patch.object(service, "get_pending_reminders", return_value=[pending_reminder]), \
             patch.object(service, "send_reminder", return_value={"success": True}), \
             patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockStatus.SENT = "sent"
            MockStatus.FAILED = "failed"
            result = service.process_pending_batch(batch_size=50)

        assert result["processed"] == 1
        assert result["sent"] == 1

    def test_batch_with_no_template(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)

        pending_reminder = SimpleNamespace(
            id=1, appointment_id=1, message_template=None,
            status=None, failure_reason=None, sent_at=None, failed_at=None,
        )

        with patch.object(service, "get_pending_reminders", return_value=[pending_reminder]), \
             patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockStatus.FAILED = "failed"
            result = service.process_pending_batch(batch_size=50)

        assert result["processed"] == 1
        assert result["failed"] == 1

    def test_batch_handles_exception(self, mock_db):
        from services.reminder_service import ReminderService

        service = ReminderService(mock_db)

        pending_reminder = SimpleNamespace(
            id=1, appointment_id=1, message_template="5",
            status=None, failure_reason=None, sent_at=None, failed_at=None,
        )

        def fail_send(*args, **kwargs):
            raise RuntimeError("Network error")

        with patch.object(service, "get_pending_reminders", return_value=[pending_reminder]), \
             patch.object(service, "send_reminder", side_effect=fail_send), \
             patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockStatus.FAILED = "failed"
            result = service.process_pending_batch(batch_size=50)

        assert result["processed"] == 1
        assert result["failed"] == 1


# ============================================================================
# Pending Query Tests
# ============================================================================

class TestGetPendingReminders:
    """Tests for get_pending_reminders()."""

    @patch("services.reminder_service.ReminderService._get_models")
    def test_get_pending_returns_list(self, mock_get_models, mock_db):
        from services.reminder_service import ReminderService

        MockReminder = MagicMock()
        mock_get_models.return_value = {"AppointmentReminder": MockReminder}

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        service = ReminderService(mock_db)

        with patch("smart_scheduler_models.ReminderStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            result = service.get_pending_reminders(batch_size=10)

        assert isinstance(result, list)


# ============================================================================
# Route Helper Tests
# ============================================================================

class TestTimingLabel:
    """Tests for the _timing_label helper."""

    def test_days(self):
        from routes.scheduler.reminders import _timing_label

        assert _timing_label(1440) == "1 day before"
        assert _timing_label(2880) == "2 days before"
        assert _timing_label(10080) == "7 days before"

    def test_hours(self):
        from routes.scheduler.reminders import _timing_label

        assert _timing_label(60) == "1 hour before"
        assert _timing_label(120) == "2 hours before"
        assert _timing_label(240) == "4 hours before"

    def test_minutes(self):
        from routes.scheduler.reminders import _timing_label

        assert _timing_label(15) == "15 minutes before"
        assert _timing_label(30) == "30 minutes before"
        assert _timing_label(1) == "1 minute before"


# ============================================================================
# Integration-style Tests (mocked transport)
# ============================================================================

class TestReminderIntegration:
    """Higher-level tests verifying the full flow with mocked transport."""

    @patch("services.notification_service.notification_service")
    def test_send_email_via_notification_service(self, mock_notif):
        from services.reminder_service import ReminderService

        mock_notif.send_email.return_value = {"success": True, "message_id": "sg-123"}

        result = ReminderService._send_email(
            "test@example.com",
            "Test Subject",
            "Test body content",
        )
        assert result["success"] is True
        mock_notif.send_email.assert_called_once()

    @patch("services.notification_service.notification_service")
    def test_send_sms_via_notification_service(self, mock_notif):
        from services.reminder_service import ReminderService

        mock_notif.send_sms.return_value = {"success": True, "message_sid": "tx-456"}

        result = ReminderService._send_sms("+15551234567", "Your appointment is coming up!")
        assert result["success"] is True
        mock_notif.send_sms.assert_called_once()


# ============================================================================
# MAX_REMINDERS constant test
# ============================================================================

class TestConstants:
    """Verify module-level constants are correct."""

    def test_max_reminders_constant(self):
        from services.reminder_service import MAX_REMINDERS_PER_APPOINTMENT
        assert MAX_REMINDERS_PER_APPOINTMENT == 3

    def test_default_template_count(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES
        assert len(DEFAULT_REMINDER_TEMPLATES) == 3

    def test_email_template_has_subject(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES
        email_templates = [t for t in DEFAULT_REMINDER_TEMPLATES if t["channel"] == "email"]
        for t in email_templates:
            assert t["subject_template"] is not None

    def test_sms_templates_have_stop_opt_out(self):
        from database.models.reminder_config import DEFAULT_REMINDER_TEMPLATES
        sms_templates = [t for t in DEFAULT_REMINDER_TEMPLATES if t["channel"] == "sms"]
        for t in sms_templates:
            assert "STOP" in t["body_template"], f"SMS template {t['name']} missing STOP opt-out"
