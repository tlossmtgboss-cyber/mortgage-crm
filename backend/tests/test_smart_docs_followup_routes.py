"""
Tests for Smart Docs Follow-Up & Appointment Scheduling Routes

Covers:
    - Campaign CRUD: create, list, detail, pause, resume, cancel, events, response
    - Appointment CRUD: create, list, update (confirm, cancel, reschedule, complete, no-show)
    - Template CRUD: list, create, update
    - Admin: process-pending, stats
    - Tenant isolation verification
    - Input validation edge cases
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy import text

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


# ============================================================================
# Constants
# ============================================================================

PREFIX = "/api/smart-docs"


# ============================================================================
# Helpers
# ============================================================================

def _seed_loan(db, loan_id=100, organization_id=1):
    """Insert a minimal loan row for tenant verification."""
    db.execute(
        text(
            "INSERT OR IGNORE INTO loans (id, organization_id, loan_number, stage) "
            "VALUES (:id, :org, :num, 'PROCESSING')"
        ),
        {"id": loan_id, "org": organization_id, "num": f"TST-{loan_id}"},
    )
    db.flush()


def _seed_campaign(
    db,
    loan_id=100,
    organization_id=1,
    status=CampaignStatus.ACTIVE,
    campaign_type=CampaignType.INITIAL_REQUEST,
    current_step=0,
    next_action_at=None,
    step_config=None,
    max_reminders=5,
    reminders_sent=0,
    borrower_responded=False,
):
    """Insert a FollowupCampaign and return it."""
    campaign = FollowupCampaign(
        organization_id=organization_id,
        loan_id=loan_id,
        campaign_type=campaign_type,
        status=status,
        total_steps=3,
        current_step=current_step,
        step_config=step_config or [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder_sms"},
            {"step": 3, "channel": "email", "delay_hours": 96, "template": "second_reminder"},
        ],
        max_reminders=max_reminders,
        reminders_sent=reminders_sent,
        borrower_responded=borrower_responded,
        started_at=datetime.now(timezone.utc),
        next_action_at=next_action_at,
    )
    db.add(campaign)
    db.flush()
    return campaign


def _seed_appointment(
    db,
    loan_id=100,
    organization_id=1,
    status=AppointmentStatus.SCHEDULED,
    title="Doc Review",
):
    """Insert a DocumentAppointment and return it."""
    now = datetime.now(timezone.utc)
    appointment = DocumentAppointment(
        organization_id=organization_id,
        loan_id=loan_id,
        appointment_type=AppointmentType.DOCUMENT_REVIEW,
        title=title,
        status=status,
        scheduled_date=now.date(),
        scheduled_time_start=now + timedelta(hours=2),
        duration_minutes=30,
    )
    db.add(appointment)
    db.flush()
    return appointment


def _seed_template(
    db,
    organization_id=1,
    slug="test-template",
    is_default=False,
    is_active=True,
    channel="email",
):
    """Insert a FollowupTemplate and return it."""
    template = FollowupTemplate(
        organization_id=organization_id,
        name="Test Template",
        slug=slug,
        channel=channel,
        category="initial",
        subject_template="Subject: {{borrower_name}}",
        body_template="Hello {{borrower_name}}, please upload your docs.",
        variables=["borrower_name"],
        is_default=is_default,
        is_active=is_active,
    )
    db.add(template)
    db.flush()
    return template


# ============================================================================
# Campaign Tests
# ============================================================================


class TestCreateCampaign:
    """POST /api/smart-docs/followup/campaigns"""

    def test_create_campaign_success(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=100, organization_id=1)
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 100,
                "campaign_type": "INITIAL_REQUEST",
                "trigger_source": "manual",
                "max_reminders": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["campaign_type"] == "initial_request"
        assert data["status"] == "active"
        assert data["max_reminders"] == 3
        assert data["total_steps"] == 3  # default step config has 3 steps
        assert data["current_step"] == 0
        assert data["next_action_at"] is not None

    def test_create_campaign_custom_steps(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=101, organization_id=1)
        custom_steps = [
            {"step": 1, "channel": "sms", "delay_hours": 0, "template": "custom_sms"},
        ]
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 101,
                "campaign_type": "GENTLE_REMINDER",
                "step_config": custom_steps,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] == 1
        assert data["step_config"] == custom_steps

    def test_create_campaign_invalid_type(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=102, organization_id=1)
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 102,
                "campaign_type": "BOGUS_TYPE",
            },
        )
        assert resp.status_code == 400
        assert "Invalid campaign_type" in resp.json()["detail"]

    def test_create_campaign_escalation_alias(self, authenticated_client, db_session):
        """DOCUMENT_REJECTED and DOCUMENT_EXPIRED should map to ESCALATION type."""
        _seed_loan(db_session, loan_id=103, organization_id=1)
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 103,
                "campaign_type": "DOCUMENT_REJECTED",
                "trigger_source": "document_rejected",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_type"] == "escalation"
        assert data["trigger_source"] == "document_rejected"


class TestListCampaigns:
    """GET /api/smart-docs/followup/campaigns"""

    def test_list_campaigns_for_loan(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=200, organization_id=1)
        _seed_campaign(db_session, loan_id=200, organization_id=1)
        _seed_campaign(db_session, loan_id=200, organization_id=1, status=CampaignStatus.COMPLETED)

        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns", params={"loan_id": 200})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["campaigns"]) == 2

    def test_list_campaigns_filter_status(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=201, organization_id=1)
        _seed_campaign(db_session, loan_id=201, organization_id=1, status=CampaignStatus.ACTIVE)
        _seed_campaign(db_session, loan_id=201, organization_id=1, status=CampaignStatus.COMPLETED)

        resp = authenticated_client.get(
            f"{PREFIX}/followup/campaigns",
            params={"loan_id": 201, "status": "active"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["campaigns"][0]["status"] == "active"

    def test_list_campaigns_invalid_status(self, authenticated_client, db_session):
        resp = authenticated_client.get(
            f"{PREFIX}/followup/campaigns",
            params={"status": "nonexistent"},
        )
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]


class TestCampaignDetail:
    """GET /api/smart-docs/followup/campaigns/{campaign_id}"""

    def test_get_campaign_detail_with_events(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=300, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=300, organization_id=1)

        # Add an event
        event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.EMAIL_SENT,
            step_number=1,
            channel="email",
            template_used="initial_request",
            delivery_status=DeliveryStatus.SENT,
        )
        db_session.add(event)
        db_session.flush()

        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns/{campaign.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == campaign.id
        assert data["event_count"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "email_sent"

    def test_get_campaign_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns/99999")
        assert resp.status_code == 404


class TestPauseCampaign:
    """POST /api/smart-docs/followup/campaigns/{campaign_id}/pause"""

    def test_pause_active_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=400, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=400, organization_id=1, status=CampaignStatus.ACTIVE)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/pause",
            json={"reason": "Borrower called to discuss"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "paused"

    def test_pause_non_active_campaign_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=401, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=401, organization_id=1, status=CampaignStatus.COMPLETED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/pause",
            json={"reason": "test"},
        )
        assert resp.status_code == 400
        assert "Only active campaigns" in resp.json()["detail"]


class TestResumeCampaign:
    """POST /api/smart-docs/followup/campaigns/{campaign_id}/resume"""

    def test_resume_paused_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=500, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=500, organization_id=1, status=CampaignStatus.PAUSED)

        resp = authenticated_client.post(f"{PREFIX}/followup/campaigns/{campaign.id}/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    def test_resume_non_paused_campaign_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=501, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=501, organization_id=1, status=CampaignStatus.ACTIVE)

        resp = authenticated_client.post(f"{PREFIX}/followup/campaigns/{campaign.id}/resume")
        assert resp.status_code == 400
        assert "Only paused campaigns" in resp.json()["detail"]


class TestCancelCampaign:
    """POST /api/smart-docs/followup/campaigns/{campaign_id}/cancel"""

    def test_cancel_active_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=600, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=600, organization_id=1, status=CampaignStatus.ACTIVE)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/cancel",
            json={"reason": "Borrower withdrew application"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"

    def test_cancel_already_cancelled_campaign_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=601, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=601, organization_id=1, status=CampaignStatus.CANCELLED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/cancel",
            json={"reason": "double cancel"},
        )
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_cancel_completed_campaign_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=602, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=602, organization_id=1, status=CampaignStatus.COMPLETED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/cancel",
            json={"reason": "too late"},
        )
        assert resp.status_code == 400


class TestCampaignEvents:
    """GET /api/smart-docs/followup/campaigns/{campaign_id}/events"""

    def test_get_campaign_events(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=700, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=700, organization_id=1)

        for i in range(3):
            db_session.add(FollowupEvent(
                campaign_id=campaign.id,
                event_type=FollowupEventType.EMAIL_SENT,
                step_number=i + 1,
                channel="email",
            ))
        db_session.flush()

        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns/{campaign.id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["campaign_id"] == campaign.id


class TestRecordBorrowerResponse:
    """POST /api/smart-docs/followup/campaigns/{campaign_id}/response"""

    def test_record_uploaded_response_completes_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=800, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=800, organization_id=1)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/response",
            json={"response_type": "uploaded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "uploaded"
        assert data["campaign_status"] == "completed"

    def test_record_called_back_keeps_campaign_active(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=801, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=801, organization_id=1)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/response",
            json={"response_type": "called_back"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_status"] == "active"

    def test_record_invalid_response_type(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=802, organization_id=1)
        campaign = _seed_campaign(db_session, loan_id=802, organization_id=1)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/response",
            json={"response_type": "invalid_type"},
        )
        assert resp.status_code == 400
        assert "Invalid response_type" in resp.json()["detail"]


# ============================================================================
# Appointment Tests
# ============================================================================


class TestCreateAppointment:
    """POST /api/smart-docs/followup/appointments"""

    def test_create_appointment_success(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=900, organization_id=1)
        start_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments",
            json={
                "loan_id": 900,
                "appointment_type": "DOCUMENT_REVIEW",
                "title": "Review income documents",
                "scheduled_time_start": start_time,
                "duration_minutes": 45,
                "location_type": "video_call",
                "attendee_name": "John Smith",
                "attendee_email": "john@example.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 900
        assert data["appointment_type"] == "document_review"
        assert data["status"] == "scheduled"
        assert data["title"] == "Review income documents"
        assert data["duration_minutes"] == 45
        assert data["location_type"] == "video_call"
        assert data["attendee_name"] == "John Smith"

    def test_create_appointment_invalid_type(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=901, organization_id=1)
        start_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments",
            json={
                "loan_id": 901,
                "appointment_type": "INVALID_TYPE",
                "title": "Test",
                "scheduled_time_start": start_time,
            },
        )
        assert resp.status_code == 400
        assert "Invalid appointment_type" in resp.json()["detail"]

    def test_create_appointment_invalid_location_type(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=902, organization_id=1)
        start_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments",
            json={
                "loan_id": 902,
                "appointment_type": "DOCUMENT_REVIEW",
                "title": "Test",
                "scheduled_time_start": start_time,
                "location_type": "teleport",
            },
        )
        assert resp.status_code == 400
        assert "Invalid location_type" in resp.json()["detail"]


class TestListAppointments:
    """GET /api/smart-docs/followup/appointments"""

    def test_list_appointments_for_loan(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1000, organization_id=1)
        _seed_appointment(db_session, loan_id=1000, organization_id=1, title="Appt 1")
        _seed_appointment(db_session, loan_id=1000, organization_id=1, title="Appt 2")

        resp = authenticated_client.get(
            f"{PREFIX}/followup/appointments",
            params={"loan_id": 1000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_appointments_filter_status(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1001, organization_id=1)
        _seed_appointment(db_session, loan_id=1001, organization_id=1, status=AppointmentStatus.SCHEDULED)
        _seed_appointment(db_session, loan_id=1001, organization_id=1, status=AppointmentStatus.COMPLETED)

        resp = authenticated_client.get(
            f"{PREFIX}/followup/appointments",
            params={"loan_id": 1001, "status": "scheduled"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["appointments"][0]["status"] == "scheduled"

    def test_list_appointments_invalid_status(self, authenticated_client, db_session):
        resp = authenticated_client.get(
            f"{PREFIX}/followup/appointments",
            params={"status": "bogus"},
        )
        assert resp.status_code == 400


class TestConfirmAppointment:
    """POST /api/smart-docs/followup/appointments/{id}/confirm"""

    def test_confirm_scheduled_appointment(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1100, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1100, status=AppointmentStatus.SCHEDULED)

        resp = authenticated_client.post(f"{PREFIX}/followup/appointments/{appt.id}/confirm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_confirm_already_confirmed_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1101, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1101, status=AppointmentStatus.CONFIRMED)

        resp = authenticated_client.post(f"{PREFIX}/followup/appointments/{appt.id}/confirm")
        assert resp.status_code == 400


class TestCancelAppointment:
    """POST /api/smart-docs/followup/appointments/{id}/cancel"""

    def test_cancel_scheduled_appointment(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1200, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1200, status=AppointmentStatus.SCHEDULED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/cancel",
            json={"reason": "Borrower unavailable"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"

    def test_cancel_completed_appointment_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1201, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1201, status=AppointmentStatus.COMPLETED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/cancel",
            json={"reason": "test"},
        )
        assert resp.status_code == 400

    def test_cancel_no_show_appointment_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1202, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1202, status=AppointmentStatus.NO_SHOW)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/cancel",
            json={"reason": "test"},
        )
        assert resp.status_code == 400


class TestRescheduleAppointment:
    """POST /api/smart-docs/followup/appointments/{id}/reschedule"""

    def test_reschedule_appointment_creates_new(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1300, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1300, status=AppointmentStatus.SCHEDULED)
        new_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/reschedule",
            json={
                "new_start_time": new_time,
                "reason": "Borrower requested different time",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_appointment_id"] == appt.id
        assert data["new_appointment"]["status"] == "scheduled"
        assert data["new_appointment"]["rescheduled_from_id"] == appt.id
        assert data["new_appointment"]["id"] != appt.id

    def test_reschedule_completed_appointment_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1301, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1301, status=AppointmentStatus.COMPLETED)
        new_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/reschedule",
            json={"new_start_time": new_time},
        )
        assert resp.status_code == 400


class TestCompleteAppointment:
    """POST /api/smart-docs/followup/appointments/{id}/complete"""

    def test_complete_appointment_with_notes(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1400, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1400, status=AppointmentStatus.CONFIRMED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/complete",
            json={
                "outcome_notes": "Borrower provided W-2 and bank statements",
                "documents_collected": [10, 11, 12],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_complete_cancelled_appointment_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1401, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1401, status=AppointmentStatus.CANCELLED)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/complete",
            json={"outcome_notes": "test"},
        )
        assert resp.status_code == 400


class TestMarkNoShow:
    """GET /api/smart-docs/followup/appointments/{id}/no-show"""

    def test_mark_no_show(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1500, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1500, status=AppointmentStatus.CONFIRMED)

        resp = authenticated_client.get(f"{PREFIX}/followup/appointments/{appt.id}/no-show")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_show"

    def test_mark_no_show_completed_rejected(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1501, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1501, status=AppointmentStatus.COMPLETED)

        resp = authenticated_client.get(f"{PREFIX}/followup/appointments/{appt.id}/no-show")
        assert resp.status_code == 400


# ============================================================================
# Template Tests
# ============================================================================


class TestListTemplates:
    """GET /api/smart-docs/followup/templates"""

    def test_list_templates_includes_defaults(self, authenticated_client, db_session):
        _seed_template(db_session, organization_id=1, slug="org-tmpl", is_default=False)
        _seed_template(db_session, organization_id=None, slug="platform-default", is_default=True)

        resp = authenticated_client.get(f"{PREFIX}/followup/templates")
        assert resp.status_code == 200
        data = resp.json()
        # Should include both org-specific and platform defaults
        assert data["total"] >= 2

    def test_list_templates_filter_channel(self, authenticated_client, db_session):
        _seed_template(db_session, organization_id=1, slug="email-tmpl", channel="email")
        _seed_template(db_session, organization_id=1, slug="sms-tmpl", channel="sms")

        resp = authenticated_client.get(
            f"{PREFIX}/followup/templates",
            params={"channel": "sms"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for t in data["templates"]:
            assert t["channel"] == "sms"


class TestCreateTemplate:
    """POST /api/smart-docs/followup/templates"""

    def test_create_template_success(self, authenticated_client, db_session):
        resp = authenticated_client.post(
            f"{PREFIX}/followup/templates",
            json={
                "name": "Income Docs Reminder",
                "slug": "income-docs-reminder",
                "channel": "email",
                "category": "reminder",
                "subject_template": "Action needed: {{document_list}}",
                "body_template": "Hi {{borrower_name}}, please upload {{document_list}}.",
                "variables": ["borrower_name", "document_list"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "income-docs-reminder"
        assert data["channel"] == "email"
        assert data["is_default"] is False
        assert data["is_active"] is True
        assert "borrower_name" in data["variables"]

    def test_create_template_duplicate_slug(self, authenticated_client, db_session):
        _seed_template(db_session, organization_id=1, slug="existing-slug")

        resp = authenticated_client.post(
            f"{PREFIX}/followup/templates",
            json={
                "name": "Duplicate",
                "slug": "existing-slug",
                "channel": "email",
                "body_template": "Hello",
            },
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_template_invalid_channel(self, authenticated_client, db_session):
        resp = authenticated_client.post(
            f"{PREFIX}/followup/templates",
            json={
                "name": "Bad Channel",
                "slug": "bad-channel",
                "channel": "fax",
                "body_template": "Hello",
            },
        )
        assert resp.status_code == 400
        assert "Invalid channel" in resp.json()["detail"]


class TestUpdateTemplate:
    """PUT /api/smart-docs/followup/templates/{template_id}"""

    def test_update_own_template(self, authenticated_client, db_session):
        tmpl = _seed_template(db_session, organization_id=1, slug="update-me")

        resp = authenticated_client.put(
            f"{PREFIX}/followup/templates/{tmpl.id}",
            json={
                "name": "Updated Name",
                "body_template": "New body {{borrower_name}}",
                "is_active": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["is_active"] is False

    def test_update_default_template_blocked_for_non_admin(self, authenticated_client, db_session):
        tmpl = _seed_template(db_session, organization_id=1, slug="default-tmpl", is_default=True)

        resp = authenticated_client.put(
            f"{PREFIX}/followup/templates/{tmpl.id}",
            json={"name": "Hacked Name"},
        )
        assert resp.status_code == 403
        assert "platform default" in resp.json()["detail"].lower()

    def test_update_template_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.put(
            f"{PREFIX}/followup/templates/99999",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404

    def test_update_template_invalid_channel(self, authenticated_client, db_session):
        tmpl = _seed_template(db_session, organization_id=1, slug="channel-test")

        resp = authenticated_client.put(
            f"{PREFIX}/followup/templates/{tmpl.id}",
            json={"channel": "carrier_pigeon"},
        )
        assert resp.status_code == 400
        assert "Invalid channel" in resp.json()["detail"]


# ============================================================================
# Admin / Cron Tests
# ============================================================================


class TestProcessPendingFollowups:
    """POST /api/smart-docs/followup/process-pending"""

    def test_process_pending_advances_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1600, organization_id=1)
        # Campaign with next_action_at in the past (should be picked up)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        campaign = _seed_campaign(
            db_session,
            loan_id=1600,
            organization_id=1,
            status=CampaignStatus.ACTIVE,
            current_step=0,
            next_action_at=past,
        )

        resp = authenticated_client.post(f"{PREFIX}/followup/process-pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed_count"] >= 1
        assert campaign.id in data["processed_campaign_ids"]

    def test_process_pending_no_due_campaigns(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1601, organization_id=1)
        # Campaign with next_action_at in the future (should NOT be picked up)
        future = datetime.now(timezone.utc) + timedelta(hours=24)
        _seed_campaign(
            db_session,
            loan_id=1601,
            organization_id=1,
            status=CampaignStatus.ACTIVE,
            current_step=0,
            next_action_at=future,
        )

        resp = authenticated_client.post(f"{PREFIX}/followup/process-pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed_count"] == 0

    def test_process_pending_completes_exhausted_campaign(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1602, organization_id=1)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        step_config = [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "t1"},
        ]
        campaign = _seed_campaign(
            db_session,
            loan_id=1602,
            organization_id=1,
            status=CampaignStatus.ACTIVE,
            current_step=1,  # Already past last step
            next_action_at=past,
            step_config=step_config,
        )

        resp = authenticated_client.post(f"{PREFIX}/followup/process-pending")
        assert resp.status_code == 200
        data = resp.json()
        assert campaign.id in data["completed_campaign_ids"]


class TestFollowupStats:
    """GET /api/smart-docs/followup/stats"""

    def test_get_followup_stats(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1700, organization_id=1)
        _seed_campaign(db_session, loan_id=1700, organization_id=1, status=CampaignStatus.ACTIVE)
        _seed_campaign(db_session, loan_id=1700, organization_id=1, status=CampaignStatus.COMPLETED)
        _seed_appointment(db_session, loan_id=1700, organization_id=1, status=AppointmentStatus.SCHEDULED)
        _seed_appointment(db_session, loan_id=1700, organization_id=1, status=AppointmentStatus.NO_SHOW)

        resp = authenticated_client.get(f"{PREFIX}/followup/stats")
        assert resp.status_code == 200
        data = resp.json()

        assert "campaigns" in data
        assert "appointments" in data
        assert "channels" in data
        assert data["campaigns"]["total"] >= 2
        assert data["campaigns"]["active"] >= 1
        assert data["campaigns"]["completed"] >= 1
        assert data["appointments"]["total"] >= 2
        assert data["appointments"]["no_show"] >= 1
        assert "response_rate" in data["campaigns"]
        assert "no_show_rate" in data["appointments"]
        assert "email" in data["channels"]
        assert "sms" in data["channels"]

    def test_stats_empty_org(self, authenticated_client, db_session):
        """Stats endpoint should work even with no data (zero counts)."""
        resp = authenticated_client.get(f"{PREFIX}/followup/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaigns"]["total"] >= 0
        assert data["campaigns"]["response_rate"] >= 0


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestTenantIsolation:
    """Verify that users cannot access resources from other organizations."""

    def test_campaign_from_other_org_not_visible(self, authenticated_client, db_session):
        """Campaigns belonging to org_id=999 should not be accessible by user in org_id=1."""
        _seed_loan(db_session, loan_id=1800, organization_id=999)
        campaign = _seed_campaign(db_session, loan_id=1800, organization_id=999)

        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns/{campaign.id}")
        # _verify_loan_tenant checks org mismatch and raises 404
        assert resp.status_code == 404

    def test_appointment_from_other_org_not_visible(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1801, organization_id=999)
        appt = _seed_appointment(db_session, loan_id=1801, organization_id=999)

        resp = authenticated_client.get(f"{PREFIX}/followup/appointments/{appt.id}")
        assert resp.status_code == 404

    def test_create_campaign_for_other_org_loan_blocked(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1802, organization_id=999)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 1802,
                "campaign_type": "INITIAL_REQUEST",
            },
        )
        assert resp.status_code == 404

    def test_create_appointment_for_other_org_loan_blocked(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1803, organization_id=999)
        start_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments",
            json={
                "loan_id": 1803,
                "appointment_type": "DOCUMENT_REVIEW",
                "title": "Cross-tenant attempt",
                "scheduled_time_start": start_time,
            },
        )
        assert resp.status_code == 404

    def test_pause_campaign_from_other_org_blocked(self, authenticated_client, db_session):
        _seed_loan(db_session, loan_id=1804, organization_id=999)
        campaign = _seed_campaign(db_session, loan_id=1804, organization_id=999, status=CampaignStatus.ACTIVE)

        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign.id}/pause",
            json={"reason": "Cross-tenant pause attempt"},
        )
        assert resp.status_code == 404

    def test_template_from_other_org_not_editable(self, authenticated_client, db_session):
        tmpl = _seed_template(db_session, organization_id=999, slug="other-org-tmpl")

        resp = authenticated_client.put(
            f"{PREFIX}/followup/templates/{tmpl.id}",
            json={"name": "Hijacked"},
        )
        assert resp.status_code == 404

    def test_list_campaigns_scoped_to_org(self, authenticated_client, db_session):
        """Listing campaigns should only return those for the user's org."""
        _seed_loan(db_session, loan_id=1805, organization_id=1)
        _seed_loan(db_session, loan_id=1806, organization_id=999)
        _seed_campaign(db_session, loan_id=1805, organization_id=1)
        _seed_campaign(db_session, loan_id=1806, organization_id=999)

        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        for c in data["campaigns"]:
            assert c["organization_id"] == 1


