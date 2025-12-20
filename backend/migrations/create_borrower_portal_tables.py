"""
Database Migration: Create Borrower Portal Tables

Creates tables for borrower-facing application functionality:
- borrower_applications: Application data and progress
- borrower_documents: Document uploads
- coborrower_invitations: Co-borrower invitations
- concierge_messages: AI concierge chat history
- scheduled_calls: Review call scheduling

Run with: python -m migrations.create_borrower_portal_tables
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def create_tables():
    """Create all borrower portal tables."""
    print("Creating borrower portal tables...")

    with engine.connect() as conn:
        # Borrower Applications table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS borrower_applications (
                id TEXT PRIMARY KEY,
                borrower_profile_id TEXT NOT NULL,
                loan_purpose TEXT NOT NULL,
                property_type TEXT,
                status TEXT DEFAULT 'in_progress',
                current_step TEXT DEFAULT 'profile',
                progress_percentage INTEGER DEFAULT 0,
                profile_data TEXT,
                income_data TEXT,
                asset_data TEXT,
                property_data TEXT,
                declarations TEXT,
                lo_id INTEGER,
                submitted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (borrower_profile_id) REFERENCES borrower_profiles(id),
                FOREIGN KEY (lo_id) REFERENCES users(id)
            )
        """))
        print("  - Created borrower_applications table")

        # Borrower Documents table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS borrower_documents (
                id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                borrower_id TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                doc_category TEXT DEFAULT 'other',
                filename TEXT NOT NULL,
                original_filename TEXT,
                file_size INTEGER,
                mime_type TEXT,
                file_content TEXT,
                status TEXT DEFAULT 'pending_review',
                review_notes TEXT,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (application_id) REFERENCES borrower_applications(id),
                FOREIGN KEY (borrower_id) REFERENCES borrower_profiles(id),
                FOREIGN KEY (reviewed_by) REFERENCES users(id)
            )
        """))
        print("  - Created borrower_documents table")

        # Co-borrower Invitations table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS coborrower_invitations (
                id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                email TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                relationship TEXT,
                invitation_token TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP,
                completed_at TIMESTAMP,
                expires_at TIMESTAMP,
                coborrower_data TEXT,
                FOREIGN KEY (application_id) REFERENCES borrower_applications(id)
            )
        """))
        print("  - Created coborrower_invitations table")

        # Concierge Messages table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concierge_messages (
                id TEXT PRIMARY KEY,
                borrower_id TEXT NOT NULL,
                application_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (borrower_id) REFERENCES borrower_profiles(id),
                FOREIGN KEY (application_id) REFERENCES borrower_applications(id)
            )
        """))
        print("  - Created concierge_messages table")

        # Scheduled Calls table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduled_calls (
                id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL,
                borrower_id TEXT NOT NULL,
                lo_id INTEGER,
                preferred_date TEXT,
                preferred_time TEXT,
                timezone TEXT DEFAULT 'America/New_York',
                confirmed_datetime TIMESTAMP,
                notes TEXT,
                status TEXT DEFAULT 'pending',
                meeting_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (application_id) REFERENCES borrower_applications(id),
                FOREIGN KEY (borrower_id) REFERENCES borrower_profiles(id),
                FOREIGN KEY (lo_id) REFERENCES users(id)
            )
        """))
        print("  - Created scheduled_calls table")

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_borrower_apps_borrower
            ON borrower_applications(borrower_profile_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_borrower_docs_app
            ON borrower_documents(application_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_coborrower_inv_app
            ON coborrower_invitations(application_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_concierge_msgs_borrower
            ON concierge_messages(borrower_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_calls_app
            ON scheduled_calls(application_id)
        """))

        conn.commit()
        print("  - Created indexes")

    print("\nBorrower portal tables created successfully!")


if __name__ == "__main__":
    print(f"Connecting to database...")
    create_tables()
    print("\nMigration complete!")
