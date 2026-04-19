# SMS ORM models for tables accessed via raw SQL by integrations.
#
# These models exist so Base.metadata.create_all() can create the
# underlying tables.  The integration modules (sms_retry_queue.py,
# sms_rate_limiter.py) use raw SQL for performance, so the ORM
# classes are never queried directly.
#
# Canonical compliance models (SMSOptOut, SMSConsent, SMSComplianceLog)
# live in database/models/sms_compliance.py.
# Canonical delivery tracking (SMSDeliveryLog) lives in
# database/models/sms_delivery.py.

from sqlalchemy import Column, Integer, String, Text, DateTime, func


# Re-export canonical models for backward compatibility with
# `from models.sms_models import SMSOptOut` (etc.) -- but prefer
# importing from database.models.sms_compliance directly.
from database.models.sms_compliance import SMSOptOut, SMSConsent, SMSComplianceLog  # noqa: F401
from database.models.sms_delivery import SMSDeliveryLog  # noqa: F401

# SMSConversation is defined canonically in database/models/communication.py
from database.models.communication import SMSConversation  # noqa: F401

from database import Base


class SMSRateLimitLog(Base):
    """Per-send rate limit log for sliding-window rate limiting.

    Matches the sms_rate_limit_log table queried by sms_rate_limiter.py.
    """
    __tablename__ = "sms_rate_limit_log"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), index=True)
    user_id = Column(Integer, nullable=True, index=True)
    lead_id = Column(Integer, nullable=True, index=True)
    sent_at = Column(DateTime, server_default=func.now(), index=True)


class SMSQueue(Base):
    """SMS send queue with retry support.

    Matches the sms_queue table queried by sms_retry_queue.py.
    """
    __tablename__ = "sms_queue"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), nullable=False, index=True)
    from_phone = Column(String(20), nullable=True)
    message_body = Column(Text, nullable=False)
    lead_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True)
    template_id = Column(Integer, nullable=True)
    priority = Column(Integer, default=5)
    status = Column(String(20), default="pending", index=True)
    retry_count = Column(Integer, default=0)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    telnyx_message_id = Column(String(100), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_error = Column(Text, nullable=True)
    failed_at = Column(DateTime, nullable=True)
