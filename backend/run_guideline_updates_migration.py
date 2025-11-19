#!/usr/bin/env python3
"""
Run Guideline Updates migration directly
"""
import sys
import os

# Set up path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run migration
from migrations.add_guideline_updates_tables import run_migration

if __name__ == "__main__":
    print("Running Guideline Updates tables migration...")
    success = run_migration()
    if success:
        print("✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("❌ Migration failed!")
        sys.exit(1)
