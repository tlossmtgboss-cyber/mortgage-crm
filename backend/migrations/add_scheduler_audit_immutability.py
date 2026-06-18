"""
Migration: Scheduler Audit Log Immutability + Hash Chain

Enterprise security remediation: scheduler_audit_log must be append-only with
tamper detection, matching the guarantee already on audit_logs.

This migration:
1. Adds hash chain columns (row_hash VARCHAR(64), prev_hash VARCHAR(64))
2. Creates a BEFORE INSERT trigger that maintains a SHA-256 hash chain
3. Creates a BEFORE UPDATE OR DELETE trigger that rejects all mutations

Run standalone: python backend/migrations/add_scheduler_audit_immutability.py
"""

import logging

logger = logging.getLogger(__name__)

TABLE_NAME = "scheduler_audit_log"


def _table_exists(engine) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return TABLE_NAME in sa_inspect(engine).get_table_names()


def run_migration(engine=None):
    """
    Apply immutability trigger and hash-chain trigger to scheduler_audit_log.

    Runs in AUTOCOMMIT mode — DDL statements must be outside transactions.
    Skips silently if the table does not exist yet.
    """
    from sqlalchemy import text

    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not _table_exists(engine):
        logger.info("[SKIP] %s — table %s does not exist yet", __name__, TABLE_NAME)
        return

    # SQLite (test environments) does not support plpgsql triggers — skip.
    is_sqlite = "sqlite" in str(engine.url)
    if is_sqlite:
        logger.info("[SKIP] %s — SQLite detected, triggers are PostgreSQL-only", __name__)
        return

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        # ------------------------------------------------------------------
        # Part 1 — Hash chain columns
        # ------------------------------------------------------------------
        logger.info("[%s] Adding hash chain columns...", TABLE_NAME)
        conn.execute(text(
            f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS row_hash VARCHAR(64)"
        ))
        conn.execute(text(
            f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS prev_hash VARCHAR(64)"
        ))
        logger.info("[%s] Hash chain columns ready.", TABLE_NAME)

        # ------------------------------------------------------------------
        # Part 2 — BEFORE INSERT hash-chain trigger
        # ------------------------------------------------------------------
        logger.info("[%s] Creating hash-chain trigger function...", TABLE_NAME)
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION scheduler_audit_hash_chain()
            RETURNS TRIGGER AS $$
            DECLARE
                latest_hash TEXT;
            BEGIN
                SELECT row_hash INTO latest_hash
                FROM scheduler_audit_log
                ORDER BY created_at DESC, id DESC
                LIMIT 1;

                NEW.prev_hash := COALESCE(
                    latest_hash,
                    '0000000000000000000000000000000000000000000000000000000000000000'
                );

                NEW.row_hash := encode(sha256(
                    (
                        COALESCE(NEW.id::text, '') || '|' ||
                        COALESCE(NEW.action, '') || '|' ||
                        COALESCE(NEW.entity_id::text, '') || '|' ||
                        COALESCE(NEW.organization_id::text, '') || '|' ||
                        NEW.prev_hash
                    )::bytea
                ), 'hex');

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))

        conn.execute(text(
            f"DROP TRIGGER IF EXISTS scheduler_audit_hash_trigger ON {TABLE_NAME}"
        ))
        conn.execute(text(f"""
            CREATE TRIGGER scheduler_audit_hash_trigger
                BEFORE INSERT ON {TABLE_NAME}
                FOR EACH ROW EXECUTE FUNCTION scheduler_audit_hash_chain()
        """))
        logger.info("[%s] Hash-chain trigger created.", TABLE_NAME)

        # ------------------------------------------------------------------
        # Part 3 — BEFORE UPDATE OR DELETE immutability trigger
        # ------------------------------------------------------------------
        logger.info("[%s] Creating immutability trigger function...", TABLE_NAME)
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION prevent_scheduler_audit_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION
                    'scheduler_audit_log is immutable: UPDATE and DELETE are not permitted';
            END;
            $$ LANGUAGE plpgsql
        """))

        conn.execute(text(
            f"DROP TRIGGER IF EXISTS scheduler_audit_immutable ON {TABLE_NAME}"
        ))
        conn.execute(text(f"""
            CREATE TRIGGER scheduler_audit_immutable
                BEFORE UPDATE OR DELETE ON {TABLE_NAME}
                FOR EACH ROW EXECUTE FUNCTION prevent_scheduler_audit_modification()
        """))
        logger.info("[%s] Immutability trigger created.", TABLE_NAME)

    logger.info("[OK] scheduler_audit_log immutability + hash-chain migration complete.")


def rollback(engine=None):
    """
    Remove the triggers and functions added by this migration.

    Columns (row_hash, prev_hash) are intentionally NOT dropped — existing
    hash data must be preserved for audit purposes.
    """
    from sqlalchemy import text

    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not _table_exists(engine):
        logger.info("[SKIP] rollback — table %s does not exist", TABLE_NAME)
        return

    is_sqlite = "sqlite" in str(engine.url)
    if is_sqlite:
        logger.info("[SKIP] rollback — SQLite detected, nothing to drop")
        return

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        conn.execute(text(
            f"DROP TRIGGER IF EXISTS scheduler_audit_immutable ON {TABLE_NAME}"
        ))
        conn.execute(text(
            "DROP FUNCTION IF EXISTS prevent_scheduler_audit_modification()"
        ))

        conn.execute(text(
            f"DROP TRIGGER IF EXISTS scheduler_audit_hash_trigger ON {TABLE_NAME}"
        ))
        conn.execute(text(
            "DROP FUNCTION IF EXISTS scheduler_audit_hash_chain()"
        ))

    logger.info("[OK] scheduler_audit_log triggers and functions removed.")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_migration()
    sys.exit(0)
