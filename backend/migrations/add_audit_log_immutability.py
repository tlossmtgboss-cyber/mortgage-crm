"""
Migration: Audit Log Immutability + Hash Chain

P0-4 Enterprise Remediation: Audit logs must be append-only with tamper detection.

This migration:
1. Adds hash chain columns (sequence_number, record_hash, previous_hash, hash_algorithm)
2. Creates DB triggers to prevent UPDATE and DELETE on audit_logs (PostgreSQL only)
3. Backfills sequence_number and computes initial record_hash for existing rows

Run: python backend/migrations/add_audit_log_immutability.py
"""

import os
import sys
import hashlib
import json
import logging

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _column_exists(conn, table, column, is_sqlite):
    """Check if a column exists in a table."""
    from sqlalchemy import text
    if is_sqlite:
        result = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in result)
    else:
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :col
        """), {"table": table, "col": column}).fetchone()
        return result is not None


def run_migration():
    """Execute the audit log immutability migration."""
    from sqlalchemy import text
    from db import engine

    is_sqlite = "sqlite" in str(engine.url)

    with engine.connect() as conn:
        # Step 1: Add hash chain columns
        logger.info("Step 1: Adding hash chain columns to audit_logs...")

        columns = {
            "sequence_number": "INTEGER",
            "record_hash": "VARCHAR(64)",
            "previous_hash": "VARCHAR(64)",
            "hash_algorithm": "VARCHAR(10) DEFAULT 'sha256'",
        }

        for col_name, col_type in columns.items():
            if not _column_exists(conn, "audit_logs", col_name, is_sqlite):
                conn.execute(text(f"""
                    ALTER TABLE audit_logs ADD COLUMN {col_name} {col_type}
                """))
                logger.info(f"  Added column {col_name}.")
            else:
                logger.info(f"  Column {col_name} already exists.")
        conn.commit()

        # Step 2: Create index on sequence_number
        logger.info("Step 2: Creating index on sequence_number...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_audit_logs_sequence
            ON audit_logs (sequence_number)
        """))
        conn.commit()

        # Step 3: Backfill sequence_number and record_hash for existing rows
        logger.info("Step 3: Backfilling hash chain for existing rows...")

        rows = conn.execute(text("""
            SELECT id, user_id, change_type, entity_type, timestamp,
                   before_state, after_state
            FROM audit_logs
            WHERE sequence_number IS NULL
            ORDER BY id ASC
        """)).fetchall()

        logger.info(f"  Found {len(rows)} rows to backfill.")

        if rows:
            # Get the current max sequence number (in case some are already filled)
            max_seq = conn.execute(text("""
                SELECT COALESCE(MAX(sequence_number), 0) FROM audit_logs
            """)).scalar()

            prev_hash = None
            # If there are already hash-chained rows, get the last hash
            if max_seq > 0:
                prev_hash = conn.execute(text("""
                    SELECT record_hash FROM audit_logs
                    WHERE sequence_number = :seq
                """), {"seq": max_seq}).scalar()

            seq = max_seq
            batch_size = 500
            for i, row in enumerate(rows):
                seq += 1
                row_id, user_id, change_type, entity_type, ts, before_state, after_state = row

                before_json = json.dumps(before_state, sort_keys=True, default=str) if before_state else None
                after_json = json.dumps(after_state, sort_keys=True, default=str) if after_state else None
                ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)

                payload = "|".join([
                    str(user_id),
                    change_type or "",
                    entity_type or "",
                    ts_str,
                    before_json or "",
                    after_json or "",
                    prev_hash or "",
                ])
                record_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

                conn.execute(text("""
                    UPDATE audit_logs
                    SET sequence_number = :seq,
                        record_hash = :hash,
                        previous_hash = :prev_hash,
                        hash_algorithm = 'sha256'
                    WHERE id = :row_id
                """), {
                    "seq": seq,
                    "hash": record_hash,
                    "prev_hash": prev_hash,
                    "row_id": row_id,
                })

                prev_hash = record_hash

                if (i + 1) % batch_size == 0:
                    conn.commit()
                    logger.info(f"  Backfilled {i + 1}/{len(rows)} rows...")

            conn.commit()
            logger.info(f"  Backfill complete: {len(rows)} rows hash-chained.")

        # Step 4: Create immutability triggers (PostgreSQL only)
        if is_sqlite:
            logger.info("Step 4: Skipping immutability triggers (SQLite — triggers are PostgreSQL-only).")
        else:
            logger.info("Step 4: Creating immutability triggers...")

            conn.execute(text("""
                CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'audit_logs table is append-only: % not allowed', TG_OP;
                END;
                $$ LANGUAGE plpgsql
            """))

            # Drop existing triggers first (idempotent)
            conn.execute(text("""
                DROP TRIGGER IF EXISTS audit_log_no_update ON audit_logs
            """))
            conn.execute(text("""
                DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_logs
            """))

            conn.execute(text("""
                CREATE TRIGGER audit_log_no_update
                    BEFORE UPDATE ON audit_logs
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_modification()
            """))

            conn.execute(text("""
                CREATE TRIGGER audit_log_no_delete
                    BEFORE DELETE ON audit_logs
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_modification()
            """))

            conn.commit()
            logger.info("  Immutability triggers created.")

        logger.info("Audit log immutability migration complete.")


if __name__ == "__main__":
    run_migration()
