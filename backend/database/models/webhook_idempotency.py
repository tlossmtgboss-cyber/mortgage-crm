"""
Webhook Idempotency Records

Tracks processed webhook callbacks from external providers (Vapi, Telnyx,
Stripe) to prevent duplicate processing when providers retry on timeout
or failure.  Without this, retries can double-book appointments, create
duplicate activities, or trigger duplicate SMS sends.

Records older than 72 hours can be purged via the created_at index.

Usage:
    from database.models.webhook_idempotency import WebhookIdempotencyRecord

    record = WebhookIdempotencyRecord(
        idempotency_key="vapi:call.completed:evt_abc123",
        provider="vapi",
        event_type="call.completed",
        event_id="evt_abc123",
        status="processed",
        response_code=200,
    )
    db.add(record)
    db.commit()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Index,
    func,
)

from db import Base


class WebhookIdempotencyRecord(Base):
    """
    Append-only log of processed webhook events.

    The idempotency_key is a composite of provider + event_type + event_id
    (or a hash of provider + raw body when no event_id is available).
    The unique constraint prevents the same event from being processed twice.
    """
    __tablename__ = "webhook_idempotency"
    __table_args__ = (
        Index("ix_webhook_idem_provider", "provider"),
        Index("ix_webhook_idem_created", "created_at"),
        Index("ix_webhook_idem_provider_event", "provider", "event_type"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(
        String(255), unique=True, nullable=False, index=True,
    )
    provider = Column(String(50), nullable=False)       # 'vapi', 'telnyx', 'stripe'
    event_type = Column(String(100), nullable=True)      # 'call.completed', 'message.received', etc.
    event_id = Column(String(255), nullable=True)        # provider's event ID
    status = Column(
        String(20), nullable=False, default="processing",
    )  # 'processing', 'processed', 'failed'
    response_code = Column(Integer, nullable=True)       # HTTP status we returned
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create the webhook_idempotency table if it doesn't exist."""
    WebhookIdempotencyRecord.__table__.create(engine, checkfirst=True)
