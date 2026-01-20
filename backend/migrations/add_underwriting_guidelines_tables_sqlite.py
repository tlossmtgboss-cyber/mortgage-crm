"""
Migration: Add Underwriting Guidelines Tables (SQLite)

SQLite-compatible version of the underwriting guidelines migration.

Run with: python -m migrations.add_underwriting_guidelines_tables_sqlite
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from sqlalchemy import text


def run_migration():
    """Run the underwriting guidelines migration for SQLite."""
    print("=" * 60)
    print("Underwriting Guidelines Tables Migration (SQLite)")
    print("=" * 60)

    sql_statements = [
        # 1. Underwriting Guidelines table
        """
        CREATE TABLE IF NOT EXISTS underwriting_guidelines (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            version TEXT,
            guideline_type TEXT NOT NULL,
            category TEXT,
            loan_program TEXT DEFAULT 'all',
            investor_name TEXT,
            source_file_name TEXT,
            source_file_path TEXT,
            source_file_type TEXT,
            source_file_size INTEGER,
            source_url TEXT,
            full_text TEXT,
            summary TEXT,
            key_points TEXT DEFAULT '[]',
            keywords TEXT DEFAULT '[]',
            structured_rules TEXT DEFAULT '{}',
            tags TEXT DEFAULT '[]',
            effective_date TEXT,
            expiration_date TEXT,
            last_reviewed_at TEXT,
            reviewed_by TEXT,
            is_active INTEGER DEFAULT 1,
            is_processed INTEGER DEFAULT 0,
            last_processed_at TEXT,
            processing_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Indexes for underwriting_guidelines
        "CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_type ON underwriting_guidelines(guideline_type)",
        "CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_category ON underwriting_guidelines(category)",
        "CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_loan_program ON underwriting_guidelines(loan_program)",
        "CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_active ON underwriting_guidelines(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_investor ON underwriting_guidelines(investor_name)",

        # 2. Guideline Sections table
        """
        CREATE TABLE IF NOT EXISTS guideline_sections (
            id TEXT PRIMARY KEY,
            guideline_id TEXT NOT NULL REFERENCES underwriting_guidelines(id) ON DELETE CASCADE,
            section_number TEXT,
            section_title TEXT,
            page_number INTEGER,
            content TEXT NOT NULL,
            summary TEXT,
            category TEXT,
            topics TEXT DEFAULT '[]',
            position_start INTEGER,
            position_end INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Indexes for guideline_sections
        "CREATE INDEX IF NOT EXISTS ix_guideline_sections_guideline_id ON guideline_sections(guideline_id)",
        "CREATE INDEX IF NOT EXISTS ix_guideline_sections_category ON guideline_sections(category)",
        "CREATE INDEX IF NOT EXISTS ix_guideline_sections_section_number ON guideline_sections(section_number)",
    ]

    # Execute statements
    with engine.connect() as conn:
        for statement in sql_statements:
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                    # Show first 60 chars of statement
                    preview = statement.replace('\n', ' ')[:60]
                    print(f"  OK: {preview}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  Skipped (exists): {statement[:50]}...")
                    else:
                        print(f"  Warning: {e}")
        conn.commit()

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("Tables created:")
    print("  - underwriting_guidelines")
    print("  - guideline_sections")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
