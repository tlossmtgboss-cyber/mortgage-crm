#!/usr/bin/env python3
"""
Add partner_category column to production database
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect

# Get DATABASE_URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Usage: DATABASE_URL='your_db_url' python add_partner_category_column.py")
    sys.exit(1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

# Check if partner_category column exists
inspector = inspect(engine)
columns = [col['name'] for col in inspector.get_columns('referral_partners')]

print(f"Current columns in referral_partners table:")
for col in columns:
    print(f"  - {col}")

if 'partner_category' in columns:
    print("\n✅ partner_category column already exists!")

    # Update any NULL values to 'individual'
    with engine.connect() as conn:
        result = conn.execute(text("UPDATE referral_partners SET partner_category = 'individual' WHERE partner_category IS NULL"))
        conn.commit()
        if result.rowcount > 0:
            print(f"✅ Updated {result.rowcount} records with default partner_category='individual'")
        else:
            print("✅ All records already have partner_category values")
else:
    print("\n❌ partner_category column is missing!")
    print("Adding partner_category column...")

    # Add the column
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE referral_partners ADD COLUMN partner_category VARCHAR DEFAULT 'individual'"))
        conn.commit()

    print("✅ Column added successfully!")

    # Verify
    inspector = inspect(engine)
    new_columns = [col['name'] for col in inspector.get_columns('referral_partners')]
    if 'partner_category' in new_columns:
        print("✅ Verified: partner_category column now exists")
    else:
        print("❌ Failed to add column")
        sys.exit(1)

print("\n✅ Migration completed successfully!")
