"""
Tests for the Lead Routing Engine.

Validates:
  - Rule matching by loan_type, state, zip_code, language, source
  - Round-robin assignment within matched rules
  - Capacity-based fallback routing
  - Default (catch-all) rules
  - Edge cases: no rules, no LOs, empty attributes
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.lead_routing_routes import (
    route_lead,
    _get_routing_rules,
    _get_round_robin_next,
    _get_lo_pipeline_counts,
    _check_availability,
    _fallback_route,
)


# =============================================================================
# Helpers: create mock routing rules
# =============================================================================

def _make_rule(id, rule_type, match_value, lo_ids, priority=0, rule_name=None):
    """Create a mock routing rule row."""
    mock = MagicMock()
    mock.id = id
    mock.rule_name = rule_name or f"Rule-{id}"
    mock.rule_type = rule_type
    mock.match_value = match_value
    mock.assigned_lo_ids = lo_ids  # Can be list or comma-separated string
    mock.priority = priority
    mock.weight = 1
    mock.is_active = True
    return mock


def _make_user_row(id, first_name, last_name):
    """Create a mock user row."""
    mock = MagicMock()
    mock.id = id
    mock.first_name = first_name
    mock.last_name = last_name
    return mock


# =============================================================================
# Rule matching tests
# =============================================================================

class TestRuleMatching:
    """Test that rules match on the correct lead attribute."""

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=10)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_match_by_loan_type(self, mock_rules, mock_rr, mock_avail):
        """A loan_type rule should match when lead's loan_type matches."""
        mock_rules.return_value = [_make_rule(1, "loan_type", "VA", [10, 11])]

        mock_db = MagicMock()
        user_row = _make_user_row(10, "John", "Doe")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, loan_type="VA")

        assert result is not None
        assert result["lo_id"] == 10
        assert "loan_type=VA" in result["reason"]

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=20)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_match_by_state(self, mock_rules, mock_rr, mock_avail):
        """A state rule should match when lead's state matches (case-insensitive)."""
        mock_rules.return_value = [_make_rule(2, "state", "CA", [20])]

        mock_db = MagicMock()
        user_row = _make_user_row(20, "Jane", "Smith")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, state="ca")

        assert result is not None
        assert result["lo_id"] == 20
        assert "state=CA" in result["reason"]

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=30)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_match_by_zip_code_prefix(self, mock_rules, mock_rr, mock_avail):
        """A zip_code rule should match on prefix (e.g., '787' matches '78701')."""
        mock_rules.return_value = [_make_rule(3, "zip_code", "787", [30])]

        mock_db = MagicMock()
        user_row = _make_user_row(30, "Bob", "Jones")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, zip_code="78701")

        assert result is not None
        assert result["lo_id"] == 30
        assert "zip_code" in result["reason"]

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=40)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_match_by_source(self, mock_rules, mock_rr, mock_avail):
        """A source rule should match when lead's source matches."""
        mock_rules.return_value = [_make_rule(4, "source", "referral", [40])]

        mock_db = MagicMock()
        user_row = _make_user_row(40, "Alice", "Brown")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, source="referral")

        assert result is not None
        assert result["lo_id"] == 40

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=50)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_match_by_language(self, mock_rules, mock_rr, mock_avail):
        """A language rule should match when lead's language matches."""
        mock_rules.return_value = [_make_rule(5, "language", "spanish", [50])]

        mock_db = MagicMock()
        user_row = _make_user_row(50, "Carlos", "Garcia")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, language="Spanish")

        assert result is not None
        assert result["lo_id"] == 50

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=10)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_no_match_tries_next_rule(self, mock_rules, mock_rr, mock_avail):
        """When first rule doesn't match, engine should try the next rule."""
        mock_rules.return_value = [
            _make_rule(1, "loan_type", "VA", [10], priority=10),  # Won't match
            _make_rule(2, "state", "TX", [20], priority=5),        # Will match
        ]

        mock_db = MagicMock()
        user_row = _make_user_row(20, "Tex", "Ranger")
        mock_db.execute.return_value.fetchone.return_value = user_row

        # Set round-robin to return 20 for the second rule
        mock_rr.return_value = 20

        result = route_lead(mock_db, org_id=1, loan_type="conventional", state="TX")

        assert result is not None
        assert result["lo_id"] == 20
        assert "state=TX" in result["reason"]


# =============================================================================
# Default / catch-all rule
# =============================================================================

