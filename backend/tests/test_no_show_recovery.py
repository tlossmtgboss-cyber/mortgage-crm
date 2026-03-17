"""
Tests for No-Show Recovery System

Covers:
- Opt-out token generation and verification
- Opt-out recording and idempotency
- Chronic no-show detection
- Recovery step execution with opt-out checks
- SMS STOP handling
- Message template rendering
- Recovery sequence lifecycle
"""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Set a test SECRET_KEY before importing the module
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.first.return_value = None
    db.count.return_value = 0
    db.all.return_value = []
    db.flush.return_value = None
    db.commit.return_value = None
    db.add.return_value = None
    db.delete.return_value = 0
    return db


@pytest.fixture
def mock_appointment():
    """Create a mock appointment object."""
    appt = MagicMock()
    appt.id = 42
    appt.attendee_email = "borrower@example.com"
    appt.attendee_phone = "+15551234567"
    appt.attendee_name = "Jane Doe"
    appt.organization_id = 1
    appt.assigned_user_id = 10
    appt.title = "Discovery Call"
    appt.scheduled_start = datetime(2026, 3, 11, 14, 0, tzinfo=timezone.utc)
    appt.internal_notes = None
    appt.status = MagicMock()
    appt.status.value = "no_show"
    return appt


@pytest.fixture
def recovery_service():
    """Create a NoShowRecoveryService with mocked notification service."""
    from services.no_show_recovery import NoShowRecoveryService

    service = NoShowRecoveryService()
    mock_notif = MagicMock()
    mock_notif.send_sms.return_value = {"success": True, "error": None}
    mock_notif.send_email.return_value = {"success": True, "error": None}
    service._notification_service = mock_notif
    return service


# ============================================================================
# Token Tests
# ============================================================================

class TestOptOutTokens:
    """Test JWT opt-out token generation and verification."""

    def test_generate_and_verify_token(self):
        """A valid token should round-trip through generate and verify."""
        from services.no_show_recovery import (
            generate_opt_out_token,
            verify_opt_out_token,
        )

        token = generate_opt_out_token(
            email="test@example.com",
            organization_id=1,
            appointment_id=42,
        )
        assert isinstance(token, str)
        assert len(token) > 10

        payload = verify_opt_out_token(token)
        assert payload is not None
        assert payload["email"] == "test@example.com"
        assert payload["org_id"] == 1
        assert payload["appt_id"] == 42
        assert payload["purpose"] == "recovery_opt_out"

    def test_expired_token_returns_none(self):
        """An expired token should return None."""
        import jwt as jwt_lib
        from services.no_show_recovery import verify_opt_out_token, _get_secret_key

        expired_payload = {
            "email": "test@example.com",
            "org_id": 1,
            "purpose": "recovery_opt_out",
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
        }
        token = jwt_lib.encode(expired_payload, _get_secret_key(), algorithm="HS256")

        result = verify_opt_out_token(token)
        assert result is None

    def test_invalid_purpose_returns_none(self):
        """A token with wrong purpose should return None."""
        import jwt as jwt_lib
        from services.no_show_recovery import verify_opt_out_token, _get_secret_key

        bad_payload = {
            "email": "test@example.com",
            "org_id": 1,
            "purpose": "something_else",
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
        }
        token = jwt_lib.encode(bad_payload, _get_secret_key(), algorithm="HS256")

        result = verify_opt_out_token(token)
        assert result is None

    def test_tampered_token_returns_none(self):
        """A tampered token should return None."""
        from services.no_show_recovery import verify_opt_out_token

        result = verify_opt_out_token("clearly.not.a.valid.token")
        assert result is None

    def test_build_opt_out_url(self):
        """build_opt_out_url should return a full URL with token."""
        from services.no_show_recovery import build_opt_out_url

        url = build_opt_out_url(
            email="test@example.com",
            organization_id=1,
            appointment_id=42,
            base_url="https://api.example.com",
        )
        assert url.startswith("https://api.example.com/api/v1/scheduler/recovery/opt-out/")
        # Should contain a JWT token after the last slash
        token_part = url.split("/opt-out/")[1]
        assert len(token_part) > 10


