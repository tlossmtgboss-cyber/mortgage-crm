"""
Add partial index on scheduler_appointments for active (non-terminal) rows.

Eliminates full-table status predicate evaluation on availability and team
calendar queries that filter WHERE status NOT IN ('CANCELLED', 'NO_SHOW').
Must run CONCURRENTLY (outside a transaction) to avoid table locks.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

INDEX_NAME = "idx_appointment_active"
TABLE_NAME = "scheduler_appointments"

# status literals lowercase-only — matches VARCHAR after enum-to-VARCHAR migration
DDL = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
    f"ON {TABLE_NAME} (organization_id, assigned_user_id, scheduled_start) "
    f"WHERE status NOT IN ('cancelled', 'no_show')"
)


def _index_exists(conn) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": INDEX_NAME},
    )
    return result.fetchone() is not None


def _table_exists(engine) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return TABLE_NAME in sa_inspect(engine).get_table_names()


def run_migration(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not _table_exists(engine):
        logger.info("[SKIP] %s — table %s does not exist yet", INDEX_NAME, TABLE_NAME)
        return

    # CONCURRENTLY must run outside any transaction block.
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        if _index_exists(conn):
            logger.info("[SKIP] %s already exists", INDEX_NAME)
            return

        try:
            conn.execute(text(DDL))
            logger.info("[OK] Created partial index %s", INDEX_NAME)
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err:
                logger.info("[SKIP] %s — already exists (race condition)", INDEX_NAME)
            else:
                logger.warning("[FAIL] Could not create %s: %s", INDEX_NAME, e)


def rollback(engine=None):
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"))
            logger.info("Dropped index %s", INDEX_NAME)
        except Exception as e:
            logger.warning("Could not drop index %s: %s", INDEX_NAME, e)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_migration()
    sys.exit(0)
