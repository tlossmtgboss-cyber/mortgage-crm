"""
Migration: Add engagement engine tables
Creates call_dispositions and organization_ai_configs tables.
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
    """Create engagement engine tables."""
    sql_commands = [
        """
        CREATE TABLE IF NOT EXISTS call_dispositions (
            id VARCHAR(255) PRIMARY KEY,
            call_log_id VARCHAR(255),
            lead_id INTEGER REFERENCES leads(id),
            loan_id VARCHAR(255),
            user_id INTEGER REFERENCES users(id),
            organization_id INTEGER NOT NULL,
            disposition VARCHAR(50) NOT NULL,
            sub_disposition VARCHAR(50),
            call_direction VARCHAR(20) DEFAULT 'outbound',
            call_duration_seconds INTEGER,
            caller_phone VARCHAR(50),
            ai_summary TEXT,
            sentiment VARCHAR(20),
            intent_detected VARCHAR(100),
            qualification_score FLOAT,
            follow_up_required BOOLEAN DEFAULT FALSE,
            follow_up_date TIMESTAMP WITH TIME ZONE,
            follow_up_notes TEXT,
            notes TEXT,
            voice_note_url VARCHAR(500),
            transcript_url VARCHAR(500),
            source VARCHAR(50) DEFAULT 'dialer',
            session_id VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_disposition_org_date ON call_dispositions(organization_id, created_at);",
        "CREATE INDEX IF NOT EXISTS ix_disposition_user_date ON call_dispositions(user_id, created_at);",
        "CREATE INDEX IF NOT EXISTS ix_disposition_lead ON call_dispositions(lead_id);",
        "CREATE INDEX IF NOT EXISTS ix_disposition_call_log ON call_dispositions(call_log_id);",

        """
        CREATE TABLE IF NOT EXISTS organization_ai_configs (
            organization_id INTEGER PRIMARY KEY,
            config_data JSON NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ]

    with engine.connect() as conn:
        for sql in sql_commands:
            conn.execute(text("SAVEPOINT engagement_stmt"))
            try:
                conn.execute(text(sql))
                conn.execute(text("RELEASE SAVEPOINT engagement_stmt"))
                logger.info(f"Executed: {sql[:60]}...")
            except Exception as e:
                conn.execute(text("ROLLBACK TO SAVEPOINT engagement_stmt"))
                logger.warning(f"Skipped: {e}")
        conn.commit()

    logger.info("Engagement engine tables migration complete.")


if __name__ == "__main__":
    run_migration()
