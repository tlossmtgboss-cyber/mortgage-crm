"""
Tests for Document Follow-Up & Scheduling Models.

Covers FollowupCampaign, FollowupEvent, DocumentAppointment, and FollowupTemplate
models with in-memory SQLite for isolation. Validates creation, status transitions,
relationships, scheduling conflicts, template rendering, escalation tracking,
multi-step sequences, and tenant isolation.
"""

import re
import pytest
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import Base
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


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def engine():
    """Create an in-memory SQLite engine scoped to the test module."""
    eng = create_engine("sqlite:///:memory:")
    # Create only the four tables under test
    for model in (FollowupCampaign, FollowupEvent, DocumentAppointment, FollowupTemplate):
        model.__table__.create(bind=eng, checkfirst=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    """Provide a clean transactional session per test, rolled back afterwards."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# 1. FollowupCampaign — Creation
# =============================================================================

@pytest.mark.unit
class TestFollowupCampaignCreation:
    """Validate that FollowupCampaign records can be created with all fields."""

    def test_create_campaign_minimal(self, db: Session):
        """Create a campaign with only required fields."""
        campaign = FollowupCampaign(
            loan_id=100,
            campaign_type=CampaignType.INITIAL_REQUEST,
            status=CampaignStatus.ACTIVE,
        )
        db.add(campaign)
        db.flush()

        assert campaign.id is not None
        assert campaign.loan_id == 100
        assert campaign.campaign_type == CampaignType.INITIAL_REQUEST
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.current_step == 0
        assert campaign.total_steps == 3
        assert campaign.max_reminders == 5
        assert campaign.reminders_sent == 0
        assert campaign.borrower_responded is False

    def test_create_campaign_full(self, db: Session):
        """Create a campaign with all optional fields populated."""
        now = _utcnow()
        step_config = [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_reminder"},
            {"step": 3, "channel": "call", "delay_hours": 96, "template": "urgent_reminder"},
        ]
        campaign = FollowupCampaign(
            organization_id=10,
            loan_id=200,
            borrower_id=300,
            campaign_type=CampaignType.ESCALATION,
            status=CampaignStatus.ACTIVE,
            trigger_source=CampaignTriggerSource.SLA_BREACH,
            linked_request_ids=[1, 2, 3],
            total_steps=3,
            current_step=1,
            step_config=step_config,
            next_action_at=now + timedelta(hours=48),
            started_at=now,
            max_reminders=3,
            reminders_sent=1,
            created_by_user_id=42,
        )
        db.add(campaign)
        db.flush()

        assert campaign.id is not None
        assert campaign.organization_id == 10
        assert campaign.borrower_id == 300
        assert campaign.trigger_source == CampaignTriggerSource.SLA_BREACH
        assert campaign.linked_request_ids == [1, 2, 3]
        assert len(campaign.step_config) == 3
        assert campaign.step_config[1]["channel"] == "sms"
        assert campaign.created_by_user_id == 42


# =============================================================================
# 2. FollowupCampaign — Status Transitions
# =============================================================================

@pytest.mark.unit
class TestCampaignStatusTransitions:
    """Validate campaign status can transition through its lifecycle."""

    def _make_campaign(self, db: Session, status: CampaignStatus) -> FollowupCampaign:
        campaign = FollowupCampaign(
            loan_id=1,
            campaign_type=CampaignType.GENTLE_REMINDER,
            status=status,
        )
        db.add(campaign)
        db.flush()
        return campaign

    def test_active_to_paused(self, db: Session):
        campaign = self._make_campaign(db, CampaignStatus.ACTIVE)
        campaign.status = CampaignStatus.PAUSED
        db.flush()

        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.status == CampaignStatus.PAUSED

    def test_paused_to_active(self, db: Session):
        campaign = self._make_campaign(db, CampaignStatus.PAUSED)
        campaign.status = CampaignStatus.ACTIVE
        db.flush()

        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.status == CampaignStatus.ACTIVE

    def test_active_to_completed(self, db: Session):
        now = _utcnow()
        campaign = self._make_campaign(db, CampaignStatus.ACTIVE)
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = now
        db.flush()

        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.status == CampaignStatus.COMPLETED
        assert fetched.completed_at is not None

    def test_active_to_cancelled(self, db: Session):
        now = _utcnow()
        campaign = self._make_campaign(db, CampaignStatus.ACTIVE)
        campaign.status = CampaignStatus.CANCELLED
        campaign.cancelled_at = now
        campaign.cancel_reason = "Borrower withdrew application"
        db.flush()

        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.status == CampaignStatus.CANCELLED
        assert fetched.cancel_reason == "Borrower withdrew application"


# =============================================================================
# 3. FollowupEvent — Creation & Channels
# =============================================================================

@pytest.mark.unit
class TestFollowupEventCreation:
    """Validate FollowupEvent creation across different channels."""

    def test_create_email_event(self, db: Session):
        event = FollowupEvent(
            campaign_id=1,
            event_type=FollowupEventType.EMAIL_SENT,
            step_number=1,
            channel="email",
            template_used="initial_request",
            recipient_email="borrower@example.com",
            message_subject="Documents needed for your loan",
            message_preview="Hi John, we need the following documents...",
            delivery_status=DeliveryStatus.SENT,
        )
        db.add(event)
        db.flush()

        assert event.id is not None
        assert event.channel == "email"
        assert event.event_type == FollowupEventType.EMAIL_SENT
        assert event.delivery_status == DeliveryStatus.SENT

    def test_create_sms_event(self, db: Session):
        event = FollowupEvent(
            campaign_id=1,
            event_type=FollowupEventType.SMS_SENT,
            step_number=2,
            channel="sms",
            recipient_phone="+15551234567",
            message_preview="Reminder: please upload your bank statements.",
            delivery_status=DeliveryStatus.DELIVERED,
        )
        db.add(event)
        db.flush()

        assert event.channel == "sms"
        assert event.recipient_phone == "+15551234567"
        assert event.delivery_status == DeliveryStatus.DELIVERED

    def test_create_call_event(self, db: Session):
        event = FollowupEvent(
            campaign_id=1,
            event_type=FollowupEventType.CALL_COMPLETED,
            step_number=3,
            channel="call",
            recipient_phone="+15559876543",
            extra_metadata={"duration_seconds": 180, "outcome": "left_voicemail"},
        )
        db.add(event)
        db.flush()

        assert event.channel == "call"
        assert event.extra_metadata["duration_seconds"] == 180

    def test_create_appointment_event(self, db: Session):
        event = FollowupEvent(
            campaign_id=2,
            event_type=FollowupEventType.APPOINTMENT_BOOKED,
            channel="appointment",
            extra_metadata={"appointment_id": 55},
        )
        db.add(event)
        db.flush()

        assert event.event_type == FollowupEventType.APPOINTMENT_BOOKED
        assert event.extra_metadata["appointment_id"] == 55

    def test_delivery_status_lifecycle(self, db: Session):
        """Verify delivery status can progress through its lifecycle."""
        event = FollowupEvent(
            campaign_id=1,
            event_type=FollowupEventType.EMAIL_SENT,
            channel="email",
            delivery_status=DeliveryStatus.QUEUED,
        )
        db.add(event)
        db.flush()
        assert event.delivery_status == DeliveryStatus.QUEUED

        event.delivery_status = DeliveryStatus.SENT
        db.flush()
        assert event.delivery_status == DeliveryStatus.SENT

        event.delivery_status = DeliveryStatus.DELIVERED
        db.flush()

        now = _utcnow()
        event.delivery_status = DeliveryStatus.OPENED
        event.opened_at = now
        db.flush()
        assert event.delivery_status == DeliveryStatus.OPENED
        assert event.opened_at is not None

        event.delivery_status = DeliveryStatus.CLICKED
        event.clicked_at = now
        db.flush()
        assert event.delivery_status == DeliveryStatus.CLICKED


# =============================================================================
# 4. DocumentAppointment — Scheduling & Status
# =============================================================================

@pytest.mark.unit
class TestDocumentAppointmentCreation:
    """Validate DocumentAppointment creation and status tracking."""

    def test_create_appointment(self, db: Session):
        start = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        appt = DocumentAppointment(
            organization_id=10,
            loan_id=100,
            borrower_id=200,
            appointment_type=AppointmentType.DOCUMENT_REVIEW,
            title="Review income documents",
            description="Discuss W2 and paystub requirements",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=date(2026, 3, 15),
            scheduled_time_start=start,
            scheduled_time_end=end,
            duration_minutes=30,
            location_type=LocationType.VIDEO_CALL,
            meeting_link="https://meet.example.com/abc123",
            assigned_to_user_id=42,
            attendee_name="John Borrower",
            attendee_email="john@example.com",
            attendee_phone="+15551230000",
            documents_to_discuss=[10, 11, 12],
        )
        db.add(appt)
        db.flush()

        assert appt.id is not None
        assert appt.appointment_type == AppointmentType.DOCUMENT_REVIEW
        assert appt.status == AppointmentStatus.SCHEDULED
        assert appt.duration_minutes == 30
        assert appt.location_type == LocationType.VIDEO_CALL
        assert appt.documents_to_discuss == [10, 11, 12]

    def test_appointment_status_to_confirmed(self, db: Session):
        appt = DocumentAppointment(
            loan_id=1,
            appointment_type=AppointmentType.NOTARY_SIGNING,
            title="Signing appointment",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=date(2026, 3, 20),
            scheduled_time_start=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.flush()

        appt.status = AppointmentStatus.CONFIRMED
        appt.confirmed_at = _utcnow()
        db.flush()

        fetched = db.get(DocumentAppointment, appt.id)
        assert fetched.status == AppointmentStatus.CONFIRMED
        assert fetched.confirmed_at is not None

    def test_appointment_completion(self, db: Session):
        appt = DocumentAppointment(
            loan_id=1,
            appointment_type=AppointmentType.DOCUMENT_COLLECTION,
            title="Collect tax returns",
            status=AppointmentStatus.IN_PROGRESS,
            scheduled_date=date(2026, 3, 10),
            scheduled_time_start=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.flush()

        appt.status = AppointmentStatus.COMPLETED
        appt.completed_at = _utcnow()
        appt.outcome_notes = "Collected 2024 and 2025 tax returns"
        appt.documents_collected = ["tax_return_2024", "tax_return_2025"]
        db.flush()

        fetched = db.get(DocumentAppointment, appt.id)
        assert fetched.status == AppointmentStatus.COMPLETED
        assert fetched.documents_collected == ["tax_return_2024", "tax_return_2025"]
        assert "2024" in fetched.outcome_notes

    def test_appointment_no_show(self, db: Session):
        appt = DocumentAppointment(
            loan_id=1,
            appointment_type=AppointmentType.GENERAL_CONSULTATION,
            title="Consultation",
            status=AppointmentStatus.CONFIRMED,
            scheduled_date=date(2026, 3, 8),
            scheduled_time_start=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.flush()

        appt.status = AppointmentStatus.NO_SHOW
        db.flush()

        fetched = db.get(DocumentAppointment, appt.id)
        assert fetched.status == AppointmentStatus.NO_SHOW


# =============================================================================
# 5. FollowupTemplate — Creation & Variables
# =============================================================================

@pytest.mark.unit
class TestFollowupTemplateCreation:
    """Validate FollowupTemplate creation with merge variables."""

    def test_create_email_template(self, db: Session):
        template = FollowupTemplate(
            organization_id=10,
            name="Initial Document Request",
            slug="initial-doc-request",
            channel="email",
            category="initial",
            subject_template="Action required: documents needed for loan {{loan_number}}",
            body_template=(
                "Hi {{borrower_name}},\n\n"
                "We need the following documents to proceed with your loan:\n"
                "{{document_list}}\n\n"
                "Please upload them at {{portal_link}} by {{due_date}}.\n\n"
                "Thanks,\n{{lo_name}}\n{{lo_phone}}"
            ),
            variables=["borrower_name", "loan_number", "document_list", "portal_link", "due_date", "lo_name", "lo_phone"],
            is_default=False,
            is_active=True,
        )
        db.add(template)
        db.flush()

        assert template.id is not None
        assert template.slug == "initial-doc-request"
        assert template.channel == "email"
        assert len(template.variables) == 7
        assert "borrower_name" in template.variables
        assert template.usage_count == 0

    def test_create_sms_template(self, db: Session):
        template = FollowupTemplate(
            name="SMS Reminder",
            slug="sms-reminder",
            channel="sms",
            category="reminder",
            body_template="Hi {{borrower_name}}, reminder to upload your {{document_type}}. Link: {{portal_link}}",
            variables=["borrower_name", "document_type", "portal_link"],
            is_default=True,
            is_active=True,
        )
        db.add(template)
        db.flush()

        assert template.is_default is True
        assert template.channel == "sms"
        assert template.subject_template is None  # SMS has no subject

    def test_template_usage_count_increment(self, db: Session):
        template = FollowupTemplate(
            name="Test Template",
            slug="test-usage",
            channel="email",
            body_template="Hello {{borrower_name}}",
            variables=["borrower_name"],
        )
        db.add(template)
        db.flush()
        assert template.usage_count == 0

        template.usage_count += 1
        db.flush()
        assert template.usage_count == 1

        template.usage_count += 4
        db.flush()
        assert template.usage_count == 5


# =============================================================================
# 6. Campaign-to-Event Relationships
# =============================================================================

@pytest.mark.unit
class TestCampaignEventRelationship:
    """Validate that events correctly reference campaigns via campaign_id FK."""

    def test_events_reference_campaign(self, db: Session):
        campaign = FollowupCampaign(
            loan_id=500,
            campaign_type=CampaignType.URGENT_REMINDER,
            status=CampaignStatus.ACTIVE,
        )
        db.add(campaign)
        db.flush()

        events = []
        for step_num, etype in enumerate(
            [FollowupEventType.EMAIL_SENT, FollowupEventType.SMS_SENT, FollowupEventType.CALL_SCHEDULED],
            start=1,
        ):
            ev = FollowupEvent(
                campaign_id=campaign.id,
                event_type=etype,
                step_number=step_num,
                channel=["email", "sms", "call"][step_num - 1],
            )
            db.add(ev)
            events.append(ev)

        db.flush()

        # Query events for this campaign
        found = db.query(FollowupEvent).filter(
            FollowupEvent.campaign_id == campaign.id
        ).order_by(FollowupEvent.step_number).all()

        assert len(found) == 3
        assert found[0].event_type == FollowupEventType.EMAIL_SENT
        assert found[1].event_type == FollowupEventType.SMS_SENT
        assert found[2].event_type == FollowupEventType.CALL_SCHEDULED
        assert all(e.campaign_id == campaign.id for e in found)


# =============================================================================
# 7. Appointment Scheduling Conflicts
# =============================================================================

@pytest.mark.unit
class TestAppointmentSchedulingConflicts:
    """Validate detection of overlapping appointment times for the same user."""

    def _make_appt(self, db: Session, user_id: int, start: datetime, end: datetime, org_id: int = 1) -> DocumentAppointment:
        appt = DocumentAppointment(
            organization_id=org_id,
            loan_id=1,
            appointment_type=AppointmentType.DOCUMENT_REVIEW,
            title="Review docs",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=start.date(),
            scheduled_time_start=start,
            scheduled_time_end=end,
            duration_minutes=int((end - start).total_seconds() / 60),
            assigned_to_user_id=user_id,
        )
        db.add(appt)
        db.flush()
        return appt

    def _has_conflict(self, db: Session, user_id: int, start: datetime, end: datetime, exclude_id: int = None) -> bool:
        """Check if a proposed time slot conflicts with existing appointments."""
        query = db.query(DocumentAppointment).filter(
            DocumentAppointment.assigned_to_user_id == user_id,
            DocumentAppointment.status.in_([
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CONFIRMED,
                AppointmentStatus.IN_PROGRESS,
            ]),
            DocumentAppointment.scheduled_time_start < end,
            DocumentAppointment.scheduled_time_end > start,
        )
        if exclude_id is not None:
            query = query.filter(DocumentAppointment.id != exclude_id)
        return query.count() > 0

    def test_no_conflict_different_times(self, db: Session):
        start1 = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
        self._make_appt(db, user_id=42, start=start1, end=end1)

        start2 = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        end2 = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        assert not self._has_conflict(db, user_id=42, start=start2, end=end2)

    def test_conflict_overlapping_times(self, db: Session):
        start1 = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
        end1 = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        self._make_appt(db, user_id=42, start=start1, end=end1)

        # Overlaps by 30 minutes
        start2 = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
        end2 = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
        assert self._has_conflict(db, user_id=42, start=start2, end=end2)

    def test_no_conflict_cancelled_appointment(self, db: Session):
        start = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 15, 14, 30, tzinfo=timezone.utc)
        appt = self._make_appt(db, user_id=42, start=start, end=end)

        # Cancel it
        appt.status = AppointmentStatus.CANCELLED
        appt.cancelled_at = _utcnow()
        db.flush()

        # Same slot should now be available
        assert not self._has_conflict(db, user_id=42, start=start, end=end)


# =============================================================================
# 8. Template Rendering with Variables
# =============================================================================

@pytest.mark.unit
class TestTemplateRendering:
    """Validate that templates can be rendered by substituting merge variables."""

    @staticmethod
    def _render(template_str: str, variables: dict) -> str:
        """Simple mustache-style template rendering matching the model's convention."""
        result = template_str
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result

    def test_render_email_body(self, db: Session):
        template = FollowupTemplate(
            name="Render Test",
            slug="render-test",
            channel="email",
            subject_template="Docs needed for loan {{loan_number}}",
            body_template="Hi {{borrower_name}}, please upload {{document_list}}. Link: {{portal_link}}",
            variables=["borrower_name", "loan_number", "document_list", "portal_link"],
        )
        db.add(template)
        db.flush()

        vars_map = {
            "borrower_name": "Jane Doe",
            "loan_number": "LN-2026-0042",
            "document_list": "W2, bank statements",
            "portal_link": "https://portal.example.com/upload",
        }

        rendered_subject = self._render(template.subject_template, vars_map)
        rendered_body = self._render(template.body_template, vars_map)

        assert "LN-2026-0042" in rendered_subject
        assert "Jane Doe" in rendered_body
        assert "W2, bank statements" in rendered_body
        assert "https://portal.example.com/upload" in rendered_body
        # No unreplaced placeholders
        assert "{{" not in rendered_body
        assert "{{" not in rendered_subject

    def test_render_preserves_unmatched_variables(self, db: Session):
        """If a variable is missing from the map, the placeholder stays intact."""
        body = "Hi {{borrower_name}}, your LO is {{lo_name}}"
        partial_vars = {"borrower_name": "Bob"}
        rendered = self._render(body, partial_vars)
        assert "Bob" in rendered
        assert "{{lo_name}}" in rendered

    def test_all_declared_variables_extractable(self, db: Session):
        """Variables declared in the JSON list match placeholders in the body."""
        template = FollowupTemplate(
            name="Variable Check",
            slug="var-check",
            channel="email",
            subject_template="Hello {{borrower_name}}",
            body_template="Dear {{borrower_name}}, your docs: {{document_list}}. Due: {{due_date}}",
            variables=["borrower_name", "document_list", "due_date"],
        )
        db.add(template)
        db.flush()

        # Extract placeholders from body and subject
        full_text = (template.subject_template or "") + " " + template.body_template
        found_vars = set(re.findall(r"\{\{(\w+)\}\}", full_text))
        declared_vars = set(template.variables)
        assert found_vars == declared_vars, f"Mismatch: found={found_vars}, declared={declared_vars}"


# =============================================================================
# 9. Campaign Escalation Tracking
# =============================================================================

@pytest.mark.unit
class TestCampaignEscalationTracking:
    """Validate escalation campaign type and escalation events."""

    def test_escalation_campaign_creation(self, db: Session):
        campaign = FollowupCampaign(
            loan_id=999,
            campaign_type=CampaignType.ESCALATION,
            status=CampaignStatus.ACTIVE,
            trigger_source=CampaignTriggerSource.SLA_BREACH,
            step_config=[
                {"step": 1, "channel": "email", "delay_hours": 0, "template": "escalation_notice"},
                {"step": 2, "channel": "call", "delay_hours": 24, "template": "lo_followup_call"},
            ],
            total_steps=2,
            current_step=0,
        )
        db.add(campaign)
        db.flush()

        assert campaign.campaign_type == CampaignType.ESCALATION
        assert campaign.trigger_source == CampaignTriggerSource.SLA_BREACH

    def test_escalation_event_recorded(self, db: Session):
        campaign = FollowupCampaign(
            loan_id=999,
            campaign_type=CampaignType.ESCALATION,
            status=CampaignStatus.ACTIVE,
        )
        db.add(campaign)
        db.flush()

        escalation_event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.ESCALATED_TO_LO,
            channel="email",
            recipient_email="lo@company.com",
            message_subject="ESCALATION: borrower non-responsive on loan #999",
            extra_metadata={"escalation_reason": "3 unanswered attempts", "days_outstanding": 14},
        )
        db.add(escalation_event)
        db.flush()

        fetched = db.get(FollowupEvent, escalation_event.id)
        assert fetched.event_type == FollowupEventType.ESCALATED_TO_LO
        assert fetched.extra_metadata["days_outstanding"] == 14

    def test_escalation_campaign_triggers(self, db: Session):
        """All CampaignTriggerSource values should be storable and retrievable."""
        for trigger in CampaignTriggerSource:
            campaign = FollowupCampaign(
                loan_id=1,
                campaign_type=CampaignType.INITIAL_REQUEST,
                status=CampaignStatus.ACTIVE,
                trigger_source=trigger,
            )
            db.add(campaign)
        db.flush()

        stored = db.query(FollowupCampaign).filter(
            FollowupCampaign.loan_id == 1,
        ).all()
        stored_triggers = {c.trigger_source for c in stored}
        assert stored_triggers == set(CampaignTriggerSource)


