"""
Migration: Add Document Visibility Tables
Creates document_visibility and document_visibility_audit tables for
controlling document visibility to borrowers and partners with audit trail.

Compatible with both SQLite and PostgreSQL.
"""

import os
from sqlalchemy import create_engine, text
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


def table_exists(conn, table_name: str, is_sqlite: bool) -> bool:
    """Check if a table exists (works for both SQLite and PostgreSQL)."""
    if is_sqlite:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
        ), {"table_name": table_name})
        return result.fetchone() is not None
    else:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = :table_name
            )
        """), {"table_name": table_name})
        return result.scalar()


def run_migration():
    """Create document visibility tables."""
    if not DATABASE_URL:
        print("DATABASE_URL not set, skipping migration")
        return

    engine = create_engine(DATABASE_URL)
    is_sqlite = "sqlite" in DATABASE_URL.lower()

    if is_sqlite:
        print("Detected SQLite database")
    else:
        print("Detected PostgreSQL database")

    with engine.connect() as conn:
        # Check if document_visibility table already exists
        if table_exists(conn, "document_visibility", is_sqlite):
            print("document_visibility table already exists, skipping creation")
        else:
            print("Creating document_visibility table...")

            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE document_visibility (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,

                        -- Polymorphic document reference (supports multiple document tables)
                        document_table VARCHAR(50) NOT NULL,
                        document_id INTEGER NOT NULL,
                        loan_id INTEGER NOT NULL,

                        -- Visibility flags
                        visible_to_borrower BOOLEAN NOT NULL DEFAULT 1,
                        visible_to_partner BOOLEAN NOT NULL DEFAULT 1,
                        visible_to_internal BOOLEAN NOT NULL DEFAULT 1,

                        -- Release configuration
                        release_mode VARCHAR(20) DEFAULT 'manual',
                        release_milestone VARCHAR(50),
                        release_at TIMESTAMP,

                        -- Lock and reason
                        visibility_locked BOOLEAN DEFAULT 0,
                        hidden_reason TEXT,

                        -- Change tracking
                        last_changed_by INTEGER,
                        last_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                        -- Unique constraint per document
                        UNIQUE(document_table, document_id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE document_visibility (
                        id SERIAL PRIMARY KEY,

                        -- Polymorphic document reference (supports multiple document tables)
                        document_table VARCHAR(50) NOT NULL,
                        document_id INTEGER NOT NULL,
                        loan_id INTEGER NOT NULL,

                        -- Visibility flags
                        visible_to_borrower BOOLEAN NOT NULL DEFAULT true,
                        visible_to_partner BOOLEAN NOT NULL DEFAULT true,
                        visible_to_internal BOOLEAN NOT NULL DEFAULT true,

                        -- Release configuration
                        release_mode VARCHAR(20) DEFAULT 'manual',
                        release_milestone VARCHAR(50),
                        release_at TIMESTAMP WITH TIME ZONE,

                        -- Lock and reason
                        visibility_locked BOOLEAN DEFAULT false,
                        hidden_reason TEXT,

                        -- Change tracking
                        last_changed_by INTEGER REFERENCES users(id),
                        last_changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                        -- Unique constraint per document
                        UNIQUE(document_table, document_id)
                    )
                """))
            print("document_visibility table created")

            # Create indexes
            print("Creating indexes for document_visibility...")
            conn.execute(text("""
                CREATE INDEX idx_doc_visibility_loan ON document_visibility(loan_id)
            """))

            if is_sqlite:
                # SQLite: simple indexes without partial index syntax
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_borrower
                    ON document_visibility(visible_to_borrower)
                """))
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_partner
                    ON document_visibility(visible_to_partner)
                """))
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_release
                    ON document_visibility(release_mode, release_milestone)
                """))
            else:
                # PostgreSQL: partial indexes for better performance
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_borrower
                    ON document_visibility(visible_to_borrower)
                    WHERE visible_to_borrower = false
                """))
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_partner
                    ON document_visibility(visible_to_partner)
                    WHERE visible_to_partner = false
                """))
                conn.execute(text("""
                    CREATE INDEX idx_doc_visibility_release
                    ON document_visibility(release_mode, release_milestone)
                    WHERE release_mode = 'milestone'
                """))
            print("Indexes created")

        # Check if document_visibility_audit table already exists
        if table_exists(conn, "document_visibility_audit", is_sqlite):
            print("document_visibility_audit table already exists, skipping creation")
        else:
            print("Creating document_visibility_audit table...")

            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE document_visibility_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_visibility_id INTEGER,
                        loan_id INTEGER NOT NULL,

                        -- Change details
                        field_changed VARCHAR(50) NOT NULL,
                        old_value BOOLEAN,
                        new_value BOOLEAN,

                        -- Actor info
                        change_source VARCHAR(50) NOT NULL,
                        changed_by INTEGER,
                        change_reason TEXT,

                        -- Timestamp
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                        FOREIGN KEY (document_visibility_id) REFERENCES document_visibility(id) ON DELETE CASCADE
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE document_visibility_audit (
                        id SERIAL PRIMARY KEY,
                        document_visibility_id INTEGER REFERENCES document_visibility(id) ON DELETE CASCADE,
                        loan_id INTEGER NOT NULL,

                        -- Change details
                        field_changed VARCHAR(50) NOT NULL,
                        old_value BOOLEAN,
                        new_value BOOLEAN,

                        -- Actor info
                        change_source VARCHAR(50) NOT NULL,
                        changed_by INTEGER REFERENCES users(id),
                        change_reason TEXT,

                        -- Timestamp
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
            print("document_visibility_audit table created")

            # Create indexes for audit table
            print("Creating indexes for document_visibility_audit...")
            conn.execute(text("""
                CREATE INDEX idx_doc_visibility_audit_doc
                ON document_visibility_audit(document_visibility_id, created_at DESC)
            """))
            conn.execute(text("""
                CREATE INDEX idx_doc_visibility_audit_loan
                ON document_visibility_audit(loan_id, created_at DESC)
            """))
            print("Audit indexes created")

        conn.commit()
        print("Document visibility migration completed successfully!")


if __name__ == "__main__":
    run_migration()
