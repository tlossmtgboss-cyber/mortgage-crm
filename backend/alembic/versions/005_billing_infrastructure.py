"""Add billing infrastructure for multi-tenant SaaS

Revision ID: 005_billing
Revises: 004_multi_role
Create Date: 2026-01-30

This migration creates the billing infrastructure for Stripe integration:
- plans: Subscription plan definitions with feature limits
- subscriptions: Organization subscriptions linked to Stripe
- invoices: Billing invoices with line items
- usage_records: Granular usage tracking for metered billing
- payment_methods: Stored payment methods
- stripe_events: Webhook event log for idempotency
- organization_features: Feature flag overrides per organization
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic
revision = '005_billing'
down_revision = '004_multi_role'
branch_labels = None
depends_on = None


def get_uuid_type():
    """Return appropriate UUID type based on database dialect."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import UUID
        return UUID(as_uuid=True)
    else:
        # Use String(36) for SQLite and other databases
        return sa.String(36)


def get_json_type():
    """Return appropriate JSON type based on database dialect."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import json_type
        return json_type
    else:
        return sa.JSON


def get_uuid_default():
    """Return appropriate UUID default based on database dialect."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        return sa.text('gen_random_uuid()')
    else:
        # SQLite doesn't have UUID function, let application handle it
        return None


