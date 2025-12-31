"""
Migration: Create Intake Engine Tables
Creates tables for intake sessions, audit events, and SLA tasks
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

def run_migration():
    """Create intake engine tables"""
    print(f"Connecting to database...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        print("Creating intake engine tables...")

        # Create intake_sessions table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS intake_sessions (
                session_id VARCHAR(50) PRIMARY KEY,
                data JSONB NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("✓ intake_sessions table created")

        # Create index on expires_at for cleanup
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_intake_sessions_expires
            ON intake_sessions(expires_at)
        """))

        # Create intake_audit_events table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS intake_audit_events (
                event_id VARCHAR(50) PRIMARY KEY,
                session_id VARCHAR(50) NOT NULL,
                party_id VARCHAR(50),
                event_type VARCHAR(50) NOT NULL,
                payload JSONB,
                hash_prev VARCHAR(64),
                hash_self VARCHAR(64),
                pii_redacted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES intake_sessions(session_id) ON DELETE CASCADE
            )
        """))
        print("✓ intake_audit_events table created")

        # Create indexes for audit events
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_intake_audit_session
            ON intake_audit_events(session_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_intake_audit_type
            ON intake_audit_events(event_type)
        """))

        # Create intake_sla_tasks table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS intake_sla_tasks (
                task_id VARCHAR(50) PRIMARY KEY,
                session_id VARCHAR(50) NOT NULL,
                loan_id VARCHAR(50),
                task_type VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                due_in_minutes INTEGER,
                assignee_role VARCHAR(100),
                trigger_flags TEXT[],
                score_band VARCHAR(50),
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES intake_sessions(session_id) ON DELETE CASCADE
            )
        """))
        print("✓ intake_sla_tasks table created")

        # Create index for SLA tasks
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_intake_sla_session
            ON intake_sla_tasks(session_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_intake_sla_status
            ON intake_sla_tasks(status)
        """))

        db.commit()
        print("\n✅ All intake engine tables created successfully!")

if __name__ == "__main__":
    run_migration()
