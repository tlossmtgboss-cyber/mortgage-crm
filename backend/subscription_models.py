"""
Perennia AI Subscription & Permission Models
Database models for subscription tiers, features, and usage tracking
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import text
from sqlalchemy.orm import relationship
from database import Base


class OrganizationSubscription(Base):
    """Organization subscription and billing information"""
    __tablename__ = 'organization_subscriptions'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, unique=True)

    # Subscription tier: lead_management, lead_and_active, full_pipeline
    tier = Column(String(50), nullable=False, default='lead_management')

    # Billing
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    billing_cycle = Column(String(20), default='monthly')  # monthly, annual
    monthly_price = Column(Numeric(10, 2), nullable=False, default=99.00)

    # Status
    status = Column(String(20), default='active')  # active, trial, past_due, canceled
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)

    # Feature add-ons (stored as JSONB for flexibility)
    enabled_addons = Column(JSONB, default=list)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))
    updated_at = Column(DateTime, nullable=False, server_default=text('NOW()'))


class FeatureDefinition(Base):
    """Defines available features and their tier requirements"""
    __tablename__ = 'feature_definitions'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))

    # Feature identification
    feature_key = Column(String(100), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)  # leads, loans, mum, ai, communications

    # Tier requirements (minimum tier needed)
    min_tier = Column(String(50), nullable=False)  # lead_management, lead_and_active, full_pipeline

    # Usage limits (null = unlimited)
    monthly_limit = Column(Integer, nullable=True)
    is_addon = Column(Boolean, default=False)
    addon_price = Column(Numeric(10, 2), nullable=True)

    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))


class FeatureUsage(Base):
    """Tracks feature usage per organization"""
    __tablename__ = 'feature_usage'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    feature_key = Column(String(100), nullable=False)

    # Usage tracking
    usage_count = Column(Integer, default=0)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))
    updated_at = Column(DateTime, nullable=False, server_default=text('NOW()'))


class UsageWarning(Base):
    """Tracks usage warnings sent to users"""
    __tablename__ = 'usage_warnings'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    feature_key = Column(String(100), nullable=False)

    # Warning details
    warning_type = Column(String(50), nullable=False)  # approaching_limit, limit_reached, feature_blocked
    threshold_percent = Column(Integer, nullable=True)  # 80, 90, 100
    message = Column(Text, nullable=True)

    # Status
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))


class AdminAction(Base):
    """Audit log for admin subscription actions"""
    __tablename__ = 'admin_actions'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)

    # Action details
    action_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    previous_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=text('NOW()'))


# Tier configuration constants
SUBSCRIPTION_TIERS = {
    'lead_management': {
        'name': 'Lead Management',
        'price_monthly': 299,
        'price_annual': 2999,
        'stages': ['lead_received', 'contacted', 'qualified', 'pre_approved', 'application', 'ratified_contract'],
        'features': {
            'leads': True,
            'basic_tasks': True,
            'email_templates': True,
            'basic_reports': True,
            'ai_assistant': True,
            'monthly_ai_queries': 100,
            'monthly_emails': 500,
            'monthly_sms': 100,
        }
    },
    'lead_and_active': {
        'name': 'Lead + Active Loan',
        'price_monthly': 399,
        'price_annual': 3999,
        'stages': ['lead_received', 'contacted', 'qualified', 'pre_approved', 'application',
                   'ratified_contract', 'processing', 'underwriting', 'conditional_approval',
                   'clear_to_close', 'closing', 'funding'],
        'features': {
            'leads': True,
            'active_loans': True,
            'document_tracking': True,
            'milestone_alerts': True,
            'advanced_tasks': True,
            'ai_assistant': True,
            'monthly_ai_queries': 500,
            'monthly_emails': 2000,
            'monthly_sms': 500,
        }
    },
    'full_pipeline': {
        'name': 'Full Perennia AI',
        'price_monthly': 499,
        'price_annual': 4999,
        'stages': 'all',
        'features': {
            'leads': True,
            'active_loans': True,
            'mum_clients': True,
            'referral_partners': True,
            'advanced_analytics': True,
            'custom_reports': True,
            'api_access': True,
            'ai_assistant': True,
            'monthly_ai_queries': 'unlimited',
            'monthly_emails': 'unlimited',
            'monthly_sms': 2000,
            'voice_features': True,
        }
    }
}

FEATURE_ADDONS = {
    'extra_ai_queries': {'price': 29, 'amount': 500, 'unit': 'queries'},
    'extra_emails': {'price': 19, 'amount': 1000, 'unit': 'emails'},
    'extra_sms': {'price': 29, 'amount': 500, 'unit': 'sms'},
    'ringless_voicemail': {'price': 49, 'amount': 200, 'unit': 'drops'},
    'advanced_analytics': {'price': 49, 'amount': None, 'unit': 'feature'},
    'api_access': {'price': 99, 'amount': None, 'unit': 'feature'},
}
