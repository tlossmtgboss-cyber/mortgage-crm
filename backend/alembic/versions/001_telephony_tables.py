"""Create telephony tables for Power Dialer

Revision ID: 001_telephony
Revises:
Create Date: 2024-11-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_telephony'
down_revision = None  # Replace with your last migration if you have one
branch_labels = None
depends_on = None


def upgrade():
    # Agent telephony settings - links to users table
    op.create_table(
        'agent_telephony_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('cell_phone', sa.String(20), nullable=True),
        sa.Column('business_caller_id', sa.String(20), nullable=True),
        sa.Column('dialer_enabled', sa.Boolean(), default=True),
        sa.Column('max_calls_per_day', sa.Integer(), default=100),
        sa.Column('auto_advance', sa.Boolean(), default=True),
        sa.Column('pause_between_calls', sa.Integer(), default=3),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_agent_telephony_user')
    )

    # Verified caller IDs
    op.create_table(
        'verified_caller_ids',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('friendly_name', sa.String(100), nullable=True),
        sa.Column('verification_status', sa.String(20), default='pending'),
        sa.Column('provider_sid', sa.String(100), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_verified_caller_ids_phone', 'verified_caller_ids', ['phone_number'])

    # Dialer sessions
    op.create_table(
        'dialer_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), default='active'),  # active, paused, stopped, completed
        sa.Column('current_task_id', sa.Integer(), nullable=True),
        sa.Column('total_tasks', sa.Integer(), default=0),
        sa.Column('completed_tasks', sa.Integer(), default=0),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_dialer_sessions_agent_status', 'dialer_sessions', ['agent_id', 'status'])

    # Dialer session tasks
    op.create_table(
        'dialer_session_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),  # Reference to tasks table
        sa.Column('contact_phone', sa.String(20), nullable=False),
        sa.Column('contact_name', sa.String(200), nullable=True),
        sa.Column('lead_id', sa.Integer(), nullable=True),
        sa.Column('loan_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), default='pending'),  # pending, in_progress, completed, no_answer, failed, skipped
        sa.Column('call_sid', sa.String(100), nullable=True),
        sa.Column('disposition', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('position', sa.Integer(), default=0),
        sa.Column('attempts', sa.Integer(), default=0),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['session_id'], ['dialer_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['loan_id'], ['loans.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_session_tasks_session_position', 'dialer_session_tasks', ['session_id', 'position'])
    op.create_index('idx_session_tasks_status', 'dialer_session_tasks', ['status'])

    # Call logs
    op.create_table(
        'call_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('session_task_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('contact_phone', sa.String(20), nullable=False),
        sa.Column('contact_name', sa.String(200), nullable=True),
        sa.Column('lead_id', sa.Integer(), nullable=True),
        sa.Column('loan_id', sa.Integer(), nullable=True),
        sa.Column('call_sid', sa.String(100), nullable=True),
        sa.Column('direction', sa.String(20), default='outbound'),  # outbound, inbound
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('outcome', sa.String(50), nullable=True),  # completed, no-answer, busy, failed, etc.
        sa.Column('disposition', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('answered_by', sa.String(50), nullable=True),  # human, machine, etc.
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['dialer_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['loan_id'], ['loans.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_call_logs_agent_date', 'call_logs', ['agent_id', 'created_at'])
    op.create_index('idx_call_logs_call_sid', 'call_logs', ['call_sid'])
    op.create_index('idx_call_logs_contact_phone', 'call_logs', ['contact_phone'])

    # Active calls (soft lock to prevent multiple agents calling same number)
    op.create_table(
        'active_calls',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('contact_phone', sa.String(20), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('call_sid', sa.String(100), nullable=True),
        sa.Column('locked_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_active_calls_phone', 'active_calls', ['contact_phone'])
    op.create_index('idx_active_calls_expires', 'active_calls', ['expires_at'])

    # Do Not Call list
    op.create_table(
        'contact_dnc_status',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('phone_number', sa.String(20), nullable=False, unique=True),
        sa.Column('reason', sa.String(200), nullable=True),
        sa.Column('added_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['added_by_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_dnc_phone', 'contact_dnc_status', ['phone_number'])


def downgrade():
    op.drop_table('contact_dnc_status')
    op.drop_table('active_calls')
    op.drop_table('call_logs')
    op.drop_table('dialer_session_tasks')
    op.drop_table('dialer_sessions')
    op.drop_table('verified_caller_ids')
    op.drop_table('agent_telephony_settings')