# =============================================================================
# 10. Multi-Step Campaign Sequences
# =============================================================================

@pytest.mark.unit
class TestMultiStepCampaignSequences:
    """Validate advancing through campaign steps and tracking state."""

    def test_step_advancement(self, db: Session):
        """Simulate a 3-step campaign advancing from step 0 through step 3."""
        step_config = [
            {"step": 1, "channel": "email", "delay_hours": 0, "template": "initial_request"},
            {"step": 2, "channel": "sms", "delay_hours": 48, "template": "gentle_nudge"},
            {"step": 3, "channel": "call", "delay_hours": 96, "template": "urgent_call"},
        ]
        now = _utcnow()

        campaign = FollowupCampaign(
            loan_id=777,
            campaign_type=CampaignType.INITIAL_REQUEST,
            status=CampaignStatus.ACTIVE,
            total_steps=3,
            current_step=0,
            step_config=step_config,
            started_at=now,
            next_action_at=now,
            max_reminders=3,
            reminders_sent=0,
        )
        db.add(campaign)
        db.flush()

        # Step 1: send email
        campaign.current_step = 1
        campaign.reminders_sent = 1
        campaign.next_action_at = now + timedelta(hours=48)
        email_event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.EMAIL_SENT,
            step_number=1,
            channel="email",
            template_used="initial_request",
            delivery_status=DeliveryStatus.DELIVERED,
        )
        db.add(email_event)
        db.flush()

        # Step 2: send SMS
        campaign.current_step = 2
        campaign.reminders_sent = 2
        campaign.next_action_at = now + timedelta(hours=96)
        sms_event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.SMS_SENT,
            step_number=2,
            channel="sms",
            template_used="gentle_nudge",
            delivery_status=DeliveryStatus.DELIVERED,
        )
        db.add(sms_event)
        db.flush()

        # Step 3: make call
        campaign.current_step = 3
        campaign.reminders_sent = 3
        call_event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.CALL_COMPLETED,
            step_number=3,
            channel="call",
            template_used="urgent_call",
        )
        db.add(call_event)
        db.flush()

        # Complete the campaign
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = _utcnow()
        campaign.next_action_at = None
        db.flush()

        # Verify final state
        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.current_step == 3
        assert fetched.reminders_sent == 3
        assert fetched.status == CampaignStatus.COMPLETED
        assert fetched.next_action_at is None

        all_events = db.query(FollowupEvent).filter(
            FollowupEvent.campaign_id == campaign.id
        ).order_by(FollowupEvent.step_number).all()
        assert len(all_events) == 3
        assert [e.channel for e in all_events] == ["email", "sms", "call"]

    def test_campaign_stops_on_borrower_response(self, db: Session):
        """Campaign should mark borrower_responded and can be completed early."""
        campaign = FollowupCampaign(
            loan_id=888,
            campaign_type=CampaignType.GENTLE_REMINDER,
            status=CampaignStatus.ACTIVE,
            total_steps=5,
            current_step=2,
            reminders_sent=2,
        )
        db.add(campaign)
        db.flush()

        # Borrower responds after step 2
        response_event = FollowupEvent(
            campaign_id=campaign.id,
            event_type=FollowupEventType.BORROWER_RESPONDED,
            extra_metadata={"response_channel": "portal_upload"},
        )
        db.add(response_event)

        campaign.borrower_responded = True
        campaign.response_date = _utcnow()
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = _utcnow()
        db.flush()

        fetched = db.get(FollowupCampaign, campaign.id)
        assert fetched.borrower_responded is True
        assert fetched.status == CampaignStatus.COMPLETED
        assert fetched.current_step == 2  # Stopped at step 2, not 5