def upgrade():
    """Create billing infrastructure tables."""
    uuid_type = get_uuid_type()
    json_type = get_json_type()
    uuid_default = get_uuid_default()

    # 1. Create plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.String(50), primary_key=True),  # e.g., "professional"
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        # Pricing
        sa.Column('price_monthly', sa.Numeric(10, 2), nullable=False),
        sa.Column('price_annual', sa.Numeric(10, 2)),
        # Stripe IDs
        sa.Column('stripe_product_id', sa.String(100)),
        sa.Column('stripe_price_monthly_id', sa.String(100)),
        sa.Column('stripe_price_annual_id', sa.String(100)),
        # Feature limits
        sa.Column('max_users', sa.Integer(), server_default='5'),
        sa.Column('max_leads_per_month', sa.Integer(), server_default='100'),
        sa.Column('max_loans_per_month', sa.Integer(), server_default='50'),
        sa.Column('max_ai_tokens_per_month', sa.Integer(), server_default='100000'),
        sa.Column('max_storage_gb', sa.Integer(), server_default='10'),
        # Feature flags
        sa.Column('features', json_type, server_default='{}'),
        # Visibility
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_public', sa.Boolean(), server_default='true'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # 2. Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.String(50), nullable=False),
        # Stripe integration
        sa.Column('stripe_customer_id', sa.String(100)),
        sa.Column('stripe_subscription_id', sa.String(100), unique=True),
        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='trialing'),
        sa.Column('billing_interval', sa.String(20), server_default='monthly'),
        # Billing period
        sa.Column('current_period_start', sa.DateTime()),
        sa.Column('current_period_end', sa.DateTime()),
        sa.Column('trial_end', sa.DateTime()),
        # Cancellation
        sa.Column('cancel_at_period_end', sa.Boolean(), server_default='false'),
        sa.Column('canceled_at', sa.DateTime()),
        sa.Column('cancellation_reason', sa.Text()),
        # Usage tracking
        sa.Column('current_users', sa.Integer(), server_default='0'),
        sa.Column('current_leads_this_month', sa.Integer(), server_default='0'),
        sa.Column('current_loans_this_month', sa.Integer(), server_default='0'),
        sa.Column('current_ai_tokens_this_month', sa.Integer(), server_default='0'),
        sa.Column('current_storage_gb', sa.Numeric(10, 2), server_default='0'),
        # Metadata
        sa.Column('metadata', json_type, server_default='{}'),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        # Foreign keys
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
    )

    op.create_index('ix_subscriptions_organization_id', 'subscriptions', ['organization_id'])
    op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'])
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'])
    op.create_index('ix_subscription_org_status', 'subscriptions', ['organization_id', 'status'])

    # 3. Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column('subscription_id', uuid_type, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        # Stripe integration
        sa.Column('stripe_invoice_id', sa.String(100), unique=True),
        sa.Column('stripe_payment_intent_id', sa.String(100)),
        # Invoice details
        sa.Column('invoice_number', sa.String(50), unique=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        # Amounts (in cents)
        sa.Column('subtotal', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tax', sa.Integer(), server_default='0'),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('amount_paid', sa.Integer(), server_default='0'),
        sa.Column('amount_due', sa.Integer(), server_default='0'),
        # Currency
        sa.Column('currency', sa.String(3), server_default='usd'),
        # Dates
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date()),
        sa.Column('paid_at', sa.DateTime()),
        # Period covered
        sa.Column('period_start', sa.DateTime()),
        sa.Column('period_end', sa.DateTime()),
        # Line items
        sa.Column('line_items', json_type, server_default='[]'),
        # PDF storage
        sa.Column('invoice_pdf_url', sa.String(500)),
        sa.Column('hosted_invoice_url', sa.String(500)),
        # Metadata
        sa.Column('notes', sa.Text()),
        sa.Column('metadata', json_type, server_default='{}'),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        # Foreign keys
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    )

    op.create_index('ix_invoices_subscription_id', 'invoices', ['subscription_id'])
    op.create_index('ix_invoices_organization_id', 'invoices', ['organization_id'])
    op.create_index('ix_invoices_stripe_invoice_id', 'invoices', ['stripe_invoice_id'])
    op.create_index('ix_invoice_org_date', 'invoices', ['organization_id', 'invoice_date'])

    # 4. Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column('subscription_id', uuid_type, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        # Usage details
        sa.Column('usage_type', sa.String(50), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 6), nullable=False),
        sa.Column('unit_type', sa.String(30)),
        # Attribution
        sa.Column('user_id', sa.Integer()),
        sa.Column('request_id', sa.String(100)),
        # Timestamp
        sa.Column('recorded_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('usage_date', sa.Date(), nullable=False),
        # Billing
        sa.Column('is_billable', sa.Boolean(), server_default='true'),
        sa.Column('is_billed', sa.Boolean(), server_default='false'),
        sa.Column('billed_invoice_id', uuid_type),
        # Metadata
        sa.Column('metadata', json_type, server_default='{}'),
        # Foreign keys
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['billed_invoice_id'], ['invoices.id'], ondelete='SET NULL'),
    )

    op.create_index('ix_usage_records_subscription_id', 'usage_records', ['subscription_id'])
    op.create_index('ix_usage_records_organization_id', 'usage_records', ['organization_id'])
    op.create_index('ix_usage_records_usage_type', 'usage_records', ['usage_type'])
    op.create_index('ix_usage_records_user_id', 'usage_records', ['user_id'])
    op.create_index('ix_usage_org_date_type', 'usage_records', ['organization_id', 'usage_date', 'usage_type'])
    op.create_index('ix_usage_subscription_date', 'usage_records', ['subscription_id', 'usage_date'])

    # 5. Create payment_methods table
    op.create_table(
        'payment_methods',
        sa.Column('id', uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        # Stripe integration
        sa.Column('stripe_payment_method_id', sa.String(100), unique=True, nullable=False),
        sa.Column('stripe_customer_id', sa.String(100), nullable=False),
        # Card details (display only)
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('card_brand', sa.String(30)),
        sa.Column('card_last4', sa.String(4)),
        sa.Column('card_exp_month', sa.Integer()),
        sa.Column('card_exp_year', sa.Integer()),
        # Status
        sa.Column('is_default', sa.Boolean(), server_default='false'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        # Billing info
        sa.Column('billing_name', sa.String(255)),
        sa.Column('billing_email', sa.String(255)),
        sa.Column('billing_address', json_type),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        # Foreign keys
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    )

    op.create_index('ix_payment_methods_organization_id', 'payment_methods', ['organization_id'])
    op.create_index('ix_payment_methods_stripe_customer_id', 'payment_methods', ['stripe_customer_id'])
    op.create_index('ix_payment_method_org_default', 'payment_methods', ['organization_id', 'is_default'])

    # 6. Create stripe_events table
    op.create_table(
        'stripe_events',
        sa.Column('id', sa.String(100), primary_key=True),  # Stripe event ID (evt_xxx)
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('api_version', sa.String(20)),
        # Processing status
        sa.Column('processed', sa.Boolean(), server_default='false'),
        sa.Column('processed_at', sa.DateTime()),
        sa.Column('processing_error', sa.Text()),
        # Event data
        sa.Column('data', json_type, nullable=False),
        # Related objects
        sa.Column('organization_id', sa.Integer()),
        sa.Column('subscription_id', uuid_type),
        sa.Column('invoice_id', uuid_type),
        # Timestamp
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        # Foreign keys
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL'),
    )

    op.create_index('ix_stripe_events_event_type', 'stripe_events', ['event_type'])
    op.create_index('ix_stripe_events_organization_id', 'stripe_events', ['organization_id'])
    op.create_index('ix_stripe_event_type_processed', 'stripe_events', ['event_type', 'processed'])

    # 7. Create organization_features table
    op.create_table(
        'organization_features',
        sa.Column('id', uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('feature_name', sa.String(100), nullable=False),
        # Override
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text()),
        # Validity
        sa.Column('valid_from', sa.DateTime()),
        sa.Column('valid_until', sa.DateTime()),
        # Audit
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer()),
        # Foreign keys
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        # Unique constraint
        sa.UniqueConstraint('organization_id', 'feature_name', name='uq_org_feature'),
    )

    op.create_index('ix_organization_features_organization_id', 'organization_features', ['organization_id'])

    # 8. Insert default plans (database-agnostic)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("""
            INSERT INTO plans (id, name, description, price_monthly, price_annual, max_users, max_leads_per_month, max_loans_per_month, max_ai_tokens_per_month, max_storage_gb, features, sort_order)
            VALUES
            ('free', 'Free', 'Basic features for small teams', 0.00, 0.00, 2, 25, 10, 10000, 1, '{"ai_assistant": false, "automated_workflows": false, "custom_reports": false, "api_access": false}'::jsonb, 0),
            ('starter', 'Starter', 'Essential tools for growing teams', 49.00, 490.00, 5, 100, 50, 50000, 5, '{"ai_assistant": true, "automated_workflows": false, "custom_reports": false, "api_access": false}'::jsonb, 1),
            ('professional', 'Professional', 'Advanced features for professionals', 99.00, 990.00, 15, 500, 200, 200000, 25, '{"ai_assistant": true, "automated_workflows": true, "custom_reports": true, "api_access": true}'::jsonb, 2),
            ('enterprise', 'Enterprise', 'Full platform with dedicated support', 299.00, 2990.00, -1, -1, -1, 1000000, 100, '{"ai_assistant": true, "automated_workflows": true, "custom_reports": true, "api_access": true, "white_label": true, "dedicated_support": true}'::jsonb, 3)
            ON CONFLICT (id) DO NOTHING
        """)
    else:
        # SQLite-compatible INSERT OR IGNORE
        op.execute("""
            INSERT OR IGNORE INTO plans (id, name, description, price_monthly, price_annual, max_users, max_leads_per_month, max_loans_per_month, max_ai_tokens_per_month, max_storage_gb, features, sort_order)
            VALUES
            ('free', 'Free', 'Basic features for small teams', 0.00, 0.00, 2, 25, 10, 10000, 1, '{"ai_assistant": false, "automated_workflows": false, "custom_reports": false, "api_access": false}', 0),
            ('starter', 'Starter', 'Essential tools for growing teams', 49.00, 490.00, 5, 100, 50, 50000, 5, '{"ai_assistant": true, "automated_workflows": false, "custom_reports": false, "api_access": false}', 1),
            ('professional', 'Professional', 'Advanced features for professionals', 99.00, 990.00, 15, 500, 200, 200000, 25, '{"ai_assistant": true, "automated_workflows": true, "custom_reports": true, "api_access": true}', 2),
            ('enterprise', 'Enterprise', 'Full platform with dedicated support', 299.00, 2990.00, -1, -1, -1, 1000000, 100, '{"ai_assistant": true, "automated_workflows": true, "custom_reports": true, "api_access": true, "white_label": true, "dedicated_support": true}', 3)
        """)


def downgrade():
    """Remove billing infrastructure tables."""
    op.drop_table('organization_features')
    op.drop_table('stripe_events')
    op.drop_table('payment_methods')
    op.drop_table('usage_records')
    op.drop_table('invoices')
    op.drop_table('subscriptions')
    op.drop_table('plans')
