"""
Create mm_score_gate_bypass_log table.

Records every admin override of the candidate score gate, providing an
immutable audit trail for OFCCP / EEOC compliance purposes.

Columns
-------
id                  Serial PK
organization_id     FK → organizations (RLS tenant column)
candidate_id        The candidate whose gate was bypassed
bypassed_by_user_id The admin who issued the override
old_status          Candidate status before the transition
new_status          Candidate status after the transition
bypass_reason       Optional free-text reason supplied by the admin
bypassed_at         Wall-clock timestamp of the override (TIMESTAMPTZ)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLE = "mm_score_gate_bypass_log"


def run_migration(engine=None) -> dict:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    results: dict = {"created": False, "indexes": [], "errors": []}

    with engine.connect() as conn:
        try:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id                  SERIAL PRIMARY KEY,
                    organization_id     INTEGER NOT NULL,
                    candidate_id        INTEGER NOT NULL,
                    bypassed_by_user_id INTEGER NOT NULL,
                    old_status          VARCHAR(100),
                    new_status          VARCHAR(100) NOT NULL,
                    bypass_reason       TEXT,
                    bypassed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            results["created"] = True
            logger.info("Created %s table", TABLE)
        except Exception as e:
            logger.error("Error creating %s: %s", TABLE, e)
            results["errors"].append({"table": TABLE, "error": str(e)})

        indexes = [
            (f"idx_{TABLE}_org", "organization_id"),
            (f"idx_{TABLE}_candidate", "candidate_id"),
            (f"idx_{TABLE}_bypassed_at", "bypassed_at"),
            (f"idx_{TABLE}_bypassed_by", "bypassed_by_user_id"),
        ]
        for idx_name, col in indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {TABLE} ({col})"
                ))
                results["indexes"].append(idx_name)
            except Exception as e:
                logger.error("Error creating index %s: %s", idx_name, e)
                results["errors"].append({"index": idx_name, "error": str(e)})

        conn.commit()

    logger.info("add_score_gate_bypass_log migration complete: %s", results)
    return results


def rollback(engine=None) -> None:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE} CASCADE"))
        conn.commit()
    logger.info("Rolled back: dropped %s", TABLE)


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_migration()
