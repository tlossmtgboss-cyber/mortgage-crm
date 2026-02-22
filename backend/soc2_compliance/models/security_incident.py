"""
Security Incident Model — Incident response tracking.
SOC 2 Criteria: CC7 (System Operations), CC2 (Communication)
"""
from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, Integer, DateTime,
    ARRAY, ForeignKey, text
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()


class SecurityIncident(Base):
    __tablename__ = "soc2_security_incident"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="open")

    reported_by = Column(PgUUID(as_uuid=True), nullable=True)
    assigned_to = Column(PgUUID(as_uuid=True), nullable=True)
    tenant_id = Column(PgUUID(as_uuid=True), nullable=True)

    affected_systems = Column(ARRAY(Text), nullable=True)
    affected_users = Column(Integer, default=0)
    affected_records = Column(Integer, default=0)
    data_compromised = Column(Boolean, default=False)
    pii_involved = Column(Boolean, default=False)

    detected_at = Column(DateTime(timezone=True), nullable=True)
    contained_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    root_cause = Column(Text, nullable=True)
    remediation_steps = Column(Text, nullable=True)
    preventive_measures = Column(Text, nullable=True)
    lessons_learned = Column(Text, nullable=True)

    requires_notification = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    regulatory_reported = Column(Boolean, default=False)

    evidence_urls = Column(ARRAY(Text), nullable=True)
    related_audit_ids = Column(ARRAY(BigInteger), nullable=True)

    post_mortem_url = Column(Text, nullable=True)
    post_mortem_completed = Column(Boolean, default=False)

    timeline = relationship("IncidentTimeline", back_populates="incident", cascade="all, delete-orphan")


class IncidentTimeline(Base):
    __tablename__ = "soc2_incident_timeline"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    incident_id = Column(PgUUID(as_uuid=True), ForeignKey("soc2_security_incident.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    action = Column(String(100), nullable=False)
    actor_id = Column(PgUUID(as_uuid=True), nullable=True)
    description = Column(Text, nullable=False)

    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    is_automated = Column(Boolean, default=False)

    incident = relationship("SecurityIncident", back_populates="timeline")