# =============================================================================
# 11. Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Validate that queries can isolate data by organization_id."""

    def test_campaign_tenant_isolation(self, db: Session):
        """Campaigns for different orgs should be filterable by organization_id."""
        for org_id in (100, 200, 200):
            db.add(FollowupCampaign(
                organization_id=org_id,
                loan_id=1,
                campaign_type=CampaignType.INITIAL_REQUEST,
                status=CampaignStatus.ACTIVE,
            ))
        db.flush()

        org_100 = db.query(FollowupCampaign).filter(
            FollowupCampaign.organization_id == 100
        ).all()
        org_200 = db.query(FollowupCampaign).filter(
            FollowupCampaign.organization_id == 200
        ).all()

        assert len(org_100) == 1
        assert len(org_200) == 2

    def test_appointment_tenant_isolation(self, db: Session):
        """Appointments for different orgs should be filterable by organization_id."""
        for org_id in (300, 400):
            db.add(DocumentAppointment(
                organization_id=org_id,
                loan_id=1,
                appointment_type=AppointmentType.INCOME_VERIFICATION,
                title=f"Verify income for org {org_id}",
                status=AppointmentStatus.SCHEDULED,
                scheduled_date=date(2026, 4, 1),
                scheduled_time_start=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            ))
        db.flush()

        org_300 = db.query(DocumentAppointment).filter(
            DocumentAppointment.organization_id == 300
        ).all()
        org_400 = db.query(DocumentAppointment).filter(
            DocumentAppointment.organization_id == 400
        ).all()

        assert len(org_300) == 1
        assert len(org_400) == 1
        assert org_300[0].title != org_400[0].title

    def test_template_tenant_isolation(self, db: Session):
        """Templates with organization_id=NULL are platform defaults; org-specific ones are isolated."""
        # Platform default
        default_tmpl = FollowupTemplate(
            organization_id=None,
            name="Platform Default",
            slug="platform-default",
            channel="email",
            body_template="Default body",
            is_default=True,
        )
        # Org-specific
        org_tmpl = FollowupTemplate(
            organization_id=500,
            name="Org 500 Custom",
            slug="org-500-custom",
            channel="email",
            body_template="Custom body for org 500",
            is_default=False,
        )
        db.add_all([default_tmpl, org_tmpl])
        db.flush()

        # Org 500 should see its own + platform defaults
        visible = db.query(FollowupTemplate).filter(
            (FollowupTemplate.organization_id == 500) | (FollowupTemplate.organization_id.is_(None))
        ).all()
        assert len(visible) == 2

        # Org 999 (no custom templates) should see only platform defaults
        visible_999 = db.query(FollowupTemplate).filter(
            (FollowupTemplate.organization_id == 999) | (FollowupTemplate.organization_id.is_(None))
        ).all()
        assert len(visible_999) == 1
        assert visible_999[0].is_default is True


