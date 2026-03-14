"""
Add Missing Indexes for Smart Calendar / Scheduler

Adds performance indexes to scheduler_appointments and scheduler_blocked_times
tables to speed up common query patterns:

1. Composite index on appointments: (organization_id, assigned_user_id, scheduled_start)
   -- Already declared in model but may not exist in production (factory-created models)
2. Standalone index on appointments: (scheduled_start)
   -- Enables efficient date-range scans without the composite prefix
3. Index on appointments: (attendee_email)
   -- Already added by tenant isolation migration, but included for completeness
4. Index on appointments: (status)
   -- Already declared in model, included for completeness
5. Composite index on blocked_times: (organization_id, user_id, start_datetime)
   -- Covers the most common blocked-time conflict check query
6. Trigram index on appointments: (attendee_name gin_trgm_ops)
   -- Enables fast ILIKE / similarity searches on attendee names

Idempotent -- safe to run multiple times.

Usage:
    python -m migrations.add_scheduler_indexes
    # or
    from migrations.add_scheduler_indexes import run_migration
    run_migration()
"""

import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)


def _table_exists(engine, table_name: str) -> bool:
    insp = inspect(engine)
    return table_name in insp.get_table_names()


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def _extension_exists(conn, extension_name: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM pg_extension WHERE extname = :name"
    ), {"name": extension_name})
    return result.fetchone() is not None


def run_migration(engine=None):
    """Add missing scheduler performance indexes."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    logger.info("Starting scheduler index migration...")

    with engine.begin() as conn:
        # =================================================================
        # scheduler_appointments indexes
        # =================================================================
        if _table_exists(engine, "scheduler_appointments"):

            # 1. Composite: (organization_id, assigned_user_id, scheduled_start)
            #    Primary lookup pattern for "show me this user's upcoming appointments"
            if not _index_exists(conn, "ix_appointment_org_user_start"):
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_appointment_org_user_start "
                        "ON scheduler_appointments (organization_id, assigned_user_id, scheduled_start)"
                    ))
                    logger.info("Created index ix_appointment_org_user_start")
                except Exception as e:
                    logger.warning(f"Could not create ix_appointment_org_user_start: {e}")
            else:
                logger.info("Index ix_appointment_org_user_start already exists")

            # 2. Standalone: (scheduled_start)
            #    Efficient date-range scans across all users / orgs (e.g., reminder cron jobs)
            if not _index_exists(conn, "ix_sched_appt_start"):
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_sched_appt_start "
                        "ON scheduler_appointments (scheduled_start)"
                    ))
                    logger.info("Created index ix_sched_appt_start")
                except Exception as e:
                    logger.warning(f"Could not create ix_sched_appt_start: {e}")
            else:
                logger.info("Index ix_sched_appt_start already exists")

            # 3. Attendee email lookup (e.g., "find all appointments for this email")
            if not _index_exists(conn, "ix_appointment_attendee_email"):
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_appointment_attendee_email "
                        "ON scheduler_appointments (attendee_email)"
                    ))
                    logger.info("Created index ix_appointment_attendee_email")
                except Exception as e:
                    logger.warning(f"Could not create ix_appointment_attendee_email: {e}")
            else:
                logger.info("Index ix_appointment_attendee_email already exists")

            # 4. Status filter (e.g., "all booked appointments", "all no-shows")
            if not _index_exists(conn, "ix_appointment_status"):
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_appointment_status "
                        "ON scheduler_appointments (status)"
                    ))
                    logger.info("Created index ix_appointment_status")
                except Exception as e:
                    logger.warning(f"Could not create ix_appointment_status: {e}")
            else:
                logger.info("Index ix_appointment_status already exists")

            # 5. Trigram index on attendee_name for ILIKE / fuzzy search
            #    Requires pg_trgm extension -- skip gracefully if unavailable
            trgm_available = _extension_exists(conn, "pg_trgm")
            if not trgm_available:
                try:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                    trgm_available = True
                    logger.info("Enabled pg_trgm extension")
                except Exception as e:
                    logger.warning(
                        f"Could not enable pg_trgm extension (trigram index will be skipped): {e}"
                    )

            if trgm_available:
                if not _index_exists(conn, "ix_sched_appt_attendee_name_trgm"):
                    try:
                        conn.execute(text(
                            "CREATE INDEX ix_sched_appt_attendee_name_trgm "
                            "ON scheduler_appointments "
                            "USING gin (attendee_name gin_trgm_ops)"
                        ))
                        logger.info("Created trigram index ix_sched_appt_attendee_name_trgm")
                    except Exception as e:
                        logger.warning(f"Could not create trigram index: {e}")
                else:
                    logger.info("Index ix_sched_appt_attendee_name_trgm already exists")
            else:
                logger.info("Skipping trigram index -- pg_trgm extension not available")

        else:
            logger.info("Table scheduler_appointments does not exist, skipping appointment indexes")

        # =================================================================
        # scheduler_blocked_times indexes
        # =================================================================
        if _table_exists(engine, "scheduler_blocked_times"):

            # 6. Composite: (organization_id, user_id, start_datetime)
            #    Covers the blocked-time conflict check:
            #    WHERE organization_id = :org AND user_id = :uid AND start_datetime < :end
            if not _index_exists(conn, "ix_blocked_time_org_user_start"):
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_blocked_time_org_user_start "
                        "ON scheduler_blocked_times (organization_id, user_id, start_datetime)"
                    ))
                    logger.info("Created index ix_blocked_time_org_user_start")
                except Exception as e:
                    logger.warning(f"Could not create ix_blocked_time_org_user_start: {e}")
            else:
                logger.info("Index ix_blocked_time_org_user_start already exists")

        else:
            logger.info("Table scheduler_blocked_times does not exist, skipping blocked-time indexes")

    logger.info("Scheduler index migration complete")


def rollback(engine=None):
    """Remove indexes added by this migration (for rollback purposes)."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    logger.info("Rolling back scheduler index migration...")

    indexes_to_drop = [
        "ix_sched_appt_start",
        "ix_sched_appt_attendee_name_trgm",
        "ix_blocked_time_org_user_start",
        # Do NOT drop these -- they were created by earlier migrations / model declarations:
        # "ix_appointment_org_user_start",
        # "ix_appointment_attendee_email",
        # "ix_appointment_status",
    ]

    with engine.begin() as conn:
        for idx_name in indexes_to_drop:
            if _index_exists(conn, idx_name):
                try:
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                    logger.info(f"Dropped index {idx_name}")
                except Exception as e:
                    logger.warning(f"Could not drop index {idx_name}: {e}")
            else:
                logger.info(f"Index {idx_name} does not exist, nothing to drop")

    logger.info("Scheduler index rollback complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