class TestDefaultRule:
    """Test default (catch-all) rule behavior."""

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=60)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_default_rule_matches_anything(self, mock_rules, mock_rr, mock_avail):
        """A 'default' type rule should match regardless of lead attributes."""
        mock_rules.return_value = [_make_rule(99, "default", "", [60, 61])]

        mock_db = MagicMock()
        user_row = _make_user_row(60, "Default", "LO")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1)

        assert result is not None
        assert result["lo_id"] == 60

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=60)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_specific_rules_have_priority_over_default(self, mock_rules, mock_rr, mock_avail):
        """Specific rules (higher priority) should match before default."""
        mock_rules.return_value = [
            _make_rule(1, "loan_type", "FHA", [10], priority=10),
            _make_rule(99, "default", "", [60], priority=0),
        ]

        mock_db = MagicMock()
        user_row = _make_user_row(10, "FHA", "Specialist")
        mock_db.execute.return_value.fetchone.return_value = user_row
        mock_rr.return_value = 10

        result = route_lead(mock_db, org_id=1, loan_type="FHA")

        assert result["lo_id"] == 10
        assert "loan_type=FHA" in result["reason"]


# =============================================================================
# Round-robin assignment
# =============================================================================

class TestRoundRobin:
    """Test _get_round_robin_next rotates through LO list."""

    def test_first_assignment_picks_first_lo(self):
        """With no prior state, should pick the first LO."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None  # No prior state

        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[10, 20, 30])
        assert result == 10

    def test_rotates_to_next_lo(self):
        """After LO 10 was last assigned, should pick LO 20."""
        mock_db = MagicMock()
        rr_state = MagicMock()
        rr_state.last_lo_id = 10
        mock_db.execute.return_value.fetchone.return_value = rr_state

        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[10, 20, 30])
        assert result == 20

    def test_wraps_around_to_first(self):
        """After the last LO in the list, should wrap to the first."""
        mock_db = MagicMock()
        rr_state = MagicMock()
        rr_state.last_lo_id = 30
        mock_db.execute.return_value.fetchone.return_value = rr_state

        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[10, 20, 30])
        assert result == 10

    def test_unknown_last_lo_starts_from_first(self):
        """If last_lo_id is not in the list, should start from the first."""
        mock_db = MagicMock()
        rr_state = MagicMock()
        rr_state.last_lo_id = 999  # Not in the list
        mock_db.execute.return_value.fetchone.return_value = rr_state

        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[10, 20, 30])
        assert result == 10

    def test_single_lo_always_returns_same(self):
        """With only one LO, should always return that LO."""
        mock_db = MagicMock()
        rr_state = MagicMock()
        rr_state.last_lo_id = 10
        mock_db.execute.return_value.fetchone.return_value = rr_state

        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[10])
        assert result == 10

    def test_empty_lo_list_returns_none(self):
        """Empty LO list should return None."""
        mock_db = MagicMock()
        result = _get_round_robin_next(mock_db, org_id=1, lo_ids=[])
        assert result is None


# =============================================================================
# Capacity-based fallback
# =============================================================================

class TestFallbackRoute:
    """Test _fallback_route assigns to LO with smallest pipeline."""

    def test_fallback_picks_lo_with_smallest_pipeline(self):
        """Should select the LO with the fewest active loans."""
        mock_db = MagicMock()
        lo_row = MagicMock()
        lo_row.id = 42
        lo_row.first_name = "Low"
        lo_row.last_name = "Pipeline"
        lo_row.pipeline = 3
        mock_db.execute.return_value.fetchone.return_value = lo_row

        result = _fallback_route(mock_db, org_id=1)

        assert result is not None
        assert result["lo_id"] == 42
        assert result["lo_name"] == "Low Pipeline"
        assert "Fallback" in result["reason"]
        assert result["rule_id"] is None

    def test_fallback_returns_none_when_no_los(self):
        """If no LOs exist in the org, should return None."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        result = _fallback_route(mock_db, org_id=1)
        assert result is None


class TestPipelineCounts:
    """Test _get_lo_pipeline_counts."""

    def test_returns_counts_for_active_loans(self):
        """Should return pipeline count per LO, including zeros."""
        mock_db = MagicMock()
        row1 = MagicMock()
        row1.loan_officer_id = 10
        row1.cnt = 5
        row2 = MagicMock()
        row2.loan_officer_id = 20
        row2.cnt = 12
        mock_db.execute.return_value.fetchall.return_value = [row1, row2]

        counts = _get_lo_pipeline_counts(mock_db, org_id=1, lo_ids=[10, 20, 30])
        assert counts[10] == 5
        assert counts[20] == 12
        assert counts[30] == 0  # Not in results → zero pipeline

    def test_empty_lo_list_returns_empty(self):
        counts = _get_lo_pipeline_counts(MagicMock(), org_id=1, lo_ids=[])
        assert counts == {}


# =============================================================================
# Availability check
# =============================================================================