# ============================================================================
# Opt-Out Management Tests
# ============================================================================

class TestOptOutManagement:
    """Test opt-out recording, checking, and removal."""

    def test_is_opted_out_returns_false_when_no_record(self, recovery_service, mock_db):
        """is_opted_out should return False when no opt-out exists."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = recovery_service.is_opted_out(mock_db, "test@example.com", 1)
        assert result is False

    def test_is_opted_out_returns_true_when_record_exists(self, recovery_service, mock_db):
        """is_opted_out should return True when an opt-out record exists."""
        mock_record = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        result = recovery_service.is_opted_out(mock_db, "test@example.com", 1)
        assert result is True

    def test_record_opt_out_creates_new_record(self, recovery_service, mock_db):
        """record_opt_out should create a new record when none exists."""
        # No existing opt-out
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_model_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = 1
        mock_model_cls.return_value = mock_instance

        with patch("services.no_show_recovery.RecoveryOptOut", mock_model_cls, create=True), \
             patch.dict("sys.modules", {"database.models.recovery_opt_out": MagicMock(RecoveryOptOut=mock_model_cls)}):
            result = recovery_service.record_opt_out(
                mock_db,
                email="new@example.com",
                organization_id=1,
                reason="User requested",
                source="link",
            )

        assert result["status"] == "opted_out"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_record_opt_out_is_idempotent(self, recovery_service, mock_db):
        """record_opt_out should return existing record if already opted out."""
        existing = MagicMock()
        existing.id = 99
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        result = recovery_service.record_opt_out(
            mock_db,
            email="existing@example.com",
            organization_id=1,
        )

        assert result["status"] == "already_opted_out"
        assert result["id"] == 99
        mock_db.add.assert_not_called()

    def test_remove_opt_out_returns_true_when_deleted(self, recovery_service, mock_db):
        """remove_opt_out should return True when a record was deleted."""
        mock_db.query.return_value.filter.return_value.delete.return_value = 1

        result = recovery_service.remove_opt_out(mock_db, "test@example.com", 1)
        assert result is True

    def test_remove_opt_out_returns_false_when_not_found(self, recovery_service, mock_db):
        """remove_opt_out should return False when no record to delete."""
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        result = recovery_service.remove_opt_out(mock_db, "test@example.com", 1)
        assert result is False


# ============================================================================
# Chronic No-Show Tests
# ============================================================================

class TestChronicNoShow:
    """Test chronic no-show detection logic."""

    def _make_mock_appointment_model(self):
        """Create a mock Appointment model that supports SQLAlchemy-style
        column comparisons (>=, ==, etc.) without raising TypeError."""
        mock_model = MagicMock()
        # Make column attributes return MagicMock that supports comparison
        # by using spec-less MagicMock (default) which returns MagicMock for
        # comparison operators. The real issue is that MagicMock.__ge__ raises
        # TypeError with datetime. We override it to return a MagicMock filter.
        for attr in ('attendee_email', 'organization_id', 'status', 'no_show_at'):
            col = MagicMock()
            col.__ge__ = MagicMock(return_value=MagicMock())
            col.__eq__ = MagicMock(return_value=MagicMock())
            setattr(mock_model, attr, col)
        return mock_model

    def _patch_models(self, recovery_service):
        """Return a context manager that patches _get_models."""
        mock_model = self._make_mock_appointment_model()
        mock_models = {"Appointment": mock_model}
        return patch.object(recovery_service, '_get_models', return_value=mock_models)

    def test_not_chronic_when_below_threshold(self, recovery_service, mock_db):
        """Should not flag as chronic when count is below threshold."""
        mock_db.query.return_value.filter.return_value.count.return_value = 2

        with self._patch_models(recovery_service):
            result = recovery_service.is_chronic_no_show(mock_db, "test@example.com", 1)
        assert result is False

    def test_chronic_when_at_threshold(self, recovery_service, mock_db):
        """Should flag as chronic when count equals threshold."""
        mock_db.query.return_value.filter.return_value.count.return_value = 3

        with self._patch_models(recovery_service):
            result = recovery_service.is_chronic_no_show(mock_db, "test@example.com", 1)
        assert result is True

    def test_chronic_when_above_threshold(self, recovery_service, mock_db):
        """Should flag as chronic when count exceeds threshold."""
        mock_db.query.return_value.filter.return_value.count.return_value = 5

        with self._patch_models(recovery_service):
            result = recovery_service.is_chronic_no_show(mock_db, "test@example.com", 1)
        assert result is True

    def test_get_no_show_count(self, recovery_service, mock_db):
        """get_no_show_count should return the query count."""
        mock_db.query.return_value.filter.return_value.count.return_value = 4

        with self._patch_models(recovery_service):
            count = recovery_service.get_no_show_count(mock_db, "test@example.com", 1)
        assert count == 4


# ============================================================================
# Recovery Step Execution Tests
# ============================================================================

class TestRecoveryStepExecution:
    """Test individual recovery step execution."""

    @pytest.mark.asyncio
    async def test_execute_step_sends_sms_for_step_1(self, recovery_service, mock_db, mock_appointment):
        """Step 1 should send an SMS via the gentle_sms template."""
        # Mock the models lookup
        mock_models = {"Appointment": MagicMock()}
        mock_models["Appointment"].__name__ = "Appointment"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, '_get_lo_name', return_value="John Smith"), \
             patch.object(recovery_service, '_log_recovery_step'):

            result = await recovery_service.execute_step(
                mock_db,
                appointment_id=42,
                step=1,
                reschedule_url="https://app.example.com/schedule?reschedule_from=42",
            )

        assert result["sent"] is True
        assert result["channel"] == "sms"
        assert result["template"] == "gentle_sms"
        assert result["step"] == 1
        assert result["next_step"] == 2

        # Verify SMS was sent
        recovery_service.notification_service.send_sms.assert_called_once()
        call_kwargs = recovery_service.notification_service.send_sms.call_args
        sms_message = call_kwargs[1]["message"] if "message" in call_kwargs[1] else call_kwargs[0][1]
        assert "No worries at all" in str(sms_message) or "STOP" in str(sms_message)

    @pytest.mark.asyncio
    async def test_execute_step_sends_email_for_step_2(self, recovery_service, mock_db, mock_appointment):
        """Step 2 should send an email via the understanding_email template."""
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, '_get_lo_name', return_value="John Smith"), \
             patch.object(recovery_service, '_log_recovery_step'):

            result = await recovery_service.execute_step(
                mock_db,
                appointment_id=42,
                step=2,
            )

        assert result["sent"] is True
        assert result["channel"] == "email"
        assert result["template"] == "understanding_email"
        assert result["next_step"] == 3

        recovery_service.notification_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_step_skips_opted_out_attendee(self, recovery_service, mock_db, mock_appointment):
        """Should skip sending if the attendee has opted out."""
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=True):

            result = await recovery_service.execute_step(mock_db, 42, step=1)

        assert result["sent"] is False
        assert result["reason"] == "opted_out"
        recovery_service.notification_service.send_sms.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_step_skips_rescheduled_appointment(self, recovery_service, mock_db, mock_appointment):
        """Should stop if the appointment has been rescheduled."""
        from smart_scheduler_models import AppointmentStatus

        mock_appointment.status = AppointmentStatus.RESCHEDULED
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models):
            result = await recovery_service.execute_step(mock_db, 42, step=2)

        assert result["sent"] is False
        assert result["reason"] == "already_resolved"

    @pytest.mark.asyncio
    async def test_execute_step_skips_completed_appointment(self, recovery_service, mock_db, mock_appointment):
        """Should stop if the appointment has been completed."""
        from smart_scheduler_models import AppointmentStatus

        mock_appointment.status = AppointmentStatus.COMPLETED
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models):
            result = await recovery_service.execute_step(mock_db, 42, step=2)

        assert result["sent"] is False
        assert result["reason"] == "already_resolved"

    @pytest.mark.asyncio
    async def test_execute_step_handles_missing_appointment(self, recovery_service, mock_db):
        """Should handle appointment not found gracefully."""
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(recovery_service, '_get_models', return_value=mock_models):
            result = await recovery_service.execute_step(mock_db, 999, step=1)

        assert result["sent"] is False
        assert result["reason"] == "appointment_not_found"

    @pytest.mark.asyncio
    async def test_execute_step_handles_no_phone(self, recovery_service, mock_db, mock_appointment):
        """SMS step should fail gracefully when attendee has no phone."""
        mock_appointment.attendee_phone = None
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, '_get_lo_name', return_value="John"), \
             patch.object(recovery_service, '_log_recovery_step'):

            result = await recovery_service.execute_step(mock_db, 42, step=1)

        assert result["sent"] is False
        assert result["error"] == "no_phone_number"

    @pytest.mark.asyncio
    async def test_step_4_is_final(self, recovery_service, mock_db, mock_appointment):
        """Step 4 (final) should have no next_step."""
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, '_get_lo_name', return_value="John Smith"), \
             patch.object(recovery_service, '_log_recovery_step'):

            result = await recovery_service.execute_step(mock_db, 42, step=4)

        assert result["sent"] is True
        assert result["step"] == 4
        assert result["next_step"] is None
        assert result["next_delay_minutes"] is None

    @pytest.mark.asyncio
    async def test_invalid_step_returns_error(self, recovery_service, mock_db, mock_appointment):
        """An invalid step number should return an error."""
        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False):

            result = await recovery_service.execute_step(mock_db, 42, step=5)

        assert result["sent"] is False
        assert result["reason"] == "invalid_step"


# ============================================================================
# Start Recovery Tests
# ============================================================================

class TestStartRecovery:
    """Test the full start_recovery flow."""

    @pytest.mark.asyncio
    async def test_start_recovery_skips_no_email(self, recovery_service, mock_db, mock_appointment):
        """Should skip when attendee has no email."""
        mock_appointment.attendee_email = None

        result = await recovery_service.start_recovery(mock_db, mock_appointment)
        assert result["action"] == "skipped"
        assert result["reason"] == "no_email"

    @pytest.mark.asyncio
    async def test_start_recovery_skips_opted_out(self, recovery_service, mock_db, mock_appointment):
        """Should skip when attendee is opted out."""
        with patch.object(recovery_service, 'is_opted_out', return_value=True):
            result = await recovery_service.start_recovery(mock_db, mock_appointment)

        assert result["action"] == "skipped"
        assert result["reason"] == "opted_out"

    @pytest.mark.asyncio
    async def test_start_recovery_handles_chronic_no_show(self, recovery_service, mock_db, mock_appointment):
        """Should flag chronic no-show, notify LO, and auto-opt-out."""
        mock_notify = AsyncMock()
        mock_record = MagicMock(return_value={"status": "opted_out", "id": 1})

        with patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, 'is_chronic_no_show', return_value=True), \
             patch.object(recovery_service, '_notify_lo_of_chronic_no_show', mock_notify), \
             patch.object(recovery_service, 'record_opt_out', mock_record):

            result = await recovery_service.start_recovery(mock_db, mock_appointment)

            assert result["action"] == "chronic_no_show"
            mock_notify.assert_called_once()
            mock_record.assert_called_once()
            # Verify the opt-out source is "chronic_no_show"
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["source"] == "chronic_no_show"

    @pytest.mark.asyncio
    async def test_start_recovery_executes_step_1(self, recovery_service, mock_db, mock_appointment):
        """Normal start should execute step 1."""
        mock_execute = AsyncMock(return_value={"sent": True, "step": 1})

        with patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, 'is_chronic_no_show', return_value=False), \
             patch.object(recovery_service, 'execute_step', mock_execute):

            result = await recovery_service.start_recovery(mock_db, mock_appointment)

            assert result["action"] == "started"
            assert result["first_step_result"]["sent"] is True
            mock_execute.assert_called_once_with(
                mock_db,
                appointment_id=42,
                step=1,
                reschedule_url=None,
            )


# ============================================================================
# Message Template Tests
# ============================================================================

class TestMessageTemplates:
    """Test that message templates render correctly."""

    def test_sms_templates_contain_opt_out_instruction(self):
        """All SMS templates should contain STOP opt-out instruction."""
        from services.no_show_recovery import SMS_TEMPLATES

        for key, template in SMS_TEMPLATES.items():
            assert "STOP" in template, f"SMS template '{key}' missing STOP instruction"

    def test_email_templates_contain_opt_out_link(self):
        """All email templates should reference opt_out_link."""
        from services.no_show_recovery import EMAIL_TEMPLATES

        for key, template in EMAIL_TEMPLATES.items():
            assert "{opt_out_link}" in template["body"], (
                f"Email template '{key}' missing opt_out_link placeholder"
            )

    def test_sms_template_rendering(self):
        """SMS templates should render with all placeholders filled."""
        from services.no_show_recovery import SMS_TEMPLATES

        context = {
            "name": "Jane",
            "reschedule_link": "https://example.com/reschedule",
        }

        for key, template in SMS_TEMPLATES.items():
            rendered = template.format(**context)
            assert "Jane" in rendered
            assert "{" not in rendered, f"Unresolved placeholder in '{key}'"

    def test_email_template_rendering(self):
        """Email templates should render with all placeholders filled."""
        from services.no_show_recovery import EMAIL_TEMPLATES

        context = {
            "name": "Jane",
            "reschedule_link": "https://example.com/reschedule",
            "opt_out_link": "https://example.com/opt-out/token123",
            "lo_name": "John Smith",
        }

        for key, template in EMAIL_TEMPLATES.items():
            rendered_body = template["body"].format(**context)
            assert "Jane" in rendered_body
            assert "John Smith" in rendered_body
            assert "{" not in rendered_body, f"Unresolved placeholder in '{key}'"

    def test_gentle_sms_is_empathetic(self):
        """The gentle SMS should use warm, non-judgmental language."""
        from services.no_show_recovery import SMS_TEMPLATES

        sms = SMS_TEMPLATES["gentle_sms"]
        assert "No worries" in sms
        assert "weren't able to make" in sms

    def test_final_outreach_is_final(self):
        """The final outreach email should clearly state it's the last one."""
        from services.no_show_recovery import EMAIL_TEMPLATES

        body = EMAIL_TEMPLATES["final_outreach"]["body"]
        assert "last follow-up" in body
        assert "completely understand" in body


