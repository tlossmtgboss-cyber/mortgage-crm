"""
Appointment Template Models

Pre-configured appointment settings that can be quick-selected when creating
new appointments. Templates store default duration, location type, buffer times,
intake form fields, and reminder configuration.

Models:
    - AppointmentTemplate: Reusable appointment preset for an organization

Usage:
    from database.models.appointment_template import AppointmentTemplate

    # Get active templates for an org
    templates = db.query(AppointmentTemplate).filter(
        AppointmentTemplate.organization_id == org_id,
        AppointmentTemplate.is_active == True,
        AppointmentTemplate.deleted_at.is_(None),
    ).order_by(AppointmentTemplate.sort_order).all()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    ForeignKey,
    Index,
)

from db import Base


class AppointmentTemplate(Base):
    """
    Pre-configured appointment settings template.

    Each organization can have multiple templates (e.g., "Discovery Call",
    "Document Review", "Closing Walkthrough") that pre-fill appointment
    creation forms with sensible defaults.
    """
    __tablename__ = "appointment_templates"
    __table_args__ = (
        Index('ix_appt_tmpl_org_active', 'organization_id', 'is_active'),
        Index('ix_appt_tmpl_org_sort', 'organization_id', 'sort_order'),
        Index('ix_appt_tmpl_created_by', 'created_by'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Template identity
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Appointment defaults
    duration_minutes = Column(Integer, nullable=False, default=30)
    appointment_type = Column(String(100), nullable=True)  # e.g., "discovery_call", "doc_review"
    location_type = Column(String(50), nullable=False, default="virtual")  # in_person, virtual, phone

    # Location details (pre-filled when template is selected)
    default_location = Column(String(500), nullable=True)  # address, meeting URL, phone number

    # Buffer times around the appointment
    buffer_before_minutes = Column(Integer, nullable=False, default=0)
    buffer_after_minutes = Column(Integer, nullable=False, default=0)

    # Customizable intake form fields (JSON list of field definitions)
    # Example: [{"name": "loan_number", "label": "Loan Number", "type": "text", "required": true}]
    intake_form_fields = Column(JSON, nullable=True, default=list)

    # Reminder configuration (JSON object with reminder settings)
    # Example: {"reminders": [{"minutes_before": 1440, "channel": "email"}, {"minutes_before": 60, "channel": "sms"}]}
    reminder_config = Column(JSON, nullable=True, default=dict)

    # Status flags
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)

    # Display ordering (lower = shown first)
    sort_order = Column(Integer, nullable=False, default=0)

    # Soft delete
    deleted_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
