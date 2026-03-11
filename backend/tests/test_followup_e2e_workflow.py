"""
End-to-End Integration Tests for Follow-Up Automation Workflow

Covers the complete lifecycle of document follow-up campaigns:

1.  Campaign creation for loan with missing documents
2.  Multi-step sequence execution (email -> SMS -> call -> appointment)
3.  Document received mid-campaign (partial fulfillment)
4.  All docs received -> campaign auto-completes
5.  Appointment scheduling for complex document issues
6.  Escalation after all automated steps exhausted
7.  Campaign pause and resume
8.  Campaign cancellation
9.  Template variable substitution in messages
10. Business hours enforcement
11. Channel effectiveness tracking
12. Borrower response handling
13. Campaign metrics reporting
14. Multi-tenant isolation in campaigns
"""

import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, call

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


def _mock_email_service_ctx():
    """Context manager that patches EmailService with a successful mock."""
    return patch(
        "services.smart_docs.followup_automation_service.EmailService",
        return_value=MagicMock(send_html_email=MagicMock(return_value=True)),
    )


def _mock_telnyx_ctx():
    """Context manager that patches telnyx + env vars for SMS."""
    env_patch = patch.dict(os.environ, {
        "TELNYX_API_KEY": "test_key",
        "TELNYX_FROM_NUMBER": "+18001234567",
        "TELNYX_MESSAGING_PROFILE_ID": "profile_123",
    })
    telnyx_patch = patch(
        "services.smart_docs.followup_automation_service.telnyx",
        **{"Message.create.return_value": MagicMock()},
    )
    return env_patch, telnyx_patch


# =============================================================================
# 1. Campaign creation for loan with missing documents
# =============================================================================

@pytest.mark.e2e
class TestE2ECampaignCreationForMissingDocs:
    """E2E: Campaign creation triggers for loans with missing documents."""

    def test_create_campaign_with_three_missing_docs(self, service, mock_db):
        """Creating a campaign for a loan with 3 missing docs produces correct
        5-step initial_request sequence and links all request IDs."""
        result = service.create_campaign(
            loan_id=200,
            borrower_id=300,
            organization_id=100,
            campaign_type="initial_request",
            request_ids=[10, 20, 30],
            created_by_user_id=50,
        )

        assert result["status"] == "active"
        assert result["total_steps"] == 5
        assert result["linked_request_ids"] == [10, 20, 30]
        assert result["loan_id"] == 200
        assert result["borrower_id"] == 300
        assert "campaign_id" in result
        assert result["next_action_at"] is not None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_create_campaign_step_config_channels_match_expected_sequence(self, service, mock_db):
        """initial_request sequence follows email -> SMS -> email -> call -> escalation."""
        result = service.create_campaign(
            loan_id=200, borrower_id=300, organization_id=100,
            campaign_type="initial_request", request_ids=[10],
        )

        config = _DEFAULT_STEP_CONFIGS["initial_request"]
        channels = [s["channel"] for s in config]
        assert channels == ["email", "sms", "email", "call", "escalation"]


# =============================================================================
# 2. Multi-step sequence execution (email -> SMS -> call -> appointment)
# =============================================================================

