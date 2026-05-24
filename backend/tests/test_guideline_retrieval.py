"""
Tests for guideline retrieval via AriaRetrievalService.

Covers:
1. retrieve_guidelines returns correctly populated RetrievedGuideline objects
2. Agency filter is applied when agencies are passed
3. Empty result when _embed_query returns None
4. scope="guideline" in retrieve() routes to retrieve_guidelines and returns RetrievalResult
"""

import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY

EMBED_PATCH = "services.aria_memory.retrieval_service.AriaRetrievalService._embed_query"
AUDIT_PATCH = "services.aria_memory.retrieval_service.AriaRetrievalService._log_audit_event"


def _make_row(
    content="Min credit score is 620 for conventional.",
    section_number="B3-3.1-07",
    section_title="Credit Score Requirements",
    guideline_name="Fannie Mae Selling Guide",
    guideline_type="agency",
    loan_program="conventional",
    page_number=42,
    category="credit",
    overlay_priority=4,
    relevance_score=0.85,
):
    """Create a mock DB row with the expected column names."""
    row = MagicMock()
    row.content = content
    row.section_number = section_number
    row.section_title = section_title
    row.guideline_name = guideline_name
    row.guideline_type = guideline_type
    row.loan_program = loan_program
    row.page_number = page_number
    row.category = category
    row.overlay_priority = overlay_priority
    row.relevance_score = relevance_score
    return row


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    from services.aria_memory.retrieval_service import AriaRetrievalService
    return AriaRetrievalService(db=mock_db, redis=None)


# --------------------------------------------------------------------------
# 1. retrieve_guidelines returns correctly populated results
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_retrieve_guidelines_returns_results(mock_embed, mock_audit, mock_db):
    """Mock db.execute to return a row, verify RetrievedGuideline is correctly populated."""
    from services.aria_memory.retrieval_service import (
        AriaRetrievalService,
        RetrievedGuideline,
        GuidelineRetrievalResult,
    )

    fake_embedding = [0.1] * 1536
    mock_embed.return_value = fake_embedding

    row = _make_row()
    mock_db.execute.return_value.fetchall.return_value = [row]

    svc = AriaRetrievalService(db=mock_db, redis=None)
    result = await svc.retrieve_guidelines(
        query="What is the minimum credit score?",
        tenant_id=1,
    )

    assert isinstance(result, GuidelineRetrievalResult)
    assert result.no_results is False
    assert len(result.guidelines) == 1

    g = result.guidelines[0]
    assert isinstance(g, RetrievedGuideline)
    assert g.text == "Min credit score is 620 for conventional."
    assert g.section_number == "B3-3.1-07"
    assert g.section_title == "Credit Score Requirements"
    assert g.guideline_name == "Fannie Mae Selling Guide"
    assert g.guideline_type == "agency"
    assert g.loan_program == "conventional"
    assert g.page_number == 42
    assert g.category == "credit"
    assert g.overlay_priority == 4
    assert g.similarity == 0.85

    # Verify audit event was logged
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["event_type"] == "guideline_retrieval"
    assert call_kwargs["tenant_id"] == 1


# --------------------------------------------------------------------------
# 2. Agency filter is applied
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_retrieve_guidelines_applies_agency_filter(mock_embed, mock_audit, mock_db):
    """When agencies passed, verify SQL includes loan_program IN filter."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    fake_embedding = [0.2] * 1536
    mock_embed.return_value = fake_embedding

    mock_db.execute.return_value.fetchall.return_value = []

    svc = AriaRetrievalService(db=mock_db, redis=None)
    result = await svc.retrieve_guidelines(
        query="DTI requirements",
        tenant_id=1,
        agencies=["fha", "va"],
    )

    assert result.no_results is True

    # Verify the SQL was called and includes agency placeholders
    call_args = mock_db.execute.call_args
    sql_text = str(call_args[0][0])
    params = call_args[0][1]

    assert "ug.loan_program IN" in sql_text
    assert ":agency_0" in sql_text
    assert ":agency_1" in sql_text
    assert params["agency_0"] == "fha"
    assert params["agency_1"] == "va"


# --------------------------------------------------------------------------
# 3. Empty result when embedding fails
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_retrieve_guidelines_empty_on_no_embedding(mock_embed, mock_audit, mock_db):
    """When _embed_query returns None, result is empty with no DB call."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    mock_embed.return_value = None

    svc = AriaRetrievalService(db=mock_db, redis=None)
    result = await svc.retrieve_guidelines(
        query="anything",
        tenant_id=1,
    )

    assert result.no_results is True
    assert result.guidelines == []
    # DB should not be queried
    mock_db.execute.assert_not_called()


