"""Call Intelligence Orchestration Tables

Revision ID: 008_call_intelligence_orchestration
Revises: 007_call_intelligence_review
Create Date: 2025-02-05

This migration adds tables for the orchestration layer:
1. orchestration_results - Track end-to-end orchestration runs
2. scheduled_followups - Store scheduled follow-up appointments
3. document_checklists - Store generated document checklists
4. outreach_history - Track sent communications
5. lead_orchestration_events - Track lead updates from orchestration
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_call_intelligence_orchestration'
down_revision = '007_call_intelligence_review'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # 1. Create orchestration_results table
    # ==========================================================================
    op.create_table(
        'orchestration_results',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),  # pending, in_progress, completed, partial, failed
        sa.Column('lead_id', sa.String(50), nullable=True),
        sa.Column('prequal_status', sa.String(30), nullable=True),  # qualified, conditionally_qualified, not_qualified, insufficient_data
        sa.Column('prequal_max_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('prequal_programs', postgresql.JSONB, nullable=True),  # Array of qualified program names
        sa.Column('document_checklist_id', sa.Integer, nullable=True),
        sa.Column('followup_id', sa.String(50), nullable=True),
        sa.Column('steps_completed', postgresql.JSONB, nullable=True),  # Dict of step -> result
        sa.Column('errors', postgresql.JSONB, nullable=True),  # Array of error messages
        sa.Column('warnings', postgresql.JSONB, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=False),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('total_duration_ms', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_orchestration_results_call',
        'orchestration_results',
        ['call_id']
    )
    op.create_index(
        'idx_orchestration_results_loan',
        'orchestration_results',
        ['loan_id']
    )
    op.create_index(
        'idx_orchestration_results_org',
        'orchestration_results',
        ['organization_id', 'created_at']
    )
    op.create_index(
        'idx_orchestration_results_status',
        'orchestration_results',
        ['status', 'created_at']
    )

    # ==========================================================================
    # 2. Create scheduled_followups table
    # ==========================================================================
    op.create_table(
        'scheduled_followups',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('followup_id', sa.String(50), unique=True, nullable=False),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('appointment_type', sa.String(30), nullable=False),  # followup_call, consultation, etc.
        sa.Column('status', sa.String(20), default='scheduled', nullable=False),  # scheduled, confirmed, completed, cancelled
        sa.Column('scheduled_date', sa.DateTime, nullable=True),
        sa.Column('duration_minutes', sa.Integer, default=30),
        sa.Column('timezone', sa.String(50), default='America/New_York'),
        sa.Column('borrower_name', sa.String(255), nullable=True),
        sa.Column('borrower_email', sa.String(255), nullable=True),
        sa.Column('borrower_phone', sa.String(50), nullable=True),
        sa.Column('assigned_to', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('preparation_items', postgresql.JSONB, nullable=True),
        sa.Column('meeting_link', sa.String(500), nullable=True),
        sa.Column('priority', sa.String(20), default='normal'),  # urgent, high, normal, low
        sa.Column('send_reminder', sa.Boolean, default=True),
        sa.Column('reminder_hours_before', sa.Integer, default=24),
        sa.Column('reminder_sent_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index(
        'idx_followups_scheduled',
        'scheduled_followups',
        ['scheduled_date', 'status']
    )
    op.create_index(
        'idx_followups_assigned',
        'scheduled_followups',
        ['assigned_to', 'status']
    )
    op.create_index(
        'idx_followups_loan',
        'scheduled_followups',
        ['loan_id']
    )
    op.create_index(
        'idx_followups_org',
        'scheduled_followups',
        ['organization_id']
    )

    # ==========================================================================
    # 3. Create document_checklists table
    # ==========================================================================
    op.create_table(
        'document_checklists',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_type', sa.String(30), nullable=False),
        sa.Column('loan_purpose', sa.String(30), nullable=False),
        sa.Column('required_documents', postgresql.JSONB, nullable=False),  # Array of document requirements
        sa.Column('conditional_documents', postgresql.JSONB, nullable=True),
        sa.Column('optional_documents', postgresql.JSONB, nullable=True),
        sa.Column('total_required', sa.Integer, default=0),
        sa.Column('total_conditional', sa.Integer, default=0),
        sa.Column('notes', postgresql.JSONB, nullable=True),
        sa.Column('generated_at', sa.DateTime, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_checklists_loan',
        'document_checklists',
        ['loan_id']
    )
    op.create_index(
        'idx_checklists_call',
        'document_checklists',
        ['call_id']
    )

    # ==========================================================================
    # 4. Create outreach_history table
    # ==========================================================================
    op.create_table(
        'outreach_history',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('outreach_id', sa.String(50), unique=True, nullable=False),
        sa.Column('call_id', sa.String(255), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('lead_id', sa.String(50), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('channel', sa.String(20), nullable=False),  # email, sms, phone, in_app
        sa.Column('outreach_type', sa.String(30), nullable=False),  # welcome, document_request, prequal_results, etc.
        sa.Column('status', sa.String(20), nullable=False),  # pending, sent, delivered, failed, bounced, opened, clicked
        sa.Column('recipient', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('body_preview', sa.Text, nullable=True),  # First 500 chars
        sa.Column('template_id', sa.String(50), nullable=True),
        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('delivered_at', sa.DateTime, nullable=True),
        sa.Column('opened_at', sa.DateTime, nullable=True),
        sa.Column('clicked_at', sa.DateTime, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),  # ID from email/SMS provider
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_outreach_loan',
        'outreach_history',
        ['loan_id']
    )
    op.create_index(
        'idx_outreach_lead',
        'outreach_history',
        ['lead_id']
    )
    op.create_index(
        'idx_outreach_call',
        'outreach_history',
        ['call_id']
    )
    op.create_index(
        'idx_outreach_status',
        'outreach_history',
        ['status', 'created_at']
    )
    op.create_index(
        'idx_outreach_type',
        'outreach_history',
        ['outreach_type', 'created_at']
    )

    # ==========================================================================
    # 5. Create lead_orchestration_events table
    # ==========================================================================
    op.create_table(
        'lead_orchestration_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('lead_id', sa.String(50), nullable=False),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('event_type', sa.String(30), nullable=False),  # created, updated, status_changed, score_changed
        sa.Column('previous_status', sa.String(30), nullable=True),
        sa.Column('new_status', sa.String(30), nullable=True),
        sa.Column('previous_score', sa.Integer, nullable=True),
        sa.Column('new_score', sa.Integer, nullable=True),
        sa.Column('changes', postgresql.JSONB, nullable=True),  # Details of what changed
        sa.Column('source', sa.String(30), default='call_intelligence'),  # call_intelligence, manual, api
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_lead_events_lead',
        'lead_orchestration_events',
        ['lead_id', 'created_at']
    )
    op.create_index(
        'idx_lead_events_call',
        'lead_orchestration_events',
        ['call_id']
    )

    # ==========================================================================
    # 6. Create prequal_results table
    # ==========================================================================
    op.create_table(
        'prequal_results',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('status', sa.String(30), nullable=False),  # qualified, conditionally_qualified, not_qualified, insufficient_data
        sa.Column('qualified_programs', postgresql.JSONB, nullable=True),  # Array of program names
        sa.Column('max_purchase_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('max_loan_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('estimated_monthly_payment', sa.Numeric(10, 2), nullable=True),
        sa.Column('estimated_rate', sa.Numeric(5, 3), nullable=True),
        sa.Column('front_end_dti', sa.Numeric(5, 2), nullable=True),
        sa.Column('back_end_dti', sa.Numeric(5, 2), nullable=True),
        sa.Column('ltv', sa.Numeric(5, 2), nullable=True),
        sa.Column('monthly_income', sa.Numeric(12, 2), nullable=True),
        sa.Column('monthly_debt', sa.Numeric(12, 2), nullable=True),
        sa.Column('down_payment', sa.Numeric(12, 2), nullable=True),
        sa.Column('down_payment_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('total_assets', sa.Numeric(14, 2), nullable=True),
        sa.Column('months_reserves', sa.Integer, nullable=True),
        sa.Column('estimated_credit_score', sa.Integer, nullable=True),
        sa.Column('credit_tier', sa.String(20), nullable=True),
        sa.Column('recommendations', postgresql.JSONB, nullable=True),
        sa.Column('warnings', postgresql.JSONB, nullable=True),
        sa.Column('data_completeness', sa.Numeric(5, 2), nullable=True),
        sa.Column('calculated_at', sa.DateTime, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_prequal_call',
        'prequal_results',
        ['call_id']
    )
    op.create_index(
        'idx_prequal_loan',
        'prequal_results',
        ['loan_id']
    )
    op.create_index(
        'idx_prequal_org',
        'prequal_results',
        ['organization_id', 'created_at']
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('prequal_results')
    op.drop_table('lead_orchestration_events')
    op.drop_table('outreach_history')
    op.drop_table('document_checklists')
    op.drop_table('scheduled_followups')
    op.drop_table('orchestration_results')
