"""
Database Migration: Smart Docs PII Encryption Columns

Adds ``_encrypted`` shadow columns alongside existing PII columns in the
``smart_documents`` table for a gradual encryption migration:

  - ocr_text_encrypted           (mirrors ocr_text)
  - extracted_account_number_encrypted  (mirrors extracted_account_number)
  - ip_address_encrypted         (mirrors ip_address)

Also adds a ``pii_encrypted_at`` timestamp column so the migration tool can
track which rows have been processed.

The original columns are NOT dropped -- both plaintext and encrypted columns
coexist during the transition period.  Application code should:
  1. Write to both columns (encrypted in _encrypted, plaintext in original)
  2. Read from _encrypted when present, fall back to original
  3. After migration is verified, stop writing plaintext (Phase 2)
  4. Eventually drop original columns (Phase 3)

Provides ``encrypt_existing_data(engine)`` for a one-time batch encryption
of existing rows that have plaintext but no encrypted counterpart.

Run with:
    python -m migrations.smart_docs_pii_encryption

Or call programmatically:
    from migrations.smart_docs_pii_encryption import run_migration
    run_migration()
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger(__name__)

# Columns to add: (column_name, column_type_sql)
NEW_COLUMNS = [
    ("ocr_text_encrypted", "TEXT"),
    ("extracted_account_number_encrypted", "VARCHAR(512)"),
    ("ip_address_encrypted", "VARCHAR(512)"),
    ("pii_encrypted_at", "TIMESTAMP"),
]

TABLE_NAME = "smart_documents"


def get_database_url() -> str:
    """Resolve database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    env_path = os.path.join(
        os.path.dirname(__file__), os.pardir, ".env"
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1]

    return "sqlite:///./mortgage_crm.db"


def is_postgresql(database_url: str) -> bool:
    return database_url.startswith("postgresql") or database_url.startswith(
        "postgres"
    )


def table_exists(conn, table_name: str) -> bool:
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def column_exists(conn, table_name: str, column_name: str) -> bool:
    inspector = inspect(conn)
    if not table_exists(conn, table_name):
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_encryption_columns(engine) -> None:
    """Add _encrypted shadow columns to smart_documents (idempotent)."""
    database_url = str(engine.url)
    use_pg = is_postgresql(database_url)

    with engine.connect() as conn:
        if not table_exists(conn, TABLE_NAME):
            logger.warning(
                "Table %s does not exist -- skipping PII encryption migration",
                TABLE_NAME,
            )
            return

        for col_name, col_type in NEW_COLUMNS:
            if column_exists(conn, TABLE_NAME, col_name):
                logger.info("Column %s.%s already exists", TABLE_NAME, col_name)
                continue

            if use_pg:
                sql = f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            else:
                sql = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col_name} {col_type}"

            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info("Added column %s.%s (%s)", TABLE_NAME, col_name, col_type)
            except Exception as e:
                # SQLite raises if column already exists (no IF NOT EXISTS support)
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(
                        "Column %s.%s already exists (caught exception)", TABLE_NAME, col_name
                    )
                else:
                    raise

    logger.info("PII encryption column migration complete")


def encrypt_existing_data(engine, batch_size: int = 500) -> int:
    """Encrypt existing plaintext PII into the new _encrypted columns.

    Processes rows in batches.  Only touches rows where the original column
    has data but the _encrypted column is NULL.

    Returns the number of rows updated.

    Requires PII_ENCRYPTION_KEY to be set in the environment.
    """
    try:
        from services.smart_docs.pii_encryption_service import PIIEncryptionService
    except ImportError:
        logger.error(
            "Cannot import PIIEncryptionService -- ensure backend is on PYTHONPATH"
        )
        return 0

    svc = PIIEncryptionService()
    total_updated = 0

    # Pairs: (plaintext_col, encrypted_col)
    column_pairs = [
        ("ocr_text", "ocr_text_encrypted"),
        ("extracted_account_number", "extracted_account_number_encrypted"),
        ("ip_address", "ip_address_encrypted"),
    ]

    with engine.connect() as conn:
        for plain_col, enc_col in column_pairs:
            if not column_exists(conn, TABLE_NAME, enc_col):
                logger.warning(
                    "Column %s.%s missing -- run add_encryption_columns first",
                    TABLE_NAME,
                    enc_col,
                )
                continue

            # Count eligible rows
            count_result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {TABLE_NAME} "
                    f"WHERE {plain_col} IS NOT NULL AND {enc_col} IS NULL"
                )
            ).scalar()

            if not count_result:
                logger.info("No rows to encrypt for %s", plain_col)
                continue

            logger.info(
                "Encrypting %d rows for %s -> %s",
                count_result,
                plain_col,
                enc_col,
            )

            offset = 0
            while True:
                rows = conn.execute(
                    text(
                        f"SELECT id, {plain_col} FROM {TABLE_NAME} "
                        f"WHERE {plain_col} IS NOT NULL AND {enc_col} IS NULL "
                        f"ORDER BY id LIMIT :batch_size"
                    ),
                    {"batch_size": batch_size},
                ).fetchall()

                if not rows:
                    break

                for row in rows:
                    row_id = row[0]
                    plaintext_value = row[1]
                    if plaintext_value is None:
                        continue

                    encrypted_value = svc.encrypt(str(plaintext_value))
                    conn.execute(
                        text(
                            f"UPDATE {TABLE_NAME} SET "
                            f"{enc_col} = :encrypted, "
                            f"pii_encrypted_at = :now "
                            f"WHERE id = :row_id"
                        ),
                        {
                            "encrypted": encrypted_value,
                            "now": datetime.now(timezone.utc),
                            "row_id": row_id,
                        },
                    )

                conn.commit()
                total_updated += len(rows)
                offset += batch_size
                logger.info(
                    "  Encrypted %d/%d rows for %s",
                    min(offset, count_result),
                    count_result,
                    plain_col,
                )

    logger.info("Encryption migration complete: %d total row-columns updated", total_updated)
    return total_updated


def run_migration() -> None:
    """Run the full PII encryption migration (schema + optional data)."""
    database_url = get_database_url()
    print(f"Connecting to database: {database_url[:50]}...")

    engine = create_engine(database_url)

    # Phase 1: Add columns
    add_encryption_columns(engine)

    # Phase 2: Encrypt existing data (only if PII_ENCRYPTION_KEY is set)
    if os.environ.get("PII_ENCRYPTION_KEY"):
        count = encrypt_existing_data(engine)
        print(f"Encrypted {count} row-columns")
    else:
        print(
            "PII_ENCRYPTION_KEY not set -- skipping data encryption. "
            "Set it and re-run to encrypt existing data."
        )

    print("Smart Docs PII encryption migration complete!")


if __name__ == "__main__":
    # Allow running from backend/ directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logging.basicConfig(level=logging.INFO)
    run_migration()
