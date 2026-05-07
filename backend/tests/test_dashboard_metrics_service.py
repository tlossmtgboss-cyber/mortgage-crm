"""Tests for dashboard_metrics_service — shared query functions."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timedelta, timezone


def _make_mock_db():
    """Create a mock DB session with chainable query interface."""
    db = MagicMock()
    query_mock = MagicMock()
    db.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.group_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    return db, query_mock


class TestCalculateProductionMetrics:
    def test_returns_default_on_empty_db(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        result_row = MagicMock()
        result_row.annual = 0
        result_row.monthly = 0
        result_row.weekly = 0
        result_row.daily = 0
        query_mock.first.return_value = result_row
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["annualActual"] == 0
        assert result["monthlyActual"] == 0
        assert "annualGoal" in result
        assert "monthlyProgress" in result

    def test_scopes_to_branch_user_ids(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        result_row = MagicMock()
        result_row.annual = 5
        result_row.monthly = 2
        result_row.weekly = 1
        result_row.daily = 0
        query_mock.first.return_value = result_row
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1, 2, 3])
        assert result["annualActual"] == 5
        assert result["monthlyActual"] == 2

    def test_rollback_on_error(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1])
        db.rollback.assert_called_once()
        assert result["annualActual"] == 0


class TestCalculateBottlenecks:
    def test_returns_empty_list_on_error(self):
        from services.dashboard_metrics_service import calculate_bottlenecks
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_bottlenecks(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result == []
        db.rollback.assert_called_once()


class TestCalculateEfficiencySummary:
    def test_returns_default_on_error(self):
        from services.dashboard_metrics_service import calculate_efficiency_summary
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_efficiency_summary(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["overallScore"] == 0
        assert result["pullThroughRate"] == 0
        db.rollback.assert_called_once()


class TestCalculateLoanIssues:
    def test_returns_empty_list_on_error(self):
        from services.dashboard_metrics_service import calculate_loan_issues
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_loan_issues(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result == []
        db.rollback.assert_called_once()


class TestCalculateProfitability:
    def test_returns_default_on_error(self):
        from services.dashboard_metrics_service import calculate_profitability
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_profitability(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["funded_ytd"] == 0
        assert "Fund loans" in result["insights"][0]
        db.rollback.assert_called_once()
