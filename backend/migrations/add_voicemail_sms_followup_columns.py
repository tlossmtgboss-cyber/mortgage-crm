"""
Add SMS Follow-up Columns to voicemail_drops Table

Adds columns for tracking SMS follow-up after voicemail drops:
  - followup_sms_sent: Whether the follow-up SMS was sent
  - followup_sms_id: Telnyx message ID for tracking
  - followup_sms_blocked_reason: Reason if SMS was blocked by compliance

Usage:
    python -m migrations.add_voicemail_sms_followup_columns
    # or
    from migrations.add_voicemail_sms_followup_columns import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


COLUMNS = [
    ("followup_sms_sent", "BOOLEAN DEFAULT FALSE"),
    ("followup_sms_id", "VARCHAR(255)"),
    ("followup_sms_blocked_reason", "VARCHAR(500)"),
]


def run_migration():
    """Add SMS follow-up columns to the voicemail_drops table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        logger.info("Adding SMS follow-up columns to voicemail_drops table...")
        added = 0
        skipped = 0

        for col_name, col_type in COLUMNS:
            try:
                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE voicemail_drops ADD COLUMN {col_name} {col_type}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    ))
                added += 1
            except Exception as e:
                error_str = str(e).lower()
                if "duplicate column" in error_str or "already exists" in error_str:
                    skipped += 1
                elif "no such table" in error_str:
                    logger.warning("voicemail_drops table does not exist, skipping")
                    break
                else:
                    logger.warning(f"Could not add {col_name} to voicemail_drops: {e}")

        conn.commit()
        logger.info(f"  voicemail_drops: {added} added, {skipped} already existed")

    logger.info("SMS follow-up migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
