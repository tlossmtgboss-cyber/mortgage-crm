"""
Security Training Completion Records — SOC 2 CC1.4

Tracks employee completion of security awareness training programs,
attestations, and quiz scores for SOC 2 Type II audit evidence.

Usage:
    from database.models.security_training import SecurityTrainingRecord

    record = db.query(SecurityTrainingRecord).filter(
        SecurityTrainingRecord.user_id == user_id,
        SecurityTrainingRecord.training_year == 2026,
    ).first()
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON,
    Index,
)
from sqlalchemy.sql import func

# Import Base from the db module (renamed from database.py)
from db import Base


class SecurityTrainingRecord(Base):
    """Employee security training completion record for SOC 2 CC1.4 evidence."""
    __tablename__ = "security_training_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Training details
    training_type = Column(String, nullable=False)  # annual_security_awareness, onboarding, incident_response, data_handling
    training_year = Column(Integer, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Assessment
    score = Column(Integer, nullable=True)  # quiz score percentage (0-100)
    passed = Column(Boolean, default=False)
    passing_score = Column(Integer, default=80)

    # Attestation
    attestation_text = Column(Text, nullable=True)  # what the user acknowledged
    attested_at = Column(DateTime(timezone=True), nullable=True)

    # Certificate
    certificate_id = Column(String, nullable=True)  # unique cert ID for auditor reference
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Flexible metadata (training provider, module version, etc.)
    # Note: 'metadata' is reserved by SQLAlchemy's Declarative API
    training_metadata = Column("metadata", JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_security_training_user_year", "user_id", "training_year"),
        Index("ix_security_training_org_type_year", "organization_id", "training_type", "training_year"),
    )