class TestCheckAvailability:
    """Test _check_availability."""

    def test_available_lo(self):
        """Should return True when LO status is 'available'."""
        mock_db = MagicMock()
        row = MagicMock()
        row.status = "available"
        mock_db.execute.return_value.fetchone.return_value = row

        assert _check_availability(mock_db, 10) is True

    def test_no_availability_record_returns_false(self):
        """When no 'available' record exists, LO is not available."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        # The query only selects WHERE status = 'available', so no row = not available
        assert _check_availability(mock_db, 10) is False

    def test_table_missing_returns_true(self):
        """If lo_availability table doesn't exist, should return True."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("relation 'lo_availability' does not exist")

        assert _check_availability(mock_db, 10) is True


# =============================================================================
# Full route_lead flow
# =============================================================================

class TestRouteLead:
    """Test the complete route_lead function."""

    @patch("routes.lead_routing_routes._fallback_route")
    @patch("routes.lead_routing_routes._get_routing_rules", return_value=[])
    def test_no_rules_uses_fallback(self, mock_rules, mock_fallback):
        """When no rules exist, should use fallback routing."""
        mock_fallback.return_value = {"lo_id": 99, "lo_name": "Fallback LO", "reason": "Fallback", "rule_id": None}
        mock_db = MagicMock()

        result = route_lead(mock_db, org_id=1, loan_type="conventional")

        mock_fallback.assert_called_once_with(mock_db, 1)
        assert result["lo_id"] == 99

    @patch("routes.lead_routing_routes._fallback_route")
    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=None)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_no_available_lo_from_rule_falls_to_next(self, mock_rules, mock_rr, mock_avail, mock_fallback):
        """When round-robin returns None, should fall through to next rule or fallback."""
        mock_rules.return_value = [_make_rule(1, "loan_type", "VA", [10])]
        mock_fallback.return_value = {"lo_id": 99, "lo_name": "Fallback", "reason": "Fallback", "rule_id": None}
        mock_db = MagicMock()

        result = route_lead(mock_db, org_id=1, loan_type="VA")

        mock_fallback.assert_called_once()

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=10)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_lo_ids_as_comma_separated_string(self, mock_rules, mock_rr, mock_avail):
        """Should handle assigned_lo_ids stored as comma-separated string."""
        mock_rules.return_value = [_make_rule(1, "loan_type", "VA", "10,20,30")]

        mock_db = MagicMock()
        user_row = _make_user_row(10, "Test", "LO")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(mock_db, org_id=1, loan_type="VA")

        assert result is not None
        assert result["lo_id"] == 10

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=10)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_case_insensitive_loan_type_match(self, mock_rules, mock_rr, mock_avail):
        """Loan type matching should be case-insensitive."""
        mock_rules.return_value = [_make_rule(1, "loan_type", "conventional", [10])]

        mock_db = MagicMock()
        user_row = _make_user_row(10, "Test", "LO")
        mock_db.execute.return_value.fetchone.return_value = user_row

        # Lead has uppercase loan_type
        result = route_lead(mock_db, org_id=1, loan_type="CONVENTIONAL")
        assert result is not None

    @patch("routes.lead_routing_routes._check_availability", return_value=True)
    @patch("routes.lead_routing_routes._get_round_robin_next", return_value=10)
    @patch("routes.lead_routing_routes._get_routing_rules")
    def test_null_lead_attributes_dont_crash(self, mock_rules, mock_rr, mock_avail):
        """All-None lead attributes should not crash the routing engine."""
        mock_rules.return_value = [_make_rule(99, "default", "", [10])]

        mock_db = MagicMock()
        user_row = _make_user_row(10, "Default", "LO")
        mock_db.execute.return_value.fetchone.return_value = user_row

        result = route_lead(
            mock_db, org_id=1,
            loan_type=None, state=None, zip_code=None, language=None, source=None,
        )
        assert result is not None


# =============================================================================
# API endpoint tests
# =============================================================================

class TestRouteEndpoint:
    """Test POST /api/v1/lead-routing/route via TestClient."""

    @patch("routes.lead_routing_routes.route_lead", return_value={
        "lo_id": 10, "lo_name": "Test LO", "reason": "Matched loan_type=VA", "rule_id": 1
    })
    def test_route_endpoint_returns_assignment(self, mock_route, authenticated_client):
        """Should return the assigned LO details."""
        response = authenticated_client.post(
            "/api/v1/lead-routing/route",
            json={"loan_type": "VA", "state": "TX"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["assigned_lo_id"] == 10
        assert data["lo_name"] == "Test LO"
        assert "VA" in data["match_reason"]

    @patch("routes.lead_routing_routes.route_lead", return_value=None)
    def test_route_endpoint_404_when_no_lo(self, mock_route, authenticated_client):
        """Should return 404 when no eligible LO is found."""
        response = authenticated_client.post(
            "/api/v1/lead-routing/route",
            json={"loan_type": "jumbo"},
        )
        assert response.status_code == 404
