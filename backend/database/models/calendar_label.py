"""
Calendar Label Model - Color-coded labels for appointment categorization.

Provides:
- CalendarLabel: Org-level or personal labels with color, icon, and sort order
- AppointmentLabel: Junction table linking appointments to labels (many-to-many)

Default labels seeded via seed_default_labels():
  - Pre-Approval (blue), Application (green), Closing (purple),
    Follow-Up (orange), Consultation (teal)

Usage:
    from database.models.calendar_label import CalendarLabel, AppointmentLabel
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
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


class CalendarLabel(Base):
    """
    Color-coded label for categorizing calendar appointments.

    Labels can be organization-wide (user_id is NULL) or personal
    (user_id is set). Personal labels are only visible to the
    creating user; org-wide labels are visible to all members.
    """
    __tablename__ = "calendar_labels"
    __table_args__ = (
        Index("ix_calendar_labels_org", "organization_id"),
        Index("ix_calendar_labels_org_user", "organization_id", "user_id"),
        Index("ix_calendar_labels_sort", "organization_id", "sort_order"),
        UniqueConstraint(
            "organization_id", "user_id", "name",
            name="uq_calendar_labels_org_user_name",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NULL = org-wide label; set = personal label for this user only
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Display
    name = Column(String(50), nullable=False)
    color = Column(String(7), nullable=False, default="#4A90D9")  # hex, e.g. "#4A90D9"
    icon = Column(String(10), nullable=True)  # optional emoji/symbol

    # Flags
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    appointment_labels = relationship(
        "AppointmentLabel",
        back_populates="label",
        cascade="all, delete-orphan",
    )


class AppointmentLabel(Base):
    """
    Junction table linking scheduler_appointments to calendar_labels.

    An appointment can have multiple labels; a label can be on many
    appointments. This supports multi-select labeling in the UI.
    """
    __tablename__ = "appointment_labels"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id", "label_id",
            name="uq_appointment_label",
        ),
        Index("ix_appointment_labels_appointment", "appointment_id"),
        Index("ix_appointment_labels_label", "label_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    label_id = Column(
        Integer,
        ForeignKey("calendar_labels.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    assigned_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    label = relationship("CalendarLabel", back_populates="appointment_labels")


# ============================================================================
# DEFAULT LABEL SEEDING
# ============================================================================

DEFAULT_LABELS = [
    {"name": "Pre-Approval", "color": "#4A90D9", "icon": None, "sort_order": 0},
    {"name": "Application", "color": "#27AE60", "icon": None, "sort_order": 1},
    {"name": "Closing", "color": "#8E44AD", "icon": None, "sort_order": 2},
    {"name": "Follow-Up", "color": "#E67E22", "icon": None, "sort_order": 3},
    {"name": "Consultation", "color": "#16A085", "icon": None, "sort_order": 4},
]


def seed_default_labels(db_session, organization_id: int) -> list:
    """
    Seed default calendar labels for an organization.

    Idempotent: skips labels that already exist (matched by name + org + user_id IS NULL).

    Returns:
        List of created CalendarLabel instances (empty if all existed).
    """
    created = []
    for label_data in DEFAULT_LABELS:
        existing = (
            db_session.query(CalendarLabel)
            .filter(
                CalendarLabel.organization_id == organization_id,
                CalendarLabel.user_id.is_(None),
                CalendarLabel.name == label_data["name"],
            )
            .first()
        )
        if existing:
            continue

        label = CalendarLabel(
            organization_id=organization_id,
            user_id=None,
            is_default=True,
            **label_data,
        )
        db_session.add(label)
        created.append(label)

    if created:
        db_session.flush()

    return created