# --------------------------------------------------------------------------
# 4. scope="guideline" routes through retrieve() to retrieve_guidelines
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_scope_guideline_routes_to_retrieve_guidelines(mock_embed, mock_audit, mock_db):
    """Calling retrieve(scope='guideline') returns RetrievalResult converted from guideline data."""
    from services.aria_memory.retrieval_service import AriaRetrievalService, RetrievalResult

    fake_embedding = [0.3] * 1536
    mock_embed.return_value = fake_embedding

    row = _make_row(
        content="Max LTV is 97% for purchase.",
        section_number="B2-1.2-01",
        section_title="LTV Limits",
        guideline_name="Freddie Mac Guide",
        guideline_type="agency",
        loan_program="conventional",
        page_number=10,
        category="property",
        overlay_priority=4,
        relevance_score=0.78,
    )
    mock_db.execute.return_value.fetchall.return_value = [row]

    svc = AriaRetrievalService(db=mock_db, redis=None)
    result = await svc.retrieve(
        scope="guideline",
        query="What is the max LTV?",
        tenant_id=1,
        topic="conventional",
    )

    assert isinstance(result, RetrievalResult)
    assert result.no_results is False
    assert len(result.facts) == 1

    fact = result.facts[0]
    assert fact.text == "Max LTV is 97% for purchase."
    assert fact.topic == "conventional"
    assert fact.confidence == 0.78
    assert fact.freshness == "fresh"
    assert fact.fact_type == "fact"


# --------------------------------------------------------------------------
# 5. loan_program and category filters
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_retrieve_guidelines_applies_loan_program_and_category(mock_embed, mock_audit, mock_db):
    """Verify loan_program and category filters appear in SQL params."""
    from services.aria_memory.retrieval_service import AriaRetrievalService

    fake_embedding = [0.4] * 1536
    mock_embed.return_value = fake_embedding
    mock_db.execute.return_value.fetchall.return_value = []

    svc = AriaRetrievalService(db=mock_db, redis=None)
    await svc.retrieve_guidelines(
        query="income requirements",
        tenant_id=1,
        loan_program="fha",
        category="income",
    )

    call_args = mock_db.execute.call_args
    sql_text = str(call_args[0][0])
    params = call_args[0][1]

    assert "ug.loan_program = :loan_program" in sql_text
    assert "gs.category = :category" in sql_text
    assert params["loan_program"] == "fha"
    assert params["category"] == "income"


# --------------------------------------------------------------------------
# 6. Cache helpers
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@patch(AUDIT_PATCH)
@patch(EMBED_PATCH, new_callable=AsyncMock)
async def test_guideline_cache_roundtrip(mock_embed, mock_audit):
    """Verify _cache_set_guidelines / _cache_get_guidelines roundtrip."""
    from services.aria_memory.retrieval_service import (
        AriaRetrievalService,
        GuidelineRetrievalResult,
        RetrievedGuideline,
        GUIDELINE_CACHE_TTL_SECONDS,
    )

    mock_redis = MagicMock()
    stored = {}

    def setex_side_effect(key, ttl, data):
        stored[key] = data

    def get_side_effect(key):
        return stored.get(key)

    mock_redis.setex.side_effect = setex_side_effect
    mock_redis.get.side_effect = get_side_effect

    db = MagicMock()
    svc = AriaRetrievalService(db=db, redis=mock_redis)

    original = GuidelineRetrievalResult(
        guidelines=[
            RetrievedGuideline(
                text="Test guideline",
                section_number="1.1",
                section_title="Test",
                guideline_name="Test Guide",
                guideline_type="agency",
                loan_program="fha",
                similarity=0.9,
            )
        ],
        no_results=False,
    )

    cache_key = "aria:cache:guideline:1:none:abc123"
    svc._cache_set_guidelines(cache_key, original)

    # Verify TTL
    mock_redis.setex.assert_called_once()
    assert mock_redis.setex.call_args[0][1] == GUIDELINE_CACHE_TTL_SECONDS

    # Roundtrip
    retrieved = svc._cache_get_guidelines(cache_key)
    assert retrieved is not None
    assert len(retrieved.guidelines) == 1
    assert retrieved.guidelines[0].text == "Test guideline"
    assert retrieved.guidelines[0].loan_program == "fha"
    assert retrieved.no_results is False
