"""
Migration: Add booking_attribution JSON column to scheduler_appointments table.

Stores UTM parameters and referrer data captured during public booking:
  {"utm_source": "...", "utm_medium": "...", "utm_campaign": "...",
   "utm_term": "...", "utm_content": "...", "referrer": "..."}

Run: python backend/migrations/add_booking_attribution_column.py
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)


def run_migration():
    engine = create_engine(DATABASE_URL)

    migrations = [
        (
            "ALTER TABLE scheduler_appointments "
            "ADD COLUMN IF NOT EXISTS booking_attribution JSONB",
            "Add booking_attribution JSON column to scheduler_appointments",
        ),
        (
            "CREATE INDEX IF NOT EXISTS ix_appt_attribution_source "
            "ON scheduler_appointments ((booking_attribution->>'utm_source')) "
            "WHERE booking_attribution IS NOT NULL",
            "Add index on booking_attribution->>'utm_source' for analytics queries",
        ),
    ]

    with engine.begin() as conn:
        for sql, description in migrations:
            try:
                conn.execute(text(sql))
                logger.info(f"OK: {description}")
            except Exception as e:
                logger.warning(f"SKIP: {description} -- {e}")

    logger.info("Migration complete.")


if __name__ == "__main__":
    run_migration()
