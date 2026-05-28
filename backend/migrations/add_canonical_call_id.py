"""
Add canonical_call_id UUID to call_logs, call_dispositions, and cie_call_records.
Add updated_at to call_dispositions.

Links all call-related records through a single identifier assigned at call initiation.
"""

from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def run_migration(db_session):
    """Add canonical_call_id columns and updated_at to call_dispositions."""
    stmts = [
        # call_logs
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS canonical_call_id UUID UNIQUE",
        "CREATE INDEX IF NOT EXISTS ix_call_logs_canonical ON call_logs (canonical_call_id)",

        # call_dispositions
        "ALTER TABLE call_dispositions ADD COLUMN IF NOT EXISTS canonical_call_id UUID",
        "ALTER TABLE call_dispositions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "CREATE INDEX IF NOT EXISTS ix_disposition_canonical ON call_dispositions (canonical_call_id)",

        # cie_call_records
        "ALTER TABLE cie_call_records ADD COLUMN IF NOT EXISTS canonical_call_id UUID",
        "CREATE INDEX IF NOT EXISTS ix_cie_call_canonical ON cie_call_records (canonical_call_id)",

        # vapi_calls
        "ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS canonical_call_id UUID",
        "CREATE INDEX IF NOT EXISTS ix_vapi_calls_canonical ON vapi_calls (canonical_call_id)",
    ]

    for stmt in stmts:
        try:
            db_session.execute(text(stmt))
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                logger.debug("Migration step skipped (already applied): %s", stmt[:60])
            else:
                logger.warning("Migration step failed: %s — %s", stmt[:60], e)


if __name__ == "__main__":
    from db import SessionLocal
    db = SessionLocal()
    try:
        run_migration(db)
        print("Migration completed: canonical_call_id columns added.")
    finally:
        db.close()
