"""
Tests for GuidelineChartService

Covers: catalog retrieval, comparison aggregation, topic filtering,
overlay_priority sorting, and Redis caching.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Lightweight stand-in for UnderwritingGuideline rows returned by the DB query
# ---------------------------------------------------------------------------


class _FakeGuideline:
    """Mimics the SQLAlchemy model attributes used by the service."""

    def __init__(
        self,
        *,
        name: str,
        loan_program: str,
        guideline_type: str,
        structured_rules: dict | None = None,
        overlay_priority: int | None = 4,
        is_active: bool = True,
        organization_id: str = "1",
    ):
        self.id = uuid.uuid4()
        self.name = name
        self.loan_program = loan_program
        self.guideline_type = guideline_type
        self.structured_rules = structured_rules
        self.overlay_priority = overlay_priority
        self.is_active = is_active
        self.organization_id = organization_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_db(guidelines: list) -> MagicMock:
    """Return a mock Session whose .query(...).filter(...).all() yields *guidelines*."""
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.all.return_value = guidelines
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetChartCatalog:
    def test_returns_25_categories(self):
        from services.guideline_chart_service import GuidelineChartService

        svc = GuidelineChartService(db=MagicMock())
        catalog = svc.get_chart_catalog()

        assert len(catalog) == 25

    def test_first_entry_is_program_eligibility(self):
        from services.guideline_chart_service import GuidelineChartService

        svc = GuidelineChartService(db=MagicMock())
        catalog = svc.get_chart_catalog()

        first = catalog[0]
        assert first["id"] == "program_eligibility"
        assert first["name"] == "Program Eligibility Matrix"
        assert first["tag"] == "Master Chart"

    def test_last_entry_is_edge_cases(self):
        from services.guideline_chart_service import GuidelineChartService

        svc = GuidelineChartService(db=MagicMock())
        catalog = svc.get_chart_catalog()

        last = catalog[-1]
        assert last["id"] == "edge_cases"
        assert last["name"] == "Loan Scenario Edge-Case Charts"
        assert last["tag"] == "Enterprise Value"

    def test_returns_new_list_each_call(self):
        """Callers should be able to mutate the returned list without side effects."""
        from services.guideline_chart_service import GuidelineChartService

        svc = GuidelineChartService(db=MagicMock())
        a = svc.get_chart_catalog()
        b = svc.get_chart_catalog()
        assert a is not b


class TestGetComparison:
    @pytest.mark.asyncio
    async def test_aggregates_structured_rules(self):
        """Two guidelines with chart_data for the same topic are merged."""
        from services.guideline_chart_service import GuidelineChartService

        g1 = _FakeGuideline(
            name="FHA Guidelines",
            loan_program="fha",
            guideline_type="agency",
            overlay_priority=4,
            structured_rules={
                "chart_data": {
                    "credit_score": {"min_score": 580, "notes": "3.5% down"},
                }
            },
        )
        g2 = _FakeGuideline(
            name="VA Guidelines",
            loan_program="va",
            guideline_type="agency",
            overlay_priority=4,
            structured_rules={
                "chart_data": {
                    "credit_score": {"min_score": 620, "notes": "no down payment"},
                }
            },
        )

        db = _build_mock_db([g1, g2])
        svc = GuidelineChartService(db=db)
        result = await svc.get_comparison("credit_score", tenant_id=1)

        assert result["topic"] == "credit_score"
        assert result["topic_name"] == "Credit Score Matrix"
        assert len(result["programs"]) == 2

        programs_by_name = {p["guideline_name"]: p for p in result["programs"]}
        assert programs_by_name["FHA Guidelines"]["data"]["min_score"] == 580
        assert programs_by_name["VA Guidelines"]["data"]["min_score"] == 620

    @pytest.mark.asyncio
    async def test_skips_guidelines_without_topic(self):
        """Guideline with no chart_data for the requested topic is excluded."""
        from services.guideline_chart_service import GuidelineChartService

        g_has = _FakeGuideline(
            name="Conv Guidelines",
            loan_program="conventional",
            guideline_type="agency",
            structured_rules={
                "chart_data": {
                    "dti": {"max_dti": 45},
                }
            },
        )
        g_missing = _FakeGuideline(
            name="USDA Guidelines",
            loan_program="usda",
            guideline_type="agency",
            structured_rules={
                "chart_data": {
                    "ltv": {"max_ltv": 100},
                    # no "dti" key
                }
            },
        )
        g_no_chart_data = _FakeGuideline(
            name="Overlay X",
            loan_program="conventional",
            guideline_type="company",
            structured_rules={"some_other_key": True},
        )
        g_none_rules = _FakeGuideline(
            name="Empty",
            loan_program="fha",
            guideline_type="agency",
            structured_rules=None,
        )

        db = _build_mock_db([g_has, g_missing, g_no_chart_data, g_none_rules])
        svc = GuidelineChartService(db=db)
        result = await svc.get_comparison("dti", tenant_id=1)

        assert len(result["programs"]) == 1
        assert result["programs"][0]["guideline_name"] == "Conv Guidelines"

    @pytest.mark.asyncio
    async def test_sorts_by_priority(self):
        """Company overlay (priority 1) sorts before agency (priority 4)."""
        from services.guideline_chart_service import GuidelineChartService

        g_agency = _FakeGuideline(
            name="Agency",
            loan_program="conventional",
            guideline_type="agency",
            overlay_priority=4,
            structured_rules={
                "chart_data": {"credit_score": {"min": 620}},
            },
        )
        g_company = _FakeGuideline(
            name="Company Overlay",
            loan_program="conventional",
            guideline_type="company",
            overlay_priority=1,
            structured_rules={
                "chart_data": {"credit_score": {"min": 640}},
            },
        )
        g_investor = _FakeGuideline(
            name="Investor",
            loan_program="conventional",
            guideline_type="investor",
            overlay_priority=2,
            structured_rules={
                "chart_data": {"credit_score": {"min": 660}},
            },
        )

        # Intentionally pass in non-sorted order
        db = _build_mock_db([g_agency, g_company, g_investor])
        svc = GuidelineChartService(db=db)
        result = await svc.get_comparison("credit_score", tenant_id=1)

        priorities = [p["overlay_priority"] for p in result["programs"]]
        assert priorities == [1, 2, 4]
        assert result["programs"][0]["guideline_name"] == "Company Overlay"
        assert result["programs"][1]["guideline_name"] == "Investor"
        assert result["programs"][2]["guideline_name"] == "Agency"

    @pytest.mark.asyncio
    async def test_none_overlay_priority_defaults_to_4(self):
        """Guidelines with overlay_priority=None are treated as priority 4."""
        from services.guideline_chart_service import GuidelineChartService

        g = _FakeGuideline(
            name="No Priority",
            loan_program="fha",
            guideline_type="agency",
            overlay_priority=None,
            structured_rules={
                "chart_data": {"ltv": {"max": 96.5}},
            },
        )

        db = _build_mock_db([g])
        svc = GuidelineChartService(db=db)
        result = await svc.get_comparison("ltv", tenant_id=1)

        assert result["programs"][0]["overlay_priority"] == 4

    @pytest.mark.asyncio
    async def test_unknown_topic_uses_raw_name(self):
        """If topic is not in the catalog, topic_name falls back to the raw topic string."""
        from services.guideline_chart_service import GuidelineChartService

        db = _build_mock_db([])
        svc = GuidelineChartService(db=db)
        result = await svc.get_comparison("nonexistent_chart", tenant_id=1)

        assert result["topic"] == "nonexistent_chart"
        assert result["topic_name"] == "nonexistent_chart"
        assert result["programs"] == []

    @pytest.mark.asyncio
    async def test_redis_cache_hit(self):
        """When Redis has a cached value, DB query is skipped."""
        from services.guideline_chart_service import GuidelineChartService

        cached_data = {
            "topic": "dti",
            "topic_name": "DTI Matrix",
            "programs": [{"program": "fha", "guideline_name": "Cached", "guideline_type": "agency", "overlay_priority": 4, "data": {"max": 45}}],
        }

        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_data)

        db = MagicMock()
        svc = GuidelineChartService(db=db, redis=mock_redis)
        result = await svc.get_comparison("dti", tenant_id=1)

        assert result == cached_data
        # DB should NOT have been queried
        db.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_cache_miss_writes_cache(self):
        """On cache miss, result is written to Redis with correct key and TTL."""
        from services.guideline_chart_service import GuidelineChartService

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # cache miss

        db = _build_mock_db([])
        svc = GuidelineChartService(db=db, redis=mock_redis)
        result = await svc.get_comparison("condo", tenant_id=42)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "guideline:chart:42:condo"
        assert call_args[1]["ex"] == 3600
        # Verify written value round-trips
        written = json.loads(call_args[0][1])
        assert written["topic"] == "condo"
