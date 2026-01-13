"""Create estimate parser cache and failures tables

Revision ID: 003_estimate_parser
Revises: 002_add_agent_orchestration
Create Date: 2024-12-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '003_estimate_parser'
down_revision = '002_agent_orchestration'
branch_labels = None
depends_on = None


def upgrade():
    # Parse cache table - prevents re-processing identical uploads
    op.create_table(
        'estimate_parse_cache',
        sa.Column('doc_hash', sa.String(64), primary_key=True),  # SHA-256 hash
        sa.Column('parsed_json', JSONB, nullable=False),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),  # 0.00 to 1.00
        sa.Column('needs_review', sa.Boolean(), default=False),
        sa.Column('source_type', sa.String(50), nullable=True),  # loan_estimate, fee_worksheet, closing_disclosure, unknown
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('accessed_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('access_count', sa.Integer(), default=1),
    )
    op.create_index('idx_estimate_cache_created', 'estimate_parse_cache', ['created_at'])
    op.create_index('idx_estimate_cache_needs_review', 'estimate_parse_cache', ['needs_review'], postgresql_where=sa.text('needs_review = true'))
    op.create_index('idx_estimate_cache_source_type', 'estimate_parse_cache', ['source_type'])

    # Failed parse tracking - for manual review queue
    op.create_table(
        'estimate_parse_failures',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('request_id', UUID(as_uuid=True), nullable=False),
        sa.Column('doc_hash', sa.String(64), nullable=False),
        sa.Column('error_stage', sa.String(50), nullable=False),  # ocr, llm, json_parse, validation
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),  # for debugging (truncated)
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index('idx_failures_created', 'estimate_parse_failures', ['created_at'])
    op.create_index('idx_failures_stage', 'estimate_parse_failures', ['error_stage'])
    op.create_index('idx_failures_doc_hash', 'estimate_parse_failures', ['doc_hash'])

    # Estimate comparisons - track what users compared
    op.create_table(
        'estimate_comparisons',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.Integer(), nullable=True),  # null for anonymous
        sa.Column('session_id', sa.String(100), nullable=True),  # for anonymous tracking
        sa.Column('estimate_a_hash', sa.String(64), nullable=False),
        sa.Column('estimate_b_hash', sa.String(64), nullable=False),
        sa.Column('winner', sa.String(1), nullable=True),  # 'A', 'B', or null if tie
        sa.Column('winner_reason', sa.String(200), nullable=True),
        sa.Column('savings_amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('comparison_data', JSONB, nullable=True),  # full comparison details
        sa.Column('converted', sa.Boolean(), default=False),  # did user click CTA?
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['estimate_a_hash'], ['estimate_parse_cache.doc_hash'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['estimate_b_hash'], ['estimate_parse_cache.doc_hash'], ondelete='CASCADE'),
    )
    op.create_index('idx_comparisons_user', 'estimate_comparisons', ['user_id'])
    op.create_index('idx_comparisons_created', 'estimate_comparisons', ['created_at'])
    op.create_index('idx_comparisons_converted', 'estimate_comparisons', ['converted'])


def downgrade():
    op.drop_table('estimate_comparisons')
    op.drop_table('estimate_parse_failures')
    op.drop_table('estimate_parse_cache')
