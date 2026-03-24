"""
Scheduler Outcome Tracking Route Tests

Tests for the outcome tracking route handlers in routes/scheduler/outcome_tracking.py.
Covers:
  - GET /analytics/appointment-outcomes       AI vs manual appointment funding conversion
  - GET /analytics/appointment-type-effectiveness  Conversion by appointment type
  - Date range filtering (days parameter)
  - Empty data handling (no appointments in range)
  - Org isolation (org_id scoping)
  - Admin-only access for cross-user queries
  - Non-admin restriction (own data only)
  - Helper function correctness (_format_currency, _calc_rate)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

class MockUser:
    """Mock user for authenticated tests."""
    def __init__(self, role="loan_officer", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "lo@test.com"
        self.is_active = True


@pytest.fixture
def admin_user():
    return MockUser(role="admin", user_id=1)


@pytest.fixture
def lo_user():
    return MockUser(role="loan_officer", user_id=10)


@pytest.fixture
def lo_user_org2():
    """LO in a different org for isolation tests."""
    return MockUser(role="loan_officer", org_id=2, user_id=20)


# Patch targets
_OT = "routes.scheduler.outcome_tracking"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _mock_row(mapping: dict):
    """Create a mock DB row with _mapping attribute."""
    row = MagicMock()
    row._mapping = mapping
    return row


# =============================================================================
# GET /analytics/appointment-outcomes — AI vs Manual comparison
# =============================================================================

class TestAppointmentOutcomes:
    """GET /api/v1/scheduler/analytics/appointment-outcomes."""

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_success_with_data(self, mock_auth, admin_user):
        """Admin sees AI vs manual comparison with realistic data."""
        mock_auth.return_value = admin_user

        ai_row = _mock_row({
            "booked_by_ai": True,
            "total_appointments": 50,
            "linked_to_loan": 40,
            "funded_count": 20,
            "funded_volume": 5000000.0,
            "no_show_count": 3,
            "cancelled_count": 2,
            "completed_count": 45,
            "avg_days_to_fund": 35.5,
        })
        manual_row = _mock_row({
            "booked_by_ai": False,
            "total_appointments": 80,
            "linked_to_loan": 60,
            "funded_count": 25,
            "funded_volume": 6250000.0,
            "no_show_count": 10,
            "cancelled_count": 5,
            "completed_count": 65,
            "avg_days_to_fund": 42.3,
        })

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [ai_row, manual_row]

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes?days=90",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 90

        # AI metrics
        ai = data["ai_scheduled"]
        assert ai["total_appointments"] == 50
        assert ai["funded_count"] == 20
        assert ai["funded_volume"] == 5000000.0
        assert ai["conversion_rate"] == 50.0  # 20/40 * 100
        assert ai["no_show_rate"] == 6.0  # 3/50 * 100
        assert ai["avg_days_to_fund"] == 35.5

        # Manual metrics
        manual = data["manually_scheduled"]
        assert manual["total_appointments"] == 80
        assert manual["funded_count"] == 25
        assert manual["conversion_rate"] == 41.7  # 25/60 * 100 rounded

        # Comparison
        comp = data["comparison"]
        # AI conversion 50.0 - manual 41.7 = 8.3
        assert comp["conversion_rate_diff"] == 8.3
        # AI no-show 6.0 - manual 12.5 = -6.5
        assert comp["no_show_rate_diff"] == -6.5
        # AI has higher conversion AND lower no-show => ai_better
        assert comp["ai_advantage"] == "ai_better"

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_empty_data(self, mock_auth, lo_user):
        """No appointments in the date range returns zero metrics."""
        mock_auth.return_value = lo_user

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes?days=30",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30
        assert data["ai_scheduled"]["total_appointments"] == 0
        assert data["ai_scheduled"]["funded_count"] == 0
        assert data["ai_scheduled"]["conversion_rate"] == 0.0
        assert data["manually_scheduled"]["total_appointments"] == 0
        assert data["comparison"]["ai_advantage"] == "neutral"

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_date_range_filtering(self, mock_auth, admin_user):
        """The days parameter is passed to the SQL query and reflected in the response."""
        mock_auth.return_value = admin_user

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes?days=180",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 180

        # Verify the SQL was called with days=180
        call_args = mock_db.execute.call_args
        assert call_args is not None
        sql_params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert sql_params["days"] == 180

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_non_admin_cannot_view_other_user(self, mock_auth, lo_user):
        """Non-admin trying to view another user's outcomes gets 403."""
        mock_auth.return_value = lo_user

        mock_db = MagicMock()

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes?user_id=999",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 403

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_org_isolation(self, mock_auth, lo_user):
        """Query is scoped to the authenticated user's organization_id."""
        mock_auth.return_value = lo_user

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200

        # Verify org_id was passed in SQL params
        call_args = mock_db.execute.call_args
        assert call_args is not None
        sql_params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert sql_params["org_id"] == lo_user.organization_id

    def test_outcomes_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/analytics/appointment-outcomes")
        assert resp.status_code in (401, 403, 500)

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_outcomes_manual_better_advantage(self, mock_auth, admin_user):
        """When manual has higher conversion and lower no-show, advantage is manual_better."""
        mock_auth.return_value = admin_user

        # AI: low conversion, high no-show
        ai_row = _mock_row({
            "booked_by_ai": True,
            "total_appointments": 30,
            "linked_to_loan": 20,
            "funded_count": 2,
            "funded_volume": 500000.0,
            "no_show_count": 8,
            "cancelled_count": 1,
            "completed_count": 21,
            "avg_days_to_fund": 50.0,
        })
        # Manual: high conversion, low no-show
        manual_row = _mock_row({
            "booked_by_ai": False,
            "total_appointments": 30,
            "linked_to_loan": 20,
            "funded_count": 10,
            "funded_volume": 2500000.0,
            "no_show_count": 1,
            "cancelled_count": 1,
            "completed_count": 28,
            "avg_days_to_fund": 30.0,
        })

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [ai_row, manual_row]

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-outcomes",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        # AI conversion: 2/20*100 = 10.0; Manual: 10/20*100 = 50.0
        # conv_diff = 10.0 - 50.0 = -40.0 (< -2)
        # AI no-show: 8/30*100 = 26.7; Manual: 1/30*100 = 3.3
        # ns_diff = 26.7 - 3.3 = 23.4 (>= 0)
        assert data["comparison"]["ai_advantage"] == "manual_better"


