"""Add organization_id to call_transfers for multi-tenant isolation."""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add organization_id column to call_transfers table."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'call_transfers' AND column_name = 'organization_id'
        """))
        if result.fetchone():
            logger.info("call_transfers.organization_id already exists, skipping")
            return

        logger.info("Adding organization_id to call_transfers...")

        # Add nullable column first (safe for existing rows)
        conn.execute(text("""
            ALTER TABLE call_transfers
            ADD COLUMN organization_id INTEGER REFERENCES organizations(id)
        """))

        # Backfill from initiator_user_id first, then from_user_id as fallback
        conn.execute(text("""
            UPDATE call_transfers ct
            SET organization_id = u.organization_id
            FROM users u
            WHERE ct.initiator_user_id = u.id
            AND ct.organization_id IS NULL
        """))

        # Catch any remaining rows via from_user_id
        conn.execute(text("""
            UPDATE call_transfers ct
            SET organization_id = u.organization_id
            FROM users u
            WHERE ct.from_user_id = u.id
            AND ct.organization_id IS NULL
        """))

        # Last resort: backfill from to_user_id
        conn.execute(text("""
            UPDATE call_transfers ct
            SET organization_id = u.organization_id
            FROM users u
            WHERE ct.to_user_id = u.id
            AND ct.organization_id IS NULL
        """))

        # Create index for performance
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_call_transfers_org_id
            ON call_transfers (organization_id)
        """))

        conn.commit()
        logger.info("call_transfers.organization_id migration complete")
