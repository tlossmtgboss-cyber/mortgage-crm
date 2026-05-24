"""
Add AI Training Instructions Table

Creates the ai_training_instructions table for storing user-submitted
training instructions that influence AI agent behavior.

Usage:
    python -m migrations.add_training_instructions_table
    # or
    from migrations.add_training_instructions_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create ai_training_instructions table and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_postgres = "postgresql" in database_url.lower() or "postgres" in database_url.lower()

    with engine.connect() as conn:
        # ---------------------------------------------------------------
        # 1. ai_training_instructions
        # ---------------------------------------------------------------
        logger.info("Creating ai_training_instructions table...")
        try:
            if is_postgres:
                # Ensure uuid-ossp extension for gen_random_uuid()
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_training_instructions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        organization_id INTEGER,
                        instruction_text TEXT NOT NULL,
                        task_type VARCHAR(100),
                        task_context JSONB,
                        scope VARCHAR(50) DEFAULT 'task_type',
                        is_active BOOLEAN DEFAULT TRUE,
                        applied_count INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_training_instructions (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        organization_id INTEGER,
                        instruction_text TEXT NOT NULL,
                        task_type VARCHAR(100),
                        task_context TEXT,
                        scope VARCHAR(50) DEFAULT 'task_type',
                        is_active BOOLEAN DEFAULT 1,
                        applied_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            logger.info("ai_training_instructions table created/verified")
        except Exception as e:
            logger.warning("ai_training_instructions table creation: %s", e)

        # ---------------------------------------------------------------
        # 2. Indexes
        # ---------------------------------------------------------------
        for idx_name, idx_sql in [
            (
                "ix_training_instr_user_id",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_user_id ON ai_training_instructions (user_id)",
            ),
            (
                "ix_training_instr_user_org",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_user_org ON ai_training_instructions (user_id, organization_id)",
            ),
            (
                "ix_training_instr_task_type",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_task_type ON ai_training_instructions (task_type)",
            ),
            (
                "ix_training_instr_scope",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_scope ON ai_training_instructions (scope)",
            ),
            (
                "ix_training_instr_active",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_active ON ai_training_instructions (is_active)",
            ),
            (
                "ix_training_instr_org_id",
                "CREATE INDEX IF NOT EXISTS ix_training_instr_org_id ON ai_training_instructions (organization_id)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("Index %s: %s", idx_name, e)

        # ---------------------------------------------------------------
        # Commit
        # ---------------------------------------------------------------
        conn.commit()
        logger.info("ai_training_instructions migration complete")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed")
