"""
Audit Log Model — Core audit trail for all system actions.
SOC 2 Criteria: CC2, CC4, PI1
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, Integer, DateTime,
    ARRAY, JSON, text
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID, INET
from sqlalchemy.orm import declarative_base

# NOTE: Replace this with your existing Base from your app
# from app.database import Base
Base = declarative_base()


class AuditLog(Base):
    __tablename__ = "soc2_audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    # Who
    user_id = Column(PgUUID(as_uuid=True), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(100), nullable=True)
    tenant_id = Column(PgUUID(as_uuid=True), nullable=True)

    # What
    action = Column(String(50), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(255), nullable=True)

    # Details
    description = Column(Text, nullable=True)
    fields_accessed = Column(ARRAY(Text), nullable=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)

    # Context
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    request_method = Column(String(10), nullable=True)
    request_path = Column(Text, nullable=True)
    request_id = Column(PgUUID(as_uuid=True), nullable=True)
    session_id = Column(String(255), nullable=True)

    # Result
    status_code = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    # Classification
    severity = Column(String(20), default="low")
    data_classification = Column(String(20), default="internal")
    contains_pii = Column(Boolean, default=False)

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"user_id={self.user_id}, resource='{self.resource_type}/{self.resource_id}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "user_email": self.user_email,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "description": self.description,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "status_code": self.status_code,
            "success": self.success,
            "severity": self.severity,
            "contains_pii": self.contains_pii,
        }
