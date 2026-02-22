"""
Change Record Model — Change management tracking.
SOC 2 Criteria: CC8 (Change Management)
"""
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ARRAY, text
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()


class ChangeRecord(Base):
    __tablename__ = "soc2_change_record"

    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    change_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="requested")

    requested_by = Column(PgUUID(as_uuid=True), nullable=True)
    approved_by = Column(PgUUID(as_uuid=True), nullable=True)
    implemented_by = Column(PgUUID(as_uuid=True), nullable=True)
    tenant_id = Column(PgUUID(as_uuid=True), nullable=True)

    affected_systems = Column(ARRAY(Text), nullable=True)
    risk_level = Column(String(20), default="low")
    rollback_plan = Column(Text, nullable=True)
    testing_evidence = Column(Text, nullable=True)

    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    implemented_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    git_commit = Column(String(40), nullable=True)
    git_branch = Column(String(255), nullable=True)
    pull_request_url = Column(Text, nullable=True)
    deployment_id = Column(String(255), nullable=True)

    success = Column(Boolean, nullable=True)
    post_implementation_notes = Column(Text, nullable=True)
