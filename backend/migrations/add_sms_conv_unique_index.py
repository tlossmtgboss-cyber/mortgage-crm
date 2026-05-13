"""
Migration: Add partial UNIQUE index on sms_ai_conversations to prevent
duplicate active conversations for the same phone+org (race condition guard).

Index: uq_sms_conv_active_phone_org
  ON sms_ai_conversations(phone_number, organization_id)
  WHERE status = 'active'
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    if engine is None:
        from db import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_conv_active_phone_org
            ON sms_ai_conversations(phone_number, organization_id)
            WHERE status = 'active'
        """))
        conn.commit()
        logger.info(
            "[SMS_AI_CONV] Partial unique index uq_sms_conv_active_phone_org created/verified"
        )
