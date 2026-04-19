"""Tests for the Aria consolidation pipeline."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_extraction_returns_structured_items():
    """LLM extraction produces structured ExtractedItem list."""
    from services.aria_memory.consolidation_worker import ConsolidationWorker

    mock_db = MagicMock()
    mock_redis = MagicMock()
    worker = ConsolidationWorker(db=mock_db, redis=mock_redis)

    mock_llm_response = [
        {
            "fact_text": "Credit score is 740",
            "fact_type": "fact",
            "topic": "qualification",
            "confidence": 0.92,
            "transcript_span": "my credit score is 740",
            "transcript_position": 120,
            "fact_key": None,
            "destination": "memory",
            "destination_reasoning": "Explicit borrower statement about qualification data",
        }
    ]

    with patch.object(worker, "_call_extraction_llm", new_callable=AsyncMock, return_value=mock_llm_response):
        with patch.object(worker, "_check_exclusions", return_value=[]):
            items = await worker._extract_facts("Sample transcript...", tenant_id=1)

    assert len(items) == 1
    assert items[0]["fact_text"] == "Credit score is 740"
    assert items[0]["destination"] == "memory"


@pytest.mark.asyncio
async def test_exclusion_filter_blocks_protected_class():
    """Items matching exclusion rules get destination=discard."""
    from services.aria_memory.consolidation_worker import ConsolidationWorker

    mock_db = MagicMock()
    worker = ConsolidationWorker(db=mock_db, redis=MagicMock())

    items = [
        {
            "fact_text": "Borrower is Hispanic",
            "fact_type": "fact",
            "topic": "general",
            "confidence": 0.9,
            "transcript_span": "I'm Hispanic",
            "transcript_position": 50,
            "fact_key": None,
            "destination": "memory",
            "destination_reasoning": "Borrower statement",
        }
    ]

    from services.aria_memory.exclusion_list import ExclusionResult
    mock_checker = MagicMock()
    mock_checker.check.return_value = ExclusionResult(excluded=True, category="protected_class")

    with patch.object(worker, "_get_exclusion_checker", return_value=mock_checker):
        filtered = worker._apply_exclusion_filter(items, tenant_id=1, borrower_id=42)

    assert len(filtered) == 1
    assert filtered[0]["destination"] == "discard"


@pytest.mark.asyncio
async def test_idempotency_skips_already_processed_call():
    """Worker skips processing if source_call_id already has extraction event."""
    from services.aria_memory.consolidation_worker import ConsolidationWorker

    mock_db = MagicMock()
    mock_db.execute.return_value.fetchone.return_value = MagicMock(id=1)

    worker = ConsolidationWorker(db=mock_db, redis=MagicMock())
    already = worker._check_idempotency("call_abc123")

    assert already is True


@pytest.mark.asyncio
async def test_staging_queue_write():
    """Memory-destined items are written to memory_staging table."""
    from services.aria_memory.consolidation_worker import ConsolidationWorker

    mock_db = MagicMock()
    worker = ConsolidationWorker(db=mock_db, redis=MagicMock())

    items = [
        {
            "fact_text": "Prefers text messages",
            "fact_type": "preference",
            "topic": "preferences",
            "confidence": 0.95,
            "transcript_span": "just text me",
            "fact_key": "contact_method",
            "destination": "memory",
            "destination_reasoning": "Clear preference statement",
        }
    ]

    worker._write_to_staging(items, tenant_id=1, borrower_id=42, source_call_id="call_123")

    assert mock_db.add.call_count == 1
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_auto_commit_high_confidence():
    """Items above auto-commit threshold (0.85) get auto-committed."""
    from services.aria_memory.consolidation_worker import ConsolidationWorker

    mock_db = MagicMock()
    worker = ConsolidationWorker(db=mock_db, redis=MagicMock())

    assert worker._should_auto_commit(0.90, False) is True
    assert worker._should_auto_commit(0.80, False) is False
    assert worker._should_auto_commit(0.90, True) is False  # exclusion flagged