# ============================================================================
# Edge Case / Integration Tests
# ============================================================================


class TestEdgeCases:
    """Miscellaneous edge cases and integration scenarios."""

    def test_campaign_full_lifecycle(self, authenticated_client, db_session):
        """Create -> Pause -> Resume -> Record Response (uploaded) -> verify completed."""
        _seed_loan(db_session, loan_id=1900, organization_id=1)

        # Create
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns",
            json={
                "loan_id": 1900,
                "campaign_type": "URGENT_REMINDER",
                "trigger_source": "sla_breach",
            },
        )
        assert resp.status_code == 200
        campaign_id = resp.json()["id"]

        # Pause
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign_id}/pause",
            json={"reason": "Checking with borrower"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Resume
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign_id}/resume",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        # Record uploaded response (should complete the campaign)
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/{campaign_id}/response",
            json={"response_type": "uploaded"},
        )
        assert resp.status_code == 200
        assert resp.json()["campaign_status"] == "completed"

        # Verify detail shows completed with events
        resp = authenticated_client.get(f"{PREFIX}/followup/campaigns/{campaign_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["status"] == "completed"
        assert detail["borrower_responded"] is True
        # Should have at least 3 system events (pause, resume, uploaded)
        assert detail["event_count"] >= 3

    def test_appointment_reschedule_chain(self, authenticated_client, db_session):
        """Verify that rescheduling links back to the original appointment."""
        _seed_loan(db_session, loan_id=1901, organization_id=1)
        appt = _seed_appointment(db_session, loan_id=1901, status=AppointmentStatus.SCHEDULED)
        new_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

        # Reschedule
        resp = authenticated_client.post(
            f"{PREFIX}/followup/appointments/{appt.id}/reschedule",
            json={"new_start_time": new_time, "reason": "Borrower conflict"},
        )
        assert resp.status_code == 200
        new_appt = resp.json()["new_appointment"]
        assert new_appt["rescheduled_from_id"] == appt.id

        # Original appointment should now be rescheduled status
        resp = authenticated_client.get(f"{PREFIX}/followup/appointments/{appt.id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rescheduled"

    def test_appointment_not_found(self, authenticated_client, db_session):
        resp = authenticated_client.get(f"{PREFIX}/followup/appointments/99999")
        assert resp.status_code == 404

    def test_campaign_not_found_for_pause(self, authenticated_client, db_session):
        resp = authenticated_client.post(
            f"{PREFIX}/followup/campaigns/99999/pause",
            json={"reason": "test"},
        )
        assert resp.status_code == 404
