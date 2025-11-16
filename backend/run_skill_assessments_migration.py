#!/usr/bin/env python3
"""
Runner script for skill assessments migration
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Set default DATABASE_URL if not set (for local testing)
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'sqlite:///./mortgage_crm.db'

# Import and run the migration
from migrations.add_skill_assessments import run_migration

if __name__ == "__main__":
    print("Skill Assessments Migration Runner")
    print("=" * 80)

    try:
        run_migration()
        print("\n✓ Migration completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
