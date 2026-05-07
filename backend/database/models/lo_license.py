"""
Loan Officer License Model

SQLAlchemy model for the lo_licenses table, which tracks multi-state
licensing status for mortgage loan originators.

SAFE Act (S.2039) requires all MLOs to hold active state-specific
licenses registered through NMLS. This model backs Domain 2
(Compliance) Check 2.20: Multi-State License Enforcement.

The table was originally created via alembic migration
010_los_integration_compliance.py. This model provides ORM access
so the license enforcement service can use proper queries instead
of raw SQL.

Usage:
    from database.models.lo_license import LoanOfficerLicense, LicenseStatus

    # Query active licenses for a user
    licenses = db.query(LoanOfficerLicense).filter(
        LoanOfficerLicense.user_id == user_id,
        LoanOfficerLicense.status == LicenseStatus.ACTIVE,
    ).all()
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


# =============================================================================
# Enums
# =============================================================================

class LicenseStatus(str, enum.Enum):
    """Status of a loan officer license."""
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    PENDING = "pending"


class LicenseType(str, enum.Enum):
    """Type of mortgage license."""
    MLO = "mlo"             # Mortgage Loan Originator (individual)
    BRANCH = "branch"       # Branch registration
    COMPANY = "company"     # Company license


# =============================================================================
# Model
# =============================================================================

class LoanOfficerLicense(Base):
    """Multi-state license record for a loan officer.

    Maps to the existing ``lo_licenses`` table created by alembic
    migration 010_los_integration_compliance. Each row represents
    a single state license held by one user.

    The unique constraint on (user_id, state) ensures one license
    record per user per state. Status transitions track the
    license lifecycle: pending -> active -> expired/suspended/revoked.
    """
    __tablename__ = "lo_licenses"
    __table_args__ = (
        Index("ix_lo_licenses_user_id", "user_id"),
        Index("ix_lo_licenses_state", "state"),
        UniqueConstraint("user_id", "state", name="ix_lo_licenses_user_state"),
        Index("ix_lo_licenses_org_id", "organization_id"),
        Index("ix_lo_licenses_expiration", "expiration_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    state = Column(String(2), nullable=False)
    license_type = Column(String, default="mlo")  # mlo, branch, company
    license_number = Column(String, nullable=True)
    nmls_number = Column(String, nullable=True)
    status = Column(String, default="active")  # active, expired, suspended, revoked, pending
    issue_date = Column(Date, nullable=True)
    expiration_date = Column(Date, nullable=True)
    renewal_date = Column(Date, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])


__all__ = [
    "LoanOfficerLicense",
    "LicenseStatus",
    "LicenseType",
]
