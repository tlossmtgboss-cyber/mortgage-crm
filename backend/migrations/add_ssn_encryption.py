"""
Migration: Add SSN Encryption Columns + Migrate Existing Plaintext SSNs

P0-3 Enterprise Remediation: Full 9-digit SSN must not be stored plaintext.

This migration:
1. Adds ssn_encrypted and co_ssn_encrypted columns to borrower_applications
2. Migrates any existing plaintext SSNs from step_data JSON → encrypted columns
3. Redacts SSN from step_data JSON (replaces with "***ENCRYPTED***")

Run: python backend/migrations/add_ssn_encryption.py
"""

import os
import sys
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
    """Execute the SSN encryption migration."""
    from sqlalchemy import text
    from db import engine

    is_sqlite = "sqlite" in str(engine.url)

    with engine.connect() as conn:
        # Step 1: Add encrypted SSN columns if they don't exist
        logger.info("Step 1: Adding ssn_encrypted and co_ssn_encrypted columns...")

        for col_name in ["ssn_encrypted", "co_ssn_encrypted"]:
            if not _column_exists(conn, "borrower_applications", col_name, is_sqlite):
                conn.execute(text(f"""
                    ALTER TABLE borrower_applications ADD COLUMN {col_name} VARCHAR
                """))
                logger.info(f"  Added column {col_name}.")
            else:
                logger.info(f"  Column {col_name} already exists.")
        conn.commit()

        # Step 2: Find rows with plaintext SSN in step_data
        logger.info("Step 2: Migrating plaintext SSNs from step_data...")

        if is_sqlite:
            query = text("""
                SELECT id, step_data
                FROM borrower_applications
                WHERE step_data IS NOT NULL
                  AND step_data LIKE '%"ssn"%'
            """)
        else:
            query = text("""
                SELECT id, step_data
                FROM borrower_applications
                WHERE step_data IS NOT NULL
                  AND step_data::text LIKE '%"ssn"%'
            """)

        rows = conn.execute(query).fetchall()

        logger.info(f"  Found {len(rows)} applications with SSN in step_data.")

        if rows:
            from encryption_utils import encrypt_value

            migrated = 0
            for row in rows:
                app_id = row[0]
                step_data = row[1] if isinstance(row[1], dict) else json.loads(row[1])

                ssn_raw = step_data.get("ssn")
                co_ssn_raw = step_data.get("co_ssn")

                ssn_encrypted = None
                co_ssn_encrypted = None
                modified = False

                # Encrypt primary SSN
                if ssn_raw and isinstance(ssn_raw, str):
                    # Skip already-encrypted values
                    if ssn_raw == "***ENCRYPTED***":
                        continue
                    digits = "".join(c for c in ssn_raw if c.isdigit())
                    if len(digits) == 9:
                        ssn_encrypted = encrypt_value(digits)
                        step_data["ssn"] = "***ENCRYPTED***"
                        step_data["ssn_last4"] = digits[-4:]
                        modified = True

                # Encrypt co-borrower SSN
                if co_ssn_raw and isinstance(co_ssn_raw, str):
                    if co_ssn_raw == "***ENCRYPTED***":
                        continue
                    digits = "".join(c for c in co_ssn_raw if c.isdigit())
                    if len(digits) == 9:
                        co_ssn_encrypted = encrypt_value(digits)
                        step_data["co_ssn"] = "***ENCRYPTED***"
                        step_data["co_ssn_last4"] = digits[-4:]
                        modified = True

                if modified:
                    conn.execute(text("""
                        UPDATE borrower_applications
                        SET step_data = :step_data,
                            ssn_encrypted = COALESCE(:ssn_enc, ssn_encrypted),
                            co_ssn_encrypted = COALESCE(:co_ssn_enc, co_ssn_encrypted)
                        WHERE id = :app_id
                    """), {
                        "step_data": json.dumps(step_data),
                        "ssn_enc": ssn_encrypted,
                        "co_ssn_enc": co_ssn_encrypted,
                        "app_id": app_id,
                    })
                    migrated += 1

            conn.commit()
            logger.info(f"  Migrated {migrated} applications.")
        else:
            logger.info("  No plaintext SSNs found to migrate.")

        logger.info("SSN encryption migration complete.")


if __name__ == "__main__":
    run_migration()
