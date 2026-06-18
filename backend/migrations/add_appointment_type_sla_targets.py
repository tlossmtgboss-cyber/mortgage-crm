"""
Add sla_targets JSON column to appointment_types table.

Enables per-appointment-type SLA target overrides that take the highest
priority in the three-tier SLA resolution chain:

  1. Per-type overrides  (AppointmentType.sla_targets)    <-- this migration
  2. Org-level overrides (SchedulerConfig.sla_targets)
  3. System defaults     (DEFAULT_SLA_TARGETS)

The column is nullable; NULL means "no overrides" — org/system defaults apply.

Example value:
  {"time_to_first_appointment_hours": 24, "post_appointment_followup_hours": 48}

Usage:
    python -m migrations.add_appointment_type_sla_targets
    # or
    from migrations.add_appointment_type_sla_targets import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration() -> bool:
    """Add sla_targets JSON column to appointment_types table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        logger.info("Adding sla_targets column to appointment_types table...")

        try:
            if is_sqlite:
                conn.execute(text(
                    "ALTER TABLE appointment_types ADD COLUMN sla_targets JSON"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE appointment_types ADD COLUMN IF NOT EXISTS sla_targets JSONB"
                ))
            conn.commit()
            logger.info("Successfully added sla_targets column to appointment_types")
        except Exception as exc:
            err_str = str(exc).lower()
            if "already exists" in err_str or "duplicate column" in err_str:
                logger.info("sla_targets column already exists on appointment_types — skipping")
            else:
                logger.error("Failed to add sla_targets column: %s", exc)
                return False

    logger.info("Migration add_appointment_type_sla_targets complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    exit(0 if success else 1)
