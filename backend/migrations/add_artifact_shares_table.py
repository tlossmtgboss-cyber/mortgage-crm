"""
Artifact Shares Database Migration
Creates table for managing shareable links for call artifacts (calculator results, etc.)

Tables:
- artifact_shares: Share tokens and tracking for public artifact access
"""

import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def run_migration():
    """Run the artifact shares migration."""
    if DATABASE_URL.startswith("postgres"):
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        db_url = DATABASE_URL

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        is_postgres = "postgresql" in db_url

        if is_postgres:
            # PostgreSQL version
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS artifact_shares (
                    id SERIAL PRIMARY KEY,
                    artifact_id UUID NOT NULL REFERENCES call_artifacts(id) ON DELETE CASCADE,
                    share_token VARCHAR(100) UNIQUE NOT NULL,
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    view_count INTEGER DEFAULT 0,
                    last_viewed_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT true,

                    -- Optional metadata
                    title_override VARCHAR(255),
                    description_override TEXT,

                    -- Access tracking
                    last_viewer_ip VARCHAR(45),
                    last_viewer_user_agent TEXT
                )
            """))

            # Create indexes
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_artifact_shares_token
                    ON artifact_shares(share_token);
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_artifact_shares_artifact
                    ON artifact_shares(artifact_id);
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_artifact_shares_active_expires
                    ON artifact_shares(is_active, expires_at);
            """))

        else:
            # SQLite version
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS artifact_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL,
                    share_token VARCHAR(100) UNIQUE NOT NULL,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    view_count INTEGER DEFAULT 0,
                    last_viewed_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    title_override VARCHAR(255),
                    description_override TEXT,
                    last_viewer_ip VARCHAR(45),
                    last_viewer_user_agent TEXT
                )
            """))

            # Create indexes for SQLite
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_artifact_shares_token
                    ON artifact_shares(share_token)
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_artifact_shares_artifact
                    ON artifact_shares(artifact_id)
            """))

        session.commit()
        logger.info("Artifact shares migration completed successfully")
        return {"success": True, "message": "artifact_shares table created"}

    except Exception as e:
        session.rollback()
        logger.error(f"Artifact shares migration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
