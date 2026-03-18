"""
Index Creation - Performance indexes for workflow engine and milestone queries.

Most indexes are created alongside their tables in schema.py.
This module handles indexes that are added to existing tables
independently of table creation.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_index_creation(engine, database_url: str):
    """Create performance indexes on existing tables."""
    if database_url.startswith("sqlite"):
        return

    try:
        with engine.connect() as conn:
            # Milestone status indexes for workflow engine queries
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_loans_milestone_status
                    ON loans (current_milestone_status, current_milestone_entered_at)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_leads_milestone_status
                    ON leads (current_milestone_status, current_milestone_entered_at)
            """))
            conn.commit()
            logger.info("Performance indexes created/verified")
    except Exception as e:
        logger.warning(f"Index creation note: {e}")
