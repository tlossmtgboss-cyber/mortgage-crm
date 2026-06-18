"""
Recruiting Chatbot Tables Migration

Creates:
  recruit_kb_documents  — documents uploaded by admins for the knowledge base
  recruit_kb_chunks     — text chunks with pgvector embeddings (384-dim)
  recruit_chat_sessions — candidate chat sessions
  recruit_chat_messages — per-message log

All tables use the app.current_tenant GUC pattern for RLS (same as mm_* tables).
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLES = [
    "recruit_kb_documents",
    "recruit_kb_chunks",
    "recruit_chat_sessions",
    "recruit_chat_messages",
]


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t AND table_schema = 'public'"
        ),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _policy_exists(conn, table_name: str, policy_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_policies WHERE tablename = :t AND policyname = :p"),
        {"t": table_name, "p": policy_name},
    )
    return result.fetchone() is not None


def _apply_rls(conn, table_name: str) -> None:
    policy_name = f"{table_name}_tenant_isolation"

    conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))

    if _policy_exists(conn, table_name, policy_name):
        conn.execute(text(f"DROP POLICY {policy_name} ON {table_name}"))

    conn.execute(text(f"""
        CREATE POLICY {policy_name} ON {table_name}
        FOR ALL
        USING (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
        WITH CHECK (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
    """))
    logger.info("[RLS] Tenant isolation policy applied to %s", table_name)


def run_migration(engine=None) -> None:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] add_recruit_chatbot_tables — not PostgreSQL")
        return

    logger.info("Running add_recruit_chatbot_tables migration...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        # Ensure pgvector extension is available
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("pgvector extension ready")
        except Exception as e:
            logger.warning("pgvector extension: %s", e)

        # recruit_kb_documents
        if not _table_exists(conn, "recruit_kb_documents"):
            conn.execute(text("""
                CREATE TABLE recruit_kb_documents (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    filename VARCHAR(500) NOT NULL,
                    original_filename VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    file_size_bytes INTEGER,
                    storage_path TEXT,
                    raw_text TEXT,
                    status VARCHAR(30) DEFAULT 'processing',
                    chunk_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            logger.info("✅ recruit_kb_documents created")
        else:
            logger.info("[SKIP] recruit_kb_documents already exists")

        # recruit_kb_chunks
        if not _table_exists(conn, "recruit_kb_chunks"):
            conn.execute(text("""
                CREATE TABLE recruit_kb_chunks (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER REFERENCES recruit_kb_documents(id) ON DELETE CASCADE,
                    organization_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(384),
                    token_count INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_recruit_kb_chunks_org "
                "ON recruit_kb_chunks(organization_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_recruit_kb_chunks_doc "
                "ON recruit_kb_chunks(document_id)"
            ))
            # IVFFlat index — requires at least one row to train; created here
            # but will be rebuilt automatically as data grows.
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_recruit_kb_chunks_embedding
                    ON recruit_kb_chunks
                    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)
                """))
            except Exception as e:
                logger.warning("IVFFlat index (requires data to train): %s", e)
            logger.info("✅ recruit_kb_chunks created")
        else:
            logger.info("[SKIP] recruit_kb_chunks already exists")

        # recruit_chat_sessions
        if not _table_exists(conn, "recruit_chat_sessions"):
            conn.execute(text("""
                CREATE TABLE recruit_chat_sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    visitor_id VARCHAR(64),
                    candidate_id INTEGER,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    last_message_at TIMESTAMPTZ DEFAULT NOW(),
                    message_count INTEGER DEFAULT 0,
                    collected_name VARCHAR(200),
                    collected_email VARCHAR(200),
                    collected_phone VARCHAR(50),
                    metadata JSONB DEFAULT '{}'
                )
            """))
            logger.info("✅ recruit_chat_sessions created")
        else:
            logger.info("[SKIP] recruit_chat_sessions already exists")

        # recruit_chat_messages
        if not _table_exists(conn, "recruit_chat_messages"):
            conn.execute(text("""
                CREATE TABLE recruit_chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(64) REFERENCES recruit_chat_sessions(id) ON DELETE CASCADE,
                    organization_id INTEGER NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_recruit_chat_messages_session "
                "ON recruit_chat_messages(session_id)"
            ))
            logger.info("✅ recruit_chat_messages created")
        else:
            logger.info("[SKIP] recruit_chat_messages already exists")

        # Apply RLS to all four tables
        # recruit_chat_sessions uses id (VARCHAR) as PK, no organization_id on session row
        # — apply policy to tables that have organization_id
        rls_tables = [
            "recruit_kb_documents",
            "recruit_kb_chunks",
            "recruit_chat_messages",
        ]
        for table in rls_tables:
            try:
                _apply_rls(conn, table)
            except Exception as e:
                err = str(e).lower()
                if "already exists" in err:
                    logger.info("[SKIP] RLS policy already exists on %s", table)
                else:
                    logger.warning("[WARN] RLS on %s: %s", table, e)

        # recruit_chat_sessions — RLS keyed on organization_id
        try:
            _apply_rls(conn, "recruit_chat_sessions")
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err:
                logger.info("[SKIP] RLS policy already exists on recruit_chat_sessions")
            else:
                logger.warning("[WARN] RLS on recruit_chat_sessions: %s", e)

    logger.info("add_recruit_chatbot_tables migration complete")


def rollback(engine=None) -> None:
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] rollback — not PostgreSQL")
        return

    logger.info("Rolling back add_recruit_chatbot_tables...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        for table in reversed(TABLES):
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                logger.info("[ROLLBACK] Dropped %s", table)
            except Exception as e:
                logger.warning("[ROLLBACK] %s: %s", table, e)

    logger.info("add_recruit_chatbot_tables rollback complete")


if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        run_migration()
    sys.exit(0)
