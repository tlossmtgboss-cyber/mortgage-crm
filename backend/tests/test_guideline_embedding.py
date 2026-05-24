"""
Tests for guideline embedding generation.

Covers:
- Skipping sections with unchanged content (matching chunk_hash + existing embedding)
- Embedding new/changed sections and setting chunk_hash, token_count, embedding_model
"""

import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# generate_embedding_async is lazily imported inside embed_guideline_sections,
# so we patch it at the source module where it lives.
EMBED_PATCH = "services.aria_memory.embedding_service.generate_embedding_async"
HASH_PATCH = "services.call_monitoring.guidelines_service.compute_chunk_hash"


@pytest.mark.asyncio
@patch(EMBED_PATCH, new_callable=AsyncMock)
@patch(HASH_PATCH)
async def test_embed_skips_unchanged(mock_hash, mock_embed):
    """Section with matching chunk_hash and existing embedding is NOT re-embedded."""
    from services.call_monitoring.guidelines_service import embed_guideline_sections

    section_id = uuid.uuid4()
    guideline_id = str(uuid.uuid4())
    existing_hash = "abc123"
    existing_embedding = [0.1] * 1536

    # Mock section: chunk_hash matches, embedding already present
    section = MagicMock()
    section.id = section_id
    section.content = "Some guideline content that has not changed."
    section.chunk_hash = existing_hash
    section.content_embedding = existing_embedding

    # compute_chunk_hash returns the same hash as the section already has
    mock_hash.return_value = existing_hash

    # Mock guideline for the parent update
    guideline = MagicMock()
    guideline.id = guideline_id

    # Mock db
    db = MagicMock()
    section_query = MagicMock()
    section_query.filter.return_value = section_query
    section_query.all.return_value = [section]

    guideline_query = MagicMock()
    guideline_query.filter.return_value = guideline_query
    guideline_query.first.return_value = guideline

    def query_side_effect(model):
        if model.__name__ == "GuidelineSection":
            return section_query
        return guideline_query

    db.query.side_effect = query_side_effect

    count = await embed_guideline_sections(guideline_id, db)

    assert count == 0, "Should not embed sections with matching hash and existing embedding"
    mock_embed.assert_not_called()
    # Parent guideline should still be updated
    assert guideline.embedding_status == "complete"
    assert guideline.chunk_count == 1
    db.commit.assert_called_once()


@pytest.mark.asyncio
@patch(EMBED_PATCH, new_callable=AsyncMock)
@patch(HASH_PATCH)
async def test_embed_processes_new_content(mock_hash, mock_embed):
    """Section with no embedding gets embedded, chunk_hash and token_count set."""
    from services.call_monitoring.guidelines_service import embed_guideline_sections

    section_id = uuid.uuid4()
    guideline_id = str(uuid.uuid4())
    new_hash = "def456"
    fake_embedding = [0.5] * 1536

    # Mock section: no existing embedding, no chunk_hash
    section = MagicMock()
    section.id = section_id
    section.content = "New guideline content about credit score requirements."
    section.chunk_hash = None
    section.content_embedding = None

    mock_hash.return_value = new_hash
    mock_embed.return_value = fake_embedding

    # Mock guideline for the parent update
    guideline = MagicMock()
    guideline.id = guideline_id

    # Mock db
    db = MagicMock()
    section_query = MagicMock()
    section_query.filter.return_value = section_query
    section_query.all.return_value = [section]

    guideline_query = MagicMock()
    guideline_query.filter.return_value = guideline_query
    guideline_query.first.return_value = guideline

    def query_side_effect(model):
        if model.__name__ == "GuidelineSection":
            return section_query
        return guideline_query

    db.query.side_effect = query_side_effect

    count = await embed_guideline_sections(guideline_id, db)

    assert count == 1, "Should embed the section"
    mock_embed.assert_called_once_with(section.content)

    # Verify section was updated
    assert section.content_embedding == fake_embedding
    assert section.chunk_hash == new_hash
    assert section.embedding_model == "text-embedding-3-small"
    assert section.token_count is not None  # set by _count_tokens
    # Parent guideline updated
    assert guideline.embedding_status == "complete"
    assert guideline.chunk_count == 1
    db.commit.assert_called_once()
    db.flush.assert_called()


@pytest.mark.asyncio
@patch(EMBED_PATCH, new_callable=AsyncMock)
@patch(HASH_PATCH)
async def test_embed_skips_empty_content(mock_hash, mock_embed):
    """Section with empty content is silently skipped."""
    from services.call_monitoring.guidelines_service import embed_guideline_sections

    guideline_id = str(uuid.uuid4())

    section = MagicMock()
    section.id = uuid.uuid4()
    section.content = "   "  # whitespace-only
    section.chunk_hash = None
    section.content_embedding = None

    guideline = MagicMock()
    guideline.id = guideline_id

    db = MagicMock()
    section_query = MagicMock()
    section_query.filter.return_value = section_query
    section_query.all.return_value = [section]

    guideline_query = MagicMock()
    guideline_query.filter.return_value = guideline_query
    guideline_query.first.return_value = guideline

    def query_side_effect(model):
        if model.__name__ == "GuidelineSection":
            return section_query
        return guideline_query

    db.query.side_effect = query_side_effect

    count = await embed_guideline_sections(guideline_id, db)

    assert count == 0
    mock_hash.assert_not_called()
    mock_embed.assert_not_called()


@pytest.mark.asyncio
@patch(EMBED_PATCH, new_callable=AsyncMock)
@patch(HASH_PATCH)
async def test_embed_handles_changed_content(mock_hash, mock_embed):
    """Section with existing embedding but changed content gets re-embedded."""
    from services.call_monitoring.guidelines_service import embed_guideline_sections

    guideline_id = str(uuid.uuid4())
    old_hash = "old_hash_111"
    new_hash = "new_hash_222"
    new_embedding = [0.9] * 1536

    section = MagicMock()
    section.id = uuid.uuid4()
    section.content = "Updated guideline content."
    section.chunk_hash = old_hash
    section.content_embedding = [0.1] * 1536  # existing but stale

    mock_hash.return_value = new_hash  # different from old_hash
    mock_embed.return_value = new_embedding

    guideline = MagicMock()
    guideline.id = guideline_id

    db = MagicMock()
    section_query = MagicMock()
    section_query.filter.return_value = section_query
    section_query.all.return_value = [section]

    guideline_query = MagicMock()
    guideline_query.filter.return_value = guideline_query
    guideline_query.first.return_value = guideline

    def query_side_effect(model):
        if model.__name__ == "GuidelineSection":
            return section_query
        return guideline_query

    db.query.side_effect = query_side_effect

    count = await embed_guideline_sections(guideline_id, db)

    assert count == 1
    assert section.content_embedding == new_embedding
    assert section.chunk_hash == new_hash


@pytest.mark.asyncio
@patch(EMBED_PATCH, new_callable=AsyncMock)
@patch(HASH_PATCH)
async def test_embed_returns_zero_for_no_sections(mock_hash, mock_embed):
    """Returns 0 when guideline has no sections."""
    from services.call_monitoring.guidelines_service import embed_guideline_sections

    guideline_id = str(uuid.uuid4())

    db = MagicMock()
    section_query = MagicMock()
    section_query.filter.return_value = section_query
    section_query.all.return_value = []

    db.query.return_value = section_query

    count = await embed_guideline_sections(guideline_id, db)

    assert count == 0
    mock_embed.assert_not_called()
    mock_hash.assert_not_called()
