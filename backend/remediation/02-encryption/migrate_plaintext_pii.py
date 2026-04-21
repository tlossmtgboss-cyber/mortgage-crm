"""
02-encryption/migrate_plaintext_pii.py

One-time backfill: find any PII columns storing plaintext (a consequence of
the previous fallback bug, finding #6) and encrypt them in place.

Detection heuristic: encrypted values are base64 and decode to 28+ bytes
(nonce 12 + min ciphertext 16). Plaintext SSNs look like '123-45-6789' or
'123456789'. If we can't decrypt it AND it looks like PII, we encrypt it.

Run once, post-deploy, against the live DB:
    python -m app.scripts.migrate_plaintext_pii --dry-run
    python -m app.scripts.migrate_plaintext_pii --apply

DO NOT commit the output logs — they contain PII.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.security.pii_encryption import (
    PIIDecryptionError,
    decrypt_pii,
    encrypt_pii,
)

logger = logging.getLogger(__name__)


@dataclass
class EncryptedColumn:
    table: str
    pk_column: str
    column: str
    # Pattern that matches plaintext for this column type
    plaintext_pattern: re.Pattern


# Add every column that uses EncryptedString
PII_COLUMNS = [
    EncryptedColumn("borrowers", "id", "ssn", re.compile(r"^\d{3}-?\d{2}-?\d{4}$")),
    EncryptedColumn("borrowers", "id", "date_of_birth", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    EncryptedColumn("borrowers", "id", "drivers_license_number", re.compile(r"^[A-Z0-9]{5,20}$")),
    EncryptedColumn("bank_accounts", "id", "account_number", re.compile(r"^\d{6,17}$")),
    EncryptedColumn("bank_accounts", "id", "routing_number", re.compile(r"^\d{9}$")),
    # add more as needed
]


async def audit_column(session: AsyncSession, col: EncryptedColumn) -> list[tuple[str, str]]:
    """Return (pk, raw_value) pairs that appear to be plaintext."""
    result = await session.execute(
        text(
            f"SELECT {col.pk_column}, {col.column} "
            f"FROM {col.table} "
            f"WHERE {col.column} IS NOT NULL"
        )
    )
    plaintext_rows: list[tuple[str, str]] = []
    for pk, value in result.all():
        if value is None:
            continue
        # Try decrypt — if it works, it's already encrypted, skip.
        try:
            decrypt_pii(value)
            continue
        except PIIDecryptionError:
            pass
        # If the value matches the plaintext pattern for this column, it's leaked.
        if col.plaintext_pattern.match(value):
            plaintext_rows.append((str(pk), value))
    return plaintext_rows


async def encrypt_in_place(session: AsyncSession, col: EncryptedColumn, pk: str, value: str) -> None:
    encrypted = encrypt_pii(value)
    await session.execute(
        text(
            f"UPDATE {col.table} SET {col.column} = :enc "
            f"WHERE {col.pk_column} = :pk"
        ),
        {"enc": encrypted, "pk": pk},
    )


async def main(apply: bool) -> int:
    engine = create_async_engine(settings.DATABASE_URL, pool_size=1, max_overflow=0)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_leaked = 0
    async with Session() as session:
        for col in PII_COLUMNS:
            rows = await audit_column(session, col)
            if not rows:
                logger.info("%s.%s: clean (no plaintext found)", col.table, col.column)
                continue

            total_leaked += len(rows)
            logger.warning(
                "%s.%s: %d plaintext rows detected", col.table, col.column, len(rows)
            )

            if apply:
                for pk, value in rows:
                    await encrypt_in_place(session, col, pk, value)
                await session.commit()
                logger.info("%s.%s: encrypted %d rows in place", col.table, col.column, len(rows))

    await engine.dispose()

    logger.info("Total plaintext rows: %d", total_leaked)
    if total_leaked > 0 and not apply:
        logger.warning("Dry run complete. Re-run with --apply to encrypt.")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually encrypt (default: dry run)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
