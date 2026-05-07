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
