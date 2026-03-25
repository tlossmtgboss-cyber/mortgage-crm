"""Tests for morning briefing service."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone, timedelta
from services.morning_briefing_service import MorningBriefingService


class TestBriefingLevelDetection:
    """Test briefing level determination."""

    def test_individual_level_for_sales_role(self):
        user = MagicMock()
        user.permission_role = "sales"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "individual"

    def test_manager_level_with_direct_reports(self):
        user = MagicMock()
        user.permission_role = "management"
        user.direct_reports = [MagicMock()]
        assert MorningBriefingService.determine_level(user) == "manager"

    def test_leadership_level(self):
        user = MagicMock()
        user.permission_role = "leadership"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "leadership"

    def test_admin_is_leadership(self):
        user = MagicMock()
        user.permission_role = "admin"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "leadership"

    def test_branch_manager_without_reports_is_individual(self):
        user = MagicMock()
        user.permission_role = "branch_manager"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "individual"


class TestHealthIndicator:
    """Test team member health calculation."""

    def test_green_no_issues(self):
        assert MorningBriefingService.compute_health(at_risk=0, stale_leads=0, sla_breach=False) == "green"

    def test_yellow_some_risk(self):
        assert MorningBriefingService.compute_health(at_risk=1, stale_leads=2, sla_breach=False) == "yellow"

    def test_red_sla_breach(self):
        assert MorningBriefingService.compute_health(at_risk=0, stale_leads=0, sla_breach=True) == "red"

    def test_red_many_at_risk(self):
        assert MorningBriefingService.compute_health(at_risk=3, stale_leads=0, sla_breach=False) == "red"