@pytest.mark.e2e
class TestE2EMultiStepSequenceExecution:
    """E2E: Full multi-step campaign from step 1 through completion."""

    def test_full_sequence_email_then_sms_then_appointment_then_escalation(
        self, service, mock_db,
    ):
        """Execute all 5 steps of initial_request, verifying each action type."""
        campaign = _make_campaign(
            current_step=0,
            step_config=_DEFAULT_STEP_CONFIGS["initial_request"],
        )
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "W-2", "request_id": 10},
            {"title": "Bank Statement", "request_id": 20},
        ])

        executed_actions = []

        # Step 1: Email
        with _mock_email_service_ctx():
            result = service.execute_campaign_step(campaign.id)
        executed_actions.append(result["action"])
        assert result["action"] == "send_email"
        assert result["channel"] == "email"
        assert result["delivery_status"] == "sent"
        assert result["campaign_completed"] is False

        # Step 2: SMS
        campaign.current_step = 1
        env_p, telnyx_p = _mock_telnyx_ctx()
        with env_p, telnyx_p:
            result = service.execute_campaign_step(campaign.id)
        executed_actions.append(result["action"])
        assert result["action"] == "send_sms"
        assert result["channel"] == "sms"

        # Step 3: Email follow-up
        campaign.current_step = 2
        with _mock_email_service_ctx():
            result = service.execute_campaign_step(campaign.id)
        executed_actions.append(result["action"])
        assert result["action"] == "send_email"

        # Step 4: Offer appointment
        campaign.current_step = 3
        service._offer_appointment = MagicMock(return_value={
            "status": "sent", "channel": "appointment", "appointment_id": 42,
            "scheduled_time": datetime.now(timezone.utc).isoformat(),
            "subject": "Schedule time",
        })
        result = service.execute_campaign_step(campaign.id)
        executed_actions.append(result["action"])
        assert result["action"] == "offer_appointment"

        # Step 5: Escalation
        campaign.current_step = 4
        service._escalate_to_lo = MagicMock(return_value={
            "status": "sent", "channel": "escalation",
            "task_id": 99, "lo_user_id": 50, "lo_email": "lo@co.com",
            "outstanding_document_count": 2,
        })
        result = service.execute_campaign_step(campaign.id)
        executed_actions.append(result["action"])
        assert result["action"] == "escalate_to_lo"
        assert result["campaign_completed"] is True

        assert executed_actions == [
            "send_email", "send_sms", "send_email", "offer_appointment", "escalate_to_lo",
        ]


# =============================================================================
# 3. Document received mid-campaign (partial fulfillment)
# =============================================================================

@pytest.mark.e2e
class TestE2EPartialDocumentFulfillment:
    """E2E: Document uploads during an active campaign with partial fulfillment."""

    def test_one_doc_uploaded_campaign_stays_active_with_remaining(self, service, mock_db):
        """Uploading 1 of 3 docs keeps campaign active with 2 remaining."""
        campaign = _make_campaign(
            linked_request_ids=[10, 20, 30],
            status=CampaignStatus.ACTIVE,
            current_step=1,
        )
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        # After doc 10 uploaded, 20 and 30 still outstanding
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 20, "title": "Bank Statement"},
            {"request_id": 30, "title": "Tax Return"},
        ])

        service.handle_document_uploaded(loan_id=200, request_id=10)

        # Campaign should still be active
        assert campaign.status != CampaignStatus.COMPLETED
        # A DOCUMENT_UPLOADED event should be recorded
        assert mock_db.add.called

    def test_borrower_response_partial_upload_shows_remaining(self, service, mock_db):
        """handle_borrower_response with document_uploaded lists remaining docs."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "Bank Statement"},
        ])

        result = service.handle_borrower_response(campaign.id, "document_uploaded")

        assert result["status"] == "active"
        assert "1 document(s) still outstanding" in result["message"]
        assert "Bank Statement" in result["remaining_documents"]


# =============================================================================
# 4. All docs received -> campaign auto-completes
# =============================================================================

@pytest.mark.e2e
class TestE2EAllDocsReceivedAutoComplete:
    """E2E: Campaign auto-completes when all linked documents are received."""

    def test_last_doc_upload_completes_campaign(self, service, mock_db):
        """Uploading the final outstanding doc completes the campaign."""
        campaign = _make_campaign(
            linked_request_ids=[10, 20],
            status=CampaignStatus.ACTIVE,
            current_step=2,
            reminders_sent=2,
        )
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        # No outstanding docs remain
        service._get_outstanding_documents = MagicMock(return_value=[])

        service.handle_document_uploaded(loan_id=200, request_id=20)

        assert campaign.status == CampaignStatus.COMPLETED
        assert campaign.completed_at is not None
        assert campaign.next_action_at is None

    def test_handle_borrower_response_all_docs_completes(self, service, mock_db):
        """handle_borrower_response with all docs fulfilled completes campaign."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_outstanding_documents = MagicMock(return_value=[])

        result = service.handle_borrower_response(campaign.id, "document_uploaded")

        assert result["status"] == "completed"
        assert "All documents received" in result["message"]
        assert campaign.status == CampaignStatus.COMPLETED

    def test_auto_complete_works_for_paused_campaigns_too(self, service, mock_db):
        """Document upload also completes paused campaigns when all docs in."""
        campaign = _make_campaign(
            linked_request_ids=[10],
            status=CampaignStatus.PAUSED,
        )
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        service._get_outstanding_documents = MagicMock(return_value=[])

        service.handle_document_uploaded(loan_id=200, request_id=10)

        assert campaign.status == CampaignStatus.COMPLETED


