"""
Migration: Add HNSW index on agent_memories.embedding

Creates an approximate-nearest-neighbor index using the HNSW algorithm
for the vector(1536) embedding column on agent_memories.  This replaces
sequential scans for cosine-similarity queries (the <=> operator) used
by the Aria memory retrieval service.

Index: ix_agent_mem_embedding_hnsw
  ON agent_memories USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64)

Notes:
  - Uses CONCURRENTLY to avoid blocking writes during index build.
  - CONCURRENTLY cannot run inside a transaction, so we use AUTOCOMMIT.
  - Idempotent: checks pg_indexes before attempting creation.

Usage:
    python -m migrations.add_hnsw_index_agent_memories
    # or
    from migrations.add_hnsw_index_agent_memories import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

INDEX_NAME = "ix_agent_mem_embedding_hnsw"


def run_migration(engine=None):
    """Create HNSW index on agent_memories.embedding for cosine similarity."""
    if engine is None:
        from db import engine as _engine
        engine = _engine

    # Skip for SQLite (no pgvector support)
    db_url = str(engine.url)
    if "sqlite" in db_url.lower():
        logger.info("[HNSW] Skipping — SQLite does not support pgvector")
        return True

    # Ensure pgvector extension exists
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        logger.info("[HNSW] pgvector extension verified")
    except Exception as e:
        logger.warning("[HNSW] pgvector extension check: %s", e)

    # Check if index already exists
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE indexname = :name"
            ), {"name": INDEX_NAME})
            if result.fetchone():
                logger.info("[HNSW] Index %s already exists — skipping", INDEX_NAME)
                return True
    except Exception as e:
        logger.warning("[HNSW] Index existence check failed: %s", e)

    # Check that the embedding column actually exists
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'agent_memories' AND column_name = 'embedding'"
            ))
            if not result.fetchone():
                logger.info("[HNSW] embedding column not found on agent_memories — skipping")
                return True
    except Exception as e:
        logger.warning("[HNSW] Column check failed: %s", e)

    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    # Use a raw connection with autocommit enabled.
    logger.info("[HNSW] Creating HNSW index on agent_memories.embedding (this may take a moment)...")
    raw_conn = engine.raw_connection()
    try:
        raw_conn.autocommit = True
        cursor = raw_conn.cursor()
        cursor.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_mem_embedding_hnsw "
            "ON agent_memories USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        cursor.close()
        logger.info("[HNSW] Index %s created successfully", INDEX_NAME)
        return True
    except Exception as e:
        logger.warning("[HNSW] Index creation failed: %s", e)
        return False
    finally:
        raw_conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("HNSW index migration completed successfully")
    else:
        print("HNSW index migration failed")
