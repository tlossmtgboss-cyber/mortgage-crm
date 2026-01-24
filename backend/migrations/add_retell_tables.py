"""
Migration: Add Retell AI Tables

Creates tables for Retell AI integration:
- user_retell_config: User API key configuration
- retell_agents: Agent tracking
- retell_phone_numbers: Phone number tracking
- retell_calls: Call records and analytics
- retell_call_events: Webhook deduplication
- retell_llm_configs: Custom LLM configurations

Supports both PostgreSQL and SQLite databases.
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./perennial_crm.db")


def get_db_type():
    """Determine database type from URL."""
    if DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return "sqlite"


def run_migration_postgresql():
    """Run migration for PostgreSQL."""
    import psycopg2
    from urllib.parse import urlparse

    # Parse database URL
    result = urlparse(DATABASE_URL)

    conn = psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        database=result.path[1:],
        user=result.username,
        password=result.password,
        sslmode='require' if 'sslmode' not in DATABASE_URL else None
    )
    cursor = conn.cursor()

    try:
        # User Retell Configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_retell_config (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                retell_api_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_user_retell_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: user_retell_config")

        # Retell Agents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_agents (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                retell_agent_id TEXT NOT NULL UNIQUE,
                agent_name TEXT NOT NULL,
                agent_type TEXT DEFAULT 'custom',
                voice_id TEXT,
                llm_id TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_retell_agents_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
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
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL UNIQUE,
                retell_agent_id TEXT,
                inbound_agent_id TEXT,
                outbound_agent_id TEXT,
                imported BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_retell_phones_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_phone_numbers")

        # Retell Calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_calls (
                id SERIAL PRIMARY KEY,
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

                -- AMD results
                machine_detected BOOLEAN,
                amd_result TEXT,

                CONSTRAINT fk_retell_calls_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_calls")

        # Create indexes for call lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_user ON retell_calls(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_lead ON retell_calls(lead_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_agent ON retell_calls(retell_agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_status ON retell_calls(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_created ON retell_calls(created_at)")
        print("Created indexes for retell_calls")

        # Retell Call Events (for webhook idempotency)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_call_events (
                id SERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                call_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created table: retell_call_events")

        # Retell LLM Configurations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retell_llm_configs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                retell_llm_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                general_prompt TEXT NOT NULL,
                begin_message TEXT,
                tools_config TEXT,
                states_config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_retell_llm_user FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_llm_configs")

        conn.commit()
        print("\nPostgreSQL migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def run_migration_sqlite():
    """Run migration for SQLite."""
    import sqlite3

    # Extract path from sqlite URL
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "")
        # Handle relative path with ./
        if db_path.startswith("./"):
            db_path = db_path[2:]
    else:
        db_path = "perennial_crm.db"

    print(f"Running SQLite migration on: {db_path}")

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
                to_number TEXT NOT NULL,
                from_number TEXT,
                direction TEXT DEFAULT 'outbound',
                status TEXT DEFAULT 'initiated',
                lead_id TEXT,
                loan_id TEXT,
                contact_id TEXT,
                campaign_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                ended_at TIMESTAMP,
                duration_seconds INTEGER,
                disconnection_reason TEXT,
                transcript TEXT,
                call_summary TEXT,
                user_sentiment TEXT,
                call_successful BOOLEAN,
                custom_analysis TEXT,
                machine_detected BOOLEAN,
                amd_result TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("Created table: retell_calls")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_user ON retell_calls(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_lead ON retell_calls(lead_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_agent ON retell_calls(retell_agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_status ON retell_calls(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retell_calls_created ON retell_calls(created_at)")
        print("Created indexes for retell_calls")

        # Retell Call Events
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

        # Retell LLM Configurations
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
        print("\nSQLite migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def run_migration():
    """Run the appropriate migration based on database type."""
    db_type = get_db_type()
    print(f"Database type: {db_type}")
    print(f"Database URL: {DATABASE_URL[:50]}...")

    if db_type == "postgresql":
        run_migration_postgresql()
    else:
        run_migration_sqlite()


def verify_migration():
    """Verify the migration was successful."""
    db_type = get_db_type()

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

    if db_type == "postgresql":
        import psycopg2
        from urllib.parse import urlparse

        result = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            host=result.hostname,
            port=result.port or 5432,
            database=result.path[1:],
            user=result.username,
            password=result.password
        )
        cursor = conn.cursor()

        for table in tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            status = "✓" if exists else "✗"
            print(f"  {status} {table}")
            if not exists:
                all_exist = False

        cursor.close()
        conn.close()
    else:
        import sqlite3

        db_path = DATABASE_URL.replace("sqlite:///", "").replace("./", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

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
