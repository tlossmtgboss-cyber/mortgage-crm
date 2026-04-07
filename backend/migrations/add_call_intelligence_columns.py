"""
Migration: Add Call Intelligence columns and tables

Ensures the Call Intelligence pipeline has all required schema:
- vapi_calls: ci_processed, ci_extractions_count, ci_tasks_created columns
- call_intelligence_results: per-call extraction results
- application_audit_logs: loan application audit snapshots

Usage:
    python -m migrations.add_call_intelligence_columns
    # or from startup:
    from migrations.add_call_intelligence_columns import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Add CI columns to vapi_calls and create CI results/audit tables."""
    if engine is None:
        from database import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        # -------------------------------------------------------
        # 1. Add missing columns to vapi_calls
        # -------------------------------------------------------
        vapi_columns = [
            ("ci_processed", "BOOLEAN DEFAULT FALSE"),
            ("ci_extractions_count", "INTEGER DEFAULT 0"),
            ("ci_tasks_created", "INTEGER DEFAULT 0"),
        ]

        for col_name, col_def in vapi_columns:
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'vapi_calls' AND column_name = '{col_name}'
                    ) THEN
                        ALTER TABLE vapi_calls ADD COLUMN {col_name} {col_def};
                    END IF;
                END $$;
            """))

        logger.info("vapi_calls CI columns verified")

        # -------------------------------------------------------
        # 2. Create call_intelligence_results table
        # -------------------------------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS call_intelligence_results (
                id SERIAL PRIMARY KEY,
                call_id VARCHAR(255) UNIQUE NOT NULL,
                loan_id INTEGER,
                organization_id INTEGER NOT NULL,
                extractions JSONB DEFAULT '{}',
                total_extractions INTEGER DEFAULT 0,
                high_confidence_count INTEGER DEFAULT 0,
                low_confidence_count INTEGER DEFAULT 0,
                processing_time_ms INTEGER,
                application_status VARCHAR(50),
                application_completion FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        logger.info("call_intelligence_results table verified")

        # -------------------------------------------------------
        # 3. Create application_audit_logs table
        # -------------------------------------------------------
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS application_audit_logs (
                id SERIAL PRIMARY KEY,
                loan_id INTEGER,
                overall_status VARCHAR(50),
                overall_completion FLOAT,
                total_fields INTEGER DEFAULT 0,
                complete_fields INTEGER DEFAULT 0,
                missing_fields INTEGER DEFAULT 0,
                tasks_generated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        logger.info("application_audit_logs table verified")

        # -------------------------------------------------------
        # 4. Create indexes
        # -------------------------------------------------------
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ci_results_call_id ON call_intelligence_results(call_id)",
            "CREATE INDEX IF NOT EXISTS idx_ci_results_org ON call_intelligence_results(organization_id)",
            "CREATE INDEX IF NOT EXISTS idx_ci_results_loan ON call_intelligence_results(loan_id)",
        ]

        for idx_sql in indexes:
            conn.execute(text(idx_sql))

        logger.info("call_intelligence indexes verified")

        conn.commit()

    logger.info("Call intelligence migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    print("Migration complete.")
