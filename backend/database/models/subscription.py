"""
Subscription & Billing Models

SubscriptionPlan, Subscription, PromoCode, and TeamMember models.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.subscription import SubscriptionPlan, Subscription, PromoCode, TeamMember
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Numeric,
    Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship

from db import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    price_monthly = Column(Numeric(18, 2), nullable=False)
    price_yearly = Column(Numeric(18, 2))
    stripe_price_id = Column(String)
    features = Column(JSON)  # List of features
    user_limit = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    status = Column(String, default="trialing")  # trialing, active, past_due, canceled
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    trial_end = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PromoCode(Base):
    """Promotional codes for registration discounts"""
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    discount_type = Column(String, default="percentage")  # percentage, fixed, trial_extension
    discount_value = Column(Numeric(18, 2), default=0)  # percentage (0-100) or fixed dollar amount
    trial_days = Column(Integer, default=0)  # additional trial days
    max_uses = Column(Integer)  # null = unlimited
    current_uses = Column(Integer, default=0)
    valid_from = Column(DateTime)
    valid_until = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TeamMember(Base):
    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Account owner
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)  # loan_officer, processor, underwriter, etc
    responsibilities = Column(Text)  # Parsed from upload
    status = Column(String, default="pending")  # pending, invited, active
    invited_at = Column(DateTime)
    joined_at = Column(DateTime)
    meta_data = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


__all__ = [
    "SubscriptionPlan",
    "Subscription",
    "PromoCode",
    "TeamMember",
]
