"""
Webhook Models

Database models for webhook subscriptions, delivery logs, and event tracking.
Enterprise API Gateway & Developer Experience (Domain 11).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

from db import Base


class WebhookSubscription(Base):
    """Webhook endpoint subscriptions for event notifications"""
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        Index('ix_webhook_org_active', 'organization_id', 'is_active'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Webhook configuration
    name = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    secret = Column(String, nullable=False)  # HMAC signing secret

    # Event subscriptions (e.g., ["lead.created", "loan.funded"])
    events = Column(JSON, default=list)

    # Custom headers for webhook requests
    headers = Column(JSON, default=dict)

    # Retry configuration
    retry_count = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=30)

    # Status
    is_active = Column(Boolean, default=True)

    # Stats
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    last_triggered_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    delivery_logs = relationship("WebhookDeliveryLog", back_populates="subscription", cascade="all, delete-orphan")


class WebhookDeliveryLog(Base):
    """Webhook delivery attempt logs with retry tracking"""
    __tablename__ = "webhook_delivery_logs"
    __table_args__ = (
        Index('ix_webhook_log_status', 'subscription_id', 'status'),
        Index('ix_webhook_log_created', 'created_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("webhook_subscriptions.id"), nullable=False, index=True)

    # Event details
    event_type = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)

    # Delivery status: pending, success, failed, retrying
    status = Column(String, default="pending", index=True)

    # Response details
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Retry tracking
    attempt_number = Column(Integer, default=1)
    max_attempts = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)

    # Dead-letter queue tracking
    dead_letter_at = Column(DateTime, nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    delivered_at = Column(DateTime, nullable=True)

    # Relationships
    subscription = relationship("WebhookSubscription", back_populates="delivery_logs")


class WebhookEventCatalog(Base):
    """Catalog of available webhook events for API documentation"""
    __tablename__ = "webhook_event_catalog"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, nullable=False, index=True)  # e.g., "lead.created"

    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False, index=True)  # leads, loans, documents, etc.

    # Payload schema (JSON Schema format)
    payload_schema = Column(JSON, nullable=False)

    # Example payload
    example_payload = Column(JSON, nullable=False)

    # Availability
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
