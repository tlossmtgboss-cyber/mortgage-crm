"""
Migration: Add responsibilities and skills tables

This migration creates tables for:
- Skills library (company-wide skill catalog)
- User responsibilities (job responsibilities with time allocation)
- Responsibility-skill junction table (many-to-many relationship)
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
    """Create skills, responsibilities, and junction tables"""
    print("\n" + "="*80)
    print("MIGRATION: Add responsibilities and skills tables")
    print("="*80 + "\n")

    with engine.begin() as conn:
        # Check if tables already exist
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('skills', 'user_responsibilities', 'responsibility_skills')
        """))

        existing_tables = [row[0] for row in result.fetchall()]

        # Create skills table
        if 'skills' not in existing_tables:
            print("Creating skills table...")
            conn.execute(text("""
                CREATE TABLE skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    category VARCHAR(100),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create index on name
            conn.execute(text("""
                CREATE INDEX idx_skills_name ON skills(name)
            """))

            print("✓ Skills table created")
        else:
            print("✓ Skills table already exists")

        # Create user_responsibilities table
        if 'user_responsibilities' not in existing_tables:
            print("Creating user_responsibilities table...")
            conn.execute(text("""
                CREATE TABLE user_responsibilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    ownership VARCHAR(50) NOT NULL,
                    time_allocation INTEGER,
                    priority VARCHAR(50) NOT NULL,
                    effective_date DATE NOT NULL,
                    end_date DATE,
                    archived BOOLEAN DEFAULT 0,
                    display_order INTEGER DEFAULT 0,
                    created_by_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """))

            # Create indexes
            conn.execute(text("""
                CREATE INDEX idx_responsibilities_user_id ON user_responsibilities(user_id)
            """))

            conn.execute(text("""
                CREATE INDEX idx_responsibilities_archived ON user_responsibilities(archived)
            """))

            conn.execute(text("""
                CREATE INDEX idx_responsibilities_display_order ON user_responsibilities(display_order)
            """))

            print("✓ User responsibilities table created")
        else:
            print("✓ User responsibilities table already exists")

        # Create responsibility_skills junction table
        if 'responsibility_skills' not in existing_tables:
            print("Creating responsibility_skills junction table...")
            conn.execute(text("""
                CREATE TABLE responsibility_skills (
                    responsibility_id INTEGER NOT NULL,
                    skill_id INTEGER NOT NULL,
                    PRIMARY KEY (responsibility_id, skill_id),
                    FOREIGN KEY (responsibility_id) REFERENCES user_responsibilities(id) ON DELETE CASCADE,
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
                )
            """))

            print("✓ Responsibility skills junction table created")
        else:
            print("✓ Responsibility skills junction table already exists")

        # Insert some default skills
        print("\nInserting default skills...")
        default_skills = [
            ('Client Communication', 'soft_skill'),
            ('FHA/VA Loan Processing', 'technical'),
            ('Underwriting', 'technical'),
            ('Compliance', 'technical'),
            ('Sales', 'soft_skill'),
            ('CRM Management', 'technical'),
            ('Lead Generation', 'soft_skill'),
            ('Document Review', 'technical'),
            ('Risk Assessment', 'technical'),
            ('Team Leadership', 'soft_skill'),
            ('Problem Solving', 'soft_skill'),
            ('Time Management', 'soft_skill')
        ]

        for skill_name, category in default_skills:
            # Check if skill already exists
            result = conn.execute(text("""
                SELECT id FROM skills WHERE name = :name
            """), {"name": skill_name})

            if not result.fetchone():
                conn.execute(text("""
                    INSERT INTO skills (name, category)
                    VALUES (:name, :category)
                """), {"name": skill_name, "category": category})
                print(f"  ✓ Added skill: {skill_name}")
            else:
                print(f"  - Skill already exists: {skill_name}")

        print("\n✓ Migration completed successfully!")
        print("\nCreated:")
        print("  - Table: skills")
        print("  - Table: user_responsibilities")
        print("  - Table: responsibility_skills")
        print("  - Indexes: idx_skills_name, idx_responsibilities_user_id, idx_responsibilities_archived, idx_responsibilities_display_order")
        print(f"  - Default skills: {len(default_skills)} skills added")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
