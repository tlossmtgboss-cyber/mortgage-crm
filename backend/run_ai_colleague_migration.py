#!/usr/bin/env python3
"""
Run AI Colleague Performance Tracking migration for Mission Control
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add migrations to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'migrations'))

from add_ai_colleague_tracking import run_migration

if __name__ == "__main__":
    print("=" * 70)
    print("AI Colleague Performance Tracking - Database Migration")
    print("=" * 70)
    print()
    print("This will create the following tables:")
    print("  ✓ ai_colleague_actions - Core action tracking")
    print("  ✓ ai_learning_metrics - Performance metrics")
    print("  ✓ ai_performance_daily - Daily rollups for dashboard")
    print("  ✓ ai_journey_insights - Cross-journey pattern detection")
    print("  ✓ ai_health_score - Overall health calculations")
    print()
    print("Plus views and functions for Mission Control dashboard")
    print()

    # Verify DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("❌ Error: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL in your .env file")
        sys.exit(1)

    print("🔄 Starting migration...")
    print()

    success = run_migration()

    if success:
        print()
        print("=" * 70)
        print("🎉 Migration completed successfully!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Add logging to existing AI agents (Smart AI, SMS Agent, etc.)")
        print("  2. Create Mission Control API endpoints in FastAPI")
        print("  3. Build Mission Control React dashboard")
        print("  4. Wire up real-time tracking")
        print("  5. Deploy and test Mission Control")
        print()
    else:
        print()
        print("❌ Migration failed. Please check the error messages above.")
        sys.exit(1)
