import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


def test_search_guidelines_rag_returns_citations():
    """RAG tool should return answer with citations."""
    from aria.tools.knowledge_tools import KnowledgeTools

    tools = KnowledgeTools()

    mock_result = {
        "answer": "The minimum credit score for FHA is 580.",
        "citations": [{"section_number": "4000.1.II.A.4", "guideline_name": "FHA Handbook"}],
        "sources": [{"name": "FHA Handbook", "citation_count": 1}],
        "confidence": 0.92,
        "query": "min credit score FHA",
    }

    with patch("aria.tools.knowledge_tools.GuidelineSearchService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.search = AsyncMock(return_value=mock_result)

        result = asyncio.run(
            tools.search_guidelines_rag("min credit score FHA")
        )

    assert result["answer"] is not None
    assert result["rag_enabled"] is True
    assert len(result["citations"]) == 1


def test_search_guidelines_rag_fallback_on_error():
    """When RAG fails, should fall back to Claude training data."""
    from aria.tools.knowledge_tools import KnowledgeTools

    tools = KnowledgeTools()

    with patch("aria.tools.knowledge_tools.GuidelineSearchService", side_effect=Exception("No DB")):
        with patch("aria.tools.knowledge_tools.client") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="FHA minimum is 580 for 3.5% down.")]
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            result = asyncio.run(
                tools.search_guidelines_rag("min credit score FHA")
            )

    assert result["rag_enabled"] is False
    assert result["answer"] is not None


def test_search_guidelines_rag_with_agency_filter():
    """RAG tool should pass agency filter to service."""
    from aria.tools.knowledge_tools import KnowledgeTools

    tools = KnowledgeTools()

    mock_result = {
        "answer": "VA requires no down payment.",
        "citations": [],
        "sources": [],
        "confidence": 0.88,
        "query": "VA down payment",
    }

    with patch("aria.tools.knowledge_tools.GuidelineSearchService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.search = AsyncMock(return_value=mock_result)

        result = asyncio.run(
            tools.search_guidelines_rag("VA down payment", agency="va")
        )

    assert result["rag_enabled"] is True
    mock_instance.search.assert_called_once()
    call_kwargs = mock_instance.search.call_args
    assert call_kwargs.kwargs.get("agencies") == ["va"] or call_kwargs[1].get("agencies") == ["va"]


def test_knowledge_tools_has_income_analysis():
    """Income analysis method should still exist after refactor."""
    from aria.tools.knowledge_tools import KnowledgeTools
    tools = KnowledgeTools()
    assert hasattr(tools, 'run_income_analysis')
