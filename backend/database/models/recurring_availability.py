"""
Recurring Availability Models

Database models for the recurring weekly availability pattern system.

Tables:
- recurring_availability: Weekly recurring time slots (e.g., Mon 9:00-12:00, Tue 13:00-17:00)
- availability_exceptions: Date-specific overrides (e.g., blocked Dec 25, extra slot Jan 3)
- availability_templates: Reusable org-level schedule templates (e.g., "Standard 9-5", "Weekend")

These models work alongside the existing SchedulerConfig.working_hours JSON to provide
structured, queryable availability patterns with per-date exception support.
"""

from datetime import datetime, date, time, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time,
    Text, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship

from db import Base


class RecurringAvailability(Base):
    """
    Weekly recurring availability pattern for a user.

    Each row represents a time block on a specific day of the week.
    Multiple rows per day are allowed (e.g., morning + afternoon blocks with lunch gap).
    Rows can have effective_from/effective_until for seasonal schedules.
    """
    __tablename__ = "recurring_availability"
    __table_args__ = (
        Index('ix_recur_avail_user_dow', 'user_id', 'day_of_week'),
        Index('ix_recur_avail_org', 'organization_id'),
        Index('ix_recur_avail_active', 'user_id', 'is_active'),
        Index('ix_recur_avail_effective', 'effective_from', 'effective_until'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Day of week: 0=Monday, 1=Tuesday, ..., 6=Sunday (ISO standard)
    day_of_week = Column(Integer, nullable=False)

    # Time range for this availability block
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Effective date range (null = indefinite)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)

    # Timezone for interpreting start_time/end_time
    timezone = Column(String(100), nullable=False, default="America/Chicago")

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AvailabilityException(Base):
    """
    Date-specific availability override.

    Overrides the recurring weekly schedule for a specific date:
    - is_blocked=True, start_time=None, end_time=None: Entire day blocked (PTO, holiday)
    - is_blocked=True, start_time set, end_time set: Specific time range blocked
    - is_blocked=False, start_time set, end_time set: Extra availability window added
    """
    __tablename__ = "availability_exceptions"
    __table_args__ = (
        Index('ix_avail_exc_user_date', 'user_id', 'date'),
        Index('ix_avail_exc_org', 'organization_id'),
        Index('ix_avail_exc_date_range', 'date'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # The specific date this exception applies to
    date = Column(Date, nullable=False)

    # Optional time range (null = applies to entire day)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    # True = unavailable/blocked, False = extra availability
    is_blocked = Column(Boolean, nullable=False, default=True)

    # Human-readable reason (e.g., "Doctor appointment", "Holiday", "Extra office hours")
    reason = Column(String(500), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AvailabilityTemplate(Base):
    """
    Reusable org-level schedule template.

    Stores a complete weekly schedule as JSON that can be applied to users.
    Example schedule JSON:
    {
        "0": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
        "1": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
        ...
        "5": [],  // Saturday - no availability
        "6": []   // Sunday - no availability
    }
    """
    __tablename__ = "availability_templates"
    __table_args__ = (
        Index('ix_avail_tmpl_org', 'organization_id'),
        Index('ix_avail_tmpl_default', 'organization_id', 'is_default'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # JSON schedule: keys are day_of_week (0-6), values are lists of {start, end} dicts
    schedule = Column(JSON, nullable=False, default=dict)

    # Whether this is the default template for new users in the org
    is_default = Column(Boolean, default=False, nullable=False)

    # Timezone the template times are expressed in
    timezone = Column(String(100), nullable=False, default="America/Chicago")

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
