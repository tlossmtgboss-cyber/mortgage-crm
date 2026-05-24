"""
Migration: Add pgvector support to guideline_sections and ai_knowledge_base

Changes:
  1. Enable pgvector extension
  2. Convert guideline_sections.content_embedding from real[] to vector(1536)
  3. Add metadata columns to guideline_sections: embedding_model, token_count, chunk_hash
  4. Add columns to underwriting_guidelines: embedding_status, chunk_count, overlay_priority
  5. Add content_embedding, embedding_model, chunk_hash to ai_knowledge_base
  6. Create HNSW indexes for cosine similarity search
  7. Create B-tree index on chunk_hash for dedup lookups

All statements are idempotent (IF NOT EXISTS / DO $$ guards).

Usage:
    from migrations.add_guideline_vector_columns import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

ENABLE_PGVECTOR = "CREATE EXTENSION IF NOT EXISTS vector;"

# Convert guideline_sections.content_embedding from real[] to vector(1536).
# ALTER TYPE cannot convert array -> vector, so we DROP + re-ADD inside a
# DO $$ block that checks the current column type first.
CONVERT_EMBEDDING_COLUMN = """
DO $$
BEGIN
    -- Only convert if the column exists and is NOT already vector type
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guideline_sections'
          AND column_name = 'content_embedding'
          AND data_type != 'USER-DEFINED'
    ) THEN
        ALTER TABLE guideline_sections DROP COLUMN content_embedding;
        ALTER TABLE guideline_sections ADD COLUMN content_embedding vector(1536);
        RAISE NOTICE 'Converted guideline_sections.content_embedding from array to vector(1536)';
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guideline_sections'
          AND column_name = 'content_embedding'
    ) THEN
        -- Column doesn't exist at all — add it fresh
        ALTER TABLE guideline_sections ADD COLUMN content_embedding vector(1536);
        RAISE NOTICE 'Added guideline_sections.content_embedding as vector(1536)';
    ELSE
        RAISE NOTICE 'guideline_sections.content_embedding is already vector type — skipping';
    END IF;
END $$;
"""

# Add metadata columns to guideline_sections
ADD_GUIDELINE_SECTION_COLS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guideline_sections' AND column_name = 'embedding_model'
    ) THEN
        ALTER TABLE guideline_sections
            ADD COLUMN embedding_model VARCHAR(50) DEFAULT 'text-embedding-3-small';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guideline_sections' AND column_name = 'token_count'
    ) THEN
        ALTER TABLE guideline_sections ADD COLUMN token_count INTEGER;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guideline_sections' AND column_name = 'chunk_hash'
    ) THEN
        ALTER TABLE guideline_sections ADD COLUMN chunk_hash VARCHAR(64);
    END IF;
END $$;
"""

# Add columns to underwriting_guidelines
ADD_UW_GUIDELINE_COLS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'underwriting_guidelines' AND column_name = 'embedding_status'
    ) THEN
        ALTER TABLE underwriting_guidelines
            ADD COLUMN embedding_status VARCHAR(20) DEFAULT 'pending';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'underwriting_guidelines' AND column_name = 'chunk_count'
    ) THEN
        ALTER TABLE underwriting_guidelines
            ADD COLUMN chunk_count INTEGER DEFAULT 0;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'underwriting_guidelines' AND column_name = 'overlay_priority'
    ) THEN
        ALTER TABLE underwriting_guidelines
            ADD COLUMN overlay_priority INTEGER DEFAULT 4;
    END IF;
END $$;
"""

# Add embedding columns to ai_knowledge_base
ADD_AI_KB_COLS = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_knowledge_base' AND column_name = 'content_embedding'
    ) THEN
        ALTER TABLE ai_knowledge_base ADD COLUMN content_embedding vector(1536);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_knowledge_base' AND column_name = 'embedding_model'
    ) THEN
        ALTER TABLE ai_knowledge_base ADD COLUMN embedding_model VARCHAR(50);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_knowledge_base' AND column_name = 'chunk_hash'
    ) THEN
        ALTER TABLE ai_knowledge_base ADD COLUMN chunk_hash VARCHAR(64);
    END IF;
END $$;
"""

# HNSW index on guideline_sections.content_embedding
CREATE_GS_HNSW_INDEX = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'ix_guideline_sections_embedding_hnsw'
    ) THEN
        CREATE INDEX ix_guideline_sections_embedding_hnsw
            ON guideline_sections
            USING hnsw (content_embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        RAISE NOTICE 'Created HNSW index on guideline_sections.content_embedding';
    END IF;
END $$;
"""

# HNSW index on ai_knowledge_base.content_embedding
CREATE_KB_HNSW_INDEX = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'ix_ai_kb_embedding_hnsw'
    ) THEN
        CREATE INDEX ix_ai_kb_embedding_hnsw
            ON ai_knowledge_base
            USING hnsw (content_embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        RAISE NOTICE 'Created HNSW index on ai_knowledge_base.content_embedding';
    END IF;
END $$;
"""

# B-tree index on guideline_sections.chunk_hash for dedup lookups
CREATE_CHUNK_HASH_INDEX = """
CREATE INDEX IF NOT EXISTS ix_guideline_sections_chunk_hash
    ON guideline_sections (chunk_hash);
"""

# Ordered list of all migration steps
MIGRATION_STEPS = [
    ("Enable pgvector extension", ENABLE_PGVECTOR),
    ("Convert guideline_sections.content_embedding to vector(1536)", CONVERT_EMBEDDING_COLUMN),
    ("Add metadata columns to guideline_sections", ADD_GUIDELINE_SECTION_COLS),
    ("Add columns to underwriting_guidelines", ADD_UW_GUIDELINE_COLS),
    ("Add embedding columns to ai_knowledge_base", ADD_AI_KB_COLS),
    ("Create HNSW index on guideline_sections", CREATE_GS_HNSW_INDEX),
    ("Create HNSW index on ai_knowledge_base", CREATE_KB_HNSW_INDEX),
    ("Create chunk_hash index on guideline_sections", CREATE_CHUNK_HASH_INDEX),
]


def run_migration(engine):
    """Execute all migration steps. Each step is idempotent.

    Args:
        engine: SQLAlchemy engine connected to the target database.

    Returns:
        True if all steps succeeded, False if any failed.
    """
    success = True
    with engine.connect() as conn:
        for label, sql in MIGRATION_STEPS:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info("[GuidelineVec] %s — OK", label)
            except Exception as e:
                logger.error("[GuidelineVec] %s — FAILED: %s", label, e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                success = False
    return success
