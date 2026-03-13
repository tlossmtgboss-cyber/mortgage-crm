"""
Tests for DocumentAnalyticsAgent

Behavioral tests that import the agent class, instantiate with a mock context,
and verify each tool produces the expected ToolResult shape. Uses mocks for
DB sessions so no live database is required.
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _make_context(org_id=1, user_id=42):
    """Build a minimal AgentContext dict."""
    return {
        "organization_id": str(org_id),
        "user_id": str(user_id),
        "user_role": "admin",
        "autonomous_mode": True,
    }


def _make_agent(org_id=1):
    """Instantiate DocumentAnalyticsAgent with mock context."""
    from agents.specialized.document_analytics_agent import DocumentAnalyticsAgent
    return DocumentAnalyticsAgent(_make_context(org_id))


def _mock_db_row(**kwargs):
    """Create a mock DB row that supports attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    row._mapping = kwargs
    return row


# ---------------------------------------------------------------------------
# Test: Agent registration and tool count
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    """Verify agent initializes with all 15 tools."""

    def test_agent_has_15_tools(self):
        agent = _make_agent()
        assert len(agent.tools) == 15

    def test_agent_name(self):
        agent = _make_agent()
        assert agent.name == "DocumentAnalyticsAgent"

    def test_all_tools_are_analysis_category(self):
        from agents.specialized.base import ToolCategory
        agent = _make_agent()
        for tool in agent.tools.values():
            assert tool.category == ToolCategory.ANALYSIS

    def test_all_tools_are_low_risk(self):
        from agents.specialized.base import RiskLevel
        agent = _make_agent()
        for tool in agent.tools.values():
            assert tool.risk_level == RiskLevel.LOW

    def test_require_org_id_raises_without_context(self):
        from agents.specialized.document_analytics_agent import DocumentAnalyticsAgent
        agent = DocumentAnalyticsAgent({"user_id": "1"})
        with pytest.raises(ValueError, match="requires organization_id"):
            agent.require_org_id()


# ---------------------------------------------------------------------------
# Test: get_collection_velocity
# ---------------------------------------------------------------------------

class TestCollectionVelocity:
    """get_collection_velocity returns velocity metrics."""

    @pytest.mark.asyncio
    async def test_returns_summary_and_by_type(self):
        agent = _make_agent()
        overall_row = _mock_db_row(
            total_docs=120, total_requests=95, avg_days_to_upload=5.3,
            median_days_to_upload=4.1, accepted_count=80, open_count=15,
        )
        type_row = _mock_db_row(doc_type="PAYSTUB", doc_count=30, avg_days=3.2)

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=overall_row)),
            MagicMock(fetchall=MagicMock(return_value=[type_row])),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._get_collection_velocity({"days": 90}, _make_context())

        assert result.success is True
        assert result.data["summary"]["avg_days_to_upload"] == 5.3
        assert len(result.data["by_doc_type"]) == 1
        assert result.data["by_doc_type"][0]["doc_type"] == "PAYSTUB"


# ---------------------------------------------------------------------------
# Test: identify_collection_bottlenecks
# ---------------------------------------------------------------------------

