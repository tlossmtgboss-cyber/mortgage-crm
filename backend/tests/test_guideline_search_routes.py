"""
Tests for Guideline Search API Routes (Task 6).

Contract tests verifying endpoints exist, accept correct inputs,
and return correct response shapes. Uses mocks to avoid real DB/service deps.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a test client with mocked auth and DB."""
    from fastapi.testclient import TestClient
    from main import app
    from database import get_db

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_db.query.return_value.count.return_value = 0

    def override_get_db():
        yield mock_db

    # Override auth so we don't need real tokens
    from auth.dependencies import get_current_user_flexible

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_flexible] = lambda: MagicMock(
        id=1, organization_id=1, email="test@test.com"
    )

    yield TestClient(app)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /search/rag
# ---------------------------------------------------------------------------

class TestSearchRAG:
    """RAG-powered search endpoint."""

    def test_search_rag_requires_query(self, client):
        """Missing query field returns 422."""
        resp = client.post(
            "/api/v1/underwriting-guidelines/search/rag",
            json={},
        )
        assert resp.status_code == 422

    def test_search_rag_accepts_valid_body(self, client):
        """Valid body reaches the service (mocked)."""
        mock_result = {
            "answer": "Min credit score is 620.",
            "citations": [],
            "sources": [],
        }
        with patch(
            "services.guideline_search_service.GuidelineSearchService.search",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/underwriting-guidelines/search/rag",
                json={"query": "minimum credit score"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "answer" in data

    def test_search_rag_with_filters(self, client):
        """Filters are accepted without error."""
        mock_result = {"answer": "...", "citations": [], "sources": []}
        with patch(
            "services.guideline_search_service.GuidelineSearchService.search",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/underwriting-guidelines/search/rag",
                json={
                    "query": "DTI limits",
                    "agencies": ["fannie_mae", "freddie_mac"],
                    "loan_program": "conventional",
                    "category": "income",
                    "top_k": 5,
                },
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /compare/catalog
# ---------------------------------------------------------------------------

class TestCompareCatalog:
    """Chart catalog endpoint."""

    def test_catalog_returns_charts(self, client):
        """Catalog returns a list of chart definitions."""
        mock_catalog = [
            {"id": "credit_score", "label": "Credit Score Requirements"},
            {"id": "dti_limits", "label": "DTI Limits"},
        ]
        with patch(
            "services.guideline_chart_service.GuidelineChartService.get_chart_catalog",
            return_value=mock_catalog,
        ):
            resp = client.get(
                "/api/v1/underwriting-guidelines/compare/catalog"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "charts" in data
            assert isinstance(data["charts"], list)


# ---------------------------------------------------------------------------
# GET /compare/{topic}
# ---------------------------------------------------------------------------

class TestCompare:
    """Comparison chart endpoint."""

    def test_compare_returns_data(self, client):
        """Comparison returns chart data for a topic."""
        mock_comparison = {
            "topic": "credit_score",
            "columns": ["Fannie Mae", "Freddie Mac", "FHA"],
            "rows": [{"metric": "Min Score", "values": [620, 620, 580]}],
        }
        with patch(
            "services.guideline_chart_service.GuidelineChartService.get_comparison",
            new_callable=AsyncMock,
            return_value=mock_comparison,
        ):
            resp = client.get(
                "/api/v1/underwriting-guidelines/compare/credit_score"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["topic"] == "credit_score"


# ---------------------------------------------------------------------------
# POST /library
# ---------------------------------------------------------------------------

class TestLibrarySave:
    """Save query endpoint."""

    def test_save_query_returns_confirmation(self, client):
        """Saving a query returns saved=True."""
        resp = client.post(
            "/api/v1/underwriting-guidelines/library",
            json={"name": "Credit check", "query": "minimum credit score"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["name"] == "Credit check"
        assert data["query"] == "minimum credit score"

    def test_save_query_requires_name(self, client):
        """Missing name returns 422."""
        resp = client.post(
            "/api/v1/underwriting-guidelines/library",
            json={"query": "test"},
        )
        assert resp.status_code == 422

    def test_save_query_requires_query(self, client):
        """Missing query returns 422."""
        resp = client.post(
            "/api/v1/underwriting-guidelines/library",
            json={"name": "test"},
        )
        assert resp.status_code == 422

    def test_save_query_with_filters(self, client):
        """Filters dict is accepted."""
        resp = client.post(
            "/api/v1/underwriting-guidelines/library",
            json={
                "name": "FHA DTI",
                "query": "DTI limits FHA",
                "filters": {"agency": "fha", "category": "income"},
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /library
# ---------------------------------------------------------------------------

class TestLibraryList:
    """List saved queries endpoint."""

    def test_list_queries_returns_empty(self, client):
        """Initial library is empty."""
        resp = client.get("/api/v1/underwriting-guidelines/library")
        assert resp.status_code == 200
        data = resp.json()
        assert "queries" in data
        assert data["queries"] == []


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

class TestStats:
    """Guideline statistics endpoint."""

    def test_stats_returns_counts(self, client):
        """Stats endpoint returns expected shape."""
        resp = client.get("/api/v1/underwriting-guidelines/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_guidelines" in data
        assert "total_sections" in data
        assert "embedded_sections" in data
        assert "embedding_coverage" in data
        assert "by_status" in data
        assert isinstance(data["by_status"], dict)

    def test_stats_coverage_zero_when_no_sections(self, client):
        """Coverage is 0 when there are no sections."""
        resp = client.get("/api/v1/underwriting-guidelines/stats")
        data = resp.json()
        assert data["embedding_coverage"] == 0