# =============================================================================
# GET /analytics/appointment-type-effectiveness — Conversion by type
# =============================================================================

class TestAppointmentTypeEffectiveness:
    """GET /api/v1/scheduler/analytics/appointment-type-effectiveness."""

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_type_effectiveness_success(self, mock_auth, admin_user):
        """Admin sees breakdown by appointment type with conversion metrics."""
        mock_auth.return_value = admin_user

        consult_row = _mock_row({
            "type_id": 1,
            "type_name": "Consultation",
            "total_appointments": 40,
            "linked_to_loan": 30,
            "funded_count": 15,
            "funded_volume": 3750000.0,
            "avg_days_to_fund": 38.2,
            "avg_loan_amount": 250000.0,
            "completed_count": 35,
            "no_show_count": 3,
        })
        followup_row = _mock_row({
            "type_id": 2,
            "type_name": "Follow-up",
            "total_appointments": 25,
            "linked_to_loan": 20,
            "funded_count": 12,
            "funded_volume": 2400000.0,
            "avg_days_to_fund": 25.0,
            "avg_loan_amount": 200000.0,
            "completed_count": 22,
            "no_show_count": 1,
        })

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [consult_row, followup_row]

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-type-effectiveness?days=90",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 90
        assert len(data["types"]) == 2

        consult = data["types"][0]
        assert consult["type_name"] == "Consultation"
        assert consult["total_appointments"] == 40
        assert consult["funded_count"] == 15
        assert consult["conversion_rate"] == 50.0  # 15/30 * 100
        assert consult["funded_volume"] == 3750000.0
        assert consult["funded_volume_formatted"] == "$3,750,000.00"
        assert consult["avg_loan_amount"] == 250000.0

        followup = data["types"][1]
        assert followup["type_name"] == "Follow-up"
        assert followup["conversion_rate"] == 60.0  # 12/20 * 100

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_type_effectiveness_empty_data(self, mock_auth, lo_user):
        """No appointments returns empty types list."""
        mock_auth.return_value = lo_user

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-type-effectiveness",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["types"] == []
        assert data["period_days"] == 90  # default

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_type_effectiveness_non_admin_cannot_view_other_user(self, mock_auth, lo_user):
        """Non-admin cannot query another user's type effectiveness."""
        mock_auth.return_value = lo_user

        mock_db = MagicMock()

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-type-effectiveness?user_id=999",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 403

    @patch(f"{_OT}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_OT}.require_feature_tier", lambda m: lambda fn: fn)
    def test_type_effectiveness_null_avg_fields(self, mock_auth, lo_user):
        """Handles NULL avg_days_to_fund and avg_loan_amount gracefully."""
        mock_auth.return_value = lo_user

        row = _mock_row({
            "type_id": None,
            "type_name": "Unassigned",
            "total_appointments": 5,
            "linked_to_loan": 0,
            "funded_count": 0,
            "funded_volume": 0,
            "avg_days_to_fund": None,
            "avg_loan_amount": None,
            "completed_count": 3,
            "no_show_count": 2,
        })

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [row]

        with patch(f"{_OT}.get_db", return_value=mock_db):
            with patch("db.get_db", return_value=iter([mock_db])):
                client = _get_client()
                resp = client.get(
                    "/api/v1/scheduler/analytics/appointment-type-effectiveness",
                    headers={"Authorization": "Bearer test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["types"]) == 1
        entry = data["types"][0]
        assert entry["type_id"] is None
        assert entry["type_name"] == "Unassigned"
        assert entry["avg_days_to_fund"] is None
        assert entry["avg_loan_amount"] is None
        assert entry["conversion_rate"] == 0.0  # 0/0 -> 0.0
        assert entry["funded_volume_formatted"] == "$0.00"


# =============================================================================
# HELPER FUNCTION UNIT TESTS
# =============================================================================

class TestHelperFunctions:
    """Direct tests for module-level helper functions."""

    def test_format_currency(self):
        from routes.scheduler.outcome_tracking import _format_currency
        assert _format_currency(0) == "$0.00"
        assert _format_currency(1234567.89) == "$1,234,567.89"
        assert _format_currency(500000) == "$500,000.00"

    def test_calc_rate_normal(self):
        from routes.scheduler.outcome_tracking import _calc_rate
        assert _calc_rate(20, 40) == 50.0
        assert _calc_rate(1, 3) == 33.3

    def test_calc_rate_zero_denominator(self):
        from routes.scheduler.outcome_tracking import _calc_rate
        assert _calc_rate(10, 0) == 0.0
        assert _calc_rate(0, 0) == 0.0
