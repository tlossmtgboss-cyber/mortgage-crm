"""
Calendar Event Map Model

Maps internal scheduler appointments to external calendar events across any
provider. Replaces the hardcoded google_calendar_event_id / outlook_event_id
columns on the Appointment model with a flexible many-to-many mapping that
supports an unlimited number of calendar providers.

Usage:
    from database.models.calendar_event_map import CalendarEventMap

Table: calendar_event_maps
    - One row per (appointment_id, provider) pair
    - Unique constraint ensures at most one mapping per provider per appointment
    - Composite index on (provider, external_id) for reverse lookups
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


class CalendarEventMap(Base):
    """Maps an internal scheduler appointment to an external calendar event.

    Each row represents a single sync relationship: one appointment synced to
    one external calendar provider. An appointment can be synced to multiple
    providers (e.g., Google + Outlook + Salesforce simultaneously).
    """

    __tablename__ = "calendar_event_maps"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id",
            "provider",
            name="uq_calendar_event_map_appt_provider",
        ),
        Index(
            "ix_calendar_event_map_external",
            "provider",
            "external_id",
        ),
        Index(
            "ix_calendar_event_map_org",
            "organization_id",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Link to the internal appointment
    appointment_id = Column(
        Integer,
        ForeignKey("scheduler_appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provider identification
    provider = Column(
        String(50),
        nullable=False,
        comment="Calendar provider key (google, outlook, salesforce, etc.)",
    )

    # External event reference
    external_id = Column(
        String(255),
        nullable=False,
        comment="Event ID in the external calendar system",
    )
    external_link = Column(
        String(500),
        nullable=True,
        comment="Web URL to view the event in the external system",
    )

    # Sync status tracking
    sync_status = Column(
        String(20),
        nullable=False,
        default="synced",
        comment="Current sync state: synced, pending, failed, deleted",
    )
    synced_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="Timestamp of the last successful sync",
    )
    last_error = Column(
        Text,
        nullable=True,
        comment="Last sync error message, if any",
    )

    # Metadata
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<CalendarEventMap appointment_id={self.appointment_id} "
            f"provider={self.provider!r} external_id={self.external_id!r}>"
        )
