"""
Call Intelligence Expansion Migration

Adds indexes and columns to support:
- Stacked notes across calls
- UW review completion tasks for Production Assistant
- Review task creation from JR LO and Underwriter

Changes:
- Index on call_artifacts for stacked_note queries
- task_type, source, source_id columns on tasks table
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def run_migration():
    """Run the call intelligence expansion migration."""
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
            try:
                # Ensure session_id column exists on call_artifacts (may have been created by older migration)
                session.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'call_artifacts' AND column_name = 'session_id'
                        ) THEN
                            ALTER TABLE call_artifacts ADD COLUMN session_id UUID REFERENCES call_sessions(id) ON DELETE CASCADE;
                        END IF;
                    END $$;
                """))

                # Index for efficient stacked notes query
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_call_artifacts_stacked_notes
                    ON call_artifacts (artifact_type, session_id)
                    WHERE artifact_type = 'stacked_note'
                """))

                # Index for 5 C's artifacts
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_call_artifacts_five_c
                    ON call_artifacts (artifact_type, session_id)
                    WHERE artifact_type LIKE 'five_c_%'
                """))

                # Index for UW review items
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_call_artifacts_uw_review
                    ON call_artifacts (artifact_type, session_id, execution_status)
                    WHERE artifact_type = 'uw_review_item'
                """))

                # Add task_type column to tasks table if not exists
                session.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'tasks' AND column_name = 'task_type'
                        ) THEN
                            ALTER TABLE tasks ADD COLUMN task_type VARCHAR(50);
                        END IF;
                    END $$;
                """))

                # Add source column to tasks table if not exists
                session.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'tasks' AND column_name = 'source'
                        ) THEN
                            ALTER TABLE tasks ADD COLUMN source VARCHAR(100);
                        END IF;
                    END $$;
                """))

                # Add source_id column to tasks table if not exists
                session.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'tasks' AND column_name = 'source_id'
                        ) THEN
                            ALTER TABLE tasks ADD COLUMN source_id UUID;
                        END IF;
                    END $$;
                """))

                # Index for task source lookups
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_tasks_source
                    ON tasks (source, source_id)
                    WHERE source IS NOT NULL
                """))

                session.commit()
            except Exception:
                session.rollback()
                raise

        else:
            # SQLite version

            # Create indexes (SQLite doesn't support partial indexes with WHERE clause)
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_call_artifacts_stacked_notes
                ON call_artifacts (artifact_type, session_id)
            """))

            session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_call_artifacts_five_c
                ON call_artifacts (artifact_type, session_id)
            """))

            # Check and add columns for SQLite
            # Get existing columns
            result = session.execute(text("PRAGMA table_info(tasks)"))
            columns = [row[1] for row in result.fetchall()]

            if 'task_type' not in columns:
                session.execute(text("""
                    ALTER TABLE tasks ADD COLUMN task_type VARCHAR(50)
                """))

            if 'source' not in columns:
                session.execute(text("""
                    ALTER TABLE tasks ADD COLUMN source VARCHAR(100)
                """))

            if 'source_id' not in columns:
                session.execute(text("""
                    ALTER TABLE tasks ADD COLUMN source_id TEXT
                """))

            # Index for task source lookups
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_tasks_source
                ON tasks (source, source_id)
            """))

        session.commit()
        logger.info("Call Intelligence expansion migration completed successfully")
        return {"success": True, "message": "Call Intelligence expansion indexes and columns added"}

    except Exception as e:
        session.rollback()
        logger.error(f"Call Intelligence expansion migration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
