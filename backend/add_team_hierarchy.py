#!/usr/bin/env python3
"""
Migration script to add team hierarchy support to referral_partners table
Adds parent_team_id column to enable team → member relationships
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set!")
    print("   Set it with: export DATABASE_URL='your_database_url'")
    exit(1)

# Create engine
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def add_team_hierarchy():
    """Add parent_team_id column to referral_partners table"""

    session = Session()

    try:
        print("🔧 Adding team hierarchy support...")

        # Check if column already exists
        result = session.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='referral_partners'
            AND column_name='parent_team_id';
        """))

        if result.fetchone():
            print("✅ parent_team_id column already exists!")
            return

        # Add parent_team_id column
        print("   Adding parent_team_id column...")
        session.execute(text("""
            ALTER TABLE referral_partners
            ADD COLUMN parent_team_id INTEGER REFERENCES referral_partners(id);
        """))

        session.commit()

        print("✅ Successfully added team hierarchy support!")
        print("\n📋 What you can do now:")
        print("   1. Create a Team Partner (partner_category='team')")
        print("   2. Add Individual Partners with parent_team_id pointing to the team")
        print("   3. Use GET /api/v1/referral-partners/{team_id}/members to list team members")
        print("\n   Example:")
        print("   - Keller Williams Team (team, ID=1)")
        print("     ├── Sarah Johnson (individual, parent_team_id=1)")
        print("     ├── Mike Roberts (individual, parent_team_id=1)")
        print("     └── Lisa Chen (individual, parent_team_id=1)")

    except Exception as e:
        session.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    add_team_hierarchy()
