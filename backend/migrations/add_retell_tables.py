"""
Migration: Add Retell AI Tables

Creates tables for Retell AI integration:
- user_retell_config: User API key configuration
- retell_agents: Agent tracking
- retell_phone_numbers: Phone number tracking
- retell_calls: Call records and analytics
"""

import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./perennial_crm.db")


def get_db_path():
    """Extract database file path from URL."""
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.replace("sqlite:///", "")
    return "perennial_crm.db"


def run_migration():
    """Run the migration to add Retell AI tables."""
    db_path = get_db_path()
    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # User Retell Configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_retell_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                retell_api_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: user_retell_config")

        # Retell Agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                retell_agent_id TEXT NOT NULL UNIQUE,
                agent_name TEXT NOT NULL,
                agent_type TEXT DEFAULT 'custom',
                voice_id TEXT,
                llm_id TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_agents")

        # Create index for agent lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_agents_user
            ON retell_agents(user_id)
        """)

        # Retell Phone Numbers
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_phone_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL UNIQUE,
                retell_agent_id TEXT,
                inbound_agent_id TEXT,
                outbound_agent_id TEXT,
                imported BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_phone_numbers")

        # Retell Calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                retell_call_id TEXT NOT NULL UNIQUE,
                retell_agent_id TEXT,

                -- Call details
                to_number TEXT NOT NULL,
                from_number TEXT,
                direction TEXT DEFAULT 'outbound',
                status TEXT DEFAULT 'initiated',

                -- CRM references
                lead_id TEXT,
                loan_id TEXT,
                contact_id TEXT,
                campaign_id TEXT,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP,

                -- Call metrics
                duration_seconds INTEGER,
                disconnection_reason TEXT,

                -- Analysis
                transcript TEXT,
                call_summary TEXT,
                user_sentiment TEXT,
                call_successful BOOLEAN,
                custom_analysis TEXT,

                -- AMD results (if applicable)
                machine_detected BOOLEAN,
                amd_result TEXT,

                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_calls")

        # Create indexes for call lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_calls_user
            ON retell_calls(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_calls_lead
            ON retell_calls(lead_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_calls_agent
            ON retell_calls(retell_agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_calls_status
            ON retell_calls(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retell_calls_created
            ON retell_calls(created_at)
        """)
        print("Created indexes for retell_calls")

        # Retell Call Events (for webhook idempotency)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_call_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                call_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created table: retell_call_events")

        # Retell LLM Configurations (for custom prompts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_llm_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                retell_llm_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                general_prompt TEXT NOT NULL,
                begin_message TEXT,
                tools_config TEXT,
                states_config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_llm_configs")

        conn.commit()
        print("\nMigration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise

    finally:
        conn.close()


def verify_migration():
    """Verify the migration was successful."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = [
        "user_retell_config",
        "retell_agents",
        "retell_phone_numbers",
        "retell_calls",
        "retell_call_events",
        "retell_llm_configs",
    ]

    print("\nVerifying tables...")
    all_exist = True
    for table in tables:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        exists = cursor.fetchone() is not None
        status = "✓" if exists else "✗"
        print(f"  {status} {table}")
        if not exists:
            all_exist = False

    conn.close()

    if all_exist:
        print("\nAll tables verified!")
    else:
        print("\nSome tables are missing!")

    return all_exist


if __name__ == "__main__":
    run_migration()
    verify_migration()
