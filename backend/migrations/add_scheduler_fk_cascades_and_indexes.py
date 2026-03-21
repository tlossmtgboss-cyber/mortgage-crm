"""
Migration: Add FK cascade rules, unique constraint, and composite indexes to scheduler tables.

Fixes:
- SchedulerConfig: user_id FK → SET NULL, unique constraint on (org_id, user_id)
- SchedulerAppointmentType: config_id FK → CASCADE
- AppointmentStatusHistory: changed_by_user_id FK → SET NULL
- SlotHold: lo_id FK → CASCADE
- Appointment: composite indexes for org+status+start, org+created_at

Run: python backend/migrations/add_scheduler_fk_cascades_and_indexes.py
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    logger.error("DATABASE_URL not set")
    sys.exit(1)


def run_migration():
    engine = create_engine(DATABASE_URL)

    migrations = [
        # FK cascade rules — drop old FK, add new one with ondelete
        # SchedulerConfig.user_id → SET NULL
        (
            "ALTER TABLE scheduler_configs DROP CONSTRAINT IF EXISTS scheduler_configs_user_id_fkey",
            "Drop old FK on scheduler_configs.user_id",
        ),
        (
            "ALTER TABLE scheduler_configs ADD CONSTRAINT scheduler_configs_user_id_fkey "
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL",
            "Add SET NULL FK on scheduler_configs.user_id",
        ),
        # SchedulerAppointmentType.config_id → CASCADE
        (
            "ALTER TABLE appointment_types DROP CONSTRAINT IF EXISTS appointment_types_config_id_fkey",
            "Drop old FK on appointment_types.config_id",
        ),
        (
            "ALTER TABLE appointment_types ADD CONSTRAINT appointment_types_config_id_fkey "
            "FOREIGN KEY (config_id) REFERENCES scheduler_configs(id) ON DELETE CASCADE",
            "Add CASCADE FK on appointment_types.config_id",
        ),
        # AppointmentStatusHistory.changed_by_user_id → SET NULL
        (
            "ALTER TABLE appointment_status_history DROP CONSTRAINT IF EXISTS appointment_status_history_changed_by_user_id_fkey",
            "Drop old FK on appointment_status_history.changed_by_user_id",
        ),
        (
            "ALTER TABLE appointment_status_history ADD CONSTRAINT appointment_status_history_changed_by_user_id_fkey "
            "FOREIGN KEY (changed_by_user_id) REFERENCES users(id) ON DELETE SET NULL",
            "Add SET NULL FK on appointment_status_history.changed_by_user_id",
        ),
        # SlotHold.lo_id → CASCADE
        (
            "ALTER TABLE slot_holds DROP CONSTRAINT IF EXISTS slot_holds_lo_id_fkey",
            "Drop old FK on slot_holds.lo_id",
        ),
        (
            "ALTER TABLE slot_holds ADD CONSTRAINT slot_holds_lo_id_fkey "
            "FOREIGN KEY (lo_id) REFERENCES users(id) ON DELETE CASCADE",
            "Add CASCADE FK on slot_holds.lo_id",
        ),
        # Unique constraint on SchedulerConfig (org_id, user_id)
        # Note: Postgres allows multiple NULL user_id rows per org (NULL != NULL)
        (
            "ALTER TABLE scheduler_configs DROP CONSTRAINT IF EXISTS uq_scheduler_config_org_user",
            "Drop existing unique constraint if present",
        ),
        (
            "ALTER TABLE scheduler_configs ADD CONSTRAINT uq_scheduler_config_org_user "
            "UNIQUE (organization_id, user_id)",
            "Add unique constraint on (organization_id, user_id)",
        ),
        # Composite performance indexes
        (
            "CREATE INDEX IF NOT EXISTS ix_appt_org_status_start "
            "ON scheduler_appointments (organization_id, status, scheduled_start)",
            "Add composite index for slot generation queries",
        ),
        (
            "CREATE INDEX IF NOT EXISTS ix_appt_org_created "
            "ON scheduler_appointments (organization_id, created_at DESC)",
            "Add composite index for recent appointments queries",
        ),
    ]

    with engine.connect() as conn:
        for sql, description in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"OK: {description}")
            except Exception as e:
                conn.rollback()
                logger.warning(f"SKIP: {description} — {e}")

    logger.info("Migration complete.")


if __name__ == "__main__":
    run_migration()
