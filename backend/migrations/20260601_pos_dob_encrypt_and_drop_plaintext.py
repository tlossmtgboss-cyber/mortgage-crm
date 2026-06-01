"""
Encrypt legacy POS DOB columns, then drop the plaintext columns.

Background
----------
`pos_application_pii` historically stored borrower/co-borrower date of birth in
plaintext `dob` / `co_dob` Date columns. The model and write path now use the
encrypted `dob_encrypted` / `co_dob_encrypted` columns (ISO-8601 string under the
shared EncryptedString / Fernet TypeDecorator); the plaintext columns are only
read as a fallback for un-migrated rows and are NEVER written by current code.

This migration finishes the transition:
  1. Backfill: for every row that has a plaintext `dob` (resp. `co_dob`) but a
     NULL `dob_encrypted` (resp. `co_dob_encrypted`), encrypt the plaintext value
     into the encrypted column using the SAME EncryptedString the model uses.
  2. Verify: count rows still holding un-migrated plaintext DOB.
  3. Drop the plaintext columns — ONLY if step 2 found zero un-migrated rows.

Safety
------
- Idempotent: re-running after a full migration is a no-op (backfill matches
  nothing; columns already dropped → DROP COLUMN IF EXISTS).
- Fail-safe: the irreversible DROP is GATED on a clean verification count. If any
  row still has plaintext DOB without an encrypted value, the DROP is SKIPPED and
  the migration returns False so the operator can investigate — it will never
  destroy un-migrated PII.
- Requires the encryption key (DATA_ENCRYPTION_KEY, or SECRET_KEY fallback) to be
  configured, identical to the running app — otherwise backfilled ciphertext would
  be unreadable. The migration refuses to run if encryption can't initialize.

Usage
-----
    # Dry run (backfill + verify, never drops):
    python migrations/20260601_pos_dob_encrypt_and_drop_plaintext.py --dry-run

    # Full run (backfill, verify, drop if clean):
    python migrations/20260601_pos_dob_encrypt_and_drop_plaintext.py

    # From init_db.py
    from migrations.20260601_pos_dob_encrypt_and_drop_plaintext import run_migration
    run_migration(engine)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_encryptor():
    """Return the model's EncryptedString instance for consistent encryption.

    We reuse EncryptedString.process_bind_param so the ciphertext written here is
    byte-for-byte what the ORM would write — same key, same Fernet, same format.
    Raises if encryption can't initialize (refuse to write unreadable data).
    """
    from encryption_utils import EncryptedString  # noqa: WPS433 (local import by design)

    enc = EncryptedString()
    # Probe: encrypting a sentinel must round-trip, or we must NOT proceed.
    sample = enc.process_bind_param("1970-01-01", dialect=None)
    if not sample or enc.process_result_value(sample, dialect=None) != "1970-01-01":
        raise RuntimeError(
            "EncryptedString round-trip failed — DATA_ENCRYPTION_KEY/SECRET_KEY "
            "is not configured the same as the app. Aborting to avoid writing "
            "unreadable ciphertext."
        )
    return enc


def run_migration(engine=None, *, dry_run: bool = False) -> bool:
    """Backfill encrypted DOB, verify, then drop plaintext columns if clean.

    Args:
        engine: SQLAlchemy engine. If None, created from DATABASE_URL.
        dry_run: If True, backfill + verify only; never drop columns.

    Returns:
        True on success (or clean no-op). False if un-migrated rows remain (DROP
        skipped) or on error.
    """
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    # If the table or plaintext columns are already gone, this is a clean no-op.
    try:
        with engine.connect() as conn:
            cols = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'pos_application_pii'"
            )).scalars().all()
    except Exception as e:
        logger.error(f"Could not inspect pos_application_pii schema: {e}")
        return False

    if "pos_application_pii" and not cols:
        logger.info("pos_application_pii not present — nothing to migrate.")
        return True
    has_plain = "dob" in cols or "co_dob" in cols
    if not has_plain:
        logger.info("Plaintext dob/co_dob columns already dropped — no-op.")
        return True

    try:
        enc = _get_encryptor()
    except Exception as e:
        logger.error(f"Encryption unavailable, refusing to backfill: {e}")
        return False

    # ---- 1. Backfill un-migrated rows -------------------------------------
    backfilled = 0
    try:
        with engine.begin() as conn:
            for plain_col, enc_col in (("dob", "dob_encrypted"), ("co_dob", "co_dob_encrypted")):
                if plain_col not in cols:
                    continue
                rows = conn.execute(text(
                    f"SELECT application_id, {plain_col} AS d FROM pos_application_pii "
                    f"WHERE {plain_col} IS NOT NULL AND {enc_col} IS NULL"
                )).mappings().all()
                for row in rows:
                    iso = row["d"].isoformat() if hasattr(row["d"], "isoformat") else str(row["d"])
                    ciphertext = enc.process_bind_param(iso, dialect=None)
                    conn.execute(
                        text(
                            f"UPDATE pos_application_pii SET {enc_col} = :c "
                            f"WHERE application_id = :aid"
                        ),
                        {"c": ciphertext, "aid": row["application_id"]},
                    )
                    backfilled += 1
        logger.info(f"Backfilled {backfilled} encrypted DOB value(s).")
    except Exception as e:
        logger.error(f"Backfill failed (no columns dropped): {e}")
        return False

    # ---- 2. Verify: zero un-migrated plaintext rows remain ---------------
    try:
        with engine.connect() as conn:
            remaining = 0
            for plain_col, enc_col in (("dob", "dob_encrypted"), ("co_dob", "co_dob_encrypted")):
                if plain_col not in cols:
                    continue
                remaining += conn.execute(text(
                    f"SELECT COUNT(*) FROM pos_application_pii "
                    f"WHERE {plain_col} IS NOT NULL AND {enc_col} IS NULL"
                )).scalar() or 0
    except Exception as e:
        logger.error(f"Verification query failed (no columns dropped): {e}")
        return False

    if remaining > 0:
        logger.error(
            f"{remaining} row(s) still have plaintext DOB without an encrypted "
            f"value. DROP SKIPPED — investigate before re-running."
        )
        return False

    logger.info("Verification clean: 0 un-migrated plaintext DOB rows.")

    if dry_run:
        logger.info("--dry-run: backfill + verify complete, columns NOT dropped.")
        return True

    # ---- 3. Drop plaintext columns (gated on clean verification) ---------
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE pos_application_pii DROP COLUMN IF EXISTS dob"))
            conn.execute(text("ALTER TABLE pos_application_pii DROP COLUMN IF EXISTS co_dob"))
        logger.info("Dropped plaintext dob/co_dob columns. Migration complete.")
        return True
    except Exception as e:
        logger.error(f"Column drop failed: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Backfill + verify only; never drop the plaintext columns.",
    )
    args = parser.parse_args()

    logger.info("Starting POS DOB encryption migration (dry_run=%s)...", args.dry_run)
    ok = run_migration(dry_run=args.dry_run)
    if ok:
        logger.info("Migration step completed.")
    else:
        logger.error("Migration did not complete cleanly — see errors above.")
        sys.exit(1)