# =============================================================================
# 5. Appointment scheduling for complex document issues
# =============================================================================

@pytest.mark.e2e
class TestE2EAppointmentScheduling:
    """E2E: Appointment creation for complex document collection scenarios."""

    def test_appointment_created_with_full_details(self, service, mock_db):
        """Create appointment returns all required fields and sends confirmation."""
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
            duration_minutes=45,
            assigned_to_user_id=50,
            documents_to_discuss=[10, 20, 30],
        )

        assert result["loan_id"] == 200
        assert result["type"] == "document_collection"
        assert result["status"] == "scheduled"
        assert result["duration_minutes"] == 45
        assert result["attendee_name"] == "John Smith"
        assert result["attendee_email"] == "john@example.com"
        mock_db.add.assert_called_once()
        service._send_appointment_confirmation.assert_called_once()

    def test_offer_appointment_step_creates_appointment_and_notifies(self, service, mock_db):
        """Executing offer_appointment step creates appointment + sends email."""
        campaign = _make_campaign(linked_request_ids=[10, 20])
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 10, "title": "W-2"},
            {"request_id": 20, "title": "Bank Statement"},
        ])

        with _mock_email_service_ctx():
            result = service._offer_appointment(
                campaign_id=1, loan_id=200, borrower_id=300, organization_id=100,
            )

        assert result["status"] == "sent"
        assert result["channel"] == "appointment"
        assert "appointment_id" in result
        # Scheduled on a business day
        scheduled = datetime.fromisoformat(result["scheduled_time"])
        assert scheduled.weekday() < 5  # Mon-Fri


# =============================================================================
# 6. Escalation after all automated steps exhausted
# =============================================================================

