"""
Add Agent Memory Tables

Creates three tables for the AI agent memory persistence system:
  - agent_conversations: Conversation session summaries
  - agent_memories: Individual facts, preferences, and context snippets
  - agent_contexts: Lightweight key-value store for cross-session state

Usage:
    python -m migrations.add_agent_memory_tables
    # or
    from migrations.add_agent_memory_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create agent memory tables and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()
    is_postgres = "postgresql" in database_url.lower() or "postgres" in database_url.lower()

    with engine.connect() as conn:
        # ---------------------------------------------------------------
        # 1. agent_conversations
        # ---------------------------------------------------------------
        logger.info("Creating agent_conversations table...")
        try:
            if is_postgres:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_conversations (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        agent_role VARCHAR(100) NOT NULL,
                        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        ended_at TIMESTAMP,
                        summary TEXT,
                        key_points JSONB,
                        message_count INTEGER DEFAULT 0
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        agent_role VARCHAR(100) NOT NULL,
                        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        ended_at TIMESTAMP,
                        summary TEXT,
                        key_points TEXT,
                        message_count INTEGER DEFAULT 0
                    )
                """))
            logger.info("agent_conversations table created/verified")
        except Exception as e:
            logger.warning("agent_conversations table creation: %s", e)

        # Indexes for agent_conversations
        for idx_name, idx_sql in [
            (
                "ix_agent_conv_user_org",
                "CREATE INDEX IF NOT EXISTS ix_agent_conv_user_org ON agent_conversations (user_id, organization_id)",
            ),
            (
                "ix_agent_conv_role",
                "CREATE INDEX IF NOT EXISTS ix_agent_conv_role ON agent_conversations (agent_role)",
            ),
            (
                "ix_agent_conv_started",
                "CREATE INDEX IF NOT EXISTS ix_agent_conv_started ON agent_conversations (started_at)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("Index %s: %s", idx_name, e)

        # ---------------------------------------------------------------
        # 2. agent_memories
        # ---------------------------------------------------------------
        logger.info("Creating agent_memories table...")
        try:
            if is_postgres:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_memories (
                        id SERIAL PRIMARY KEY,
                        conversation_id INTEGER REFERENCES agent_conversations(id) ON DELETE SET NULL,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        memory_type VARCHAR(50) NOT NULL DEFAULT 'fact',
                        key VARCHAR(255) NOT NULL,
                        value TEXT NOT NULL,
                        confidence DOUBLE PRECISION DEFAULT 1.0,
                        agent_role VARCHAR(100),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMP
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER REFERENCES agent_conversations(id) ON DELETE SET NULL,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        memory_type VARCHAR(50) NOT NULL DEFAULT 'fact',
                        key VARCHAR(255) NOT NULL,
                        value TEXT NOT NULL,
                        confidence REAL DEFAULT 1.0,
                        agent_role VARCHAR(100),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    )
                """))
            logger.info("agent_memories table created/verified")
        except Exception as e:
            logger.warning("agent_memories table creation: %s", e)

        # Indexes for agent_memories
        for idx_name, idx_sql in [
            (
                "ix_agent_mem_user_org",
                "CREATE INDEX IF NOT EXISTS ix_agent_mem_user_org ON agent_memories (user_id, organization_id)",
            ),
            (
                "ix_agent_mem_type",
                "CREATE INDEX IF NOT EXISTS ix_agent_mem_type ON agent_memories (memory_type)",
            ),
            (
                "ix_agent_mem_key",
                "CREATE INDEX IF NOT EXISTS ix_agent_mem_key ON agent_memories (key)",
            ),
            (
                "ix_agent_mem_expires",
                "CREATE INDEX IF NOT EXISTS ix_agent_mem_expires ON agent_memories (expires_at)",
            ),
            (
                "ix_agent_mem_conv",
                "CREATE INDEX IF NOT EXISTS ix_agent_mem_conv ON agent_memories (conversation_id)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("Index %s: %s", idx_name, e)

        # ---------------------------------------------------------------
        # 3. agent_contexts
        # ---------------------------------------------------------------
        logger.info("Creating agent_contexts table...")
        try:
            if is_postgres:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_contexts (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        context_key VARCHAR(255) NOT NULL,
                        context_value TEXT,
                        last_updated TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS agent_contexts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        context_key VARCHAR(255) NOT NULL,
                        context_value TEXT,
                        last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            logger.info("agent_contexts table created/verified")
        except Exception as e:
            logger.warning("agent_contexts table creation: %s", e)

        # Indexes for agent_contexts
        for idx_name, idx_sql in [
            (
                "ix_agent_ctx_user_org",
                "CREATE INDEX IF NOT EXISTS ix_agent_ctx_user_org ON agent_contexts (user_id, organization_id)",
            ),
            (
                "ix_agent_ctx_key",
                "CREATE INDEX IF NOT EXISTS ix_agent_ctx_key ON agent_contexts (context_key)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.debug("Index %s: %s", idx_name, e)

        # ---------------------------------------------------------------
        # Commit
        # ---------------------------------------------------------------
        conn.commit()
        logger.info("Agent memory tables migration complete")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed")
