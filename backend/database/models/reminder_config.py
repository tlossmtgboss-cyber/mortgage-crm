"""
Appointment Reminder Configuration & Logging Models

Provides:
- ReminderTemplate: Org-configurable reminder templates (channel, timing, content)
- ReminderLog: Audit trail of all reminder send attempts

These models complement the existing AppointmentReminder model in
smart_scheduler_models.py.  ReminderTemplate holds the *configuration*
(what to send, when, and how), while the existing AppointmentReminder
tracks per-appointment *delivery state*.  ReminderLog is a write-once
audit table recording every send attempt for compliance and debugging.

Default templates seeded via seed_default_templates():
  - 24-hour email reminder
  - 1-hour SMS reminder
  - 15-minute SMS reminder

Usage:
    from database.models.reminder_config import ReminderTemplate, ReminderLog
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from db import Base


class ReminderTemplate(Base):
    """
    Org-level reminder template configuration.

    Each template defines a single reminder touchpoint: the channel, the
    timing relative to the appointment start, and the message content with
    variable placeholders.

    Supported template variables:
        {client_name}       - Attendee / borrower name
        {appointment_type}  - Meeting type display name
        {date}              - Appointment date (formatted)
        {time}              - Appointment start time (formatted)
        {lo_name}           - Assigned loan officer name
        {location}          - Physical location or "Video Call"
        {join_url}          - Video meeting link
        {cancel_url}        - One-click cancellation link
        {reschedule_url}    - One-click reschedule link
    """
    __tablename__ = "reminder_templates"
    __table_args__ = (
        Index("ix_reminder_templates_org_active", "organization_id", "is_active"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Template identity
    name = Column(String(100), nullable=False)

    # Channel: "email", "sms", or "both"
    channel = Column(String(10), nullable=False, default="email")

    # Timing: minutes before appointment start (e.g. 1440 = 24 hr, 60 = 1 hr, 15 = 15 min)
    timing_minutes = Column(Integer, nullable=False, default=1440)

    # Email subject (only used when channel is email or both)
    subject_template = Column(String(255), nullable=True)

    # Message body with {variable} placeholders
    body_template = Column(Text, nullable=False)

    # Active toggle
    is_active = Column(Boolean, default=True, nullable=False)

    # Optional: restrict to a specific appointment type (null = applies to all)
    appointment_type_id = Column(
        Integer,
        ForeignKey("appointment_types.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    logs = relationship("ReminderLog", back_populates="template", cascade="all, delete-orphan")


class ReminderLog(Base):
    """
    Write-once audit log for every reminder send attempt.

    One row per send attempt -- retries get separate rows so failure
    patterns are visible.
    """
    __tablename__ = "reminder_logs"
    __table_args__ = (
        Index("ix_reminder_logs_appointment", "appointment_id"),
        Index("ix_reminder_logs_template", "template_id"),
        Index("ix_reminder_logs_sent_at", "sent_at"),
        Index("ix_reminder_logs_created_at", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id = Column(
        Integer,
        ForeignKey("reminder_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Channel used for this specific send
    channel = Column(String(10), nullable=False)  # "email" or "sms"

    # Record creation (set once when the log row is first written)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Delivery (sent_at is set only when status transitions to "sent")
    sent_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, sent, failed, skipped
    error_message = Column(Text, nullable=True)

    # External provider reference (SendGrid message ID, Telnyx SMS ID)
    external_id = Column(String(255), nullable=True)

    # Recipient info (denormalized for audit)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(20), nullable=True)

    # Relationships
    template = relationship("ReminderTemplate", back_populates="logs")


# ============================================================================
# DEFAULT TEMPLATE SEEDING
# ============================================================================

DEFAULT_REMINDER_TEMPLATES = [
    {
        "name": "24-Hour Email Reminder",
        "channel": "email",
        "timing_minutes": 1440,
        "subject_template": "Reminder: {appointment_type} tomorrow at {time}",
        "body_template": (
            "Hi {client_name},\n\n"
            "This is a reminder that you have a {appointment_type} scheduled for "
            "{date} at {time} with {lo_name}.\n\n"
            "Location: {location}\n"
            "{join_url}\n\n"
            "Need to make changes?\n"
            "Reschedule: {reschedule_url}\n"
            "Cancel: {cancel_url}\n\n"
            "We look forward to speaking with you!\n\n"
            "Best regards,\n{lo_name}"
        ),
        "is_active": True,
    },
    {
        "name": "1-Hour SMS Reminder",
        "channel": "sms",
        "timing_minutes": 60,
        "subject_template": None,
        "body_template": (
            "Reminder: Your {appointment_type} with {lo_name} is in 1 hour "
            "at {time}. {join_url} Reply STOP to opt out."
        ),
        "is_active": True,
    },
    {
        "name": "15-Minute SMS Reminder",
        "channel": "sms",
        "timing_minutes": 15,
        "subject_template": None,
        "body_template": (
            "Starting soon! Your {appointment_type} with {lo_name} begins in "
            "15 minutes at {time}. {join_url} Reply STOP to opt out."
        ),
        "is_active": True,
    },
]


def seed_default_templates(db_session, organization_id: int) -> list:
    """
    Seed default reminder templates for an organization.

    Idempotent: skips templates that already exist (matched by name + org).

    Returns:
        List of created ReminderTemplate instances (empty if all existed).
    """
    created = []
    for tmpl_data in DEFAULT_REMINDER_TEMPLATES:
        existing = (
            db_session.query(ReminderTemplate)
            .filter(
                ReminderTemplate.organization_id == organization_id,
                ReminderTemplate.name == tmpl_data["name"],
            )
            .first()
        )
        if existing:
            continue

        template = ReminderTemplate(
            organization_id=organization_id,
            **tmpl_data,
        )
        db_session.add(template)
        created.append(template)

    if created:
        db_session.flush()

    return created
