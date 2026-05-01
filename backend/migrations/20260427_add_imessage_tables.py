"""
Create iMessage / BlueBubbles integration tables.

Run standalone:  python -m migrations.20260427_add_imessage_tables
Or auto-runs via init_db.py model import + Base.metadata.create_all(checkfirst=True).

Tables:
  imessage_lines          — Mac mini relays
  imessage_threads        — per (org, lead, line) conversation
  imessage_messages       — every message exchanged
  imessage_lookup_cache   — phone → iMessage/SMS cache
  imessage_webhook_log    — append-only BB webhook audit
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def run_migration():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from database import Base, engine
    from integrations.imessage.models import (  # noqa: F401 — import triggers registration
        IMessageLine,
        IMessageThread,
        IMessageMessage,
        IMessageLookupCache,
        IMessageWebhookLog,
    )

    tables = [
        IMessageLine.__table__,
        IMessageThread.__table__,
        IMessageMessage.__table__,
        IMessageLookupCache.__table__,
        IMessageWebhookLog.__table__,
    ]
    for table in tables:
        table.create(engine, checkfirst=True)
        logger.info("ensured table exists: %s", table.name)

    logger.info("iMessage migration complete — 5 tables ensured")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
