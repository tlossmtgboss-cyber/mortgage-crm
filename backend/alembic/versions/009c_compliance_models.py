"""Compliance models for TRID, ECOA, HMDA enterprise readiness

Revision ID: 009c_compliance_models
Revises: 009b_security
Create Date: 2026-02-19

Creates tables for Domain 2 compliance automation:
1. loan_fees - TRID tolerance tracking per fee line item
2. disclosure_events - TRID disclosure delivery audit trail
3. adverse_action_notices - ECOA adverse action compliance
4. compliance_alerts - Real-time compliance violation alerting
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009c_compliance_models'
down_revision = '009b_security'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # 1. Create loan_fees table (TRID tolerance tracking)
    # ==========================================================================
    op.create_table(
        'loan_fees',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=False),
        sa.Column('fee_name', sa.String, nullable=False),
        sa.Column('fee_category', sa.String, nullable=True),
        sa.Column('tolerance_category', sa.String, nullable=False),  # zero, ten_percent, unlimited
        sa.Column('le_amount', sa.Numeric(12, 2), server_default='0'),
        sa.Column('le_revision_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('le_revision_date', sa.DateTime, nullable=True),
        sa.Column('le_revision_reason', sa.String, nullable=True),
        sa.Column('cd_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('variance', sa.Numeric(12, 2), nullable=True),
        sa.Column('cure_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('is_violation', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index('ix_loan_fees_loan_id', 'loan_fees', ['loan_id'])
    op.create_index('ix_loan_fees_org_id', 'loan_fees', ['organization_id'])

    # ==========================================================================
    # 2. Create disclosure_events table (TRID audit trail)
    # ==========================================================================
    op.create_table(
        'disclosure_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=False),
        sa.Column('disclosure_type', sa.String, nullable=False),  # loan_estimate, revised_le, closing_disclosure, revised_cd
        sa.Column('prepared_at', sa.DateTime, nullable=True),
        sa.Column('sent_at', sa.DateTime, nullable=False),
        sa.Column('delivery_method', sa.String, nullable=True),
        sa.Column('received_at', sa.DateTime, nullable=True),
        sa.Column('deadline_date', sa.Date, nullable=True),
        sa.Column('is_on_time', sa.Boolean, nullable=True),
        sa.Column('business_days_used', sa.Integer, nullable=True),
        sa.Column('change_reason', sa.String, nullable=True),
        sa.Column('change_description', sa.Text, nullable=True),
        sa.Column('document_id', sa.Integer, sa.ForeignKey('documents.id'), nullable=True),
        sa.Column('created_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index('ix_disclosure_events_loan_id', 'disclosure_events', ['loan_id'])
    op.create_index('ix_disclosure_events_org_id', 'disclosure_events', ['organization_id'])

    # ==========================================================================
    # 3. Create adverse_action_notices table (ECOA compliance)
    # ==========================================================================
    op.create_table(
        'adverse_action_notices',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=False),
        sa.Column('lead_id', sa.Integer, sa.ForeignKey('leads.id'), nullable=True),
        sa.Column('denial_date', sa.Date, nullable=False),
        sa.Column('notice_deadline', sa.Date, nullable=False),
        sa.Column('notice_sent_date', sa.Date, nullable=True),
        sa.Column('is_on_time', sa.Boolean, nullable=True),
        sa.Column('primary_reason', sa.String, nullable=False),  # ECOA reason code
        sa.Column('secondary_reasons', sa.JSON, nullable=True),
        sa.Column('reason_description', sa.Text, nullable=True),
        sa.Column('delivery_method', sa.String, nullable=True),
        sa.Column('recipient_name', sa.String, nullable=True),
        sa.Column('recipient_address', sa.Text, nullable=True),
        sa.Column('creditor_name', sa.String, nullable=True),
        sa.Column('creditor_address', sa.Text, nullable=True),
        sa.Column('federal_regulator', sa.String, nullable=True),
        sa.Column('status', sa.String, server_default='pending'),
        sa.Column('created_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index('ix_adverse_action_loan_id', 'adverse_action_notices', ['loan_id'])
    op.create_index('ix_adverse_action_org_id', 'adverse_action_notices', ['organization_id'])

    # ==========================================================================
    # 4. Create compliance_alerts table
    # ==========================================================================
    op.create_table(
        'compliance_alerts',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('lead_id', sa.Integer, sa.ForeignKey('leads.id'), nullable=True),
        sa.Column('alert_type', sa.String, nullable=False),
        sa.Column('severity', sa.String, nullable=False),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('deadline_date', sa.Date, nullable=True),
        sa.Column('days_remaining', sa.Integer, nullable=True),
        sa.Column('status', sa.String, server_default='open'),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('resolved_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index('ix_compliance_alerts_loan_id', 'compliance_alerts', ['loan_id'])
    op.create_index('ix_compliance_alerts_org_id', 'compliance_alerts', ['organization_id'])
    op.create_index('ix_compliance_alerts_status', 'compliance_alerts', ['status'])


def downgrade() -> None:
    op.drop_table('compliance_alerts')
    op.drop_table('adverse_action_notices')
    op.drop_table('disclosure_events')
    op.drop_table('loan_fees')
