#!/usr/bin/env python3
"""
Add Permanent Conversation Memory Tables
Stores all AI conversations forever for cross-session memory
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine, Base
from conversation_memory_models import AIConversationMemory, AIActionHistory


def create_tables():
    """Create permanent conversation memory tables"""

    print("=" * 80)
    print("PERMANENT CONVERSATION MEMORY MIGRATION")
    print("=" * 80)
    print()

    tables_to_create = [
        AIConversationMemory.__table__,
        AIActionHistory.__table__,
    ]

    print("Creating the following tables:")
    for table in tables_to_create:
        print(f"  - {table.name}")
    print()

    try:
        # Create all tables
        Base.metadata.create_all(engine, tables=tables_to_create)

        # Create full-text search index
        with engine.connect() as conn:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conv_search
                ON ai_conversation_memory
                USING gin(to_tsvector('english', content))
            """)
            conn.commit()

        print("Successfully created permanent conversation memory tables!")
        print()
        print("Tables created:")
        print("  1. ai_conversation_memory - Stores every message forever")
        print("  2. ai_action_history - Stores all actions taken")
        print()
        print("Indexes created:")
        print("  - idx_conv_user_date - Fast user timeline queries")
        print("  - idx_conv_session - Fast session message retrieval")
        print("  - idx_conv_search - Full-text search on content")
        print("  - idx_action_user_date - Fast action history queries")
        print()
        print("AI will now remember every conversation forever!")

    except Exception as e:
        print(f"Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    create_tables()
