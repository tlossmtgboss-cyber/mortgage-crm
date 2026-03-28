"""
Migration: Fix empty working_hours in scheduler_configs

Finds all scheduler_configs rows with NULL or empty working_hours JSON
and updates them to the sensible M-F 9am-5pm default schedule.

This migration is idempotent — safe to run multiple times. It only
updates rows where working_hours is NULL or an empty JSON object ({}).

Usage:
    cd backend && python migrations/fix_empty_working_hours.py
"""

import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_WORKING_HOURS = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "09:00", "end": "13:00", "enabled": False},
    "sunday": {"start": "09:00", "end": "13:00", "enabled": False},
}


def run_migration():
    from sqlalchemy import text
    from db import SessionLocal

    db = SessionLocal()
    try:
        # Find configs with NULL or empty working_hours
        # PostgreSQL: '{}' is the JSON representation of an empty object
        # Also handle NULL values
        result = db.execute(text("""
            SELECT id, user_id, organization_id, working_hours
            FROM scheduler_configs
            WHERE working_hours IS NULL
               OR working_hours::text = '{}'
               OR working_hours::text = 'null'
        """))
        rows = result.fetchall()

        if not rows:
            logger.info("No scheduler_configs with empty working_hours found. Nothing to update.")
            return 0

        logger.info(f"Found {len(rows)} scheduler_configs with empty working_hours")

        # Update each row
        default_json = json.dumps(DEFAULT_WORKING_HOURS)
        updated_count = db.execute(text("""
            UPDATE scheduler_configs
            SET working_hours = :default_hours
            WHERE working_hours IS NULL
               OR working_hours::text = '{}'
               OR working_hours::text = 'null'
        """), {"default_hours": default_json})

        db.commit()
        count = updated_count.rowcount
        logger.info(f"Updated {count} scheduler_configs with default M-F 9am-5pm working hours")

        # Log details for audit trail
        for row in rows:
            logger.info(
                f"  - config id={row[0]}, user_id={row[1]}, org_id={row[2]}, "
                f"old_working_hours={row[3]!r}"
            )

        return count

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Migration: Fix empty working_hours in scheduler_configs")
    logger.info("=" * 60)
    count = run_migration()
    logger.info(f"Migration complete. {count} configs updated.")
