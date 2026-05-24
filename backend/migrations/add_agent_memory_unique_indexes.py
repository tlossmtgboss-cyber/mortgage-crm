"""
Migration: Add partial unique indexes on agent_memories

Creates two partial unique indexes to enforce dedup at the database level:

  ix_agent_mem_active_fact_key
    ON agent_memories (borrower_id, organization_id, fact_key)
    WHERE superseded_by IS NULL AND fact_key IS NOT NULL

  ix_agent_mem_active_content_hash
    ON agent_memories (borrower_id, organization_id, content_hash)
    WHERE superseded_by IS NULL AND content_hash IS NOT NULL

Before creating each index, the migration cleans up any existing duplicate
rows by superseding older entries (keeping the row with the highest id).

Notes:
  - Uses CONCURRENTLY to avoid blocking writes during index build.
  - CONCURRENTLY cannot run inside a transaction, so we use AUTOCOMMIT.
  - Idempotent: checks pg_indexes before attempting creation.

Usage:
    python -m migrations.add_agent_memory_unique_indexes
    # or
    from migrations.add_agent_memory_unique_indexes import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

FACT_KEY_INDEX = "ix_agent_mem_active_fact_key"
CONTENT_HASH_INDEX = "ix_agent_mem_active_content_hash"


def _index_exists(engine, index_name: str) -> bool:
    """Check whether an index already exists in pg_indexes."""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
                {"name": index_name},
            )
            return result.fetchone() is not None
    except Exception as e:
        logger.warning("[MemIdx] Index existence check failed for %s: %s", index_name, e)
        return False


def _clean_fact_key_duplicates(engine) -> int:
    """
    Find active memories with duplicate (borrower_id, organization_id, fact_key)
    where superseded_by IS NULL and fact_key IS NOT NULL.
    Keep the newest one (highest id), supersede the rest.
    Returns the number of rows superseded.
    """
    sql = text("""
        WITH dupes AS (
            SELECT id, borrower_id, organization_id, fact_key,
                   ROW_NUMBER() OVER (
                       PARTITION BY borrower_id, organization_id, fact_key
                       ORDER BY id DESC
                   ) AS rn
            FROM agent_memories
            WHERE superseded_by IS NULL
              AND fact_key IS NOT NULL
        ),
        keeper AS (
            SELECT d1.id AS old_id,
                   (SELECT d2.id FROM dupes d2
                    WHERE d2.borrower_id = d1.borrower_id
                      AND d2.organization_id IS NOT DISTINCT FROM d1.organization_id
                      AND d2.fact_key = d1.fact_key
                      AND d2.rn = 1) AS new_id
            FROM dupes d1
            WHERE d1.rn > 1
        )
        UPDATE agent_memories
        SET superseded_by = keeper.new_id
        FROM keeper
        WHERE agent_memories.id = keeper.old_id
    """)
    try:
        with engine.connect() as conn:
            result = conn.execute(sql)
            conn.commit()
            return result.rowcount
    except Exception as e:
        logger.warning("[MemIdx] fact_key duplicate cleanup failed: %s", e)
        return 0


def _clean_content_hash_duplicates(engine) -> int:
    """
    Find active memories with duplicate (borrower_id, organization_id, content_hash)
    where superseded_by IS NULL and content_hash IS NOT NULL.
    Keep the newest one (highest id), supersede the rest.
    Returns the number of rows superseded.
    """
    sql = text("""
        WITH dupes AS (
            SELECT id, borrower_id, organization_id, content_hash,
                   ROW_NUMBER() OVER (
                       PARTITION BY borrower_id, organization_id, content_hash
                       ORDER BY id DESC
                   ) AS rn
            FROM agent_memories
            WHERE superseded_by IS NULL
              AND content_hash IS NOT NULL
        ),
        keeper AS (
            SELECT d1.id AS old_id,
                   (SELECT d2.id FROM dupes d2
                    WHERE d2.borrower_id = d1.borrower_id
                      AND d2.organization_id IS NOT DISTINCT FROM d1.organization_id
                      AND d2.content_hash = d1.content_hash
                      AND d2.rn = 1) AS new_id
            FROM dupes d1
            WHERE d1.rn > 1
        )
        UPDATE agent_memories
        SET superseded_by = keeper.new_id
        FROM keeper
        WHERE agent_memories.id = keeper.old_id
    """)
    try:
        with engine.connect() as conn:
            result = conn.execute(sql)
            conn.commit()
            return result.rowcount
    except Exception as e:
        logger.warning("[MemIdx] content_hash duplicate cleanup failed: %s", e)
        return 0


def run_migration(engine=None):
    """Create partial unique indexes on agent_memories for dedup enforcement."""
    if engine is None:
        from db import engine as _engine
        engine = _engine

    # Skip for SQLite (no partial indexes with this syntax)
    db_url = str(engine.url)
    if "sqlite" in db_url.lower():
        logger.info("[MemIdx] Skipping — SQLite does not support partial unique indexes")
        return True

    # Check that the agent_memories table exists
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'agent_memories'"
            ))
            if not result.fetchone():
                logger.info("[MemIdx] agent_memories table not found — skipping")
                return True
    except Exception as e:
        logger.warning("[MemIdx] Table check failed: %s", e)

    success = True

    # --- fact_key partial unique index ---
    if _index_exists(engine, FACT_KEY_INDEX):
        logger.info("[MemIdx] Index %s already exists — skipping", FACT_KEY_INDEX)
    else:
        cleaned = _clean_fact_key_duplicates(engine)
        if cleaned:
            logger.info("[MemIdx] Superseded %d duplicate fact_key rows before index creation", cleaned)

        logger.info("[MemIdx] Creating partial unique index %s ...", FACT_KEY_INDEX)
        raw_conn = engine.raw_connection()
        try:
            raw_conn.autocommit = True
            cursor = raw_conn.cursor()
            cursor.execute(
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_mem_active_fact_key "
                "ON agent_memories (borrower_id, organization_id, fact_key) "
                "WHERE superseded_by IS NULL AND fact_key IS NOT NULL"
            )
            cursor.close()
            logger.info("[MemIdx] Index %s created successfully", FACT_KEY_INDEX)
        except Exception as e:
            logger.error("[MemIdx] Index %s creation failed: %s", FACT_KEY_INDEX, e)
            success = False
        finally:
            raw_conn.close()

    # --- content_hash partial unique index ---
    if _index_exists(engine, CONTENT_HASH_INDEX):
        logger.info("[MemIdx] Index %s already exists — skipping", CONTENT_HASH_INDEX)
    else:
        cleaned = _clean_content_hash_duplicates(engine)
        if cleaned:
            logger.info("[MemIdx] Superseded %d duplicate content_hash rows before index creation", cleaned)

        logger.info("[MemIdx] Creating partial unique index %s ...", CONTENT_HASH_INDEX)
        raw_conn = engine.raw_connection()
        try:
            raw_conn.autocommit = True
            cursor = raw_conn.cursor()
            cursor.execute(
                "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_mem_active_content_hash "
                "ON agent_memories (borrower_id, organization_id, content_hash) "
                "WHERE superseded_by IS NULL AND content_hash IS NOT NULL"
            )
            cursor.close()
            logger.info("[MemIdx] Index %s created successfully", CONTENT_HASH_INDEX)
        except Exception as e:
            logger.error("[MemIdx] Index %s creation failed: %s", CONTENT_HASH_INDEX, e)
            success = False
        finally:
            raw_conn.close()

    return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ok = run_migration()
    if ok:
        print("Agent memory unique index migration completed successfully")
    else:
        print("Agent memory unique index migration failed")
