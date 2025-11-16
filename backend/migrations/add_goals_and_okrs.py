"""
Migration: Add goals and OKRs tables

This migration creates tables for:
- User goals (objectives with timeline)
- Goal key results (measurable outcomes)
- Employee self-assessments
- Manager assessments
- Goal-responsibility junction table
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
    """Create goals, key results, assessments, and junction tables"""
    print("\n" + "="*80)
    print("MIGRATION: Add goals and OKRs tables")
    print("="*80 + "\n")

    with engine.begin() as conn:
        # Check if tables already exist
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN (
                'user_goals',
                'goal_key_results',
                'goal_employee_assessments',
                'goal_manager_assessments',
                'goal_responsibilities'
            )
        """))

        existing_tables = [row[0] for row in result.fetchall()]

        # Create user_goals table
        if 'user_goals' not in existing_tables:
            print("Creating user_goals table...")
            conn.execute(text("""
                CREATE TABLE user_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    objective TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    status VARCHAR(50) DEFAULT 'not_started',
                    created_by_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL,
                    CHECK (status IN ('not_started', 'on_track', 'at_risk', 'blocked', 'completed'))
                )
            """))

            # Create indexes
            conn.execute(text("""
                CREATE INDEX idx_goals_user_id ON user_goals(user_id)
            """))

            print("✓ User goals table created")
        else:
            print("✓ User goals table already exists")

        # Create goal_key_results table
        if 'goal_key_results' not in existing_tables:
            print("Creating goal_key_results table...")
            conn.execute(text("""
                CREATE TABLE goal_key_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER NOT NULL,
                    metric VARCHAR(255) NOT NULL,
                    target REAL NOT NULL,
                    current REAL DEFAULT 0,
                    unit VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'not_started',
                    FOREIGN KEY (goal_id) REFERENCES user_goals(id) ON DELETE CASCADE,
                    CHECK (status IN ('not_started', 'on_track', 'at_risk', 'ahead', 'completed'))
                )
            """))

            # Create index
            conn.execute(text("""
                CREATE INDEX idx_key_results_goal_id ON goal_key_results(goal_id)
            """))

            print("✓ Goal key results table created")
        else:
            print("✓ Goal key results table already exists")

        # Create goal_employee_assessments table
        if 'goal_employee_assessments' not in existing_tables:
            print("Creating goal_employee_assessments table...")
            conn.execute(text("""
                CREATE TABLE goal_employee_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER NOT NULL UNIQUE,
                    progress_percent INTEGER,
                    status VARCHAR(50) DEFAULT 'on_track',
                    achievements TEXT,
                    challenges TEXT,
                    support_needed TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (goal_id) REFERENCES user_goals(id) ON DELETE CASCADE,
                    CHECK (status IN ('on_track', 'at_risk', 'blocked')),
                    CHECK (progress_percent >= 0 AND progress_percent <= 100)
                )
            """))

            # Create index
            conn.execute(text("""
                CREATE INDEX idx_employee_assessments_goal_id ON goal_employee_assessments(goal_id)
            """))

            print("✓ Goal employee assessments table created")
        else:
            print("✓ Goal employee assessments table already exists")

        # Create goal_manager_assessments table
        if 'goal_manager_assessments' not in existing_tables:
            print("Creating goal_manager_assessments table...")
            conn.execute(text("""
                CREATE TABLE goal_manager_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER NOT NULL UNIQUE,
                    notes TEXT,
                    updated_by_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (goal_id) REFERENCES user_goals(id) ON DELETE CASCADE,
                    FOREIGN KEY (updated_by_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """))

            # Create index
            conn.execute(text("""
                CREATE INDEX idx_manager_assessments_goal_id ON goal_manager_assessments(goal_id)
            """))

            print("✓ Goal manager assessments table created")
        else:
            print("✓ Goal manager assessments table already exists")

        # Create goal_responsibilities junction table
        if 'goal_responsibilities' not in existing_tables:
            print("Creating goal_responsibilities junction table...")
            conn.execute(text("""
                CREATE TABLE goal_responsibilities (
                    goal_id INTEGER NOT NULL,
                    responsibility_id INTEGER NOT NULL,
                    PRIMARY KEY (goal_id, responsibility_id),
                    FOREIGN KEY (goal_id) REFERENCES user_goals(id) ON DELETE CASCADE,
                    FOREIGN KEY (responsibility_id) REFERENCES user_responsibilities(id) ON DELETE CASCADE
                )
            """))

            print("✓ Goal responsibilities junction table created")
        else:
            print("✓ Goal responsibilities junction table already exists")

        print("\n✓ Migration completed successfully!")
        print("\nCreated:")
        print("  - Table: user_goals")
        print("  - Table: goal_key_results")
        print("  - Table: goal_employee_assessments")
        print("  - Table: goal_manager_assessments")
        print("  - Table: goal_responsibilities")
        print("  - Indexes: idx_goals_user_id, idx_key_results_goal_id, idx_employee_assessments_goal_id, idx_manager_assessments_goal_id")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
