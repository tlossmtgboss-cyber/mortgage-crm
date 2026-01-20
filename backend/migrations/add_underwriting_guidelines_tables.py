"""
Migration: Add Underwriting Guidelines Tables

This migration creates tables for storing and managing underwriting guidelines
that the AI Underwriter agent can reference:
- underwriting_guidelines: Store uploaded guideline documents
- guideline_sections: Store sections for granular searching

Run with: python -m migrations.add_underwriting_guidelines_tables
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from sqlalchemy import text


def run_migration():
    """Run the underwriting guidelines migration."""
    print("=" * 60)
    print("Underwriting Guidelines Tables Migration")
    print("=" * 60)

    sql_statements = """
    -- =============================================================================
    -- UNDERWRITING GUIDELINES TABLES
    -- =============================================================================

    -- 1. Underwriting Guidelines - Store uploaded guideline documents
    CREATE TABLE IF NOT EXISTS underwriting_guidelines (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        -- Basic info
        name VARCHAR(500) NOT NULL,
        description TEXT,
        version VARCHAR(50),

        -- Classification
        guideline_type VARCHAR(50) NOT NULL,
        category VARCHAR(50),
        loan_program VARCHAR(50) DEFAULT 'all',
        investor_name VARCHAR(200),

        -- Source file
        source_file_name VARCHAR(500),
        source_file_path VARCHAR(1000),
        source_file_type VARCHAR(20),
        source_file_size INTEGER,
        source_url VARCHAR(1000),

        -- Content
        full_text TEXT,
        summary TEXT,
        key_points JSONB DEFAULT '[]'::jsonb,
        keywords JSONB DEFAULT '[]'::jsonb,

        -- Structured rules (for quick lookups)
        structured_rules JSONB DEFAULT '{}'::jsonb,

        -- Metadata
        tags JSONB DEFAULT '[]'::jsonb,
        effective_date DATE,
        expiration_date DATE,
        last_reviewed_at TIMESTAMPTZ,
        reviewed_by UUID,

        -- Status
        is_active BOOLEAN DEFAULT true,
        is_processed BOOLEAN DEFAULT false,
        last_processed_at TIMESTAMPTZ,
        processing_notes TEXT,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Create indexes for common queries
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_type
        ON underwriting_guidelines(guideline_type);
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_category
        ON underwriting_guidelines(category);
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_loan_program
        ON underwriting_guidelines(loan_program);
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_active
        ON underwriting_guidelines(is_active);
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_investor
        ON underwriting_guidelines(investor_name);

    -- Full text search index on key fields
    CREATE INDEX IF NOT EXISTS ix_underwriting_guidelines_search
        ON underwriting_guidelines USING gin(to_tsvector('english',
            COALESCE(name, '') || ' ' ||
            COALESCE(description, '') || ' ' ||
            COALESCE(full_text, '')
        ));

    -- 2. Guideline Sections - For granular searching
    CREATE TABLE IF NOT EXISTS guideline_sections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        guideline_id UUID NOT NULL REFERENCES underwriting_guidelines(id) ON DELETE CASCADE,

        -- Section identification
        section_number VARCHAR(50),
        section_title VARCHAR(500),
        page_number INTEGER,

        -- Content
        content TEXT NOT NULL,
        summary TEXT,

        -- Classification
        category VARCHAR(50),
        topics JSONB DEFAULT '[]'::jsonb,

        -- Position in document
        position_start INTEGER,
        position_end INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Create indexes for section queries
    CREATE INDEX IF NOT EXISTS ix_guideline_sections_guideline_id
        ON guideline_sections(guideline_id);
    CREATE INDEX IF NOT EXISTS ix_guideline_sections_category
        ON guideline_sections(category);
    CREATE INDEX IF NOT EXISTS ix_guideline_sections_section_number
        ON guideline_sections(section_number);

    -- Full text search on section content
    CREATE INDEX IF NOT EXISTS ix_guideline_sections_search
        ON guideline_sections USING gin(to_tsvector('english',
            COALESCE(section_title, '') || ' ' || COALESCE(content, '')
        ));

    -- =============================================================================
    -- MIGRATION COMPLETE
    -- =============================================================================
    """

    # Execute statements
    with engine.connect() as conn:
        for statement in sql_statements.split(";"):
            statement = statement.strip()
            if statement and not statement.startswith("--"):
                try:
                    conn.execute(text(statement))
                    print(f"  Executed: {statement[:60]}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  Skipped (exists): {statement[:60]}...")
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
