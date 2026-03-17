"""
Migration: Consolidate three appointment tables into canonical scheduler_appointments.
Tables: scheduler_appointments (keep), scheduled_appointments (migrate), calendar_events (migrate)

This migration:
1. Adds missing columns to scheduler_appointments that exist in the other tables
2. Migrates data from scheduled_appointments -> scheduler_appointments
3. Migrates data from calendar_events -> scheduler_appointments
4. Creates views for backward compatibility
5. Does NOT drop old tables (they become read-only views after rename)

Source enum values:
  'manual'           - manually created in the UI
  'ai_booked'        - booked by AI agent
  'public_booking'   - booked via public scheduling link
  'google_sync'      - synced from Google Calendar
  'outlook_sync'     - synced from Outlook Calendar
  'legacy_scheduler' - migrated from scheduled_appointments table
  'legacy_calendar'  - migrated from calendar_events table
  'salesforce_sync'  - synced from Salesforce calendar
  'call_monitoring'  - created by call monitoring orchestrator

Idempotent: safe to run multiple times.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """
    Run the appointment table consolidation migration.

    Args:
        engine: SQLAlchemy engine. If None, imports from database module.
    """
    if engine is None:
        from database import engine

    from sqlalchemy import text, inspect

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        # ==================================================================
        # STEP 1: Add new columns to scheduler_appointments
        # ==================================================================
        logger.info("Step 1: Adding new columns to scheduler_appointments...")

        new_columns = [
            # Source tracking
            ("source", "VARCHAR(50) DEFAULT 'manual'"),
            ("legacy_id", "VARCHAR(100)"),
            ("legacy_table", "VARCHAR(50)"),

            # Recurrence support
            ("is_recurring", "BOOLEAN DEFAULT FALSE"),
            ("recurrence_pattern", "JSONB"),
            ("parent_appointment_id", "INTEGER REFERENCES scheduler_appointments(id)"),

            # Conversion tracking
            ("conversion_tracked", "BOOLEAN DEFAULT FALSE"),

            # Fields from calendar_events
            ("all_day", "BOOLEAN DEFAULT FALSE"),
            ("attendees", "JSONB"),
            ("reminder_minutes", "INTEGER"),
            ("meta_data", "JSONB"),
            ("event_type", "VARCHAR(100)"),

            # Fields from scheduled_appointments
            ("booked_via", "VARCHAR(50)"),
            ("conversation_id", "VARCHAR(255)"),
            ("confirmed_at", "TIMESTAMP WITH TIME ZONE"),
            ("customer_invite_sent", "BOOLEAN DEFAULT FALSE"),
            ("lo_invite_sent", "BOOLEAN DEFAULT FALSE"),
            ("lo_confirmation_sent", "BOOLEAN DEFAULT FALSE"),
            ("legacy_appointment_id", "VARCHAR(50)"),
        ]

        if "scheduler_appointments" in existing_tables:
            existing_cols = {c["name"] for c in insp.get_columns("scheduler_appointments")}

            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE scheduler_appointments ADD COLUMN {col_name} {col_def}"
                        ))
                        logger.info(f"  Added column: {col_name}")
                    except Exception as e:
                        # Column might already exist despite not showing in inspection (race condition)
                        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                            logger.debug(f"  Column {col_name} already exists, skipping")
                        else:
                            raise

            # Add indexes for new columns
            _create_index_safe(conn, "ix_scheduler_appt_source", "scheduler_appointments", "source")
            _create_index_safe(conn, "ix_scheduler_appt_legacy_id", "scheduler_appointments", "legacy_id")
            _create_index_safe(conn, "ix_scheduler_appt_legacy_table", "scheduler_appointments", "legacy_table")
            _create_index_safe(conn, "ix_scheduler_appt_parent_id", "scheduler_appointments", "parent_appointment_id")
            _create_index_safe(conn, "ix_scheduler_appt_event_type", "scheduler_appointments", "event_type")
            _create_index_safe(conn, "ix_scheduler_appt_booked_via", "scheduler_appointments", "booked_via")
        else:
            logger.warning("scheduler_appointments table does not exist yet, skipping column additions")

        # ==================================================================
        # STEP 2: Migrate data from scheduled_appointments
        # ==================================================================
        if "scheduled_appointments" in existing_tables and "scheduler_appointments" in existing_tables:
            logger.info("Step 2: Migrating data from scheduled_appointments...")

            # Check if migration already happened (look for legacy_table = 'scheduled_appointments')
            already_migrated = conn.execute(text("""
                SELECT COUNT(*) FROM scheduler_appointments
                WHERE legacy_table = 'scheduled_appointments'
            """)).scalar()

            if already_migrated > 0:
                logger.info(f"  Already migrated {already_migrated} rows from scheduled_appointments, skipping")
            else:
                migrated_count = conn.execute(text("""
                    INSERT INTO scheduler_appointments (
                        organization_id,
                        assigned_user_id,
                        contact_id,
                        title,
                        description,
                        scheduled_start,
                        scheduled_end,
                        duration_minutes,
                        location,
                        video_link,
                        attendee_name,
                        attendee_email,
                        attendee_phone,
                        status,
                        internal_notes,
                        cancelled_at,
                        created_at,
                        updated_at,
                        -- New consolidation columns
                        source,
                        legacy_id,
                        legacy_table,
                        legacy_appointment_id,
                        booked_via,
                        conversation_id,
                        confirmed_at,
                        customer_invite_sent,
                        lo_invite_sent,
                        lo_confirmation_sent,
                        booked_by_ai,
                        event_type
                    )
                    SELECT
                        sa.organization_id,
                        sa.loan_officer_id,
                        sa.contact_id,
                        COALESCE(
                            sa.appointment_type || ' with ' || COALESCE(sa.contact_name, 'Contact'),
                            'Appointment with ' || COALESCE(sa.contact_name, 'Contact')
                        ),
                        sa.notes,
                        sa.start_time,
                        sa.end_time,
                        sa.duration_minutes,
                        sa.location,
                        sa.meeting_link,
                        sa.contact_name,
                        sa.contact_email,
                        sa.contact_phone,
                        -- Map status values
                        CASE sa.status
                            WHEN 'scheduled' THEN 'booked'
                            WHEN 'confirmed' THEN 'booked'
                            WHEN 'completed' THEN 'completed'
                            WHEN 'cancelled' THEN 'cancelled'
                            WHEN 'no_show' THEN 'no_show'
                            WHEN 'rescheduled' THEN 'rescheduled'
                            ELSE 'booked'
                        END,
                        sa.internal_notes,
                        sa.cancelled_at,
                        sa.created_at,
                        sa.updated_at,
                        -- Consolidation columns
                        'legacy_scheduler',
                        CAST(sa.id AS VARCHAR),
                        'scheduled_appointments',
                        sa.appointment_id,
                        sa.booked_via,
                        sa.conversation_id,
                        sa.confirmed_at,
                        COALESCE(sa.customer_invite_sent, FALSE),
                        COALESCE(sa.lo_invite_sent, FALSE),
                        COALESCE(sa.lo_confirmation_sent, FALSE),
                        CASE WHEN sa.booked_via = 'ai_assistant' THEN TRUE ELSE FALSE END,
                        sa.appointment_type
                    FROM scheduled_appointments sa
                    WHERE NOT EXISTS (
                        SELECT 1 FROM scheduler_appointments sa2
                        WHERE sa2.legacy_table = 'scheduled_appointments'
                          AND sa2.legacy_id = CAST(sa.id AS VARCHAR)
                    )
                """)).rowcount

                logger.info(f"  Migrated {migrated_count} rows from scheduled_appointments")
        else:
            logger.info("Step 2: scheduled_appointments table not found, skipping migration")

        # ==================================================================
        # STEP 3: Migrate data from calendar_events
        # ==================================================================
        if "calendar_events" in existing_tables and "scheduler_appointments" in existing_tables:
            logger.info("Step 3: Migrating data from calendar_events...")

            already_migrated = conn.execute(text("""
                SELECT COUNT(*) FROM scheduler_appointments
                WHERE legacy_table = 'calendar_events'
            """)).scalar()

            if already_migrated > 0:
                logger.info(f"  Already migrated {already_migrated} rows from calendar_events, skipping")
            else:
                migrated_count = conn.execute(text("""
                    INSERT INTO scheduler_appointments (
                        organization_id,
                        assigned_user_id,
                        lead_id,
                        loan_id,
                        title,
                        description,
                        scheduled_start,
                        scheduled_end,
                        duration_minutes,
                        location,
                        status,
                        created_at,
                        updated_at,
                        -- New consolidation columns
                        source,
                        legacy_id,
                        legacy_table,
                        all_day,
                        attendees,
                        reminder_minutes,
                        meta_data,
                        event_type
                    )
                    SELECT
                        ce.organization_id,
                        ce.user_id,
                        ce.lead_id,
                        ce.loan_id,
                        ce.title,
                        ce.description,
                        ce.start_time,
                        ce.end_time,
                        -- Calculate duration in minutes from start/end
                        COALESCE(
                            EXTRACT(EPOCH FROM (ce.end_time - ce.start_time)) / 60,
                            30  -- default 30 minutes if calculation fails
                        )::INTEGER,
                        ce.location,
                        -- Map status values
                        CASE ce.status
                            WHEN 'scheduled' THEN 'booked'
                            WHEN 'completed' THEN 'completed'
                            WHEN 'cancelled' THEN 'cancelled'
                            ELSE 'booked'
                        END,
                        ce.created_at,
                        ce.updated_at,
                        -- Consolidation columns
                        'legacy_calendar',
                        CAST(ce.id AS VARCHAR),
                        'calendar_events',
                        COALESCE(ce.all_day, FALSE),
                        ce.attendees,
                        ce.reminder_minutes,
                        ce.meta_data,
                        ce.event_type
                    FROM calendar_events ce
                    WHERE NOT EXISTS (
                        SELECT 1 FROM scheduler_appointments sa
                        WHERE sa.legacy_table = 'calendar_events'
                          AND sa.legacy_id = CAST(ce.id AS VARCHAR)
                    )
                """)).rowcount

                logger.info(f"  Migrated {migrated_count} rows from calendar_events")
        else:
            logger.info("Step 3: calendar_events table not found, skipping migration")

        # ==================================================================
        # STEP 4: Tag existing scheduler_appointments rows that have no source
        # ==================================================================
        if "scheduler_appointments" in existing_tables:
            logger.info("Step 4: Tagging existing scheduler_appointments rows with source...")

            # Tag AI-booked records
            conn.execute(text("""
                UPDATE scheduler_appointments
                SET source = 'ai_booked'
                WHERE source IS NULL AND booked_by_ai = TRUE
            """))

            # Tag records synced from Google
            conn.execute(text("""
                UPDATE scheduler_appointments
                SET source = 'google_sync'
                WHERE source IS NULL AND google_calendar_event_id IS NOT NULL
            """))

            # Tag records synced from Outlook
            conn.execute(text("""
                UPDATE scheduler_appointments
                SET source = 'outlook_sync'
                WHERE source IS NULL AND outlook_event_id IS NOT NULL
            """))

            # Tag remaining records as manual
            conn.execute(text("""
                UPDATE scheduler_appointments
                SET source = 'manual'
                WHERE source IS NULL
            """))

            logger.info("  Source tagging complete")

        # ==================================================================
        # STEP 5: Create backward-compatible views
        # ==================================================================
        logger.info("Step 5: Creating backward-compatible views...")

        # Rename old tables (if they still exist as real tables, not views)
        # We need to check if the object is a table vs a view
        existing_views = set()
        try:
            view_result = conn.execute(text("""
                SELECT table_name FROM information_schema.views
                WHERE table_schema = 'public'
                  AND table_name IN ('scheduled_appointments_v', 'calendar_events_v')
            """))
            existing_views = {row[0] for row in view_result}
        except Exception:
            pass

        # Create view for scheduled_appointments backward compatibility
        # Only if the real table exists and we've successfully migrated
        if "scheduled_appointments" in existing_tables:
            # First, rename the old table to preserve the data
            old_table_exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'scheduled_appointments'
                      AND table_type = 'BASE TABLE'
                )
            """)).scalar()

            if old_table_exists:
                # Check if backup already exists
                backup_exists = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'scheduled_appointments_backup'
                    )
                """)).scalar()

                if not backup_exists:
                    conn.execute(text(
                        "ALTER TABLE scheduled_appointments RENAME TO scheduled_appointments_backup"
                    ))
                    logger.info("  Renamed scheduled_appointments -> scheduled_appointments_backup")
                else:
                    logger.info("  scheduled_appointments_backup already exists, skipping rename")
                    # Drop the original if backup already exists (re-run scenario)
                    try:
                        conn.execute(text("DROP TABLE IF EXISTS scheduled_appointments CASCADE"))
                    except Exception:
                        pass

            # Create backward-compatible view
            conn.execute(text("DROP VIEW IF EXISTS scheduled_appointments CASCADE"))
            conn.execute(text("""
                CREATE VIEW scheduled_appointments AS
                SELECT
                    sa.id,
                    sa.legacy_appointment_id AS appointment_id,
                    sa.organization_id,
                    sa.assigned_user_id AS loan_officer_id,
                    NULL::VARCHAR(255) AS lo_name,
                    NULL::VARCHAR(255) AS lo_email,
                    sa.contact_id,
                    sa.attendee_name AS contact_name,
                    sa.attendee_email AS contact_email,
                    sa.attendee_phone AS contact_phone,
                    sa.event_type AS appointment_type,
                    sa.scheduled_start AS start_time,
                    sa.scheduled_end AS end_time,
                    sa.duration_minutes,
                    -- Reverse-map status
                    CASE sa.status
                        WHEN 'booked' THEN 'scheduled'
                        WHEN 'completed' THEN 'completed'
                        WHEN 'cancelled' THEN 'cancelled'
                        WHEN 'no_show' THEN 'no_show'
                        WHEN 'rescheduled' THEN 'rescheduled'
                        ELSE sa.status
                    END AS status,
                    sa.video_link AS meeting_link,
                    sa.location,
                    sa.description AS notes,
                    sa.internal_notes,
                    sa.booked_via,
                    sa.conversation_id,
                    sa.customer_invite_sent,
                    sa.lo_invite_sent,
                    sa.lo_confirmation_sent,
                    sa.created_at,
                    sa.updated_at,
                    sa.confirmed_at,
                    sa.cancelled_at
                FROM scheduler_appointments sa
                WHERE sa.source IN ('legacy_scheduler', 'ai_booked', 'manual')
                   OR sa.booked_via IS NOT NULL
            """))
            logger.info("  Created view: scheduled_appointments")

        # Create view for calendar_events backward compatibility
        if "calendar_events" in existing_tables:
            old_table_exists = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'calendar_events'
                      AND table_type = 'BASE TABLE'
                )
            """)).scalar()

            if old_table_exists:
                backup_exists = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'calendar_events_backup'
                    )
                """)).scalar()

                if not backup_exists:
                    conn.execute(text(
                        "ALTER TABLE calendar_events RENAME TO calendar_events_backup"
                    ))
                    logger.info("  Renamed calendar_events -> calendar_events_backup")
                else:
                    logger.info("  calendar_events_backup already exists, skipping rename")
                    try:
                        conn.execute(text("DROP TABLE IF EXISTS calendar_events CASCADE"))
                    except Exception:
                        pass

            conn.execute(text("DROP VIEW IF EXISTS calendar_events CASCADE"))
            conn.execute(text("""
                CREATE VIEW calendar_events AS
                SELECT
                    sa.id,
                    sa.organization_id,
                    sa.title,
                    sa.description,
                    sa.scheduled_start AS start_time,
                    sa.scheduled_end AS end_time,
                    COALESCE(sa.all_day, FALSE) AS all_day,
                    sa.location,
                    sa.event_type,
                    sa.lead_id,
                    sa.loan_id,
                    sa.assigned_user_id AS user_id,
                    sa.attendees,
                    sa.reminder_minutes,
                    CASE sa.status
                        WHEN 'booked' THEN 'scheduled'
                        WHEN 'completed' THEN 'completed'
                        WHEN 'cancelled' THEN 'cancelled'
                        ELSE sa.status
                    END AS status,
                    sa.meta_data,
                    sa.created_at,
                    sa.updated_at
                FROM scheduler_appointments sa
                WHERE sa.source IN ('legacy_calendar', 'manual', 'salesforce_sync', 'call_monitoring')
                   OR sa.event_type IS NOT NULL
            """))
            logger.info("  Created view: calendar_events")

        logger.info("Migration complete: appointment tables consolidated")


def run_rollback(engine=None):
    """
    Rollback the consolidation: drop views and restore original tables.

    Args:
        engine: SQLAlchemy engine. If None, imports from database module.
    """
    if engine is None:
        from database import engine

    from sqlalchemy import text, inspect

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        logger.info("Rolling back appointment table consolidation...")

        # Step 1: Drop views
        conn.execute(text("DROP VIEW IF EXISTS scheduled_appointments CASCADE"))
        conn.execute(text("DROP VIEW IF EXISTS calendar_events CASCADE"))
        logger.info("  Dropped backward-compatible views")

        # Step 2: Restore original tables from backups
        if "scheduled_appointments_backup" in existing_tables:
            conn.execute(text(
                "ALTER TABLE scheduled_appointments_backup RENAME TO scheduled_appointments"
            ))
            logger.info("  Restored scheduled_appointments from backup")

        if "calendar_events_backup" in existing_tables:
            conn.execute(text(
                "ALTER TABLE calendar_events_backup RENAME TO calendar_events"
            ))
            logger.info("  Restored calendar_events from backup")

        # Step 3: Remove migrated rows from scheduler_appointments
        deleted = conn.execute(text("""
            DELETE FROM scheduler_appointments
            WHERE legacy_table IN ('scheduled_appointments', 'calendar_events')
        """)).rowcount
        logger.info(f"  Removed {deleted} migrated rows from scheduler_appointments")

        # Step 4: Drop new columns (optional - they don't hurt anything)
        # We leave the new columns in place since they don't affect existing queries.
        # To fully remove them, uncomment below:
        #
        # drop_columns = [
        #     "source", "legacy_id", "legacy_table", "is_recurring",
        #     "recurrence_pattern", "parent_appointment_id",
        #     "conversion_tracked", "all_day", "attendees",
        #     "reminder_minutes", "meta_data", "event_type",
        #     "booked_via", "conversation_id", "confirmed_at",
        #     "customer_invite_sent", "lo_invite_sent",
        #     "lo_confirmation_sent", "legacy_appointment_id",
        # ]
        # for col in drop_columns:
        #     try:
        #         conn.execute(text(
        #             f"ALTER TABLE scheduler_appointments DROP COLUMN IF EXISTS {col}"
        #         ))
        #     except Exception as e:
        #         logger.warning(f"  Could not drop column {col}: {e}")

        logger.info("Rollback complete")


def _create_index_safe(conn, index_name, table_name, column_name):
    """Create an index, ignoring if it already exists."""
    from sqlalchemy import text
    try:
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"
        ))
    except Exception as e:
        if "already exists" in str(e).lower():
            pass
        else:
            logger.warning(f"Could not create index {index_name}: {e}")


# ==================================================================
# CLI entry point
# ==================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Allow DATABASE_URL override
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)

    from sqlalchemy import create_engine
    eng = create_engine(database_url)

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        print("Rolling back appointment table consolidation...")
        run_rollback(eng)
    else:
        print("Running appointment table consolidation migration...")
        run_migration(eng)

    print("Done.")