class TestCollectionBottlenecks:
    """identify_collection_bottlenecks flags slow doc types."""

    @pytest.mark.asyncio
    async def test_critical_bottleneck_detected(self):
        agent = _make_agent()
        rows = [
            _mock_db_row(doc_type="BANK_STATEMENT", total_requests=40, still_open=20,
                         avg_days_outstanding=12.5, max_days_waiting=25.0),
            _mock_db_row(doc_type="W2", total_requests=30, still_open=5,
                         avg_days_outstanding=3.1, max_days_waiting=7.0),
        ]
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=rows))

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._identify_collection_bottlenecks({"days": 90}, _make_context())

        assert result.success is True
        assert result.data["critical_count"] == 1
        assert result.data["bottlenecks"][0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# Test: analyze_rejection_patterns
# ---------------------------------------------------------------------------

class TestRejectionPatterns:
    """analyze_rejection_patterns breaks down rejections."""

    @pytest.mark.asyncio
    async def test_returns_by_category_and_type(self):
        agent = _make_agent()
        cat_rows = [_mock_db_row(rejection_category="SCREENSHOT", rejection_count=15, affected_loans=10)]
        type_rows = [_mock_db_row(doc_type="PAYSTUB", total_uploads=50, rejections=8, acceptances=42)]

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=cat_rows)),
            MagicMock(fetchall=MagicMock(return_value=type_rows)),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._analyze_rejection_patterns({"days": 90}, _make_context())

        assert result.success is True
        assert result.data["total_rejections"] == 15
        assert result.data["by_category"][0]["category"] == "SCREENSHOT"


# ---------------------------------------------------------------------------
# Test: measure_ai_effectiveness
# ---------------------------------------------------------------------------

class TestAIEffectiveness:
    """measure_ai_effectiveness reports accuracy metrics."""

    @pytest.mark.asyncio
    async def test_accuracy_calculation(self):
        agent = _make_agent()
        overall = _mock_db_row(
            total_classifications=200, correct=170, incorrect=10,
            unreviewed=20, avg_confidence=88.5, avg_duration_ms=120,
        )
        type_row = _mock_db_row(
            predicted_doc_type="W2", total=50, correct=48, incorrect=2, avg_confidence=92.0,
        )

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=overall)),
            MagicMock(fetchall=MagicMock(return_value=[type_row])),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._measure_ai_effectiveness({"days": 90}, _make_context())

        assert result.success is True
        # 170 correct / (170 + 10) reviewed = 94.4%
        assert result.data["summary"]["accuracy_pct"] == 94.4


# ---------------------------------------------------------------------------
# Test: predict_collection_timeline
# ---------------------------------------------------------------------------

class TestPredictCollectionTimeline:
    """predict_collection_timeline returns predictions for open requests."""

    @pytest.mark.asyncio
    async def test_all_collected_returns_no_predictions(self):
        agent = _make_agent()
        mock_db = MagicMock()
        # verify_loan_tenant check
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=_mock_db_row(id=1))),  # tenant check
            MagicMock(fetchall=MagicMock(return_value=[])),  # no open requests
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._predict_collection_timeline({"loan_id": 1}, _make_context())

        assert result.success is True
        assert result.data["open_requests"] == 0

    @pytest.mark.asyncio
    async def test_loan_not_found_raises(self):
        agent = _make_agent()
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchone=MagicMock(return_value=None))

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._predict_collection_timeline({"loan_id": 999}, _make_context())

        # verify_loan_tenant raises ValueError which gets caught by execute_tool
        assert result.success is False


# ---------------------------------------------------------------------------
# Test: generate_management_dashboard
# ---------------------------------------------------------------------------

class TestManagementDashboard:
    """generate_management_dashboard produces KPIs and health status."""

    @pytest.mark.asyncio
    async def test_healthy_dashboard(self):
        agent = _make_agent()
        kpis = _mock_db_row(
            total_docs_processed=200, loans_with_docs=50,
            accepted=170, rejected=20, needs_review=10,
            auto_reviewed=120, avg_review_hours=2.5,
            screenshots_detected=3,
        )
        open_result = _mock_db_row(open_count=8)
        campaigns = _mock_db_row(active_campaigns=15, responded=10)

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=kpis)),
            MagicMock(fetchone=MagicMock(return_value=open_result)),
            MagicMock(fetchone=MagicMock(return_value=campaigns)),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._generate_management_dashboard({"days": 30}, _make_context())

        assert result.success is True
        assert result.data["health"]["status"] == "healthy"
        assert result.data["kpis"]["acceptance_rate"] == 85.0  # 170/200

    @pytest.mark.asyncio
    async def test_critical_dashboard_with_alerts(self):
        agent = _make_agent()
        kpis = _mock_db_row(
            total_docs_processed=100, loans_with_docs=30,
            accepted=40, rejected=50, needs_review=10,
            auto_reviewed=20, avg_review_hours=30.0,
            screenshots_detected=15,
        )
        open_result = _mock_db_row(open_count=80)
        campaigns = _mock_db_row(active_campaigns=5, responded=1)

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=kpis)),
            MagicMock(fetchone=MagicMock(return_value=open_result)),
            MagicMock(fetchone=MagicMock(return_value=campaigns)),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._generate_management_dashboard({"days": 30}, _make_context())

        assert result.success is True
        assert result.data["health"]["status"] == "critical"
        assert len(result.data["health"]["alerts"]) >= 2


