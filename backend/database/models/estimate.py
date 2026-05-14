"""
Estimate Parser Models

Models for loan estimate parsing, caching, failure tracking, and comparison analytics.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.estimate import EstimateParseCache, EstimateParseFailure, EstimateComparison
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    Text, ForeignKey, Index, JSON, Numeric
)
from sqlalchemy.orm import relationship

from db import Base


class EstimateParseCache(Base):
    """
    Cache for parsed loan estimates - prevents re-processing identical uploads.
    Uses SHA-256 hash of file contents as primary key for deduplication.
    """
    __tablename__ = "estimate_parse_cache"

    doc_hash = Column(String(64), primary_key=True)  # SHA-256 hash
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    parsed_json = Column(JSON, nullable=False)
    confidence_score = Column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00
    needs_review = Column(Boolean, default=False)
    source_type = Column(String(50), nullable=True)  # loan_estimate, fee_worksheet, closing_disclosure
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    accessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    access_count = Column(Integer, default=1)


class EstimateParseFailure(Base):
    """
    Tracks failed parse attempts for manual review and LLM prompt tuning.
    """
    __tablename__ = "estimate_parse_failures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(36), nullable=False)
    doc_hash = Column(String(64), nullable=False)
    error_stage = Column(String(50), nullable=False)  # ocr, llm, json_parse, validation
    error_message = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)  # truncated for debugging
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EstimateComparison(Base):
    """
    Tracks estimate comparisons made by users for analytics and conversion tracking.
    """
    __tablename__ = "estimate_comparisons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(100), nullable=True)  # for anonymous tracking
    estimate_a_hash = Column(String(64), ForeignKey("estimate_parse_cache.doc_hash", ondelete="CASCADE"), nullable=False)
    estimate_b_hash = Column(String(64), ForeignKey("estimate_parse_cache.doc_hash", ondelete="CASCADE"), nullable=False)
    winner = Column(String(1), nullable=True)  # 'A', 'B', or null if tie
    winner_reason = Column(String(200), nullable=True)
    savings_amount = Column(Numeric(12, 2), nullable=True)
    comparison_data = Column(JSON, nullable=True)
    converted = Column(Boolean, default=False)  # did user click CTA?
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="estimate_comparisons")


__all__ = [
    "EstimateParseCache",
    "EstimateParseFailure",
    "EstimateComparison",
]