# =============================================================================
# 12. Appointment Linked to Campaign
# =============================================================================

@pytest.mark.unit
class TestAppointmentCampaignLink:
    """Validate that appointments can be linked to campaigns."""

    def test_appointment_references_campaign(self, db: Session):
        campaign = FollowupCampaign(
            loan_id=50,
            campaign_type=CampaignType.APPOINTMENT_OFFER,
            status=CampaignStatus.ACTIVE,
        )
        db.add(campaign)
        db.flush()

        appt = DocumentAppointment(
            loan_id=50,
            campaign_id=campaign.id,
            appointment_type=AppointmentType.GENERAL_CONSULTATION,
            title="Discuss outstanding documents",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=date(2026, 3, 25),
            scheduled_time_start=datetime(2026, 3, 25, 15, 0, tzinfo=timezone.utc),
        )
        db.add(appt)
        db.flush()

        fetched = db.get(DocumentAppointment, appt.id)
        assert fetched.campaign_id == campaign.id

        # Query appointments for a campaign
        campaign_appts = db.query(DocumentAppointment).filter(
            DocumentAppointment.campaign_id == campaign.id
        ).all()
        assert len(campaign_appts) == 1


# =============================================================================
# 13. Appointment Rescheduling
# =============================================================================

@pytest.mark.unit
class TestAppointmentRescheduling:
    """Validate rescheduling creates a new appointment referencing the original."""

    def test_reschedule_appointment(self, db: Session):
        original = DocumentAppointment(
            loan_id=60,
            appointment_type=AppointmentType.DOCUMENT_REVIEW,
            title="Original review",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=date(2026, 3, 12),
            scheduled_time_start=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
            scheduled_time_end=datetime(2026, 3, 12, 10, 30, tzinfo=timezone.utc),
        )
        db.add(original)
        db.flush()

        # Mark original as rescheduled
        original.status = AppointmentStatus.RESCHEDULED
        original.cancelled_at = _utcnow()
        original.cancellation_reason = "Borrower requested new time"

        # Create the rescheduled appointment
        rescheduled = DocumentAppointment(
            loan_id=60,
            appointment_type=AppointmentType.DOCUMENT_REVIEW,
            title="Rescheduled review",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=date(2026, 3, 14),
            scheduled_time_start=datetime(2026, 3, 14, 14, 0, tzinfo=timezone.utc),
            scheduled_time_end=datetime(2026, 3, 14, 14, 30, tzinfo=timezone.utc),
            rescheduled_from_id=original.id,
        )
        db.add(rescheduled)
        db.flush()

        assert rescheduled.rescheduled_from_id == original.id
        assert original.status == AppointmentStatus.RESCHEDULED

        # Verify the chain
        fetched_new = db.get(DocumentAppointment, rescheduled.id)
        fetched_old = db.get(DocumentAppointment, original.id)
        assert fetched_new.rescheduled_from_id == fetched_old.id
        assert fetched_old.status == AppointmentStatus.RESCHEDULED
