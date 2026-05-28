"""CIE database models — two tables, both RLS-protected."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database import Base
from engine.cipher import EncryptedCallField


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CIECallRecord(Base):
    """Raw call data — encrypted PII, provider-agnostic."""
    __tablename__ = "cie_call_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    canonical_call_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    external_call_id = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False, default="inbound")

    phone_from = Column(EncryptedCallField, nullable=True)
    phone_to = Column(EncryptedCallField, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    transcript_encrypted = Column(Text, nullable=True)
    recording_url_encrypted = Column(EncryptedCallField, nullable=True)
    raw_payload = Column(JSONB, nullable=True)

    # CRM linkage (nullable — unmatched calls still record)
    contact_id = Column(Integer, nullable=True)
    loan_id = Column(Integer, nullable=True)
    lead_id = Column(Integer, nullable=True)
    owner_user_id = Column(Integer, nullable=True)

    processing_status = Column(
        String(20), nullable=False, default="pending",
        comment="pending | processing | completed | failed | too_short",
    )
    processing_error = Column(Text, nullable=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    report = relationship("CIEIntelligenceReport", back_populates="call_record", uselist=False, lazy="joined")

    __table_args__ = (
        UniqueConstraint("external_call_id", "organization_id", name="uq_cie_call_ext_org"),
        Index("ix_cie_call_org_created", "organization_id", "created_at"),
        Index("ix_cie_call_status", "processing_status"),
        Index("ix_cie_call_loan", "loan_id"),
        Index("ix_cie_call_lead", "lead_id"),
    )


class CIEIntelligenceReport(Base):
    """Analysis output — scores, intent, conversion, compliance, actions."""
    __tablename__ = "cie_intelligence_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    call_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cie_call_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Scoring — 6 dimensions + composite
    cis_composite = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    information_quality_score = Column(Float, nullable=True)
    objection_handling_score = Column(Float, nullable=True)
    compliance_score = Column(Float, nullable=True)
    rapport_score = Column(Float, nullable=True)
    closing_effectiveness_score = Column(Float, nullable=True)

    # Intent
    primary_intent = Column(String(100), nullable=True)
    intent_confidence = Column(Float, nullable=True)

    # Conversion
    conversion_probability = Column(Float, nullable=True)
    conversion_ci_low = Column(Float, nullable=True)
    conversion_ci_high = Column(Float, nullable=True)

    # Structured findings (JSONB for flexible schema evolution)
    summary = Column(Text, nullable=True)
    summary_bullets = Column(JSONB, nullable=True)
    opportunities = Column(JSONB, nullable=True)
    risks = Column(JSONB, nullable=True)
    objections = Column(JSONB, nullable=True)
    compliance_flags = Column(JSONB, nullable=True)
    coaching_suggestions = Column(JSONB, nullable=True)
    generated_tasks = Column(JSONB, nullable=True)
    draft_messages = Column(JSONB, nullable=True)

    # Metadata
    llm_model_used = Column(String(100), nullable=True)
    pipeline_version = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    call_record = relationship("CIECallRecord", back_populates="report")

    __table_args__ = (
        Index("ix_cie_report_org_created", "organization_id", "created_at"),
        Index("ix_cie_report_call", "call_record_id"),
    )
