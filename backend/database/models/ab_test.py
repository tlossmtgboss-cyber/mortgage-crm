"""
A/B Testing Models for Public Booking Pages

Tables:
- ab_tests: Test configurations (headline, CTA, layout, color scheme variants)
- ab_test_results: Per-visitor impression and conversion tracking

Used by the scheduler booking system to optimize public booking page elements.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Text,
    Index,
)
from sqlalchemy.orm import relationship
import enum

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class ABTestStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"


class ABTestElementType(str, enum.Enum):
    HEADLINE = "headline"
    CTA_BUTTON = "cta_button"
    LAYOUT = "layout"
    COLOR_SCHEME = "color_scheme"


# ============================================================================
# AB TEST MODEL
# ============================================================================

class ABTest(Base):
    """
    Defines an A/B test for a public booking page element.

    Each test compares two variants (A and B) with configurable traffic split.
    Tests move through draft -> active -> completed lifecycle.
    """
    __tablename__ = "ab_tests"
    __table_args__ = (
        Index("ix_ab_tests_org_status", "organization_id", "status"),
        Index("ix_ab_tests_org_element", "organization_id", "element_type"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default=ABTestStatus.DRAFT.value)
    element_type = Column(String(30), nullable=False)

    # Variant configurations stored as JSON
    # Example for headline: {"text": "Book Your Free Consultation", "font_size": "24px"}
    # Example for cta_button: {"text": "Schedule Now", "color": "#2563eb", "size": "lg"}
    variant_a = Column(JSON, nullable=False, default=dict)
    variant_b = Column(JSON, nullable=False, default=dict)

    # Percentage of traffic routed to variant A (remainder goes to B)
    traffic_split = Column(Integer, nullable=False, default=50)

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", backref="ab_tests")
    results = relationship("ABTestResult", back_populates="ab_test", cascade="all, delete-orphan")


# ============================================================================
# AB TEST RESULT MODEL
# ============================================================================

class ABTestResult(Base):
    """
    Tracks individual visitor interactions with an A/B test variant.

    Each row represents a visitor's journey: impression -> optional booking conversion.
    The visitor_id enables deterministic assignment so returning visitors see the same variant.
    """
    __tablename__ = "ab_test_results"
    __table_args__ = (
        Index("ix_ab_results_test_variant", "ab_test_id", "variant"),
        Index("ix_ab_results_visitor", "ab_test_id", "visitor_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    ab_test_id = Column(
        Integer,
        ForeignKey("ab_tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    variant = Column(String(1), nullable=False)  # "A" or "B"
    visitor_id = Column(String(64), nullable=False, index=True)

    impressions = Column(Integer, nullable=False, default=0)
    bookings = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    ab_test = relationship("ABTest", back_populates="results")
