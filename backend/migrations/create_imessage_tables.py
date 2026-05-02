"""
Create the 5 iMessage / BlueBubbles integration tables.

Run standalone:  python -m migrations.create_imessage_tables
Or invoke run_migration() from app startup / init_db.

Tables:
  imessage_lines          — Mac mini relays + Apple ID handle
  imessage_threads        — per (org, lead, line) conversation
  imessage_messages       — every message exchanged
  imessage_lookup_cache   — phone -> iMessage/SMS service cache
  imessage_webhook_log    — append-only BB webhook audit
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def run_migration():
    """Create all 5 iMessage tables using checkfirst=True (safe to re-run)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from database import engine
    from integrations.imessage.models import (
        IMessageLine,
        IMessageThread,
        IMessageMessage,
        IMessageLookupCache,
        IMessageWebhookLog,
    )

    # Order matters: lines first (threads/webhook_log have FK to lines),
    # threads before messages (messages have FK to threads).
    models = [
        IMessageLine,
        IMessageThread,
        IMessageMessage,
        IMessageLookupCache,
        IMessageWebhookLog,
    ]

    created = []
    for model in models:
        try:
            model.__table__.create(engine, checkfirst=True)
            created.append(model.__tablename__)
            logger.info("ensured table exists: %s", model.__tablename__)
        except Exception as e:
            logger.error(
                "failed to create table %s: %s", model.__tablename__, e
            )

    logger.info(
        "iMessage table migration complete — %d/%d tables ensured: %s",
        len(created),
        len(models),
        ", ".join(created),
    )
    return created


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
