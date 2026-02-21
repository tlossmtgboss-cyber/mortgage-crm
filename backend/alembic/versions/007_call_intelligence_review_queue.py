"""Call Intelligence Review Queue and Model Versioning

Revision ID: 007_call_intelligence_review
Revises: 006_rls
Create Date: 2025-02-05

This migration adds:
1. extraction_review_queue - For human review of low-confidence extractions
2. model_versions - For tracking extraction model versions
3. model_version_extractions - For linking extractions to versions
4. batch_jobs - For batch processing job tracking
5. Updates to call_intelligence_results to add model_version_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_call_intelligence_review'
down_revision = '006_rls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # 1. Create extraction_review_queue table
    # ==========================================================================
    op.create_table(
        'extraction_review_queue',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('call_id', sa.String(255), nullable=False),
        sa.Column('loan_id', sa.Integer, sa.ForeignKey('loans.id'), nullable=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('extraction_type', sa.String(50), nullable=False),  # identity, property, etc.
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('extracted_value', postgresql.JSONB, nullable=False),
        sa.Column('confidence_score', sa.Float, nullable=False),
        sa.Column('source_text', sa.Text, nullable=True),
        sa.Column('review_status', sa.String(20), default='pending', nullable=False),
        sa.Column('reviewed_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime, nullable=True),
        sa.Column('reviewer_notes', sa.Text, nullable=True),
        sa.Column('final_value', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint('confidence_score BETWEEN 0 AND 100', name='confidence_check'),
    )

    # Indexes for review queue
    op.create_index(
        'idx_review_queue_status',
        'extraction_review_queue',
        ['review_status', 'created_at']
    )
    op.create_index(
        'idx_review_queue_loan',
        'extraction_review_queue',
        ['loan_id']
    )
    op.create_index(
        'idx_review_queue_org',
        'extraction_review_queue',
        ['organization_id']
    )
    op.create_index(
        'idx_review_queue_call',
        'extraction_review_queue',
        ['call_id']
    )

    # ==========================================================================
    # 2. Create model_versions table
    # ==========================================================================
    op.create_table(
        'model_versions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('version_id', sa.String(50), unique=True, nullable=False),
        sa.Column('llm_provider', sa.String(20), nullable=False),  # anthropic, openai
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('schema_version', sa.String(20), nullable=False),
        sa.Column('prompt_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean, default=False, nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
    )

    op.create_index(
        'idx_model_versions_active',
        'model_versions',
        ['is_active', 'created_at']
    )

    # ==========================================================================
    # 3. Create model_version_extractions table
    # ==========================================================================
    op.create_table(
        'model_version_extractions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('call_id', sa.String(255), unique=True, nullable=False),
        sa.Column('version_id', sa.String(50), sa.ForeignKey('model_versions.version_id'), nullable=False),
        sa.Column('total_extractions', sa.Integer, default=0),
        sa.Column('high_confidence_count', sa.Integer, default=0),
        sa.Column('processing_time_ms', sa.Integer, default=0),
        sa.Column('extraction_details', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        'idx_version_extractions_version',
        'model_version_extractions',
        ['version_id', 'created_at']
    )

    # ==========================================================================
    # 4. Create batch_jobs table
    # ==========================================================================
    op.create_table(
        'batch_jobs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.String(50), unique=True, nullable=False),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('total_requests', sa.Integer, nullable=False),
        sa.Column('completed', sa.Integer, default=0),
        sa.Column('failed', sa.Integer, default=0),
        sa.Column('status', sa.String(20), default='pending', nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('request_ids', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )

    op.create_index(
        'idx_batch_jobs_status',
        'batch_jobs',
        ['status', 'created_at']
    )
    op.create_index(
        'idx_batch_jobs_org',
        'batch_jobs',
        ['organization_id']
    )

    # ==========================================================================
    # 5. Add model_version_id to call_intelligence_results
    # ==========================================================================
    # First check if the column already exists
    # Using raw SQL for ALTER TABLE since we need to handle existing data
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'call_intelligence_results'
                AND column_name = 'model_version_id'
            ) THEN
                ALTER TABLE call_intelligence_results
                ADD COLUMN model_version_id VARCHAR(50);
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'call_intelligence_results'
                AND column_name = 'extraction_method'
            ) THEN
                ALTER TABLE call_intelligence_results
                ADD COLUMN extraction_method VARCHAR(30) DEFAULT 'parallel_agents';
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'call_intelligence_results'
                AND column_name = 'pending_review_count'
            ) THEN
                ALTER TABLE call_intelligence_results
                ADD COLUMN pending_review_count INTEGER DEFAULT 0;
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'call_intelligence_results'
                AND column_name = 'batch_job_id'
            ) THEN
                ALTER TABLE call_intelligence_results
                ADD COLUMN batch_job_id VARCHAR(50);
            END IF;
        END $$;
    """)

    # Add foreign key constraint if model_versions table exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_ci_results_model_version'
            ) THEN
                BEGIN
                    ALTER TABLE call_intelligence_results
                    ADD CONSTRAINT fk_ci_results_model_version
                    FOREIGN KEY (model_version_id)
                    REFERENCES model_versions(version_id);
                EXCEPTION
                    WHEN undefined_table THEN NULL;
                END;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove foreign key from call_intelligence_results
    op.execute("""
        ALTER TABLE call_intelligence_results
        DROP CONSTRAINT IF EXISTS fk_ci_results_model_version;
    """)

    # Remove added columns from call_intelligence_results
    op.execute("""
        ALTER TABLE call_intelligence_results
        DROP COLUMN IF EXISTS model_version_id,
        DROP COLUMN IF EXISTS extraction_method,
        DROP COLUMN IF EXISTS pending_review_count,
        DROP COLUMN IF EXISTS batch_job_id;
    """)

    # Drop tables in reverse order
    op.drop_table('batch_jobs')
    op.drop_table('model_version_extractions')
    op.drop_table('model_versions')
    op.drop_table('extraction_review_queue')