# ============================================================================
# Recovery Steps Configuration Tests
# ============================================================================

class TestRecoveryStepsConfig:
    """Test the RECOVERY_STEPS configuration."""

    def test_steps_are_in_order(self):
        """Steps should be numbered 1 through N."""
        from services.no_show_recovery import RECOVERY_STEPS

        for i, step in enumerate(RECOVERY_STEPS, start=1):
            assert step["step"] == i, f"Step {i} has wrong step number: {step['step']}"

    def test_delays_increase(self):
        """Each step's delay should be greater than the previous."""
        from services.no_show_recovery import RECOVERY_STEPS

        for i in range(1, len(RECOVERY_STEPS)):
            assert RECOVERY_STEPS[i]["delay_minutes"] > RECOVERY_STEPS[i - 1]["delay_minutes"], (
                f"Step {i + 1} delay is not greater than step {i}"
            )

    def test_channels_alternate(self):
        """Steps should alternate between SMS and email."""
        from services.no_show_recovery import RECOVERY_STEPS

        channels = [s["channel"] for s in RECOVERY_STEPS]
        assert channels == ["sms", "email", "sms", "email"]

    def test_step_1_delay_is_15_minutes(self):
        """First step should have a 15-minute delay."""
        from services.no_show_recovery import RECOVERY_STEPS

        assert RECOVERY_STEPS[0]["delay_minutes"] == 15

    def test_step_4_delay_is_72_hours(self):
        """Final step should be at 72 hours (4320 minutes)."""
        from services.no_show_recovery import RECOVERY_STEPS

        assert RECOVERY_STEPS[3]["delay_minutes"] == 4320

    def test_each_step_has_matching_template(self):
        """Each step's template should exist in the template dictionaries."""
        from services.no_show_recovery import (
            RECOVERY_STEPS, SMS_TEMPLATES, EMAIL_TEMPLATES,
        )

        for step in RECOVERY_STEPS:
            if step["channel"] == "sms":
                assert step["template"] in SMS_TEMPLATES, (
                    f"SMS template '{step['template']}' not found"
                )
            elif step["channel"] == "email":
                assert step["template"] in EMAIL_TEMPLATES, (
                    f"Email template '{step['template']}' not found"
                )


