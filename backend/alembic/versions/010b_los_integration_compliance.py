"""LOS integration and compliance enforcement tables

Revision ID: 010b_los_compliance
Revises: 010_sso_mfa_enforcement
Create Date: 2026-02-19

Creates tables for:
1. los_sync_log - Audit trail for LOS synchronization events
2. los_webhook_events - Webhook event queue and processing log
3. lo_licenses - Multi-state license tracking for loan officers
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010b_los_compliance'
down_revision = '010_sso_mfa_enforcement'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # 1. LOS Sync Log (Domain 7 - Integration Health)
    # ==========================================================================
    op.create_table(
        'los_sync_log',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=False),
        sa.Column('los_loan_id', sa.String, nullable=True),
        sa.Column('direction', sa.String, nullable=False),  # push, pull
        sa.Column('status', sa.String, nullable=False),  # success, partial, failed, skipped
        sa.Column('provider', sa.String, default='encompass'),
        sa.Column('fields_synced', sa.Integer, default=0),
        sa.Column('fields_skipped', sa.Integer, default=0),
        sa.Column('fields_failed', sa.Integer, default=0),
        sa.Column('conflicts', sa.JSON, nullable=True),
        sa.Column('errors', sa.JSON, nullable=True),
        sa.Column('details', sa.JSON, nullable=True),
        sa.Column('initiated_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('started_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_los_sync_log_loan_id', 'los_sync_log', ['loan_id'])
    op.create_index('ix_los_sync_log_org_id', 'los_sync_log', ['organization_id'])
    op.create_index('ix_los_sync_log_started_at', 'los_sync_log', ['started_at'])

    # ==========================================================================
    # 2. LOS Webhook Events (Domain 7 - Check 7.6)
    # ==========================================================================
    op.create_table(
        'los_webhook_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('event_id', sa.String, unique=True, index=True),
        sa.Column('event_type', sa.String, nullable=False),
        sa.Column('provider', sa.String, default='encompass'),
        sa.Column('los_loan_id', sa.String, nullable=True),
        sa.Column('payload', sa.JSON, nullable=True),
        sa.Column('status', sa.String, default='received'),  # received, processing, processed, failed
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('processing_started_at', sa.DateTime, nullable=True),
        sa.Column('processing_completed_at', sa.DateTime, nullable=True),
        sa.Column('received_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_los_webhook_events_type', 'los_webhook_events', ['event_type'])
    op.create_index('ix_los_webhook_events_status', 'los_webhook_events', ['status'])
    op.create_index('ix_los_webhook_events_received', 'los_webhook_events', ['received_at'])

    # ==========================================================================
    # 3. LO Licenses (Domain 2 - Check 2.20)
    # ==========================================================================
    op.create_table(
        'lo_licenses',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('state', sa.String(2), nullable=False),
        sa.Column('license_type', sa.String, default='mlo'),  # mlo, branch, company
        sa.Column('license_number', sa.String, nullable=True),
        sa.Column('nmls_number', sa.String, nullable=True),
        sa.Column('status', sa.String, default='active'),  # active, expired, suspended, revoked, pending
        sa.Column('issue_date', sa.Date, nullable=True),
        sa.Column('expiration_date', sa.Date, nullable=True),
        sa.Column('renewal_date', sa.Date, nullable=True),
        sa.Column('verified_at', sa.DateTime, nullable=True),
        sa.Column('verified_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_lo_licenses_user_id', 'lo_licenses', ['user_id'])
    op.create_index('ix_lo_licenses_state', 'lo_licenses', ['state'])
    op.create_index('ix_lo_licenses_user_state', 'lo_licenses', ['user_id', 'state'], unique=True)
    op.create_index('ix_lo_licenses_org_id', 'lo_licenses', ['organization_id'])
    op.create_index('ix_lo_licenses_expiration', 'lo_licenses', ['expiration_date'])


def downgrade() -> None:
    op.drop_table('lo_licenses')
    op.drop_table('los_webhook_events')
    op.drop_table('los_sync_log')
