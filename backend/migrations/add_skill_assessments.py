"""
Migration: Add skill assessments table

This migration creates the user_skill_assessments table for tracking
required vs current proficiency levels for user skills.
"""

import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

def run_migration():
    """Create user_skill_assessments table"""
    print("\n" + "="*80)
    print("MIGRATION: Add skill assessments table")
    print("="*80 + "\n")

    with engine.begin() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name = 'user_skill_assessments'
        """))

        existing_table = result.fetchone()

        # Create user_skill_assessments table
        if not existing_table:
            print("Creating user_skill_assessments table...")
            conn.execute(text("""
                CREATE TABLE user_skill_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    skill_id INTEGER NOT NULL,
                    required_proficiency INTEGER NOT NULL,
                    current_proficiency INTEGER DEFAULT 0,
                    assessment_notes TEXT,
                    training_recommendations JSON,
                    assessed_by_id INTEGER,
                    assessed_at TIMESTAMP,
                    next_assessment_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                    FOREIGN KEY (assessed_by_id) REFERENCES users(id) ON DELETE SET NULL,
                    UNIQUE (user_id, skill_id)
                )
            """))

            # Create indexes
            conn.execute(text("""
                CREATE INDEX idx_skill_assessments_user_id ON user_skill_assessments(user_id)
            """))

            conn.execute(text("""
                CREATE INDEX idx_skill_assessments_skill_id ON user_skill_assessments(skill_id)
            """))

            conn.execute(text("""
                CREATE INDEX idx_skill_assessments_next_date ON user_skill_assessments(next_assessment_date)
            """))

            print("✓ User skill assessments table created")
        else:
            print("✓ User skill assessments table already exists")

        print("\n✓ Migration completed successfully!")
        print("\nCreated:")
        print("  - Table: user_skill_assessments")
        print("  - Indexes: idx_skill_assessments_user_id, idx_skill_assessments_skill_id, idx_skill_assessments_next_date")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