# ---------------------------------------------------------------------------
# Test: forecast_workload
# ---------------------------------------------------------------------------

class TestForecastWorkload:
    """forecast_workload predicts upcoming processing volume."""

    @pytest.mark.asyncio
    async def test_forecast_returns_capacity_assessment(self):
        agent = _make_agent()
        backlog = _mock_db_row(pending_review=10, open_requests=25)
        daily_avg = _mock_db_row(avg_daily_uploads=8.0, avg_daily_reviews=7.0)
        pipeline = _mock_db_row(active_loans=40, early_stage_loans=15)

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=backlog)),
            MagicMock(fetchone=MagicMock(return_value=daily_avg)),
            MagicMock(fetchone=MagicMock(return_value=pipeline)),
        ]

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._forecast_workload({"forecast_days": 14}, _make_context())

        assert result.success is True
        assert "capacity_assessment" in result.data
        assert result.data["forecast_period_days"] == 14
        assert result.data["daily_averages"]["uploads_per_day"] == 8.0


# ---------------------------------------------------------------------------
# Test: generate_team_scorecard
# ---------------------------------------------------------------------------

class TestTeamScorecard:
    """generate_team_scorecard produces ranked LO performance."""

    @pytest.mark.asyncio
    async def test_scorecard_ranking(self):
        agent = _make_agent()
        rows = [
            _mock_db_row(
                lo_id=1, lo_name="Jane Smith", loan_count=10, total_docs=50,
                accepted=45, rejected=5, avg_review_hours=2.0,
                open_requests=3, avg_collection_days=4.5,
            ),
            _mock_db_row(
                lo_id=2, lo_name="John Doe", loan_count=8, total_docs=30,
                accepted=20, rejected=10, avg_review_hours=6.0,
                open_requests=8, avg_collection_days=9.0,
            ),
        ]

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=rows))

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._generate_team_scorecard({"days": 30}, _make_context())

        assert result.success is True
        assert len(result.data["scorecards"]) == 2
        assert result.data["scorecards"][0]["rank"] == 1
        assert result.data["top_performer"] == "Jane Smith"
        # Jane should have higher score than John
        assert result.data["scorecards"][0]["overall_score"] > result.data["scorecards"][1]["overall_score"]

    @pytest.mark.asyncio
    async def test_empty_scorecard(self):
        agent = _make_agent()
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))

        with patch("agents.specialized.document_analytics_agent.SessionLocal", return_value=mock_db):
            result = await agent._generate_team_scorecard({"days": 30}, _make_context())

        assert result.success is True
        assert result.data["scorecards"] == []


# ---------------------------------------------------------------------------
# Test: tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Verify org_id is always required and used."""

    def test_require_org_id_returns_org_id(self):
        agent = _make_agent(org_id=42)
        assert agent.require_org_id() == "42"

    def test_org_filter_sql(self):
        agent = _make_agent()
        sql = agent.org_filter_sql("l")
        assert "l.organization_id = :org_id" in sql

    def test_org_filter_params(self):
        agent = _make_agent(org_id=7)
        params = agent.org_filter_params({"days": 30})
        assert params["org_id"] == "7"
        assert params["days"] == 30
