"""
Tests for Smart Docs Follow-Up Automation Service

Covers:
1.  Campaign creation with multi-step sequences
2.  Email follow-up event scheduling
3.  SMS follow-up event scheduling
4.  Call task creation for follow-ups
5.  Appointment scheduling for document issues
6.  Campaign pause/resume functionality
7.  Campaign completion when all docs received
8.  Escalation after multiple failed attempts
9.  Template variable substitution (borrower name, doc type, due date)
10. Follow-up frequency throttling (don't spam)
11. Business hours enforcement for SMS/calls
12. Campaign cancellation
13. Event delivery tracking (sent, delivered, opened, bounced)
14. Priority-based campaign ordering
15. Multi-tenant campaign isolation
"""

import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database.models.document_followup import (
    FollowupCampaign,
    FollowupEvent,
    DocumentAppointment,
    FollowupTemplate,
    CampaignType,
    CampaignStatus,
    CampaignTriggerSource,
    FollowupEventType,
    DeliveryStatus,
    AppointmentType,
    AppointmentStatus,
    LocationType,
)
from services.smart_docs.followup_automation_service import (
    FollowupAutomationService,
    _DEFAULT_STEP_CONFIGS,
    _DEFAULT_TEMPLATES,
    get_followup_automation_service,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session with query builder chains."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create a FollowupAutomationService with mocked DB."""
    svc = FollowupAutomationService(mock_db)
    svc._portal_base_url = "https://app.perenniaai.com/portal"
    return svc


def _make_campaign(
    id=1,
    organization_id=100,
    loan_id=200,
    borrower_id=300,
    campaign_type=CampaignType.INITIAL_REQUEST,
    status=CampaignStatus.ACTIVE,
    trigger_source=CampaignTriggerSource.NEEDS_LIST_GENERATED,
    linked_request_ids=None,
    total_steps=5,
    current_step=0,
    step_config=None,
    next_action_at=None,
    started_at=None,
    reminders_sent=0,
    borrower_responded=False,
    response_date=None,
    cancel_reason=None,
    max_reminders=5,
    completed_at=None,
    cancelled_at=None,
    created_at=None,
    updated_at=None,
    created_by_user_id=None,
):
    """Helper to create a mock FollowupCampaign."""
    campaign = MagicMock(spec=FollowupCampaign)
    campaign.id = id
    campaign.organization_id = organization_id
    campaign.loan_id = loan_id
    campaign.borrower_id = borrower_id
    campaign.campaign_type = campaign_type
    campaign.status = status
    campaign.trigger_source = trigger_source
    campaign.linked_request_ids = linked_request_ids or [1, 2, 3]
    campaign.total_steps = total_steps
    campaign.current_step = current_step
    campaign.step_config = step_config or _DEFAULT_STEP_CONFIGS["initial_request"]
    campaign.next_action_at = next_action_at or datetime.now(timezone.utc)
    campaign.started_at = started_at or datetime.now(timezone.utc) - timedelta(days=2)
    campaign.reminders_sent = reminders_sent
    campaign.borrower_responded = borrower_responded
    campaign.response_date = response_date
    campaign.cancel_reason = cancel_reason
    campaign.max_reminders = max_reminders
    campaign.completed_at = completed_at
    campaign.cancelled_at = cancelled_at
    campaign.created_at = created_at or datetime.now(timezone.utc)
    campaign.updated_at = updated_at or datetime.now(timezone.utc)
    campaign.created_by_user_id = created_by_user_id
    return campaign


def _make_event(
    id=1,
    campaign_id=1,
    event_type=FollowupEventType.EMAIL_SENT,
    step_number=1,
    channel="email",
    delivery_status=DeliveryStatus.SENT,
    delivery_error=None,
    recipient_email="borrower@example.com",
    recipient_phone=None,
    message_subject="Test Subject",
    message_preview="Test preview",
    template_used="initial_request",
    opened_at=None,
    clicked_at=None,
    created_at=None,
    metadata=None,
):
    """Helper to create a mock FollowupEvent."""
    event = MagicMock(spec=FollowupEvent)
    event.id = id
    event.campaign_id = campaign_id
    event.event_type = event_type
    event.step_number = step_number
    event.channel = channel
    event.delivery_status = delivery_status
    event.delivery_error = delivery_error
    event.recipient_email = recipient_email
    event.recipient_phone = recipient_phone
    event.message_subject = message_subject
    event.message_preview = message_preview
    event.template_used = template_used
    event.opened_at = opened_at
    event.clicked_at = clicked_at
    event.created_at = created_at or datetime.now(timezone.utc)
    event.metadata = metadata
    return event


def _mock_borrower_info():
    """Standard borrower info dict."""
    return {
        "borrower_name": "John Smith",
        "borrower_email": "john@example.com",
        "borrower_phone": "+15551234567",
        "lo_name": "Jane Doe",
        "lo_email": "jane@company.com",
        "lo_user_id": 50,
    }


# =============================================================================
# 1. Campaign creation with multi-step sequences
# =============================================================================

class TestCampaignCreation:
    """Campaign creation with multi-step sequences."""

    def test_create_initial_request_campaign(self, service, mock_db):
        """Create a campaign with default initial_request steps (5 steps)."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="initial_request",
            request_ids=[10, 20, 30],
            created_by_user_id=50,
        )

        assert result["loan_id"] == 200
        assert result["borrower_id"] == 300
        assert result["campaign_type"] == "initial_request"
        assert result["status"] == "active"
        assert result["total_steps"] == 5
        assert result["linked_request_ids"] == [10, 20, 30]
        assert "campaign_id" in result
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_create_urgent_reminder_campaign(self, service, mock_db):
        """Create an urgent_reminder campaign (3 steps)."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="urgent_reminder",
            request_ids=[10],
        )

        assert result["total_steps"] == 3
        assert result["status"] == "active"

    def test_create_campaign_unknown_type_falls_back(self, service, mock_db):
        """Unknown campaign_type falls back to initial_request."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="nonexistent_type",
            request_ids=[10],
        )

        # Falls back to initial_request which has 5 steps
        assert result["total_steps"] == 5

    def test_create_campaign_sets_next_action_at(self, service, mock_db):
        """next_action_at is set based on first step delay_hours."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="initial_request",
            request_ids=[10],
        )

        # initial_request step 1 has delay_hours=0, so next_action_at should be ~now
        assert result["next_action_at"] is not None

    def test_create_document_rejected_campaign(self, service, mock_db):
        """Create a document_rejected campaign (3 steps)."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="document_rejected",
            request_ids=[10],
        )

        assert result["total_steps"] == 3

    def test_create_document_expired_campaign(self, service, mock_db):
        """Create a document_expired campaign (2 steps)."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="document_expired",
            request_ids=[10, 20],
        )

        assert result["total_steps"] == 2


