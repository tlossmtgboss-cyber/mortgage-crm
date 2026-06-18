"""
Migration: Create recruit_job_postings table.
Safe to run multiple times (uses IF NOT EXISTS).
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_job_postings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                department VARCHAR(100),
                location VARCHAR(255),
                is_remote BOOLEAN DEFAULT FALSE,
                salary_range VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_recruit_job_postings_organization_id
            ON recruit_job_postings(organization_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_recruit_job_postings_is_active
            ON recruit_job_postings(is_active)
        """))

    logger.info("✅ recruit_job_postings table ready")
    return {"status": "success", "table": "recruit_job_postings"}


def rollback(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS recruit_job_postings CASCADE"))
    logger.info("Rolled back recruit_job_postings table")
    return {"status": "rolled_back"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_migration())
