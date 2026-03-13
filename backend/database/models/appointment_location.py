"""
Appointment Location Models

Saved locations for scheduling appointments. Each organization can manage
a set of locations (offices, virtual meeting links, phone lines) that LOs
can select when creating appointments.

Models:
    - AppointmentLocation: Named meeting location with type-specific details

Usage:
    from database.models.appointment_location import AppointmentLocation

    # Get active locations for an org
    locations = db.query(AppointmentLocation).filter(
        AppointmentLocation.organization_id == org_id,
        AppointmentLocation.is_active == True,
    ).order_by(AppointmentLocation.name).all()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
)

from db import Base


class AppointmentLocation(Base):
    """
    A saved meeting location for an organization.

    Supports four location types:
    - office: physical office with address
    - virtual: video conference with meeting URL template
    - phone: phone appointment with a phone number
    - borrower_home: at the borrower's home (address entered per-appointment)

    Locations can be org-wide (user_id=NULL) or user-specific (user_id set).
    One location can be marked as the default for quick selection.
    """
    __tablename__ = "appointment_locations"
    __table_args__ = (
        Index('ix_appt_loc_org_active', 'organization_id', 'is_active'),
        Index('ix_appt_loc_org_user', 'organization_id', 'user_id'),
        Index('ix_appt_loc_org_default', 'organization_id', 'is_default'),
        Index('ix_appt_loc_type', 'organization_id', 'location_type'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identity
    name = Column(String(200), nullable=False)
    location_type = Column(String(50), nullable=False, default="office")
    # Allowed values: "office", "virtual", "phone", "borrower_home"

    # Physical address fields (used for "office" and optionally "borrower_home")
    address_line1 = Column(String(300), nullable=True)
    address_line2 = Column(String(300), nullable=True)
    city = Column(String(200), nullable=True)
    state = Column(String(100), nullable=True)
    zip_code = Column(String(20), nullable=True)

    # Virtual meeting link template (Zoom, Google Meet, etc.)
    meeting_url = Column(String(1000), nullable=True)

    # Phone number for phone appointments
    phone_number = Column(String(50), nullable=True)

    # Extra instructions (parking info, entry code, lobby directions, etc.)
    instructions = Column(Text, nullable=True)

    # Flags
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

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