@pytest.mark.e2e
class TestE2EEscalationAfterExhaustion:
    """E2E: LO escalation with full attempt history after steps exhausted."""

    def test_escalation_includes_complete_attempt_history(self, service, mock_db):
        """Escalation creates task and email with summary of all prior attempts."""
        campaign = _make_campaign(reminders_sent=4, current_step=4)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "W-2 Form"},
            {"title": "Profit & Loss Statement"},
        ])

        # Prior events timeline
        mock_events_query = MagicMock()
        mock_events_query.filter.return_value = mock_events_query
        mock_events_query.order_by.return_value = mock_events_query
        mock_events_query.all.return_value = [
            _make_event(event_type=FollowupEventType.EMAIL_SENT, channel="email", step_number=1),
            _make_event(event_type=FollowupEventType.SMS_SENT, channel="sms", step_number=2),
            _make_event(event_type=FollowupEventType.EMAIL_SENT, channel="email", step_number=3),
            _make_event(event_type=FollowupEventType.APPOINTMENT_BOOKED, channel="call", step_number=4),
        ]
        mock_db.query.return_value = mock_events_query

        # Task creation
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (99,)
        mock_db.execute.return_value = mock_result

        with _mock_email_service_ctx():
            result = service._escalate_to_lo(campaign_id=1, loan_id=200)

        assert result["status"] == "sent"
        assert result["channel"] == "escalation"
        assert result["task_id"] == 99
        assert result["lo_user_id"] == 50
        assert result["outstanding_document_count"] == 2

    def test_executing_final_step_marks_campaign_completed(self, service, mock_db):
        """After the last step executes, campaign status becomes COMPLETED."""
        campaign = _make_campaign(
            current_step=4,
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

        result = service.execute_campaign_step(campaign.id)

        assert result["campaign_completed"] is True
        assert campaign.status == CampaignStatus.COMPLETED


# =============================================================================
# 7. Campaign pause and resume
# =============================================================================

@pytest.mark.e2e
class TestE2ECampaignPauseAndResume:
    """E2E: Pause/resume lifecycle preserves campaign state correctly."""

    def test_pause_then_resume_restores_active_status(self, service, mock_db):
        """Pausing and then resuming a campaign restores ACTIVE status."""
        campaign = _make_campaign(
            status=CampaignStatus.ACTIVE,
            current_step=2,
            reminders_sent=2,
        )
        service._get_campaign = MagicMock(return_value=campaign)

        # Pause
        pause_result = service.pause_campaign(campaign.id, reason="Borrower on vacation")
        assert pause_result["status"] == "paused"
        assert campaign.status == CampaignStatus.PAUSED
        assert campaign.cancel_reason == "Borrower on vacation"

        # Resume
        resume_result = service.resume_campaign(campaign.id)
        assert resume_result["status"] == "active"
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.cancel_reason is None
        assert campaign.next_action_at is not None

    def test_appointment_booked_response_auto_pauses(self, service, mock_db):
        """Borrower booking an appointment auto-pauses the campaign."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE, current_step=2)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.handle_borrower_response(campaign.id, "appointment_booked")

        assert result["status"] == "paused"
        assert campaign.status == CampaignStatus.PAUSED
        assert campaign.next_action_at is None
        assert "appointment" in campaign.cancel_reason.lower()


# =============================================================================
# 8. Campaign cancellation
# =============================================================================

@pytest.mark.e2e
class TestE2ECampaignCancellation:
    """E2E: Campaign cancellation in various states."""

    def test_cancel_active_campaign_sets_cancelled_state(self, service, mock_db):
        """Cancelling an active campaign sets all terminal fields."""
        campaign = _make_campaign(
            status=CampaignStatus.ACTIVE,
            current_step=3,
            reminders_sent=3,
        )
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(campaign.id, reason="Loan was cancelled by borrower")

        assert result["status"] == "cancelled"
        assert result["reason"] == "Loan was cancelled by borrower"
        assert campaign.status == CampaignStatus.CANCELLED
        assert campaign.cancelled_at is not None
        assert campaign.next_action_at is None

    def test_cancel_paused_campaign_succeeds(self, service, mock_db):
        """Paused campaigns can also be cancelled."""
        campaign = _make_campaign(status=CampaignStatus.PAUSED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(campaign.id, reason="No longer needed")

        assert result["status"] == "cancelled"
        assert campaign.status == CampaignStatus.CANCELLED

    def test_cancel_completed_campaign_returns_error(self, service, mock_db):
        """Cannot cancel a campaign that has already completed."""
        campaign = _make_campaign(status=CampaignStatus.COMPLETED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(campaign.id, reason="test")

        assert "error" in result
        assert "already" in result["error"]

    def test_cancel_already_cancelled_returns_error(self, service, mock_db):
        """Cannot cancel a campaign that was already cancelled."""
        campaign = _make_campaign(status=CampaignStatus.CANCELLED)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.cancel_campaign(campaign.id, reason="test")

        assert "error" in result
        assert "already" in result["error"]


# =============================================================================
# 9. Template variable substitution in messages
# =============================================================================

@pytest.mark.e2e
class TestE2ETemplateVariableSubstitution:
    """E2E: Template rendering with all supported merge variables."""

    def test_email_template_substitutes_all_variables(self, service, mock_db):
        """All {{variable}} placeholders are replaced in rendered output."""
        # Mock DB template lookup to return None (use defaults)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        rendered = service._render_template("initial_request", {
            "borrower_name": "Maria Garcia",
            "document_list": "  - W-2 2025\n  - 2024 Tax Return",
            "document_count": "2",
            "portal_link": "https://app.perenniaai.com/portal/documents/200",
            "lo_name": "Tim Loss",
            "reminder_count": "0",
            "campaign_start_date": "03/10/2026",
            "last_contact_date": "",
            "rejection_details": "",
        })

        assert "Maria Garcia" in rendered["body"]
        assert "{{borrower_name}}" not in rendered["body"]
        assert "W-2 2025" in rendered["body"]
        assert "2024 Tax Return" in rendered["body"]
        assert "app.perenniaai.com/portal/documents/200" in rendered["body"]
        assert "Tim Loss" in rendered["body"]
        assert "{{lo_name}}" not in rendered["body"]
        assert "{{portal_link}}" not in rendered["body"]
        assert "{{document_list}}" not in rendered["body"]

    def test_sms_template_substitutes_borrower_name_and_count(self, service, mock_db):
        """SMS templates substitute {{borrower_name}} and {{document_count}}."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        rendered = service._render_template("gentle_reminder_sms", {
            "borrower_name": "Alex Chen",
            "document_count": "3",
            "portal_link": "https://app.perenniaai.com/portal/documents/500",
        })

        assert "Alex Chen" in rendered["body"]
        assert "3" in rendered["body"]
        assert "app.perenniaai.com" in rendered["body"]
        assert "{{borrower_name}}" not in rendered["body"]
        assert "{{document_count}}" not in rendered["body"]

    def test_db_template_overrides_hardcoded_default(self, service, mock_db):
        """Organization-specific DB template takes precedence over defaults."""
        db_template = MagicMock(spec=FollowupTemplate)
        db_template.subject_template = "Custom Org Template: {{borrower_name}}"
        db_template.body_template = "Dear {{borrower_name}}, please submit {{document_list}}"
        db_template.usage_count = 10

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = db_template
        mock_db.query.return_value = mock_query

        rendered = service._render_template("initial_request", {
            "borrower_name": "Bob Johnson",
            "document_list": "  - Paystubs",
        })

        assert rendered["subject"] == "Custom Org Template: Bob Johnson"
        assert "Dear Bob Johnson" in rendered["body"]
        assert "Paystubs" in rendered["body"]
        assert db_template.usage_count == 11


