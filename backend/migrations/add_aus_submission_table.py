"""
Migration: Create aus_submissions table

Stores DU (Desktop Underwriter) and LPA (Loan Product Advisor) submission
records, including findings, conditions, income variance analysis, and
raw API responses.

Usage:
    from migrations.add_aus_submission_table import run_migration
    from db import engine
    run_migration(engine)
"""

import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create the aus_submissions table if it does not exist.

    Uses raw DDL rather than Base.metadata.create_all() so that we can
    run this migration independently of the full model import chain.
    """
    inspector = inspect(engine)

    if "aus_submissions" in inspector.get_table_names():
        logger.info("Migration: aus_submissions table already exists — skipping")
        return

    logger.info("Migration: creating aus_submissions table")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE aus_submissions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,

                aus_type VARCHAR(10) NOT NULL,
                case_id VARCHAR(50),

                recommendation VARCHAR(50),
                risk_class VARCHAR(20),

                conditions JSONB,
                findings JSONB,

                income_data_submitted JSONB,
                income_data_returned JSONB,
                income_variance JSONB,

                submission_status VARCHAR(20) NOT NULL DEFAULT 'submitted',
                error_message TEXT,

                submitted_at TIMESTAMP,
                completed_at TIMESTAMP,

                submitted_by_user_id INTEGER,

                raw_response JSONB,

                created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
            )
        """))

        # Indexes
        conn.execute(text(
            "CREATE INDEX ix_aus_submissions_org_loan "
            "ON aus_submissions (organization_id, loan_id)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_aus_submissions_case_id "
            "ON aus_submissions (case_id)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_aus_submissions_aus_type "
            "ON aus_submissions (aus_type)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_aus_submissions_status "
            "ON aus_submissions (submission_status)"
        ))

    logger.info("Migration: aus_submissions table created successfully")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from db import engine
    run_migration(engine)
