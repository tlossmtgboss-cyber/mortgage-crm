"""Add agent orchestration tables

Revision ID: 002_agent_orchestration
Revises: 001_telephony_tables
Create Date: 2024-12-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision = '002_agent_orchestration'
down_revision = '001_telephony'
branch_labels = None
depends_on = None


def upgrade():
    # ==========================================================================
    # AGENTS TABLE - Core agent configuration storage
    # ==========================================================================
    op.create_table(
        'agents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', sa.String(100), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('version', sa.String(20), nullable=False, server_default='1.0'),

        # Configuration stored as JSONB for flexibility
        sa.Column('config', JSONB, nullable=False, server_default='{}'),
        sa.Column('persona', JSONB, nullable=False, server_default='{}'),
        sa.Column('rules', JSONB, nullable=False, server_default='{}'),
        sa.Column('prompt_components', JSONB, nullable=False, server_default='{}'),

        # Agent classification
        sa.Column('use_case', sa.String(100)),
        sa.Column('channel', sa.String(50)),
        sa.Column('ai_provider', sa.String(50), server_default='claude'),  # claude, openai
        sa.Column('model', sa.String(100), server_default='claude-sonnet-4-6'),

        # Metadata
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
    )

    op.create_index('idx_agents_agent_id', 'agents', ['agent_id'])
    op.create_index('idx_agents_status', 'agents', ['status'])
    op.create_index('idx_agents_use_case', 'agents', ['use_case'])

    # ==========================================================================
    # AGENT EXECUTIONS TABLE - Track individual AI calls
    # ==========================================================================
    op.create_table(
        'agent_executions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id', ondelete='SET NULL')),  # White-label support

        # Stage tracking
        sa.Column('stage', sa.String(100), nullable=False),
        sa.Column('intent_detected', sa.String(255)),

        # Token tracking
        sa.Column('prompt_tokens', sa.Integer, nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer, nullable=False, server_default='0'),

        # Performance tracking
        sa.Column('latency_ms', sa.Integer, nullable=False, server_default='0'),
        sa.Column('model_used', sa.String(100)),

        # Content (for debugging and analysis)
        sa.Column('input_text', sa.Text),
        sa.Column('response_text', sa.Text),
        sa.Column('prompt_used', sa.Text),

        # Extended metadata
        sa.Column('metadata', JSONB, server_default='{}'),
        sa.Column('quality_score', sa.Numeric(5, 2)),  # 0-100 quality score

        sa.Column('executed_at', sa.DateTime, server_default=sa.func.now()),
    )

    op.create_index('idx_agent_executions_agent_id', 'agent_executions', ['agent_id'])
    op.create_index('idx_agent_executions_conversation_id', 'agent_executions', ['conversation_id'])
    op.create_index('idx_agent_executions_executed_at', 'agent_executions', ['executed_at'])
    op.create_index('idx_agent_executions_stage', 'agent_executions', ['stage'])
    op.create_index('idx_agent_executions_organization_id', 'agent_executions', ['organization_id'])

    # ==========================================================================
    # CONVERSATION OUTCOMES TABLE - Track conversation results
    # ==========================================================================
    op.create_table(
        'conversation_outcomes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('conversation_id', UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='SET NULL')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id', ondelete='SET NULL')),  # White-label support

        # Outcome tracking
        sa.Column('outcome_type', sa.String(50), nullable=False),  # qualified, booked, rejected, no_response
        sa.Column('total_messages', sa.Integer, nullable=False, server_default='0'),
        sa.Column('agent_messages', sa.Integer, nullable=False, server_default='0'),
        sa.Column('user_messages', sa.Integer, nullable=False, server_default='0'),

        # Qualification tracking
        sa.Column('qualification_complete', sa.Boolean, default=False),
        sa.Column('qualification_data', JSONB, server_default='{}'),

        # Conversion tracking
        sa.Column('booking_made', sa.Boolean, default=False),
        sa.Column('booking_id', UUID(as_uuid=True)),
        sa.Column('revenue_generated', sa.Numeric(10, 2)),

        # Quality metrics
        sa.Column('response_rate', sa.Numeric(5, 2)),  # % of messages responded to
        sa.Column('avg_response_time_seconds', sa.Integer),
        sa.Column('objections_handled', sa.Integer, server_default='0'),

        # Extended metrics
        sa.Column('metrics', JSONB, server_default='{}'),

        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime),
        sa.Column('duration_seconds', sa.Integer),
    )

    op.create_index('idx_conversation_outcomes_agent_id', 'conversation_outcomes', ['agent_id'])
    op.create_index('idx_conversation_outcomes_outcome_type', 'conversation_outcomes', ['outcome_type'])
    op.create_index('idx_conversation_outcomes_created_at', 'conversation_outcomes', ['created_at'])

    # ==========================================================================
    # AGENT AB TESTS TABLE - Track A/B test experiments
    # ==========================================================================
    op.create_table(
        'agent_ab_tests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('test_name', sa.String(255), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),

        # Variant configuration
        sa.Column('variant_a_config', JSONB, nullable=False),
        sa.Column('variant_b_config', JSONB, nullable=False),
        sa.Column('traffic_split', sa.Numeric(3, 2), server_default='0.50'),  # % to variant A

        # Results
        sa.Column('variant_a_conversations', sa.Integer, server_default='0'),
        sa.Column('variant_b_conversations', sa.Integer, server_default='0'),
        sa.Column('variant_a_conversions', sa.Integer, server_default='0'),
        sa.Column('variant_b_conversions', sa.Integer, server_default='0'),

        # Statistical analysis
        sa.Column('statistical_significance', sa.Numeric(5, 4)),
        sa.Column('winner', sa.String(1)),  # 'A', 'B', or null

        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime),
        sa.Column('ended_at', sa.DateTime),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
    )

    op.create_index('idx_agent_ab_tests_agent_id', 'agent_ab_tests', ['agent_id'])
    op.create_index('idx_agent_ab_tests_status', 'agent_ab_tests', ['status'])

    # ==========================================================================
    # PROMPT TEMPLATES TABLE - Store reusable prompt components
    # ==========================================================================
    op.create_table(
        'prompt_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id', sa.String(100), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),  # core, conditional, stage, objection
        sa.Column('priority', sa.String(50), server_default='conditional'),

        # Content
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('variables', JSONB, server_default='[]'),  # List of template variables

        # Token estimation
        sa.Column('estimated_tokens', sa.Integer),

        # Metadata
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_index('idx_prompt_templates_template_id', 'prompt_templates', ['template_id'])
    op.create_index('idx_prompt_templates_category', 'prompt_templates', ['category'])


def downgrade():
    op.drop_table('prompt_templates')
    op.drop_table('agent_ab_tests')
    op.drop_table('conversation_outcomes')
    op.drop_table('agent_executions')
    op.drop_table('agents')
