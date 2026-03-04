"""
Migration: Add recruit_workflow_config table for per-org workflow customization.

Allows organizations to override default recruiting workflow task definitions
per disposition stage (e.g., custom tasks for 'screening', 'interview', etc.).
Falls back to system defaults (RECRUITING_WORKFLOWS dict) when no override exists.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Create recruit_workflow_config table."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_workflow_config (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                disposition VARCHAR(30) NOT NULL,
                workflow_name VARCHAR(100),
                tasks JSONB NOT NULL,
                is_active BOOLEAN DEFAULT true,
                created_by INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, disposition)
            );

            CREATE INDEX IF NOT EXISTS ix_recruit_wf_config_org
                ON recruit_workflow_config(organization_id) WHERE is_active = true;
        """))
        conn.commit()

    logger.info("recruit_workflow_config table created/verified")
    return {"created": True}


if __name__ == "__main__":
    run_migration()
    print("Migration complete: recruit_workflow_config")
