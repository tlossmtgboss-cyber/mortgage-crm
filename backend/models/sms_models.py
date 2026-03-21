from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, func
from database import Base


class SMSOptOut(Base):
    """Opt-out records for TCPA compliance. Checked before every outbound SMS."""
    __tablename__ = "sms_opt_outs"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    opt_out_keyword = Column(String(20), default="STOP")
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(Integer, nullable=True, index=True)
    active = Column(Boolean, default=True)
    opted_out_at = Column(DateTime, server_default=func.now())
    opted_in_at = Column(DateTime, nullable=True)


class SMSConsent(Base):
    """Written consent records for outbound SMS (TCPA)."""
    __tablename__ = "sms_consent"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    consent_given = Column(Boolean, default=False)
    consent_source = Column(String(50))
    consented_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45), nullable=True)


class SMSComplianceLog(Base):
    """Audit trail for pre-send compliance checks."""
    __tablename__ = "sms_compliance_log"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True)
    lead_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    check_result = Column(String(50))
    checked_at = Column(DateTime, server_default=func.now())


class SMSDeliveryStatus(Base):
    """Delivery status tracking from Telnyx webhooks."""
    __tablename__ = "sms_delivery_status"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, index=True)
    phone_number = Column(String(20), index=True)
    status = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())


class SMSAnalytics(Base):
    """SMS event logging for analytics dashboards."""
    __tablename__ = "sms_analytics"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50))
    phone_number = Column(String(20))
    lead_id = Column(Integer, nullable=True)
    message_length = Column(Integer)
    timestamp = Column(DateTime, server_default=func.now())


class SMSRateLimitLog(Base):
    """Per-send rate limit log for sliding-window rate limiting.

    Matches the sms_rate_limit_log table queried by sms_rate_limiter.py.
    """
    __tablename__ = "sms_rate_limit_log"
    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), index=True)
    user_id = Column(Integer, nullable=True, index=True)
    lead_id = Column(Integer, nullable=True, index=True)
    sent_at = Column(DateTime, server_default=func.now(), index=True)


class SMSScheduledMessage(Base):
    """Scheduled SMS messages for deferred delivery."""
    __tablename__ = "sms_scheduled_messages"
    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), nullable=False)
    message_body = Column(Text, nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")


class SMSQueue(Base):
    """SMS send queue with retry support.

    Matches the sms_queue table queried by sms_retry_queue.py.
    """
    __tablename__ = "sms_queue"
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


# SMSConversation is defined canonically in database/models/communication.py
# (tenant-aware, with relationships). Re-export here for backward compatibility.
from database.models.communication import SMSConversation  # noqa: F401


class SMSDeliveryLog(Base):
    """Detailed delivery tracking log from Telnyx webhooks."""
    __tablename__ = "sms_delivery_log"
    id = Column(Integer, primary_key=True, index=True)
    telnyx_message_id = Column(String(100), unique=True, index=True)
    to_phone = Column(String(20), index=True)
    from_phone = Column(String(20), nullable=True)
    message_body = Column(Text, nullable=True)
    lead_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    queue_id = Column(Integer, nullable=True)
    status = Column(String(50), default="queued")
    segments = Column(Integer, default=1)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    error_code = Column(String(50), nullable=True)
    carrier_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
