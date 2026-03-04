"""
Migration: Add organization_id to calendar sync tables + enforce NOT NULL on calendar_events.

Tables affected:
- calendar_event_sync_map: ADD organization_id (backfill from crm_calendar_events)
- calendar_sync_log: ADD organization_id (backfill from users)
- calendar_sync_settings: ADD organization_id (backfill from users)
- calendar_events: SET organization_id NOT NULL (backfill from users)

Run: python migrations/add_calendar_sync_org_id.py
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    from sqlalchemy import create_engine, text, inspect

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_engine(database_url)

    with engine.begin() as conn:
        insp = inspect(engine)
        existing_tables = insp.get_table_names()

        # ── 1. calendar_event_sync_map ──
        if "calendar_event_sync_map" in existing_tables:
            cols = {c["name"] for c in insp.get_columns("calendar_event_sync_map")}
            if "organization_id" not in cols:
                logger.info("Adding organization_id to calendar_event_sync_map...")
                conn.execute(text(
                    "ALTER TABLE calendar_event_sync_map "
                    "ADD COLUMN organization_id INTEGER"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_cal_sync_map_org_id "
                    "ON calendar_event_sync_map (organization_id)"
                ))
                # Backfill from joined crm_calendar_events
                conn.execute(text("""
                    UPDATE calendar_event_sync_map sm
                    SET organization_id = ce.organization_id
                    FROM crm_calendar_events ce
                    WHERE sm.crm_event_id = ce.id
                      AND sm.organization_id IS NULL
                """))
                # Backfill remaining with org 1
                conn.execute(text("""
                    UPDATE calendar_event_sync_map
                    SET organization_id = (SELECT MIN(id) FROM organizations)
                    WHERE organization_id IS NULL
                """))
                conn.execute(text(
                    "ALTER TABLE calendar_event_sync_map "
                    "ALTER COLUMN organization_id SET NOT NULL"
                ))
                logger.info("  Done.")
            else:
                logger.info("calendar_event_sync_map.organization_id already exists")

        # ── 2. calendar_sync_log ──
        if "calendar_sync_log" in existing_tables:
            cols = {c["name"] for c in insp.get_columns("calendar_sync_log")}
            if "organization_id" not in cols:
                logger.info("Adding organization_id to calendar_sync_log...")
                conn.execute(text(
                    "ALTER TABLE calendar_sync_log "
                    "ADD COLUMN organization_id INTEGER"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_cal_sync_log_org_id "
                    "ON calendar_sync_log (organization_id)"
                ))
                # Backfill from users table
                conn.execute(text("""
                    UPDATE calendar_sync_log sl
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE sl.user_id = u.id
                      AND sl.organization_id IS NULL
                """))
                conn.execute(text("""
                    UPDATE calendar_sync_log
                    SET organization_id = (SELECT MIN(id) FROM organizations)
                    WHERE organization_id IS NULL
                """))
                conn.execute(text(
                    "ALTER TABLE calendar_sync_log "
                    "ALTER COLUMN organization_id SET NOT NULL"
                ))
                logger.info("  Done.")
            else:
                logger.info("calendar_sync_log.organization_id already exists")

        # ── 3. calendar_sync_settings ──
        if "calendar_sync_settings" in existing_tables:
            cols = {c["name"] for c in insp.get_columns("calendar_sync_settings")}
            if "organization_id" not in cols:
                logger.info("Adding organization_id to calendar_sync_settings...")
                conn.execute(text(
                    "ALTER TABLE calendar_sync_settings "
                    "ADD COLUMN organization_id INTEGER"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_cal_sync_settings_org_id "
                    "ON calendar_sync_settings (organization_id)"
                ))
                # Backfill from users table
                conn.execute(text("""
                    UPDATE calendar_sync_settings ss
                    SET organization_id = u.organization_id
                    FROM users u
                    WHERE ss.user_id = u.id
                      AND ss.organization_id IS NULL
                """))
                conn.execute(text("""
                    UPDATE calendar_sync_settings
                    SET organization_id = (SELECT MIN(id) FROM organizations)
                    WHERE organization_id IS NULL
                """))
                conn.execute(text(
                    "ALTER TABLE calendar_sync_settings "
                    "ALTER COLUMN organization_id SET NOT NULL"
                ))
                logger.info("  Done.")
            else:
                logger.info("calendar_sync_settings.organization_id already exists")

        # ── 4. calendar_events — enforce NOT NULL ──
        if "calendar_events" in existing_tables:
            cols = {c["name"]: c for c in insp.get_columns("calendar_events")}
            if "organization_id" in cols:
                if cols["organization_id"].get("nullable", True):
                    logger.info("Enforcing NOT NULL on calendar_events.organization_id...")
                    # Backfill nulls from users table
                    conn.execute(text("""
                        UPDATE calendar_events ce
                        SET organization_id = u.organization_id
                        FROM users u
                        WHERE ce.user_id = u.id
                          AND ce.organization_id IS NULL
                    """))
                    # Remaining nulls get first org
                    conn.execute(text("""
                        UPDATE calendar_events
                        SET organization_id = (SELECT MIN(id) FROM organizations)
                        WHERE organization_id IS NULL
                    """))
                    conn.execute(text(
                        "ALTER TABLE calendar_events "
                        "ALTER COLUMN organization_id SET NOT NULL"
                    ))
                    logger.info("  Done.")
                else:
                    logger.info("calendar_events.organization_id already NOT NULL")
            else:
                logger.info("calendar_events.organization_id column missing — will be created by ORM")

    logger.info("Migration complete.")


if __name__ == "__main__":
    run_migration()
