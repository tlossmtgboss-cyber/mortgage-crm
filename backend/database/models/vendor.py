"""
Vendor & Vendor Order Models

Tracks appraisal, title, HOI, and survey vendors plus individual orders
tied to loans. Supports performance monitoring (turnaround, quality) and
preferred-vendor ranking per organization.

Usage:
    from database.models.vendor import Vendor, VendorOrder
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date,
    Text, ForeignKey, Index, Numeric,
)
from sqlalchemy.orm import relationship

from db import Base


# ============================================================================
# VENDOR
# ============================================================================

class Vendor(Base):
    """Third-party service vendor (appraisal, title, HOI, survey)."""
    __tablename__ = "vendors"
    __table_args__ = (
        Index("ix_vendors_org_id", "organization_id"),
        Index("ix_vendors_type", "vendor_type"),
        Index("ix_vendors_org_type", "organization_id", "vendor_type"),
        Index("ix_vendors_is_preferred", "organization_id", "is_preferred"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    name = Column(String(255), nullable=False)
    vendor_type = Column(String(50), nullable=False)  # appraisal, title, hoi, survey
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    license_number = Column(String(100), nullable=True)

    # Performance metrics (updated by VendorManagementService)
    avg_turnaround_days = Column(Numeric(6, 2), nullable=True)
    quality_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    total_orders = Column(Integer, default=0)
    completed_orders = Column(Integer, default=0)
    issue_count = Column(Integer, default=0)

    is_preferred = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    orders = relationship("VendorOrder", back_populates="vendor", lazy="select")

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.name!r} type={self.vendor_type}>"


# ============================================================================
# VENDOR ORDER
# ============================================================================

class VendorOrder(Base):
    """Individual order placed with a vendor for a specific loan."""
    __tablename__ = "vendor_orders"
    __table_args__ = (
        Index("ix_vendor_orders_org_id", "organization_id"),
        Index("ix_vendor_orders_vendor_id", "vendor_id"),
        Index("ix_vendor_orders_loan_id", "loan_id"),
        Index("ix_vendor_orders_status", "status"),
        Index("ix_vendor_orders_org_status", "organization_id", "status"),
        Index("ix_vendor_orders_ordered_at", "ordered_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)

    order_type = Column(String(50), nullable=False)  # appraisal, title, hoi, survey
    status = Column(String(50), default="ordered")  # ordered, in_progress, completed, cancelled, revision_needed
    amount = Column(Numeric(10, 2), nullable=True)

    # Timeline
    ordered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    turnaround_days = Column(Numeric(6, 2), nullable=True)  # Computed on completion

    # Quality / issues
    has_issues = Column(Boolean, default=False)
    issue_description = Column(Text, nullable=True)
    revision_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    vendor = relationship("Vendor", back_populates="orders")

    def __repr__(self) -> str:
        return (
            f"<VendorOrder id={self.id} vendor_id={self.vendor_id} "
            f"loan_id={self.loan_id} type={self.order_type} status={self.status}>"
        )