# =============================================================================
# 2. Email follow-up event scheduling
# =============================================================================

class TestEmailFollowup:
    """Email follow-up event scheduling."""

    def test_send_email_reminder_success(self, service, mock_db):
        """Successful email send returns sent status."""
        campaign = _make_campaign()
        service._get_campaign = MagicMock(return_value=campaign)

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service._send_email_reminder(
                campaign_id=1,
                template_slug="initial_request",
                borrower_email="john@example.com",
                borrower_name="John Smith",
                documents=[{"title": "W-2 2025"}],
                lo_name="Jane Doe",
                portal_link="https://app.perenniaai.com/portal/documents/200",
            )

        assert result["status"] == "sent"
        assert result["channel"] == "email"
        assert result["recipient"] == "john@example.com"
        assert "W-2 2025" in result["body"]

    def test_send_email_reminder_no_email_fails(self, service, mock_db):
        """Missing borrower email returns failed status."""
        result = service._send_email_reminder(
            campaign_id=1,
            template_slug="initial_request",
            borrower_email="",
            borrower_name="John",
            documents=[],
            lo_name="Jane",
            portal_link="https://example.com",
        )

        assert result["status"] == "failed"
        assert "No borrower email" in result["error"]

    def test_send_email_reminder_service_exception(self, service, mock_db):
        """Email service exception is caught and returns failed."""
        campaign = _make_campaign()
        service._get_campaign = MagicMock(return_value=campaign)

        with patch(
            "services.smart_docs.followup_automation_service.EmailService",
            side_effect=ImportError("email_service not available"),
        ):
            result = service._send_email_reminder(
                campaign_id=1,
                template_slug="initial_request",
                borrower_email="john@example.com",
                borrower_name="John",
                documents=[],
                lo_name="Jane",
                portal_link="https://example.com",
            )

        assert result["status"] == "failed"


# =============================================================================
# 3. SMS follow-up event scheduling
# =============================================================================

