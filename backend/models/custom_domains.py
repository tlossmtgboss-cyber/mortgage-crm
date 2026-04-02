"""
Custom Domains Model

Stores custom domains for multi-tenant CORS support.
Allows users/organizations to use their own domains.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from database import Base


class CustomDomain(Base):
    """
    Stores verified custom domains for organizations/users.

    Used by CORS middleware to dynamically allow origins.
    """
    __tablename__ = "custom_domains"

    id = Column(Integer, primary_key=True, index=True)

    # Domain info
    domain = Column(String(255), unique=True, nullable=False, index=True)
    # e.g., "www.timloss.com" or "loans.company.com"

    # Ownership
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Verification status
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String(64), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # SSL/Configuration
    ssl_status = Column(String(50), default="pending")  # pending, active, failed

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Indexes for fast CORS lookups
    __table_args__ = (
        Index('idx_custom_domains_active', 'domain', 'is_active'),
    )

    def __repr__(self):
        return f"<CustomDomain {self.domain} (verified={self.is_verified})>"
