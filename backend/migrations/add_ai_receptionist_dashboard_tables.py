#!/usr/bin/env python3
"""
Create AI Receptionist Dashboard Tables
Creates tables for tracking activity, metrics, skills, errors, and conversations
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine, Base
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistMetricsDaily,
    AIReceptionistSkill,
    AIReceptionistError,
    AIReceptionistSystemHealth,
    AIReceptionistConversation
)


def create_tables():
    """Create all AI Receptionist Dashboard tables"""

    print("=" * 80)
    print("AI RECEPTIONIST DASHBOARD TABLES MIGRATION")
    print("=" * 80)
    print()

    tables_to_create = [
        AIReceptionistActivity.__table__,
        AIReceptionistMetricsDaily.__table__,
        AIReceptionistSkill.__table__,
        AIReceptionistError.__table__,
        AIReceptionistSystemHealth.__table__,
        AIReceptionistConversation.__table__,
    ]

    print("Creating the following tables:")
    for table in tables_to_create:
        print(f"  - {table.name}")
    print()

    try:
        # Create all tables
        Base.metadata.create_all(engine, tables=tables_to_create)

        print("✅ Successfully created all AI Receptionist Dashboard tables!")
        print()
        print("Tables created:")
        print("  1. ai_receptionist_activity - Real-time activity feed")
        print("  2. ai_receptionist_metrics_daily - Daily aggregated metrics")
        print("  3. ai_receptionist_skills - Skill performance tracking")
        print("  4. ai_receptionist_errors - Error logging and diagnostics")
        print("  5. ai_receptionist_system_health - System health monitoring")
        print("  6. ai_receptionist_conversations - Full conversation transcripts")
        print()
        print("🎉 Dashboard is now ready to use!")

    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    create_tables()