class TestSMSFollowup:
    """SMS follow-up event scheduling."""

    def test_send_sms_reminder_success(self, service, mock_db):
        """Successful SMS send returns sent status."""
        campaign = _make_campaign()
        service._get_campaign = MagicMock(return_value=campaign)

        with patch.dict(os.environ, {
            "TELNYX_API_KEY": "test_key",
            "TELNYX_FROM_NUMBER": "+18001234567",
            "TELNYX_MESSAGING_PROFILE_ID": "profile_123",
        }):
            with patch("telephony.sms.send_sms") as mock_send_sms:
                mock_send_sms.return_value = {"id": "msg-123", "status": "sent"}

                result = service._send_sms_reminder(
                    campaign_id=1,
                    template_slug="gentle_reminder_sms",
                    borrower_phone="+15551234567",
                    borrower_name="John",
                    document_count=3,
                )

                mock_send_sms.assert_called_once_with(
                    to="+15551234567",
                    from_="+18001234567",
                    text=result["body"],
                    messaging_profile_id="profile_123",
                    api_key="test_key",
                )

        assert result["status"] == "sent"
        assert result["channel"] == "sms"
        assert result["recipient"] == "+15551234567"

    def test_send_sms_reminder_no_phone_fails(self, service, mock_db):
        """Missing phone number returns failed."""
        result = service._send_sms_reminder(
            campaign_id=1,
            template_slug="gentle_reminder_sms",
            borrower_phone="",
            borrower_name="John",
            document_count=2,
        )

        assert result["status"] == "failed"
        assert "No borrower phone" in result["error"]

    def test_send_sms_not_configured_fails(self, service, mock_db):
        """SMS fails gracefully when Telnyx is not configured."""
        campaign = _make_campaign()
        service._get_campaign = MagicMock(return_value=campaign)

        with patch.dict(os.environ, {"TELNYX_API_KEY": "", "TELNYX_FROM_NUMBER": ""}, clear=False):
            with patch("telephony.sms.send_sms") as mock_send_sms:
                mock_send_sms.return_value = {"id": "msg-123", "status": "sent"}
                result = service._send_sms_reminder(
                    campaign_id=1,
                    template_slug="gentle_reminder_sms",
                    borrower_phone="+15551234567",
                    borrower_name="John",
                    document_count=2,
                )
                # send_sms should never be called when not configured
                mock_send_sms.assert_not_called()

        assert result["status"] == "failed"
        assert "not configured" in result["error"]


# =============================================================================
# 4. Call task creation for follow-ups
# =============================================================================

