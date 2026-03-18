"""
Migration: Add Speed-to-Lead Metrics Table
Tracks the end-to-end time from lead creation / stage change
to booking link delivery or appointment auto-booking.

Answers: "How fast is the actual end-to-end time from lead creation
to booking link delivery?" — critical because 78% of borrowers
choose the first lender who responds.
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create speed-to-lead metrics table and indexes."""

    sql_commands = [
        # Speed-to-lead metrics table
        """
        CREATE TABLE IF NOT EXISTS speed_to_lead_metrics (
            id SERIAL PRIMARY KEY,
            loan_id INTEGER,
            organization_id INTEGER,
            loan_officer_id INTEGER,
            trigger_event VARCHAR(50) NOT NULL,
            trigger_stage VARCHAR(50),
            trigger_time TIMESTAMP WITH TIME ZONE NOT NULL,
            delivery_time TIMESTAMP WITH TIME ZONE NOT NULL,
            delivery_method VARCHAR(50),
            elapsed_seconds FLOAT,
            extra_data JSON,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,

        # Index for dashboard queries: org + date range
        """
        CREATE INDEX IF NOT EXISTS idx_stl_org_created
        ON speed_to_lead_metrics (organization_id, created_at);
        """,

        # Index for LO leaderboard queries
        """
        CREATE INDEX IF NOT EXISTS idx_stl_org_lo
        ON speed_to_lead_metrics (organization_id, loan_officer_id, created_at);
        """,

        # Index for per-loan lookups
        """
        CREATE INDEX IF NOT EXISTS idx_stl_loan_id
        ON speed_to_lead_metrics (loan_id);
        """,

        # Index for method-based filtering (auto_booked vs booking_link_sms etc)
        """
        CREATE INDEX IF NOT EXISTS idx_stl_delivery_method
        ON speed_to_lead_metrics (delivery_method, created_at);
        """,
    ]

    with engine.connect() as conn:
        for sql in sql_commands:
            try:
                conn.execute(text(sql))
                logger.info(f"Executed: {sql.strip()[:80]}...")
            except Exception as e:
                logger.warning(f"Skipped (may already exist): {e}")
        conn.commit()

    logger.info("Speed-to-lead metrics migration complete")


if __name__ == "__main__":
    run_migration()
