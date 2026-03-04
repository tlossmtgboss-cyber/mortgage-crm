"""
Migration: Create ops_sweep_results table

Used by the OpsManagerAgent to store pipeline sweep history.
Previously created inline via DDL in the agent's sweep orchestrator.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create ops_sweep_results table if it doesn't exist."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ops_sweep_results (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                sweep_type VARCHAR(50) NOT NULL DEFAULT 'full',
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                duration_seconds NUMERIC(10,2),
                leads_scanned INTEGER DEFAULT 0,
                loans_scanned INTEGER DEFAULT 0,
                mum_scanned INTEGER DEFAULT 0,
                impediments_found INTEGER DEFAULT 0,
                tasks_created INTEGER DEFAULT 0,
                tasks_skipped_dedup INTEGER DEFAULT 0,
                impediment_breakdown JSONB DEFAULT '{}',
                dry_run BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
        logger.info("Migration: ops_sweep_results table ensured")
