"""
Access Event Model — Authentication & authorization tracking.
SOC 2 Criteria: CC6 (Access Controls)
"""
from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, Integer, DateTime, text
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID, INET
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AccessEvent(Base):
    __tablename__ = "soc2_access_event"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    # Who
    user_id = Column(PgUUID(as_uuid=True), nullable=True)
    attempted_email = Column(String(255), nullable=True)
    tenant_id = Column(PgUUID(as_uuid=True), nullable=True)

    # What
    event_type = Column(String(50), nullable=False)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(255), nullable=True)

    # Auth details
    auth_method = Column(String(50), nullable=True)
    mfa_method = Column(String(50), nullable=True)
    session_id = Column(String(255), nullable=True)
    token_id = Column(String(255), nullable=True)

    # Context
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    geo_location = Column(String(255), nullable=True)
    device_fingerprint = Column(String(255), nullable=True)

    # Anomaly detection
    is_anomalous = Column(Boolean, default=False)
    anomaly_reason = Column(Text, nullable=True)
    risk_score = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "event_type": self.event_type,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "is_anomalous": self.is_anomalous,
            "risk_score": self.risk_score,
        }
