"""
Migration: Create autonomous_agent_runs table for tracking scheduled agent executions.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Create the autonomous_agent_runs table if it doesn't exist."""
    if engine is None:
        from database import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS autonomous_agent_runs (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(100) NOT NULL,
                organization_id INTEGER REFERENCES organizations(id),
                started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                completed_at TIMESTAMP WITH TIME ZONE,
                success BOOLEAN DEFAULT FALSE,
                actions_taken INTEGER DEFAULT 0,
                notifications_sent INTEGER DEFAULT 0,
                error TEXT,
                summary TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_name_org
            ON autonomous_agent_runs(agent_name, organization_id, started_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_agent_runs_started
            ON autonomous_agent_runs(started_at DESC)
        """))
        conn.commit()
        logger.info("autonomous_agent_runs table ready")
