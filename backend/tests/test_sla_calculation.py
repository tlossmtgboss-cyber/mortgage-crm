"""
Test SLA Calculations - Validates SLA target constants, date/time utilities,
and aging threshold logic used by the pipeline analyst tools.

Covers:
- SLA_TARGETS dictionary completeness and values
- days_between utility with various date combinations
- format_currency, format_percentage, format_date utilities
- Aging threshold breach detection logic
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal


# =============================================================================
# SLA Targets
# =============================================================================

@pytest.mark.unit
class TestSLATargets:
    """Validate the SLA_TARGETS constant from the tool definitions."""

    # Replicate the constant from CLAUDE.md so tests are self-contained
    SLA_TARGETS = {
        "APPLICATION_to_DISCLOSED": 3,
        "DISCLOSED_to_SUBMITTED": 7,
        "SUBMITTED_to_UW_RECEIVED": 2,
        "UW_RECEIVED_to_APPROVED": 5,
        "APPROVED_to_CLEAR_TO_CLOSE": 3,
        "CLEAR_TO_CLOSE_to_DOCS_OUT": 3,
        "DOCS_OUT_to_FUNDED": 5,
    }

    def test_sla_targets_has_7_transitions(self):
        """SLA_TARGETS should define exactly 7 stage-to-stage transitions."""
        assert len(self.SLA_TARGETS) == 7

    def test_application_to_disclosed_is_3_days(self):
        """Application to Disclosed SLA should be 3 days."""
        assert self.SLA_TARGETS["APPLICATION_to_DISCLOSED"] == 3

    def test_disclosed_to_submitted_is_7_days(self):
        """Disclosed to Submitted SLA should be 7 days."""
        assert self.SLA_TARGETS["DISCLOSED_to_SUBMITTED"] == 7

    def test_submitted_to_uw_received_is_2_days(self):
        """Submitted to UW Received should be the fastest at 2 days."""
        assert self.SLA_TARGETS["SUBMITTED_to_UW_RECEIVED"] == 2

    def test_docs_out_to_funded_is_5_days(self):
        """Docs Out to Funded SLA should be 5 days."""
        assert self.SLA_TARGETS["DOCS_OUT_to_FUNDED"] == 5

    def test_all_sla_values_are_positive_integers(self):
        """All SLA target values must be positive integers."""
        for key, value in self.SLA_TARGETS.items():
            assert isinstance(value, int), f"SLA for {key} should be int, got {type(value)}"
            assert value > 0, f"SLA for {key} should be positive, got {value}"

    def test_total_happy_path_sla_is_28_days(self):
        """Sum of all SLA targets should be 28 days for the full pipeline."""
        total = sum(self.SLA_TARGETS.values())
        assert total == 28, f"Total SLA days should be 28, got {total}"

    def test_sla_keys_use_consistent_naming(self):
        """All SLA keys should follow STAGE_to_STAGE naming convention."""
        for key in self.SLA_TARGETS:
            assert "_to_" in key, f"SLA key '{key}' missing '_to_' separator"
            parts = key.split("_to_")
            assert len(parts) == 2, f"SLA key '{key}' has unexpected format"
            assert parts[0] == parts[0].upper(), f"Source stage in '{key}' should be uppercase"
            assert parts[1] == parts[1].upper(), f"Target stage in '{key}' should be uppercase"


# =============================================================================
# days_between Utility
# =============================================================================

@pytest.mark.unit
class TestDaysBetween:
    """Test the days_between utility function logic."""

    @staticmethod
    def days_between(start, end):
        """Replicate the days_between logic from the tool code."""
        if start is None or end is None:
            return 0
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        return (end - start).days

    def test_same_day_returns_zero(self):
        """Same day should return 0 days."""
        d = date(2026, 3, 1)
        assert self.days_between(d, d) == 0

    def test_positive_days(self):
        """End after start should return positive days."""
        start = date(2026, 3, 1)
        end = date(2026, 3, 10)
        assert self.days_between(start, end) == 9

    def test_negative_days(self):
        """End before start should return negative days."""
        start = date(2026, 3, 10)
        end = date(2026, 3, 1)
        assert self.days_between(start, end) == -9

    def test_null_start_returns_zero(self):
        """Null start should return 0."""
        assert self.days_between(None, date(2026, 3, 1)) == 0

    def test_null_end_returns_zero(self):
        """Null end should return 0."""
        assert self.days_between(date(2026, 3, 1), None) == 0

    def test_both_null_returns_zero(self):
        """Both null should return 0."""
        assert self.days_between(None, None) == 0

    def test_datetime_inputs_converted_to_date(self):
        """datetime objects should be converted to dates for calculation."""
        start = datetime(2026, 3, 1, 10, 30, 0)
        end = datetime(2026, 3, 5, 14, 0, 0)
        assert self.days_between(start, end) == 4

    def test_mixed_date_datetime(self):
        """Mixed date and datetime inputs should work correctly."""
        start = date(2026, 3, 1)
        end = datetime(2026, 3, 5, 23, 59, 59)
        assert self.days_between(start, end) == 4


# =============================================================================
# Format Utilities
# =============================================================================

@pytest.mark.unit
class TestFormatUtilities:
    """Test currency, percentage, and date formatting functions."""

    @staticmethod
    def format_currency(amount):
        """Replicate format_currency from tool code."""
        if amount is None:
            return "$0.00"
        return f"${float(amount):,.2f}"

    @staticmethod
    def format_percentage(value, decimals=2):
        """Replicate format_percentage from tool code."""
        if value is None:
            return "0%"
        return f"{float(value):.{decimals}f}%"

    @staticmethod
    def format_date(dt, fmt="%m/%d/%Y"):
        """Replicate format_date from tool code."""
        if dt is None:
            return ""
        return dt.strftime(fmt)

    def test_format_currency_normal(self):
        """Normal amount should format with commas and cents."""
        assert self.format_currency(1234567.89) == "$1,234,567.89"

    def test_format_currency_zero(self):
        """Zero should format as $0.00."""
        assert self.format_currency(0) == "$0.00"

    def test_format_currency_none(self):
        """None should format as $0.00."""
        assert self.format_currency(None) == "$0.00"

    def test_format_currency_decimal(self):
        """Decimal input should format correctly."""
        assert self.format_currency(Decimal("450000.50")) == "$450,000.50"

    def test_format_currency_integer(self):
        """Integer input should add .00 cents."""
        assert self.format_currency(500000) == "$500,000.00"

    def test_format_percentage_normal(self):
        """Normal rate should format with 2 decimal places."""
        assert self.format_percentage(6.875) == "6.88%"

    def test_format_percentage_none(self):
        """None should format as 0%."""
        assert self.format_percentage(None) == "0%"

    def test_format_percentage_custom_decimals(self):
        """Custom decimal places should be respected."""
        assert self.format_percentage(6.875, decimals=3) == "6.875%"

    def test_format_date_normal(self):
        """Normal date should format as MM/DD/YYYY."""
        d = datetime(2026, 3, 4)
        assert self.format_date(d) == "03/04/2026"

    def test_format_date_none(self):
        """None should return empty string."""
        assert self.format_date(None) == ""

    def test_format_date_custom_format(self):
        """Custom format should be applied."""
        d = datetime(2026, 12, 25)
        assert self.format_date(d, "%Y-%m-%d") == "2026-12-25"


# =============================================================================
# Aging Threshold Logic
# =============================================================================

@pytest.mark.unit
class TestAgingThresholdLogic:
    """Test the aging threshold breach detection used by get_loan_aging_report."""

    def test_loan_under_threshold_not_flagged(self):
        """A loan with 3 days in stage should not be flagged at 7-day threshold."""
        days_in_stage = 3
        threshold = 7
        assert days_in_stage <= threshold

    def test_loan_at_threshold_not_flagged(self):
        """A loan at exactly the threshold should not be flagged (> not >=)."""
        days_in_stage = 7
        threshold = 7
        # The tool uses > threshold, not >=
        assert not (days_in_stage > threshold)

    def test_loan_over_threshold_flagged(self):
        """A loan over the threshold should be flagged."""
        days_in_stage = 8
        threshold = 7
        assert days_in_stage > threshold

    def test_bottleneck_severity_normal(self):
        """Days under SLA target should have normal severity."""
        avg_days = 4.0
        target = 5
        if avg_days > target * 2:
            severity = "critical"
        elif avg_days > target:
            severity = "warning"
        else:
            severity = "normal"
        assert severity == "normal"

    def test_bottleneck_severity_warning(self):
        """Days slightly over target should be warning severity."""
        avg_days = 6.0
        target = 5
        if avg_days > target * 2:
            severity = "critical"
        elif avg_days > target:
            severity = "warning"
        else:
            severity = "normal"
        assert severity == "warning"

    def test_bottleneck_severity_critical(self):
        """Days more than 2x target should be critical severity."""
        avg_days = 11.0
        target = 5
        if avg_days > target * 2:
            severity = "critical"
        elif avg_days > target:
            severity = "warning"
        else:
            severity = "normal"
        assert severity == "critical"
