"""
Database Migration Script
Creates estimate parser cache, failures, and comparisons tables

Run with: python migrations/003_estimate_parser_cache.py
Requires: DATABASE_URL environment variable pointing to PostgreSQL
"""

import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

# Replace postgres:// with postgresql:// (Railway compatibility)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def check_table_exists(conn, table_name):
    """Check if a table exists in the database"""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def create_estimate_parse_cache(conn):
    """Create estimate_parse_cache table"""
    if check_table_exists(conn, "estimate_parse_cache"):
        print("  ✓ estimate_parse_cache already exists")
        return False

    print("  Creating estimate_parse_cache...")
    conn.execute(text("""
        CREATE TABLE estimate_parse_cache (
            doc_hash VARCHAR(64) PRIMARY KEY,
            parsed_json JSONB NOT NULL,
            confidence_score NUMERIC(3, 2),
            needs_review BOOLEAN DEFAULT FALSE,
            source_type VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW(),
            accessed_at TIMESTAMP DEFAULT NOW(),
            access_count INTEGER DEFAULT 1
        )
    """))

    conn.execute(text("""
        CREATE INDEX idx_estimate_cache_created ON estimate_parse_cache (created_at)
    """))
    conn.execute(text("""
        CREATE INDEX idx_estimate_cache_needs_review ON estimate_parse_cache (needs_review) WHERE needs_review = true
    """))
    conn.execute(text("""
        CREATE INDEX idx_estimate_cache_source_type ON estimate_parse_cache (source_type)
    """))

    print("  ✓ estimate_parse_cache created")
    return True


def create_estimate_parse_failures(conn):
    """Create estimate_parse_failures table"""
    if check_table_exists(conn, "estimate_parse_failures"):
        print("  ✓ estimate_parse_failures already exists")
        return False

    print("  Creating estimate_parse_failures...")
    conn.execute(text("""
        CREATE TABLE estimate_parse_failures (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id UUID NOT NULL,
            doc_hash VARCHAR(64) NOT NULL,
            error_stage VARCHAR(50) NOT NULL,
            error_message TEXT,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))

    conn.execute(text("""
        CREATE INDEX idx_failures_created ON estimate_parse_failures (created_at)
    """))
    conn.execute(text("""
        CREATE INDEX idx_failures_stage ON estimate_parse_failures (error_stage)
    """))
    conn.execute(text("""
        CREATE INDEX idx_failures_doc_hash ON estimate_parse_failures (doc_hash)
    """))

    print("  ✓ estimate_parse_failures created")
    return True


def create_estimate_comparisons(conn):
    """Create estimate_comparisons table"""
    if check_table_exists(conn, "estimate_comparisons"):
        print("  ✓ estimate_comparisons already exists")
        return False

    print("  Creating estimate_comparisons...")
    conn.execute(text("""
        CREATE TABLE estimate_comparisons (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id INTEGER,
            session_id VARCHAR(100),
            estimate_a_hash VARCHAR(64) NOT NULL,
            estimate_b_hash VARCHAR(64) NOT NULL,
            winner VARCHAR(1),
            winner_reason VARCHAR(200),
            savings_amount NUMERIC(12, 2),
            comparison_data JSONB,
            converted BOOLEAN DEFAULT FALSE,
            converted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT fk_estimate_a FOREIGN KEY (estimate_a_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE,
            CONSTRAINT fk_estimate_b FOREIGN KEY (estimate_b_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
        )
    """))

    conn.execute(text("""
        CREATE INDEX idx_comparisons_user ON estimate_comparisons (user_id)
    """))
    conn.execute(text("""
        CREATE INDEX idx_comparisons_created ON estimate_comparisons (created_at)
    """))
    conn.execute(text("""
        CREATE INDEX idx_comparisons_converted ON estimate_comparisons (converted)
    """))

    print("  ✓ estimate_comparisons created")
    return True


def run_migration():
    """Run the migration"""
    print("\n=== Estimate Parser Cache Migration ===\n")

    with engine.connect() as conn:
        try:
            created_count = 0

            # Create tables in order (dependencies)
            if create_estimate_parse_cache(conn):
                created_count += 1

            if create_estimate_parse_failures(conn):
                created_count += 1

            if create_estimate_comparisons(conn):
                created_count += 1

            conn.commit()

            print(f"\n✓ Migration complete! ({created_count} tables created)")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    run_migration()