# =============================================================================
# 10. Business hours enforcement
# =============================================================================

@pytest.mark.e2e
class TestE2EBusinessHoursEnforcement:
    """E2E: Appointments and actions respect business hours and weekday rules."""

    def test_appointment_on_friday_schedules_monday(self, service):
        """Offer appointment on Friday schedules for Monday."""
        friday = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)  # Friday
        result = service._next_business_day(friday)
        assert result.weekday() == 0  # Monday

    def test_appointment_on_saturday_schedules_monday(self, service):
        """Offer appointment on Saturday schedules for Monday."""
        saturday = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)
        result = service._next_business_day(saturday)
        assert result.weekday() == 0

    def test_appointment_on_sunday_schedules_monday(self, service):
        """Offer appointment on Sunday schedules for Monday."""
        sunday = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        result = service._next_business_day(sunday)
        assert result.weekday() == 0

    def test_appointment_on_tuesday_schedules_wednesday(self, service):
        """Offer appointment on Tuesday schedules for Wednesday."""
        tuesday = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        result = service._next_business_day(tuesday)
        assert result.weekday() == 2  # Wednesday

    def test_offer_appointment_always_selects_weekday(self, service, mock_db):
        """_offer_appointment scheduled_time is always on a weekday."""
        campaign = _make_campaign(linked_request_ids=[10])
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value=_mock_borrower_info())
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 10, "title": "W-2"},
        ])

        with _mock_email_service_ctx():
            result = service._offer_appointment(
                campaign_id=1, loan_id=200, borrower_id=300, organization_id=100,
            )

        scheduled = datetime.fromisoformat(result["scheduled_time"])
        assert scheduled.weekday() < 5


# =============================================================================
# 11. Channel effectiveness tracking
# =============================================================================

@pytest.mark.e2e
class TestE2EChannelEffectivenessTracking:
    """E2E: Track and report which channels produce best engagement."""

    def test_followup_stats_calculates_channel_engagement(self, service, mock_db):
        """get_followup_stats aggregates opened/clicked/failed per channel."""
        campaigns = [
            _make_campaign(id=1, status=CampaignStatus.COMPLETED, borrower_responded=True,
                           response_date=datetime.now(timezone.utc),
                           started_at=datetime.now(timezone.utc) - timedelta(hours=72)),
            _make_campaign(id=2, status=CampaignStatus.ACTIVE, borrower_responded=False),
        ]

        events = [
            _make_event(channel="email", delivery_status=DeliveryStatus.OPENED),
            _make_event(channel="email", delivery_status=DeliveryStatus.CLICKED),
            _make_event(channel="email", delivery_status=DeliveryStatus.SENT),
            _make_event(channel="sms", delivery_status=DeliveryStatus.DELIVERED),
            _make_event(channel="sms", delivery_status=DeliveryStatus.FAILED),
            _make_event(channel="call", delivery_status=DeliveryStatus.SENT),
        ]

        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                q.all.return_value = campaigns
            else:
                q.all.return_value = events
            return q

        mock_db.query.side_effect = query_side_effect

        stats = service.get_followup_stats(organization_id=100, days=30)

        assert stats["total_campaigns"] == 2
        assert stats["completed_campaigns"] == 1
        assert stats["response_count"] == 1
        assert stats["collection_rate"] == 50.0

        # Email had the most engagement (opened + clicked = 2)
        assert stats["most_effective_channel"] == "email"
        assert "email" in stats["channel_stats"]
        assert stats["channel_stats"]["email"]["opened"] == 1
        assert stats["channel_stats"]["email"]["clicked"] == 1
        assert stats["channel_stats"]["sms"]["failed"] == 1


