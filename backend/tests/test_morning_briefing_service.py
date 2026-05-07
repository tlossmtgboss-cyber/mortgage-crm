"""Tests for morning briefing service."""
import importlib
import sys

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone, timedelta


def _real_service():
    """Force-reload the real service module (not a test stub)."""
    mod_name = "services.morning_briefing_service"
    if mod_name in sys.modules and hasattr(sys.modules[mod_name], "__file__"):
        return sys.modules[mod_name].MorningBriefingService
    mod = importlib.import_module(mod_name)
    return mod.MorningBriefingService


class TestBriefingLevelDetection:
    """Test briefing level determination."""

    def test_individual_level_for_sales_role(self):
        Svc = _real_service()
        user = MagicMock()
        user.permission_role = "sales"
        user.direct_reports = []
        assert Svc.determine_level(user) == "individual"

    def test_manager_level_with_direct_reports(self):
        Svc = _real_service()
        user = MagicMock()
        user.permission_role = "management"
        user.direct_reports = [MagicMock()]
        assert Svc.determine_level(user) == "manager"

    def test_leadership_level(self):
        Svc = _real_service()
        user = MagicMock()
        user.permission_role = "leadership"
        user.direct_reports = []
        assert Svc.determine_level(user) == "leadership"

    def test_admin_is_leadership(self):
        Svc = _real_service()
        user = MagicMock()
        user.permission_role = "admin"
        user.direct_reports = []
        assert Svc.determine_level(user) == "leadership"

    def test_branch_manager_without_reports_is_individual(self):
        Svc = _real_service()
        user = MagicMock()
        user.permission_role = "branch_manager"
        user.direct_reports = []
        assert Svc.determine_level(user) == "individual"


class TestHealthIndicator:
    """Test team member health calculation."""

    def test_green_no_issues(self):
        Svc = _real_service()
        assert Svc.compute_health(at_risk=0, stale_leads=0, sla_breach=False) == "green"

    def test_yellow_some_risk(self):
        Svc = _real_service()
        assert Svc.compute_health(at_risk=1, stale_leads=2, sla_breach=False) == "yellow"

    def test_red_sla_breach(self):
        Svc = _real_service()
        assert Svc.compute_health(at_risk=0, stale_leads=0, sla_breach=True) == "red"

    def test_red_many_at_risk(self):
        Svc = _real_service()
        assert Svc.compute_health(at_risk=3, stale_leads=0, sla_breach=False) == "red"


class TestDashboardSnapshot:
    """Test _query_dashboard_snapshot integration."""

    def test_individual_level_returns_snapshot(self):
        Svc = _real_service()
        svc = Svc()
        db = MagicMock()
        with patch("services.morning_briefing_service.dms") as mock_dms:
            mock_dms.calculate_production_metrics.return_value = {"monthlyActual": 5}
            mock_dms.calculate_pipeline_stats.return_value = []
            mock_dms.calculate_lead_metrics.return_value = {"new_today": 0}
            mock_dms.calculate_efficiency_summary.return_value = {"overallScore": 50}
            mock_dms.calculate_profitability.return_value = {"funded_ytd": 0}
            mock_dms.calculate_loan_issues.return_value = []
            mock_dms.calculate_bottlenecks.return_value = []
            mock_dms.calculate_stage_performance.return_value = []
            result = svc._query_dashboard_snapshot(db, user_id=1, org_id=1, level="individual")
        assert "production" in result
        assert "efficiency" in result
        assert "team_stats" not in result  # individual level

    def test_manager_level_includes_team_stats(self):
        Svc = _real_service()
        svc = Svc()
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []  # no direct reports
        with patch("services.morning_briefing_service.dms") as mock_dms:
            mock_dms.calculate_production_metrics.return_value = {}
            mock_dms.calculate_pipeline_stats.return_value = []
            mock_dms.calculate_lead_metrics.return_value = {}
            mock_dms.calculate_efficiency_summary.return_value = {}
            mock_dms.calculate_profitability.return_value = {}
            mock_dms.calculate_loan_issues.return_value = []
            mock_dms.calculate_bottlenecks.return_value = []
            mock_dms.calculate_stage_performance.return_value = []
            mock_dms.calculate_team_stats.return_value = {"has_team": True}
            mock_dms.calculate_team_performance.return_value = []
            result = svc._query_dashboard_snapshot(db, user_id=1, org_id=1, level="manager")
        assert "team_stats" in result
        assert "team_performance" in result
