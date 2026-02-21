"""
Billing and Subscription Models

Provides multi-tenant billing infrastructure:
- Subscription management (plans, tiers)
- Usage-based billing
- Invoice tracking
- Stripe integration

Usage:
    from models.billing import Subscription, Invoice, UsageRecord

    # Create subscription
    subscription = Subscription(
        organization_id=org.id,
        plan_id="professional",
        stripe_subscription_id="sub_xxx",
    )
"""

import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, Numeric, JSON, Index, UniqueConstraint,
    Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class SubscriptionStatus(str, Enum):
    """Subscription lifecycle states."""
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


class PlanTier(str, Enum):
    """Available subscription tiers."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class BillingInterval(str, Enum):
    """Billing frequency."""
    MONTHLY = "monthly"
    ANNUAL = "annual"


class InvoiceStatus(str, Enum):
    """Invoice payment states."""
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


# =============================================================================
# PLANS AND FEATURES
# =============================================================================

class Plan(Base):
    """
    Subscription plan definitions.

    Defines what features and limits are included in each tier.
    """
    __tablename__ = "plans"

    id = Column(String(50), primary_key=True)  # e.g., "professional"
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Pricing
    price_monthly = Column(Numeric(10, 2), nullable=False)
    price_annual = Column(Numeric(10, 2))  # Annual price (discount)

    # Stripe Product/Price IDs
    stripe_product_id = Column(String(100))
    stripe_price_monthly_id = Column(String(100))
    stripe_price_annual_id = Column(String(100))

    # Feature limits
    max_users = Column(Integer, default=5)
    max_leads_per_month = Column(Integer, default=100)
    max_loans_per_month = Column(Integer, default=50)
    max_ai_tokens_per_month = Column(Integer, default=100000)
    max_storage_gb = Column(Integer, default=10)

    # Feature flags
    features = Column(JSONB, default=dict)
    """
    Example features:
    {
        "ai_assistant": true,
        "automated_workflows": true,
        "custom_reports": true,
        "api_access": true,
        "white_label": false,
        "dedicated_support": false
    }
    """

    # Visibility
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)  # Show on pricing page
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# SUBSCRIPTIONS
# =============================================================================

class Subscription(Base):
    """
    Organization subscription to a plan.

    Links an organization to their billing plan and Stripe subscription.
    """
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    plan_id = Column(String(50), ForeignKey("plans.id"), nullable=False)

    # Stripe integration
    stripe_customer_id = Column(String(100), index=True)
    stripe_subscription_id = Column(String(100), unique=True, index=True)

    # Status
    status = Column(SQLEnum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.TRIALING)
    billing_interval = Column(SQLEnum(BillingInterval), default=BillingInterval.MONTHLY)

    # Billing period
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    trial_end = Column(DateTime)

    # Grace period for payment failures (LIC-006)
    grace_period_ends_at = Column(DateTime, nullable=True)

    # Cancellation
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime)
    cancellation_reason = Column(Text)

    # Usage tracking
    current_users = Column(Integer, default=0)
    current_leads_this_month = Column(Integer, default=0)
    current_loans_this_month = Column(Integer, default=0)
    current_ai_tokens_this_month = Column(Integer, default=0)
    current_storage_gb = Column(Numeric(10, 2), default=0)

    # Metadata (Python attr 'meta_data' avoids conflict with SQLAlchemy's reserved .metadata)
    meta_data = Column('metadata', JSONB, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    plan = relationship("Plan")
    invoices = relationship("Invoice", back_populates="subscription", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_subscription_org_status", "organization_id", "status"),
    )

    def is_active(self) -> bool:
        """Check if subscription is in an active state."""
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)

    def has_feature(self, feature_name: str) -> bool:
        """Check if subscription plan includes a feature."""
        if self.plan and self.plan.features:
            return self.plan.features.get(feature_name, False)
        return False

    def is_within_limit(self, limit_name: str, current_value: int) -> bool:
        """Check if usage is within plan limits."""
        if not self.plan:
            return False
        limit = getattr(self.plan, limit_name, None)
        if limit is None:
            return True  # No limit defined
        return current_value < limit


# =============================================================================
# INVOICES
# =============================================================================

class Invoice(Base):
    """
    Billing invoice for subscription charges.

    Tracks both Stripe-generated invoices and custom invoices.
    """
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)

    # Stripe integration
    stripe_invoice_id = Column(String(100), unique=True, index=True)
    stripe_payment_intent_id = Column(String(100))

    # Invoice details
    invoice_number = Column(String(50), unique=True)
    status = Column(SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)

    # Amounts (in cents for precision)
    subtotal = Column(Integer, nullable=False, default=0)
    tax = Column(Integer, default=0)
    total = Column(Integer, nullable=False, default=0)
    amount_paid = Column(Integer, default=0)
    amount_due = Column(Integer, default=0)

    # Currency
    currency = Column(String(3), default="usd")

    # Dates
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date)
    paid_at = Column(DateTime)

    # Period covered
    period_start = Column(DateTime)
    period_end = Column(DateTime)

    # Line items
    line_items = Column(JSONB, default=list)
    """
    Example line items:
    [
        {"description": "Professional Plan", "amount": 9900, "quantity": 1},
        {"description": "Additional users (3)", "amount": 2700, "quantity": 3},
        {"description": "AI token overage", "amount": 500, "quantity": 1}
    ]
    """

    # PDF storage
    invoice_pdf_url = Column(String(500))
    hosted_invoice_url = Column(String(500))

    # Metadata
    notes = Column(Text)
    meta_data = Column('metadata', JSONB, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    subscription = relationship("Subscription", back_populates="invoices")

    __table_args__ = (
        Index("ix_invoice_org_date", "organization_id", "invoice_date"),
    )


# =============================================================================
# USAGE TRACKING
# =============================================================================

class UsageRecord(Base):
    """
    Granular usage tracking for metered billing.

    Records individual usage events for billing calculations.
    """
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)

    # Usage details
    usage_type = Column(String(50), nullable=False, index=True)
    # Types: ai_tokens, storage_gb, api_calls, leads_created, loans_created, users_active
    quantity = Column(Numeric(18, 6), nullable=False)
    unit_type = Column(String(30))  # tokens, gb, calls, etc.

    # Attribution
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    request_id = Column(String(100))  # For correlation

    # Timestamp
    recorded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    usage_date = Column(Date, nullable=False)  # For daily aggregation

    # Billing
    is_billable = Column(Boolean, default=True)
    is_billed = Column(Boolean, default=False)
    billed_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"))

    # Metadata
    meta_data = Column('metadata', JSONB, default=dict)

    # Relationships
    subscription = relationship("Subscription", back_populates="usage_records")

    __table_args__ = (
        Index("ix_usage_org_date_type", "organization_id", "usage_date", "usage_type"),
        Index("ix_usage_subscription_date", "subscription_id", "usage_date"),
    )


# =============================================================================
# PAYMENT METHODS
# =============================================================================

class PaymentMethod(Base):
    """
    Stored payment methods for an organization.

    Links to Stripe payment methods for secure storage.
    """
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)

    # Stripe integration
    stripe_payment_method_id = Column(String(100), unique=True, nullable=False)
    stripe_customer_id = Column(String(100), nullable=False, index=True)

    # Card details (stored by Stripe, we only keep display info)
    type = Column(String(30), nullable=False)  # card, bank_account, etc.
    card_brand = Column(String(30))  # visa, mastercard, amex
    card_last4 = Column(String(4))
    card_exp_month = Column(Integer)
    card_exp_year = Column(Integer)

    # Status
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Metadata
    billing_name = Column(String(255))
    billing_email = Column(String(255))
    billing_address = Column(JSONB)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_payment_method_org_default", "organization_id", "is_default"),
    )


# =============================================================================
# STRIPE WEBHOOK EVENTS
# =============================================================================

class StripeEvent(Base):
    """
    Log of processed Stripe webhook events.

    Used for idempotency and debugging.
    """
    __tablename__ = "stripe_events"

    id = Column(String(100), primary_key=True)  # Stripe event ID (evt_xxx)
    event_type = Column(String(100), nullable=False, index=True)
    api_version = Column(String(20))

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    processing_error = Column(Text)

    # Event data
    data = Column(JSONB, nullable=False)

    # Related objects
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"))
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_stripe_event_type_processed", "event_type", "processed"),
    )


# =============================================================================
# FEATURE FLAGS (per organization)
# =============================================================================

class OrganizationFeature(Base):
    """
    Feature flag overrides for specific organizations.

    Allows enabling/disabling features independent of plan.
    """
    __tablename__ = "organization_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    feature_name = Column(String(100), nullable=False)

    # Override
    is_enabled = Column(Boolean, nullable=False)
    reason = Column(Text)  # Why this override exists

    # Validity
    valid_from = Column(DateTime)
    valid_until = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("organization_id", "feature_name", name="uq_org_feature"),
    )