# ============================================================================
# Opt-Out Page Rendering Tests
# ============================================================================

class TestOptOutPageRendering:
    """Test the HTML opt-out confirmation page."""

    def test_success_page_contains_confirmation(self):
        """Success page should show unsubscribed confirmation."""
        from routes.recovery_opt_out_routes import _render_opt_out_page

        html = _render_opt_out_page(success=True, message="You are unsubscribed.")
        assert "Unsubscribed" in html
        assert "You are unsubscribed." in html
        assert "#10b981" in html  # Green color

    def test_error_page_contains_error(self):
        """Error page should show the error message."""
        from routes.recovery_opt_out_routes import _render_opt_out_page

        html = _render_opt_out_page(success=False, message="Link expired.")
        assert "Error" in html
        assert "Link expired." in html
        assert "#ef4444" in html  # Red color

    def test_page_escapes_html_in_message(self):
        """Page should escape HTML in the message to prevent XSS."""
        from routes.recovery_opt_out_routes import _render_opt_out_page

        html = _render_opt_out_page(
            success=True,
            message='<script>alert("xss")</script>',
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ============================================================================
# Integration-style Recovery Lifecycle Test
# ============================================================================

class TestRecoveryLifecycle:
    """Test the full recovery lifecycle across multiple steps."""

    @pytest.mark.asyncio
    async def test_full_sequence_stops_on_opt_out_mid_sequence(
        self, recovery_service, mock_db, mock_appointment
    ):
        """
        Simulate a recovery sequence where the attendee opts out
        after step 2. Steps 3 and 4 should be skipped.
        """
        call_count = 0

        def is_opted_out_side_effect(db, email, org_id):
            nonlocal call_count
            call_count += 1
            # Opted out after step 2 (third check onwards)
            return call_count > 2

        mock_models = {"Appointment": MagicMock()}
        mock_db.query.return_value.filter.return_value.first.return_value = mock_appointment

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', side_effect=is_opted_out_side_effect), \
             patch.object(recovery_service, '_get_lo_name', return_value="John"), \
             patch.object(recovery_service, '_log_recovery_step'):

            # Step 1: should send
            r1 = await recovery_service.execute_step(mock_db, 42, step=1)
            assert r1["sent"] is True

            # Step 2: should send
            r2 = await recovery_service.execute_step(mock_db, 42, step=2)
            assert r2["sent"] is True

            # Step 3: should be skipped (opted out)
            r3 = await recovery_service.execute_step(mock_db, 42, step=3)
            assert r3["sent"] is False
            assert r3["reason"] == "opted_out"

    @pytest.mark.asyncio
    async def test_full_sequence_stops_on_reschedule(
        self, recovery_service, mock_db, mock_appointment
    ):
        """
        If the attendee reschedules between steps, subsequent steps
        should recognize the new status and stop.
        """
        from smart_scheduler_models import AppointmentStatus

        mock_models = {"Appointment": MagicMock()}

        step_call = 0

        def get_appointment_side_effect(*args, **kwargs):
            nonlocal step_call
            step_call += 1
            if step_call >= 2:
                mock_appointment.status = AppointmentStatus.RESCHEDULED
            return mock_appointment

        mock_db.query.return_value.filter.return_value.first.side_effect = (
            get_appointment_side_effect
        )

        with patch.object(recovery_service, '_get_models', return_value=mock_models), \
             patch.object(recovery_service, 'is_opted_out', return_value=False), \
             patch.object(recovery_service, '_get_lo_name', return_value="John"), \
             patch.object(recovery_service, '_log_recovery_step'):

            # Step 1: should send
            r1 = await recovery_service.execute_step(mock_db, 42, step=1)
            assert r1["sent"] is True

            # Step 2: appointment now rescheduled -- should stop
            r2 = await recovery_service.execute_step(mock_db, 42, step=2)
            assert r2["sent"] is False
            assert r2["reason"] == "already_resolved"