class TestCallTaskCreation:
    """Call task creation for follow-ups."""

    def test_schedule_call_creates_task(self, service, mock_db):
        """Schedule call creates a task record and returns task_id."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (42,)
        mock_db.execute.return_value = mock_result

        result = service._schedule_call(
            campaign_id=1,
            loan_id=200,
            borrower_phone="+15551234567",
            lo_user_id=50,
        )

        assert result["status"] == "sent"
        assert result["task_id"] == 42
        assert result["assigned_to_user_id"] == 50
        assert result["borrower_phone"] == "+15551234567"
        mock_db.execute.assert_called_once()

    def test_schedule_call_no_lo_fails(self, service, mock_db):
        """No loan officer assigned returns failed."""
        result = service._schedule_call(
            campaign_id=1,
            loan_id=200,
            borrower_phone="+15551234567",
            lo_user_id=None,
        )

        assert result["status"] == "failed"
        assert "No loan officer" in result["error"]

    def test_schedule_call_db_error_handled(self, service, mock_db):
        """Database error when creating task is handled gracefully."""
        mock_db.execute.side_effect = Exception("DB connection error")

        result = service._schedule_call(
            campaign_id=1,
            loan_id=200,
            borrower_phone="+15551234567",
            lo_user_id=50,
        )

        assert result["status"] == "failed"
        assert "DB connection error" in result["error"]


# =============================================================================
# 5. Appointment scheduling for document issues
# =============================================================================

class TestAppointmentScheduling:
    """Appointment scheduling for document issues."""

    def test_create_appointment_success(self, service, mock_db):
        """Create appointment returns complete details."""
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._send_appointment_confirmation = MagicMock()

        scheduled_time = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        result = service.create_appointment(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            appointment_type="document_collection",
            title="Document Collection Assistance",
            scheduled_time=scheduled_time,
            duration_minutes=30,
            assigned_to_user_id=50,
            documents_to_discuss=[10, 20],
        )

        assert result["loan_id"] == 200
        assert result["type"] == "document_collection"
        assert result["status"] == "scheduled"
        assert result["duration_minutes"] == 30
        assert result["attendee_name"] == "John Smith"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        service._send_appointment_confirmation.assert_called_once()

    def test_create_appointment_invalid_type_defaults(self, service, mock_db):
        """Invalid appointment type falls back to general_consultation."""
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._send_appointment_confirmation = MagicMock()

        scheduled_time = datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc)

        result = service.create_appointment(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            appointment_type="invalid_type",
            title="General Help",
            scheduled_time=scheduled_time,
        )

        assert result["type"] == "general_consultation"

    def test_offer_appointment_creates_appointment_and_sends_email(self, service, mock_db):
        """_offer_appointment creates a DocumentAppointment and sends email."""
        campaign = _make_campaign(linked_request_ids=[10, 20])
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 10, "title": "W-2"},
            {"request_id": 20, "title": "Bank Statement"},
        ])

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service._offer_appointment(
                campaign_id=1,
                loan_id=200,
                borrower_id=300,
                organization_id=100,
            )

        assert result["status"] == "sent"
        assert result["channel"] == "appointment"
        assert "appointment_id" in result
        mock_db.add.assert_called_once()


# =============================================================================
# 6. Campaign pause/resume functionality
# =============================================================================

class TestCampaignPauseResume:
    """Campaign pause/resume functionality."""

    def test_pause_active_campaign(self, service, mock_db):
        """Pausing an active campaign sets status to PAUSED."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.pause_campaign(1, reason="Borrower requested hold")

        assert result["status"] == "paused"
        assert result["reason"] == "Borrower requested hold"
        assert campaign.status == CampaignStatus.PAUSED

    def test_pause_non_active_campaign_returns_error(self, service, mock_db):
        """Cannot pause a campaign that is not active."""
        campaign = _make_campaign(status=CampaignStatus.COMPLETED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.pause_campaign(1, reason="test")

        assert "error" in result
        assert "not active" in result["error"]

    def test_pause_nonexistent_campaign_returns_error(self, service, mock_db):
        """Pausing nonexistent campaign returns error."""
        service._get_campaign = MagicMock(return_value=None)

        result = service.pause_campaign(999, reason="test")

        assert "error" in result
        assert "not found" in result["error"]

    def test_resume_paused_campaign(self, service, mock_db):
        """Resuming a paused campaign sets status to ACTIVE."""
        campaign = _make_campaign(status=CampaignStatus.PAUSED, cancel_reason="temp hold")
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.resume_campaign(1)

        assert result["status"] == "active"
        assert "next_action_at" in result
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.cancel_reason is None

    def test_resume_non_paused_campaign_returns_error(self, service, mock_db):
        """Cannot resume a campaign that is not paused."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.resume_campaign(1)

        assert "error" in result
        assert "not paused" in result["error"]


# =============================================================================
# 7. Campaign completion when all docs received
# =============================================================================

class TestCampaignCompletionOnDocUpload:
    """Campaign completion when all docs received."""

    def test_handle_document_uploaded_completes_campaign(self, service, mock_db):
        """Uploading the last outstanding doc completes the campaign."""
        campaign = _make_campaign(
            linked_request_ids=[10, 20],
            status=CampaignStatus.ACTIVE,
        )
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        # No outstanding docs after upload
        service._get_outstanding_documents = MagicMock(return_value=[])

        service.handle_document_uploaded(loan_id=200, request_id=10)

        assert campaign.status == CampaignStatus.COMPLETED
        assert campaign.completed_at is not None
        assert campaign.next_action_at is None
        mock_db.flush.assert_called_once()

    def test_handle_document_uploaded_keeps_active_if_docs_remain(self, service, mock_db):
        """Uploading a doc does not complete campaign if others are still outstanding."""
        campaign = _make_campaign(
            linked_request_ids=[10, 20],
            status=CampaignStatus.ACTIVE,
        )
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        # One doc still outstanding
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 20, "title": "Bank Statement"},
        ])

        service.handle_document_uploaded(loan_id=200, request_id=10)

        # Campaign should NOT be completed
        assert campaign.status != CampaignStatus.COMPLETED

    def test_handle_document_uploaded_ignores_unlinked_request(self, service, mock_db):
        """Upload for a request not linked to the campaign is ignored."""
        campaign = _make_campaign(linked_request_ids=[10, 20])
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        # request_id=99 is not in linked_request_ids
        service.handle_document_uploaded(loan_id=200, request_id=99)

        assert campaign.status == CampaignStatus.ACTIVE

    def test_handle_borrower_response_document_uploaded_completes(self, service, mock_db):
        """handle_borrower_response with 'document_uploaded' completes when all docs done."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_outstanding_documents = MagicMock(return_value=[])

        result = service.handle_borrower_response(1, "document_uploaded")

        assert result["status"] == "completed"
        assert campaign.status == CampaignStatus.COMPLETED

    def test_handle_borrower_response_appointment_booked_pauses(self, service, mock_db):
        """handle_borrower_response with 'appointment_booked' pauses campaign."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.handle_borrower_response(1, "appointment_booked")

        assert result["status"] == "paused"
        assert campaign.status == CampaignStatus.PAUSED


# =============================================================================
# 8. Escalation after multiple failed attempts
# =============================================================================

class TestEscalation:
    """Escalation after multiple failed attempts."""

    def test_escalate_to_lo_creates_task_and_emails(self, service, mock_db):
        """Escalation creates a high-priority task and sends email to LO."""
        campaign = _make_campaign(reminders_sent=4)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "W-2 Form"},
        ])

        # Mock query for events timeline
        mock_events_query = MagicMock()
        mock_events_query.filter.return_value = mock_events_query
        mock_events_query.order_by.return_value = mock_events_query
        mock_events_query.all.return_value = [
            _make_event(event_type=FollowupEventType.EMAIL_SENT, channel="email"),
            _make_event(event_type=FollowupEventType.SMS_SENT, channel="sms"),
        ]
        mock_db.query.return_value = mock_events_query

        # Mock task creation
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (99,)
        mock_db.execute.return_value = mock_result

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service._escalate_to_lo(campaign_id=1, loan_id=200)

        assert result["status"] == "sent"
        assert result["channel"] == "escalation"
        assert result["task_id"] == 99
        assert result["lo_user_id"] == 50

    def test_escalate_no_campaign_returns_error(self, service, mock_db):
        """Escalation with missing campaign returns error."""
        service._get_campaign = MagicMock(return_value=None)

        result = service._escalate_to_lo(campaign_id=999, loan_id=200)

        assert result["status"] == "failed"
        assert "not found" in result["error"]

    def test_execute_step_escalation_action(self, service, mock_db):
        """Executing a campaign step with action=escalate_to_lo invokes escalation."""
        campaign = _make_campaign(
            current_step=4,  # Last step of initial_request
            step_config=_DEFAULT_STEP_CONFIGS["initial_request"],
            reminders_sent=4,
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[])
        service._escalate_to_lo = MagicMock(return_value={
            "status": "sent", "channel": "escalation",
            "task_id": 99, "lo_user_id": 50, "lo_email": "lo@co.com",
            "outstanding_document_count": 0,
        })

        result = service.execute_campaign_step(1)

        service._escalate_to_lo.assert_called_once()
        assert result["action"] == "escalate_to_lo"


# =============================================================================
# 9. Template variable substitution
# =============================================================================

class TestTemplateSubstitution:
    """Template variable substitution (borrower name, doc type, due date)."""

    def test_render_template_substitutes_borrower_name(self, service, mock_db):
        """{{borrower_name}} is replaced with actual name."""
        # Mock DB template lookup to return None (use defaults)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service._render_template("initial_request", {
            "borrower_name": "John Smith",
            "document_list": "  - W-2 2025\n  - Bank Statement",
            "document_count": "2",
            "portal_link": "https://portal.example.com/docs/1",
            "lo_name": "Jane Doe",
            "reminder_count": "0",
            "campaign_start_date": "03/10/2026",
            "last_contact_date": "",
            "rejection_details": "",
        })

        assert "John Smith" in result["body"]
        assert "{{borrower_name}}" not in result["body"]
        assert "W-2 2025" in result["body"]
        assert "https://portal.example.com/docs/1" in result["body"]
        assert "Jane Doe" in result["body"]

    def test_render_template_uses_db_template_when_available(self, service, mock_db):
        """DB template takes priority over hardcoded defaults."""
        db_template = MagicMock(spec=FollowupTemplate)
        db_template.subject_template = "Custom: {{borrower_name}}"
        db_template.body_template = "Hello {{borrower_name}}, custom body"
        db_template.usage_count = 5

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = db_template
        mock_db.query.return_value = mock_query

        result = service._render_template("initial_request", {
            "borrower_name": "Alice",
        })

        assert result["subject"] == "Custom: Alice"
        assert result["body"] == "Hello Alice, custom body"
        assert db_template.usage_count == 6

    def test_render_template_fallback_for_unknown_slug(self, service, mock_db):
        """Unknown template slug uses ultimate fallback."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service._render_template("nonexistent_template", {
            "borrower_name": "Bob",
            "portal_link": "https://portal.example.com",
        })

        assert "Bob" in result["body"]
        assert "portal.example.com" in result["body"]
        assert result["subject"] == "Document follow-up"


