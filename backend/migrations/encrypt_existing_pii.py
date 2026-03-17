"""
Migration: Encrypt existing PII in scheduler_appointments table.

Encrypts attendee_email and attendee_phone columns in-place.  Also widens the
columns to accommodate Fernet ciphertext (which is ~2.4x the plaintext length).

This migration is IDEMPOTENT:
  - Already-encrypted values are detected via Fernet token heuristics and skipped.
  - Column widening uses IF NOT EXISTS / safe ALTER semantics.

Usage:
    # From the backend directory:
    python -m migrations.encrypt_existing_pii

    # Or with a specific DATABASE_URL:
    DATABASE_URL=postgresql://... python -m migrations.encrypt_existing_pii
"""

import logging
import os
import sys

from sqlalchemy import create_engine, text

# Allow running as `python -m migrations.encrypt_existing_pii` from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.encryption import FieldEncryptor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

BATCH_SIZE = 500


def run_migration():
    """Encrypt attendee_email and attendee_phone in scheduler_appointments."""
    engine = create_engine(DATABASE_URL)
    encryptor = FieldEncryptor.get_instance()

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # ----------------------------------------------------------
            # Phase 1: Widen columns so ciphertext fits
            # ----------------------------------------------------------
            logger.info("Phase 1: Widening columns for ciphertext storage...")

            # PostgreSQL ALTER TYPE is safe for widening VARCHAR
            conn.execute(text(
                "ALTER TABLE scheduler_appointments "
                "ALTER COLUMN attendee_email TYPE VARCHAR(500)"
            ))
            conn.execute(text(
                "ALTER TABLE scheduler_appointments "
                "ALTER COLUMN attendee_phone TYPE VARCHAR(200)"
            ))
            logger.info("  Columns widened to VARCHAR(500) / VARCHAR(200)")

            # ----------------------------------------------------------
            # Phase 2: Encrypt existing plaintext values
            # ----------------------------------------------------------
            logger.info("Phase 2: Encrypting existing plaintext values...")

            # Count rows that need encryption
            count_result = conn.execute(text(
                "SELECT COUNT(*) AS cnt FROM scheduler_appointments "
                "WHERE attendee_email IS NOT NULL OR attendee_phone IS NOT NULL"
            ))
            total = count_result.fetchone()[0]
            logger.info(f"  {total} rows with attendee PII to process")

            if total == 0:
                logger.info("  No rows to process -- migration complete")
                trans.commit()
                return True

            # Process in batches
            offset = 0
            encrypted_count = 0
            skipped_count = 0

            while offset < total:
                rows = conn.execute(text(
                    "SELECT id, attendee_email, attendee_phone "
                    "FROM scheduler_appointments "
                    "WHERE attendee_email IS NOT NULL OR attendee_phone IS NOT NULL "
                    "ORDER BY id "
                    "LIMIT :batch OFFSET :offset"
                ), {"batch": BATCH_SIZE, "offset": offset}).fetchall()

                if not rows:
                    break

                for row in rows:
                    row_id = row[0]
                    email_val = row[1]
                    phone_val = row[2]

                    new_email = email_val
                    new_phone = phone_val
                    needs_update = False

                    # Encrypt email if not already encrypted
                    if email_val and not FieldEncryptor.is_encrypted(email_val):
                        new_email = encryptor.encrypt(email_val)
                        needs_update = True

                    # Encrypt phone if not already encrypted
                    if phone_val and not FieldEncryptor.is_encrypted(phone_val):
                        new_phone = encryptor.encrypt(phone_val)
                        needs_update = True

                    if needs_update:
                        conn.execute(text(
                            "UPDATE scheduler_appointments "
                            "SET attendee_email = :email, attendee_phone = :phone "
                            "WHERE id = :id"
                        ), {"email": new_email, "phone": new_phone, "id": row_id})
                        encrypted_count += 1
                    else:
                        skipped_count += 1

                offset += BATCH_SIZE
                logger.info(
                    f"  Processed {min(offset, total)}/{total} rows "
                    f"({encrypted_count} encrypted, {skipped_count} already encrypted)"
                )

            trans.commit()

            logger.info("=" * 60)
            logger.info("Migration complete")
            logger.info(f"  Encrypted: {encrypted_count} rows")
            logger.info(f"  Skipped (already encrypted): {skipped_count}")
            logger.info("=" * 60)
            return True

        except Exception as e:
            trans.rollback()
            logger.error(f"Migration failed, rolled back: {e}")
            raise


if __name__ == "__main__":
    logger.info("Encrypt Existing PII -- scheduler_appointments")
    logger.info("Encrypts attendee_email and attendee_phone at rest")
    logger.info("")
    success = run_migration()
    sys.exit(0 if success else 1)
