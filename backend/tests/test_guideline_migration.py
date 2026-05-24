"""
Tests for migrations/add_guideline_vector_columns.py

Validates:
  1. run_migration() executes without error (mocked engine/connection)
  2. Executed SQL includes vector extension, embedding conversion, HNSW indexes, chunk_hash
  3. Idempotency: running twice produces no errors
"""

import pytest
from unittest.mock import MagicMock, call

from migrations.add_guideline_vector_columns import run_migration, MIGRATION_STEPS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine with a connection context manager."""
    engine = MagicMock()
    conn = MagicMock()
    # engine.connect() returns a context manager yielding conn
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunMigration:
    """Tests for the run_migration function."""

    def test_executes_without_error(self, mock_engine):
        """run_migration should execute all steps and return True on success."""
        engine, conn = mock_engine
        result = run_migration(engine)
        assert result is True

    def test_executes_all_steps(self, mock_engine):
        """run_migration should execute one SQL statement per migration step."""
        engine, conn = mock_engine
        run_migration(engine)
        # Each step calls conn.execute() once and conn.commit() once
        assert conn.execute.call_count == len(MIGRATION_STEPS)
        assert conn.commit.call_count == len(MIGRATION_STEPS)

    def test_sql_includes_vector_extension(self, mock_engine):
        """Migration SQL should include CREATE EXTENSION vector."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "CREATE EXTENSION IF NOT EXISTS vector" in all_sql

    def test_sql_includes_vector_conversion(self, mock_engine):
        """Migration SQL should convert content_embedding to vector(1536)."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "vector(1536)" in all_sql
        assert "guideline_sections" in all_sql

    def test_sql_includes_hnsw_index_guideline_sections(self, mock_engine):
        """Migration should create HNSW index on guideline_sections."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "ix_guideline_sections_embedding_hnsw" in all_sql
        assert "vector_cosine_ops" in all_sql
        assert "hnsw" in all_sql

    def test_sql_includes_hnsw_index_ai_kb(self, mock_engine):
        """Migration should create HNSW index on ai_knowledge_base."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "ix_ai_kb_embedding_hnsw" in all_sql

    def test_sql_includes_chunk_hash_column(self, mock_engine):
        """Migration should add chunk_hash column."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "chunk_hash" in all_sql

    def test_sql_includes_chunk_hash_index(self, mock_engine):
        """Migration should create index on chunk_hash for dedup."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "ix_guideline_sections_chunk_hash" in all_sql

    def test_sql_includes_embedding_model_column(self, mock_engine):
        """Migration should add embedding_model column."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "embedding_model" in all_sql

    def test_sql_includes_token_count_column(self, mock_engine):
        """Migration should add token_count column."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "token_count" in all_sql

    def test_sql_includes_uw_guideline_columns(self, mock_engine):
        """Migration should add embedding_status, chunk_count, overlay_priority to underwriting_guidelines."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "embedding_status" in all_sql
        assert "chunk_count" in all_sql
        assert "overlay_priority" in all_sql

    def test_sql_includes_ai_kb_columns(self, mock_engine):
        """Migration should add columns to ai_knowledge_base."""
        engine, conn = mock_engine
        run_migration(engine)
        all_sql = _collect_sql(conn)
        assert "ai_knowledge_base" in all_sql

    def test_idempotency(self, mock_engine):
        """Running run_migration twice should succeed both times."""
        engine, conn = mock_engine
        result1 = run_migration(engine)
        result2 = run_migration(engine)
        assert result1 is True
        assert result2 is True

    def test_returns_false_on_failure(self, mock_engine):
        """run_migration should return False if any step fails."""
        engine, conn = mock_engine
        conn.execute.side_effect = Exception("simulated failure")
        result = run_migration(engine)
        assert result is False

    def test_continues_after_failure(self, mock_engine):
        """run_migration should attempt all steps even if one fails."""
        engine, conn = mock_engine
        # Fail on the second execute call only, succeed on all others
        effects = [None] * len(MIGRATION_STEPS)
        effects[1] = Exception("simulated step 2 failure")
        conn.execute.side_effect = effects
        result = run_migration(engine)
        assert result is False
        # Should still have attempted all 8 steps
        assert conn.execute.call_count == len(MIGRATION_STEPS)

    def test_migration_steps_count(self):
        """Verify the expected number of migration steps."""
        assert len(MIGRATION_STEPS) == 8

    def test_migration_steps_labels(self):
        """All migration steps should have descriptive labels."""
        for label, sql in MIGRATION_STEPS:
            assert isinstance(label, str)
            assert len(label) > 5
            assert isinstance(sql, str)
            assert len(sql) > 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sql(conn) -> str:
    """Collect all SQL text passed to conn.execute() into one string."""
    parts = []
    for c in conn.execute.call_args_list:
        # call(text_obj) — extract the .text attribute
        arg = c[0][0]  # first positional argument
        if hasattr(arg, "text"):
            parts.append(arg.text)
        else:
            parts.append(str(arg))
    return "\n".join(parts)