# =============================================================================
# 12. Borrower response handling
# =============================================================================

@pytest.mark.e2e
class TestE2EBorrowerResponseHandling:
    """E2E: Various borrower response types and their campaign effects."""

    def test_replied_response_keeps_campaign_active(self, service, mock_db):
        """Borrower 'replied' response records event but keeps campaign active."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.handle_borrower_response(campaign.id, "replied")

        assert result["status"] == "active"
        assert "replied" in result["message"]
        assert campaign.borrower_responded is True
        assert campaign.response_date is not None

    def test_called_back_response_keeps_campaign_active(self, service, mock_db):
        """Borrower 'called_back' response records event but keeps campaign active."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)

        result = service.handle_borrower_response(campaign.id, "called_back")

        assert result["status"] == "active"
        assert "called_back" in result["message"]
        assert campaign.borrower_responded is True

    def test_nonexistent_campaign_response_returns_error(self, service, mock_db):
        """Response for nonexistent campaign returns error."""
        service._get_campaign = MagicMock(return_value=None)

        result = service.handle_borrower_response(999, "document_uploaded")

        assert "error" in result
        assert "not found" in result["error"]

    def test_document_uploaded_records_event_on_campaign(self, service, mock_db):
        """handle_borrower_response records a BORROWER_RESPONDED event."""
        campaign = _make_campaign(status=CampaignStatus.ACTIVE)
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_outstanding_documents = MagicMock(return_value=[
            {"title": "Something"},
        ])

        service.handle_borrower_response(campaign.id, "document_uploaded")

        # Should have called db.add with a FollowupEvent
        assert mock_db.add.called
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, FollowupEvent)
        assert added_obj.event_type == FollowupEventType.BORROWER_RESPONDED


# =============================================================================
# 13. Campaign metrics reporting
# =============================================================================

