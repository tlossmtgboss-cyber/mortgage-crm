"""
Add human sign-off columns to recruit_ai_audit_log.

human_reviewed_by   INT nullable  — user_id of the human reviewer
human_reviewed_at   TIMESTAMPTZ nullable — when the human reviewed the recommendation

These columns create a required paper trail so that every AI hire/no-hire
recommendation can be traced to a human who acknowledged and took responsibility
for the final decision (EEOC / OFCCP compliance).
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLE = "recruit_ai_audit_log"


def run_migration(engine=None) -> dict:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    results: dict = {"altered": False, "columns_added": [], "errors": []}

    with engine.connect() as conn:
        # Check table exists
        exists = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :t AND table_schema = 'public'
        """), {"t": TABLE}).fetchone()

        if not exists:
            logger.info("Table %s does not exist — skipping", TABLE)
            results["errors"].append({"table": TABLE, "error": "table does not exist"})
            return results

        for col, col_type in [
            ("human_reviewed_by", "INTEGER"),
            ("human_reviewed_at", "TIMESTAMPTZ"),
        ]:
            col_exists = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = :t AND column_name = :c AND table_schema = 'public'
            """), {"t": TABLE, "c": col}).fetchone()

            if col_exists:
                logger.info("Column %s.%s already exists — skipping", TABLE, col)
                continue

            try:
                conn.execute(text(
                    f"ALTER TABLE {TABLE} ADD COLUMN {col} {col_type}"
                ))
                results["columns_added"].append(col)
                logger.info("Added column %s.%s", TABLE, col)
            except Exception as e:
                logger.error("Error adding %s.%s: %s", TABLE, col, e)
                results["errors"].append({"column": col, "error": str(e)})

        results["altered"] = bool(results["columns_added"])
        conn.commit()

    logger.info("add_recruit_ai_audit_log_fields migration complete: %s", results)
    return results


def rollback(engine=None) -> None:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        for col in ("human_reviewed_by", "human_reviewed_at"):
            try:
                conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {col}"))
                logger.info("Rolled back: dropped %s.%s", TABLE, col)
            except Exception as e:
                logger.warning("Rollback warning for %s.%s: %s", TABLE, col, e)
        conn.commit()


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_migration()
