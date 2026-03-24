"""
Migration: Add Morning Briefings

Creates morning_briefings table and adds manager_id, briefing_enabled,
briefing_hour columns to users table.
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create morning_briefings table and add user columns."""

    sql_commands = [
        # 1. Add manager_id to users
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_id INTEGER REFERENCES users(id);
        """,
        # 2. Add index on manager_id
        """
        CREATE INDEX IF NOT EXISTS ix_users_manager_id ON users(manager_id);
        """,
        # 3. Add briefing preferences to users
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_enabled BOOLEAN DEFAULT TRUE;
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_hour INTEGER DEFAULT 7;
        """,
        # 4. Create morning_briefings table
        """
        CREATE TABLE IF NOT EXISTS morning_briefings (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            briefing_date DATE NOT NULL,
            briefing_level VARCHAR(20) NOT NULL DEFAULT 'individual',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            briefing_data JSONB,
            team_data JSONB,
            ai_narrative TEXT,
            html_content TEXT,
            email_sent_at TIMESTAMP WITH TIME ZONE,
            email_message_id VARCHAR(255),
            viewed_in_app_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_user_briefing_date UNIQUE (user_id, briefing_date)
        );
        """,
        # 5. Indexes
        """
        CREATE INDEX IF NOT EXISTS ix_briefing_date_status
            ON morning_briefings(briefing_date, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_org_briefing_date
            ON morning_briefings(organization_id, briefing_date);
        """,
    ]

    with engine.connect() as conn:
        for cmd in sql_commands:
            try:
                conn.execute(text(cmd))
                logger.info(f"Executed: {cmd.strip()[:60]}...")
            except Exception as e:
                logger.warning(f"Skipped (may already exist): {e}")
        conn.commit()

    logger.info("Morning briefings migration complete")


if __name__ == "__main__":
    run_migration()
