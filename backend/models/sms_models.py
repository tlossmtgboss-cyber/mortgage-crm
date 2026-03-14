from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Index, func
from database import Base

class SMSOptOut(Base):
    __tablename__ = "sms_opt_outs"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    opt_out_keyword = Column(String(20), default="STOP")
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    active = Column(Boolean, default=True)
    opted_out_at = Column(DateTime, server_default=func.now())
    opted_in_at = Column(DateTime, nullable=True)

class SMSConsent(Base):
    __tablename__ = "sms_consent"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    consent_given = Column(Boolean, default=False)
    consent_source = Column(String(50))
    consented_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45), nullable=True)

class SMSComplianceLog(Base):
    __tablename__ = "sms_compliance_log"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True)
    lead_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    check_result = Column(String(50))
    checked_at = Column(DateTime, server_default=func.now())

class SMSDeliveryStatus(Base):
    __tablename__ = "sms_delivery_status"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, index=True)
    phone_number = Column(String(20), index=True)
    status = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())

class SMSAnalytics(Base):
    __tablename__ = "sms_analytics"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50))
    phone_number = Column(String(20))
    lead_id = Column(Integer, nullable=True)
    message_length = Column(Integer)
    timestamp = Column(DateTime, server_default=func.now())

class SMSRateLimit(Base):
    __tablename__ = "sms_rate_limits"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True)
    message_count = Column(Integer, default=0)
    window_start = Column(DateTime, server_default=func.now())

class SMSScheduledMessage(Base):
    __tablename__ = "sms_scheduled_messages"
    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), nullable=False)
    message_body = Column(Text, nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")

class SMSQueue(Base):
    __tablename__ = "sms_retry_queue"
    id = Column(Integer, primary_key=True, index=True)
    to_phone = Column(String(20), nullable=False)
    message_body = Column(Text, nullable=False)
    attempts = Column(Integer, default=0)
    status = Column(String(20), default="queued")
