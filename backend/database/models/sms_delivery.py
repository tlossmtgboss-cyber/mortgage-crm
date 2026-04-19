"""SMS Delivery Log model — ORM backing for the sms_delivery_log table.

This table tracks every outbound SMS sent through Telnyx with full delivery
lifecycle: queued -> sending -> sent -> delivered/failed.  Telnyx webhook
callbacks update status, carrier info, and error codes.

Previously this table was created via raw SQL (and a partial ORM definition
existed in the deprecated backend/models/sms_models.py).  This canonical
ORM model in database/models/ ensures Base.metadata.create_all() creates it,
column validation is enforced, and TCPA consent-proof columns are present.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from db import Base


class SMSDeliveryLog(Base):
    """Detailed delivery tracking record for a single outbound SMS."""

    __tablename__ = "sms_delivery_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Telnyx-assigned message ID — used for webhook correlation
    telnyx_message_id = Column(String(100), unique=True, nullable=False, index=True)

    # Destination and source phone numbers
    to_phone = Column(String(20), nullable=False, index=True)
    from_phone = Column(String(20), nullable=True)

    # Message content (truncated to 500 chars at INSERT time by tracker)
    message_body = Column(Text, nullable=True)

    # Direction ('outbound' for most rows; kept for future inbound tracking)
    direction = Column(String(20), server_default="outbound")

    # Delivery status: queued -> sending -> sent -> delivered / failed / unconfirmed
    status = Column(String(50), server_default="queued", index=True)

    # Number of SMS segments (affects billing)
    segments = Column(Integer, server_default="1")

    # ── TCPA consent proof ──────────────────────────────────────────────
    # FK to sms_consent.id that authorized this send
    consent_record_id = Column(Integer, nullable=True)
    # Timestamp when consent was verified before transmission
    consent_verified_at = Column(DateTime(timezone=True), nullable=True)
    # How consent was obtained: web_form, sms_keyword, verbal, etc.
    consent_method = Column(String(50), nullable=True)

    # ── Tenant & actor context ──────────────────────────────────────────
    organization_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    lead_id = Column(Integer, nullable=True, index=True)
    queue_id = Column(Integer, nullable=True)

    # ── Delivery details (populated by Telnyx webhooks) ─────────────────
    error_code = Column(String(50), nullable=True)
    carrier_name = Column(String(100), nullable=True)

    # ── Timestamps ──────────────────────────────────────────────────────
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = {"extend_existing": True}

    def __repr__(self) -> str:
        return (
            f"<SMSDeliveryLog id={self.id} telnyx_id={self.telnyx_message_id!r} "
            f"to={self.to_phone!r} status={self.status!r}>"
        )