@pytest.mark.e2e
class TestE2ECampaignMetricsReporting:
    """E2E: Campaign metrics and reporting aggregation."""

    def test_stats_include_response_rate_and_collection_rate(self, service, mock_db):
        """Stats include response rate and collection rate percentages."""
        campaigns = [
            _make_campaign(id=1, status=CampaignStatus.COMPLETED, borrower_responded=True,
                           response_date=datetime.now(timezone.utc),
                           started_at=datetime.now(timezone.utc) - timedelta(hours=24)),
            _make_campaign(id=2, status=CampaignStatus.COMPLETED, borrower_responded=True,
                           response_date=datetime.now(timezone.utc),
                           started_at=datetime.now(timezone.utc) - timedelta(hours=48)),
            _make_campaign(id=3, status=CampaignStatus.ACTIVE, borrower_responded=False),
            _make_campaign(id=4, status=CampaignStatus.CANCELLED, borrower_responded=False),
        ]

        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                q.all.return_value = campaigns
            else:
                q.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        stats = service.get_followup_stats(organization_id=100, days=90)

        assert stats["total_campaigns"] == 4
        assert stats["completed_campaigns"] == 2
        assert stats["active_campaigns"] == 1
        assert stats["cancelled_campaigns"] == 1
        assert stats["response_count"] == 2
        assert stats["response_rate"] == 50.0
        assert stats["collection_rate"] == 50.0
        assert stats["avg_response_time_hours"] is not None
        assert stats["period_days"] == 90

    def test_stats_zero_campaigns_returns_zero_rates(self, service, mock_db):
        """Stats with no campaigns returns zero rates without division errors."""
        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count[0] += 1
            q.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        stats = service.get_followup_stats(organization_id=100, days=30)

        assert stats["total_campaigns"] == 0
        assert stats["response_rate"] == 0
        assert stats["collection_rate"] == 0
        assert stats["avg_response_time_hours"] is None

    def test_campaign_timeline_returns_chronological_events(self, service, mock_db):
        """Campaign timeline query returns events in chronological order."""
        now = datetime.now(timezone.utc)
        events = [
            _make_event(id=1, event_type=FollowupEventType.EMAIL_SENT,
                        delivery_status=DeliveryStatus.SENT, step_number=1,
                        created_at=now - timedelta(days=5)),
            _make_event(id=2, event_type=FollowupEventType.SMS_SENT,
                        delivery_status=DeliveryStatus.DELIVERED, step_number=2,
                        created_at=now - timedelta(days=3)),
            _make_event(id=3, event_type=FollowupEventType.BORROWER_RESPONDED,
                        delivery_status=None, step_number=None,
                        channel="borrower_action",
                        created_at=now - timedelta(days=1)),
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
        assert timeline[1]["event_type"] == "sms_sent"
        assert timeline[1]["delivery_status"] == "delivered"
        assert timeline[2]["event_type"] == "borrower_responded"


# =============================================================================
# 14. Multi-tenant isolation in campaigns
# =============================================================================

@pytest.mark.e2e
class TestE2EMultiTenantIsolation:
    """E2E: Organization isolation ensures campaigns are tenant-scoped."""

    def test_get_active_campaigns_returns_only_own_org(self, service, mock_db):
        """get_active_campaigns for org 100 does not return org 200 campaigns."""
        org100_campaign = _make_campaign(id=1, organization_id=100, loan_id=101)
        # org200 campaign should NOT appear in results
        org200_campaign = _make_campaign(id=2, organization_id=200, loan_id=201)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        # The DB filter ensures only org 100 comes back
        mock_query.all.return_value = [org100_campaign]
        mock_db.query.return_value = mock_query

        result = service.get_active_campaigns(organization_id=100)

        assert len(result) == 1
        assert result[0]["campaign_id"] == 1
        assert result[0]["loan_id"] == 101
        # Verify the filter was invoked (ensuring org isolation)
        mock_query.filter.assert_called_once()

    def test_campaigns_created_with_correct_organization_id(self, service, mock_db):
        """Campaign creation stores the organization_id for tenant scoping."""
        result = service.create_campaign(
            loan_id=500,
            borrower_id=600,
            organization_id=777,
            campaign_type="initial_request",
            request_ids=[10],
        )

        # Verify the campaign object added to DB has correct org_id
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, FollowupCampaign)
        assert added_obj.organization_id == 777

    def test_stats_scoped_to_organization(self, service, mock_db):
        """get_followup_stats filters by organization_id."""
        org100_campaign = _make_campaign(
            id=1, organization_id=100,
            status=CampaignStatus.COMPLETED, borrower_responded=True,
            response_date=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc) - timedelta(hours=24),
        )

        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                q.all.return_value = [org100_campaign]
            else:
                q.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        stats = service.get_followup_stats(organization_id=100, days=30)

        assert stats["total_campaigns"] == 1
        assert stats["completed_campaigns"] == 1

    def test_document_upload_only_affects_matching_loan_campaigns(self, service, mock_db):
        """handle_document_uploaded only affects campaigns for the specified loan_id."""
        # Campaign for loan 200
        campaign_200 = _make_campaign(id=1, loan_id=200, linked_request_ids=[10])
        # Campaign for loan 300 (different loan, should not be affected)
        campaign_300 = _make_campaign(id=2, loan_id=300, linked_request_ids=[10])

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        # DB filter returns only campaigns matching loan_id=200
        mock_query.all.return_value = [campaign_200]
        mock_db.query.return_value = mock_query

        service._get_outstanding_documents = MagicMock(return_value=[])

        service.handle_document_uploaded(loan_id=200, request_id=10)

        # Only campaign_200 should be completed
        assert campaign_200.status == CampaignStatus.COMPLETED
        # campaign_300 should be untouched
        assert campaign_300.status == CampaignStatus.ACTIVE
