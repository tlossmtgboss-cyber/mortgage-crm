"""Tests for the Aria Memory shared retrieval service."""

import hashlib
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta


@pytest.mark.asyncio
async def test_retrieve_memory_returns_facts():
    """Retrieve memory facts for a known borrower."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.setex = MagicMock()

    service = AriaRetrievalService(db=mock_db, redis=mock_redis)

    mock_embedding = [0.1] * 1536
    with patch.object(service, "_embed_query", new_callable=AsyncMock, return_value=mock_embedding):
        mock_row = MagicMock()
        mock_row.value = "Prefers text over calls"
        mock_row.topic = "preferences"
        mock_row.source_call_id = "call_123"
        mock_row.transcript_span = "I prefer text messages"
        mock_row.confidence = 0.95
        mock_row.memory_type = "preference"
        mock_row.last_verified_at = datetime.now(timezone.utc) - timedelta(days=5)
        mock_row.relevance_score = 0.88

        mock_db.execute.return_value.fetchall.return_value = [mock_row]

        result = await service.retrieve(
            scope="memory",
            query="contact preferences",
            tenant_id=1,
            borrower_id=42,
            top_k=5,
        )

    assert len(result.facts) == 1
    assert result.facts[0].text == "Prefers text over calls"
    assert result.facts[0].topic == "preferences"
    assert result.facts[0].freshness == "fresh"
    assert result.no_results is False


@pytest.mark.asyncio
async def test_retrieve_memory_empty_returns_no_results():
    """Empty result set returns no_results=True."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.setex = MagicMock()

    service = AriaRetrievalService(db=mock_db, redis=mock_redis)

    mock_embedding = [0.1] * 1536
    with patch.object(service, "_embed_query", new_callable=AsyncMock, return_value=mock_embedding):
        mock_db.execute.return_value.fetchall.return_value = []

        result = await service.retrieve(
            scope="memory",
            query="anything",
            tenant_id=1,
            borrower_id=42,
        )

    assert result.no_results is True
    assert len(result.facts) == 0


@pytest.mark.asyncio
async def test_retrieve_uses_redis_cache():
    """Cache hit skips embedding + pgvector query."""
    import json
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_db = MagicMock()
    mock_redis = MagicMock()

    cached_result = json.dumps({
        "facts": [{"text": "Cached fact", "topic": "general", "source_call_date": None,
                    "transcript_span": None, "confidence": 0.9,
                    "freshness": "fresh", "fact_type": "fact"}],
        "no_results": False,
    })
    mock_redis.get = MagicMock(return_value=cached_result)

    service = AriaRetrievalService(db=mock_db, redis=mock_redis)
    result = await service.retrieve(
        scope="memory", query="test", tenant_id=1, borrower_id=42,
    )

    assert len(result.facts) == 1
    assert result.facts[0].text == "Cached fact"
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_tenant_filter_always_applied():
    """Tenant ID is always in the SQL WHERE clause."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.setex = MagicMock()

    service = AriaRetrievalService(db=mock_db, redis=mock_redis)
    mock_embedding = [0.1] * 1536

    with patch.object(service, "_embed_query", new_callable=AsyncMock, return_value=mock_embedding):
        mock_db.execute.return_value.fetchall.return_value = []

        await service.retrieve(
            scope="memory", query="test", tenant_id=99, borrower_id=1,
        )

    call_args = mock_db.execute.call_args
    sql_text = str(call_args[0][0])
    assert "organization_id" in sql_text
    # params are passed as the second positional argument to db.execute(sql, params)
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params.get("tenant_id") == 99 or params.get("org_id") == 99


@pytest.mark.asyncio
async def test_freshness_computation():
    """Verify freshness levels are computed from last_verified_at."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    service = AriaRetrievalService(db=MagicMock(), redis=MagicMock())

    now = datetime.now(timezone.utc)
    assert service._compute_freshness(now - timedelta(days=5)) == "fresh"
    assert service._compute_freshness(now - timedelta(days=45)) == "aging"
    assert service._compute_freshness(now - timedelta(days=100)) == "stale"
    assert service._compute_freshness(None) == "stale"


@pytest.mark.asyncio
async def test_audit_event_logged_on_retrieval():
    """Every retrieval logs to memory_audit_events."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value=None)
    mock_redis.setex = MagicMock()

    service = AriaRetrievalService(db=mock_db, redis=mock_redis)
    mock_embedding = [0.1] * 1536

    with patch.object(service, "_embed_query", new_callable=AsyncMock, return_value=mock_embedding):
        mock_db.execute.return_value.fetchall.return_value = []

        with patch.object(service, "_log_audit_event") as mock_audit:
            await service.retrieve(
                scope="memory", query="test query", tenant_id=1, borrower_id=42,
            )
            mock_audit.assert_called_once()
            audit_args = mock_audit.call_args
            assert audit_args[1]["event_type"] == "retrieval"
            assert audit_args[1]["tenant_id"] == 1