# =============================================================================
# 10. Follow-up frequency throttling (don't spam)
# =============================================================================

class TestFollowupThrottling:
    """Follow-up frequency throttling via delay_hours in step config."""

    def test_step_config_delay_hours_respected(self, service, mock_db):
        """After executing step, next_action_at is set to now + delay_hours."""
        campaign = _make_campaign(
            current_step=0,
            step_config=_DEFAULT_STEP_CONFIGS["initial_request"],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "W-2"},
        ])

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service.execute_campaign_step(1)

        # After step 1 (email, delay=0), next step is step 2 (sms, delay_hours=48)
        assert result["campaign_completed"] is False
        # campaign.next_action_at should be set ~48 hours from now
        assert campaign.next_action_at is not None
        # current_step should advance from 0 to 1
        assert campaign.current_step == 1

    def test_gentle_reminder_has_48_hour_gap(self):
        """gentle_reminder config has 48h delay between steps."""
        config = _DEFAULT_STEP_CONFIGS["gentle_reminder"]
        assert config[1]["delay_hours"] == 48

    def test_urgent_reminder_has_24_hour_gap(self):
        """urgent_reminder config has 24h delay for step 2."""
        config = _DEFAULT_STEP_CONFIGS["urgent_reminder"]
        assert config[1]["delay_hours"] == 24

    def test_process_pending_only_picks_due_campaigns(self, service, mock_db):
        """process_pending_actions only processes campaigns where next_action_at <= now."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []  # No campaigns are due
        mock_db.query.return_value = mock_query

        result = service.process_pending_actions()

        assert result["processed"] == 0
        assert result["succeeded"] == 0


# =============================================================================
# 11. Business hours enforcement for SMS/calls
# =============================================================================

class TestBusinessHoursEnforcement:
    """Business hours enforcement via _next_business_day for appointments."""

    def test_next_business_day_from_friday(self, service):
        """Friday should advance to Monday."""
        friday = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)  # Friday
        result = service._next_business_day(friday)
        assert result.weekday() == 0  # Monday

    def test_next_business_day_from_saturday(self, service):
        """Saturday should advance to Monday."""
        saturday = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)  # Saturday
        result = service._next_business_day(saturday)
        assert result.weekday() == 0  # Monday

    def test_next_business_day_from_monday(self, service):
        """Monday should advance to Tuesday."""
        monday = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)  # Monday
        result = service._next_business_day(monday)
        assert result.weekday() == 1  # Tuesday

    def test_next_business_day_from_wednesday(self, service):
        """Wednesday should advance to Thursday."""
        wednesday = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)  # Wednesday
        result = service._next_business_day(wednesday)
        assert result.weekday() == 3  # Thursday

    def test_appointment_offer_uses_business_day(self, service, mock_db):
        """_offer_appointment schedules on next business day."""
        campaign = _make_campaign(linked_request_ids=[10])
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 10, "title": "W-2"},
        ])

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service._offer_appointment(
                campaign_id=1,
                loan_id=200,
                borrower_id=300,
                organization_id=100,
            )

        assert result["status"] == "sent"
        # The scheduled_time should be a weekday
        scheduled = datetime.fromisoformat(result["scheduled_time"])
        assert scheduled.weekday() < 5  # Mon-Fri


# =============================================================================
# 12. Campaign cancellation
# =============================================================================

class TestCampaignCancellation:
    """Campaign cancellation."""

    def test_cancel_active_campaign(self, service, mock_db):
        """Cancel an active campaign."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(1, reason="Loan cancelled")

        assert result["status"] == "cancelled"
        assert result["reason"] == "Loan cancelled"
        assert campaign.status == CampaignStatus.CANCELLED
        assert campaign.cancelled_at is not None
        assert campaign.next_action_at is None

    def test_cancel_paused_campaign(self, service, mock_db):
        """Cancel a paused campaign."""
        campaign = _make_campaign(status=CampaignStatus.PAUSED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(1, reason="No longer needed")

        assert result["status"] == "cancelled"
        assert campaign.status == CampaignStatus.CANCELLED

    def test_cancel_completed_campaign_returns_error(self, service, mock_db):
        """Cannot cancel an already completed campaign."""
        campaign = _make_campaign(status=CampaignStatus.COMPLETED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(1, reason="test")

        assert "error" in result
        assert "already" in result["error"]

    def test_cancel_already_cancelled_returns_error(self, service, mock_db):
        """Cannot cancel an already cancelled campaign."""
        campaign = _make_campaign(status=CampaignStatus.CANCELLED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(1, reason="test")

        assert "error" in result
        assert "already" in result["error"]

    def test_cancel_nonexistent_campaign_returns_error(self, service, mock_db):
        """Cancel nonexistent campaign returns error."""
        service._get_campaign = MagicMock(return_value=None)

        result = service.cancel_campaign(999, reason="test")

        assert "error" in result
        assert "not found" in result["error"]


# =============================================================================
# 13. Event delivery tracking (sent, delivered, opened, bounced)
# =============================================================================

class TestEventDeliveryTracking:
    """Event delivery tracking (sent, delivered, opened, bounced)."""

    def test_get_campaign_timeline_returns_events(self, service, mock_db):
        """Campaign timeline returns chronologically ordered events."""
        events = [
            _make_event(id=1, event_type=FollowupEventType.EMAIL_SENT,
                        delivery_status=DeliveryStatus.SENT, step_number=1),
            _make_event(id=2, event_type=FollowupEventType.SMS_SENT,
                        delivery_status=DeliveryStatus.DELIVERED, step_number=2),
            _make_event(id=3, event_type=FollowupEventType.BORROWER_RESPONDED,
                        delivery_status=None, step_number=None,
                        channel="borrower_action"),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = events
        mock_db.query.return_value = mock_query

        timeline = service.get_campaign_timeline(campaign_id=1)

        assert len(timeline) == 3
        assert timeline[0]["event_type"] == "email_sent"
        assert timeline[0]["delivery_status"] == "sent"
        assert timeline[1]["delivery_status"] == "delivered"

    def test_followup_stats_channel_effectiveness(self, service, mock_db):
        """get_followup_stats calculates channel effectiveness correctly."""
        campaigns = [
            _make_campaign(id=1, status=CampaignStatus.COMPLETED, borrower_responded=True,
                           response_date=datetime.now(timezone.utc)),
            _make_campaign(id=2, status=CampaignStatus.ACTIVE, borrower_responded=False),
        ]

        events = [
            _make_event(channel="email", delivery_status=DeliveryStatus.OPENED),
            _make_event(channel="email", delivery_status=DeliveryStatus.CLICKED),
            _make_event(channel="sms", delivery_status=DeliveryStatus.DELIVERED),
            _make_event(channel="sms", delivery_status=DeliveryStatus.FAILED),
        ]

        # First query returns campaigns, second returns events
        query_mock = MagicMock()
        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                # Campaigns query
                q.all.return_value = campaigns
            else:
                # Events query
                q.all.return_value = events
            return q

        mock_db.query.side_effect = query_side_effect

        stats = service.get_followup_stats(organization_id=100, days=30)

        assert stats["total_campaigns"] == 2
        assert stats["completed_campaigns"] == 1
        assert stats["response_count"] == 1
        assert stats["collection_rate"] == 50.0
        assert "email" in stats["channel_stats"]

    def test_execute_step_records_event(self, service, mock_db):
        """Executing a campaign step records a FollowupEvent."""
        campaign = _make_campaign(
            current_step=0,
            step_config=_DEFAULT_STEP_CONFIGS["initial_request"],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[])

        with patch("services.smart_docs.followup_automation_service.EmailService") as MockEmail:
            mock_email_svc = MagicMock()
            mock_email_svc.send_html_email.return_value = True
            MockEmail.return_value = mock_email_svc

            result = service.execute_campaign_step(1)

        # db.add should be called with a FollowupEvent
        assert mock_db.add.called
        assert result["delivery_status"] == "sent"
        assert result["action"] == "send_email"

    def test_execute_step_failed_action_records_failed_event(self, service, mock_db):
        """Failed step action records event with FAILED delivery status."""
        campaign = _make_campaign(
            current_step=0,
            step_config=[{
                "step": 1, "channel": "email", "delay_hours": 0,
                "template": "initial_request", "action": "send_email",
            }],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value={
            **_mock_borrower_info(),
            "borrower_email": "",  # Will cause failure
        })
        service._get_outstanding_documents = MagicMock(return_value=[])

        result = service.execute_campaign_step(1)

        assert result["delivery_status"] == "failed"


# =============================================================================
# 14. Priority-based campaign ordering
# =============================================================================

class TestPriorityOrdering:
    """Priority-based campaign ordering via next_action_at."""

    def test_process_pending_actions_orders_by_next_action_at(self, service, mock_db):
        """Campaigns are processed in next_action_at ascending order."""
        earlier = _make_campaign(id=1, next_action_at=datetime.now(timezone.utc) - timedelta(hours=2))
        later = _make_campaign(id=2, next_action_at=datetime.now(timezone.utc) - timedelta(hours=1))

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [earlier, later]
        mock_db.query.return_value = mock_query

        service.execute_campaign_step = MagicMock(return_value={"status": "ok"})

        result = service.process_pending_actions()

        assert result["processed"] == 2
        # Earlier campaign should be processed first
        calls = service.execute_campaign_step.call_args_list
        assert calls[0] == call(1)
        assert calls[1] == call(2)

    def test_process_pending_actions_limits_batch_to_100(self, service, mock_db):
        """Process at most 100 campaigns per batch."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        service.process_pending_actions()

        # Verify .limit(100) was called
        mock_query.limit.assert_called_with(100)


# =============================================================================
# 15. Multi-tenant campaign isolation
# =============================================================================

class TestMultiTenantIsolation:
    """Multi-tenant campaign isolation."""

    def test_get_active_campaigns_filters_by_org(self, service, mock_db):
        """get_active_campaigns filters by organization_id."""
        org100_campaign = _make_campaign(id=1, organization_id=100)
        org200_campaign = _make_campaign(id=2, organization_id=200)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [org100_campaign]
        mock_db.query.return_value = mock_query

        result = service.get_active_campaigns(organization_id=100)

        assert len(result) == 1
        assert result[0]["campaign_id"] == 1
        # Verify filter was called (with org_id constraint)
        mock_query.filter.assert_called_once()

    def test_get_active_campaigns_filters_by_org_and_loan(self, service, mock_db):
        """get_active_campaigns filters by both org_id and loan_id."""
        campaign = _make_campaign(id=1, organization_id=100, loan_id=200)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        result = service.get_active_campaigns(organization_id=100, loan_id=200)

        assert len(result) == 1
        # filter should be called twice: once for org/status, once for loan_id
        assert mock_query.filter.call_count == 2

    def test_create_campaign_stores_organization_id(self, service, mock_db):
        """Created campaign has organization_id set for tenant isolation."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="initial_request",
            request_ids=[10],
        )

        # The FollowupCampaign added to db should have organization_id=100
        added_campaign = mock_db.add.call_args[0][0]
        assert added_campaign.organization_id == 100

    def test_followup_stats_scoped_to_org(self, service, mock_db):
        """get_followup_stats only returns stats for the specified org."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        stats = service.get_followup_stats(organization_id=100, days=30)

        assert stats["total_campaigns"] == 0
        # The filter should include organization_id constraint
        mock_query.filter.assert_called_once()


# =============================================================================
# ADDITIONAL COVERAGE
# =============================================================================

class TestExecuteCampaignStepEdgeCases:
    """Additional edge cases for execute_campaign_step."""

    def test_execute_step_nonexistent_campaign(self, service, mock_db):
        """Executing step on nonexistent campaign returns error."""
        service._get_campaign = MagicMock(return_value=None)

        result = service.execute_campaign_step(999)

        assert "error" in result
        assert "not found" in result["error"]

    def test_execute_step_on_non_active_campaign(self, service, mock_db):
        """Executing step on paused/completed campaign returns error."""
        campaign = _make_campaign(status=CampaignStatus.PAUSED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.execute_campaign_step(1)

        assert "error" in result
        assert "paused" in result["error"]

    def test_execute_step_all_steps_exhausted(self, service, mock_db):
        """When all steps are exhausted, campaign is completed."""
        campaign = _make_campaign(
            current_step=5,  # Beyond all 5 steps
            total_steps=5,
            step_config=_DEFAULT_STEP_CONFIGS["initial_request"],
        )
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.execute_campaign_step(1)

        assert result["campaign_completed"] is True
        assert campaign.status == CampaignStatus.COMPLETED

    def test_execute_step_unknown_action_skips(self, service, mock_db):
        """Unknown action in step config is skipped gracefully."""
        campaign = _make_campaign(
            current_step=0,
            step_config=[{
                "step": 1, "channel": "carrier_pigeon", "delay_hours": 0,
                "template": "pigeon_msg", "action": "send_pigeon",
            }],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[])

        result = service.execute_campaign_step(1)

        # Should not raise, event should be recorded
        assert result["action"] == "send_pigeon"
        assert mock_db.add.called

    def test_execute_step_exception_in_action_records_failed(self, service, mock_db):
        """Exception during action execution records FAILED delivery status."""
        campaign = _make_campaign(
            current_step=0,
            step_config=[{
                "step": 1, "channel": "sms", "delay_hours": 0,
                "template": "gentle_reminder_sms", "action": "send_sms",
            }],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[])
        service._send_sms_reminder = MagicMock(side_effect=RuntimeError("telnyx down"))

        result = service.execute_campaign_step(1)

        assert result["delivery_status"] == "failed"
        assert "telnyx down" in result["result"]["error"]


class TestGetFollowupServiceFactory:
    """Test the factory function."""

    def test_get_followup_automation_service_returns_instance(self):
        """get_followup_automation_service returns a properly initialized service."""
        mock_db = MagicMock()
        svc = get_followup_automation_service(mock_db)

        assert isinstance(svc, FollowupAutomationService)
        assert svc.db is mock_db


class TestBuildPortalLink:
    """Test portal link construction."""

    def test_build_portal_link_includes_loan_id(self, service):
        """Portal link includes the loan ID."""
        link = service._build_portal_link(200)
        assert link == "https://app.perenniaai.com/portal/documents/200"


class TestCampaignTypeEnumMapping:
    """Test campaign type string to enum mapping."""

    def test_resolve_initial_request(self):
        result = FollowupAutomationService._resolve_campaign_type_enum("initial_request")
        assert result == CampaignType.INITIAL_REQUEST

    def test_resolve_urgent_reminder(self):
        result = FollowupAutomationService._resolve_campaign_type_enum("urgent_reminder")
        assert result == CampaignType.URGENT_REMINDER

    def test_resolve_document_rejected_maps_to_gentle_reminder(self):
        """document_rejected maps to GENTLE_REMINDER enum (fewer enum values than config keys)."""
        result = FollowupAutomationService._resolve_campaign_type_enum("document_rejected")
        assert result == CampaignType.GENTLE_REMINDER

    def test_resolve_unknown_defaults_to_initial_request(self):
        result = FollowupAutomationService._resolve_campaign_type_enum("unknown_type")
        assert result == CampaignType.INITIAL_REQUEST


class TestProcessPendingActionsErrorHandling:
    """Error handling in batch processing."""

    def test_process_pending_exception_in_one_campaign_does_not_stop_others(self, service, mock_db):
        """Exception in one campaign step does not prevent processing others."""
        campaign1 = _make_campaign(id=1)
        campaign2 = _make_campaign(id=2)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [campaign1, campaign2]
        mock_db.query.return_value = mock_query

        call_count = [0]

        def execute_side_effect(campaign_id):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("DB error on campaign 1")
            return {"status": "ok"}

        service.execute_campaign_step = MagicMock(side_effect=execute_side_effect)

        result = service.process_pending_actions()

        assert result["processed"] == 2
        assert result["failed"] == 1
        assert result["succeeded"] == 1

    def test_process_pending_counts_completed_campaigns(self, service, mock_db):
        """Completed campaigns are counted in results."""
        campaign = _make_campaign(id=1)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        service.execute_campaign_step = MagicMock(return_value={
            "campaign_completed": True,
            "status": "ok",
        })

        result = service.process_pending_actions()

        assert result["completed_campaigns"] == 1
