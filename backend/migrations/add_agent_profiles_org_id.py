"""Add organization_id to agent_profiles for multi-tenant isolation."""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add organization_id column to agent_profiles table."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'agent_profiles' AND column_name = 'organization_id'
        """))
        if result.fetchone():
            logger.info("agent_profiles.organization_id already exists, skipping")
            return

        logger.info("Adding organization_id to agent_profiles...")

        conn.execute(text("""
            ALTER TABLE agent_profiles
            ADD COLUMN organization_id INTEGER REFERENCES organizations(id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_agent_profiles_org_id
            ON agent_profiles (organization_id)
        """))

        conn.commit()
        logger.info("agent_profiles.organization_id migration complete")
