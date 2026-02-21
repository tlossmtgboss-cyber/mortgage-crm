"""
Comparison Logic Tests for Estimate Parser Service
"""
import pytest
from unittest.mock import Mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("boto3", reason="boto3 not installed")

from services.estimate_parser_service import EstimateParserService, LoanEstimate, ComparisonResult


class TestEstimateComparison:

    def test_comparison_winner_cash_to_close(self, db_session):
        """Test that Cash to Close is the primary comparison metric"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000  # Lower
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000,
            apr=7.250,
            monthly_principal_and_interest=2661.21,
            total_closing_costs=14000,
            cash_to_close=67500  # Higher
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions
        assert comparison.winner == "A"  # $65k vs $67.5k
        assert "cash" in comparison.reason.lower() or "close" in comparison.reason.lower()
        assert comparison.savings_amount == 2500  # $67.5k - $65k

    def test_comparison_fallback_to_closing_costs(self, db_session):
        """Test fallback to Total Closing Costs when Cash to Close unavailable"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            total_closing_costs=12500,
            cash_to_close=None  # Missing
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000,
            total_closing_costs=14000,
            cash_to_close=None  # Missing
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions
        assert comparison.winner == "A"
        assert "closing" in comparison.reason.lower() or "cost" in comparison.reason.lower()
        assert comparison.savings_amount == 1500

    def test_comparison_fallback_to_apr(self, db_session):
        """Test fallback to APR when Cash to Close and Closing Costs are equal"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            total_closing_costs=12500,
            cash_to_close=65000
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000,
            apr=7.250,
            total_closing_costs=12500,  # Same
            cash_to_close=65000  # Same
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions
        assert comparison.winner == "A"
        assert "apr" in comparison.reason.lower()

    def test_comparison_fallback_to_monthly_payment(self, db_session):
        """Test fallback to Monthly P&I as last resort"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,  # Same
            apr=7.125,  # Same
            monthly_principal_and_interest=2700.00,  # Higher
            total_closing_costs=12500,  # Same
            cash_to_close=65000  # Same
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions
        assert comparison.winner == "A"
        assert "monthly" in comparison.reason.lower() or "payment" in comparison.reason.lower()

    def test_comparison_no_clear_winner(self, db_session):
        """Test comparison when estimates are identical"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000
        )

        # Identical estimate
        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            monthly_principal_and_interest=2632.45,
            total_closing_costs=12500,
            cash_to_close=65000
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions - no winner when identical
        assert comparison.winner is None
        assert comparison.savings_amount is None or comparison.savings_amount == 0

    def test_comparison_b_wins(self, db_session):
        """Test that estimate B can win"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000,
            apr=7.250,
            total_closing_costs=15000,
            cash_to_close=70000  # Higher
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            apr=7.125,
            total_closing_costs=12500,
            cash_to_close=65000  # Lower
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions
        assert comparison.winner == "B"
        assert comparison.savings_amount == 5000

    def test_comparison_result_structure(self, db_session):
        """Test that comparison result has correct structure"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875,
            cash_to_close=65000
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000,
            cash_to_close=67500
        )

        comparison = service.compare_estimates(estimate_a, estimate_b)

        # Assertions - verify ComparisonResult structure
        assert isinstance(comparison, ComparisonResult)
        assert hasattr(comparison, 'winner')
        assert hasattr(comparison, 'reason')
        assert hasattr(comparison, 'savings_amount')
        assert hasattr(comparison, 'estimate_a')
        assert hasattr(comparison, 'estimate_b')

    def test_comparison_with_partial_data(self, db_session):
        """Test comparison handles partial data gracefully"""
        service = EstimateParserService(db_session)

        estimate_a = LoanEstimate(
            loan_amount=400000,
            interest_rate=6.875
            # Missing many fields
        )

        estimate_b = LoanEstimate(
            loan_amount=400000,
            interest_rate=7.000
            # Missing many fields
        )

        # Should not raise exception
        comparison = service.compare_estimates(estimate_a, estimate_b)

        # May not have a winner if no comparable fields
        assert comparison is not None


class TestComparisonResult:
    """Test ComparisonResult model"""

    def test_comparison_result_creation(self):
        """Test creating a ComparisonResult"""
        estimate_a = LoanEstimate(loan_amount=400000)
        estimate_b = LoanEstimate(loan_amount=400000)

        result = ComparisonResult(
            winner="A",
            reason="Lower cash to close",
            savings_amount=2500,
            estimate_a=estimate_a,
            estimate_b=estimate_b
        )

        assert result.winner == "A"
        assert result.reason == "Lower cash to close"
        assert result.savings_amount == 2500

    def test_comparison_result_no_winner(self):
        """Test ComparisonResult with no winner"""
        estimate_a = LoanEstimate(loan_amount=400000)
        estimate_b = LoanEstimate(loan_amount=400000)

        result = ComparisonResult(
            winner=None,
            reason=None,
            savings_amount=None,
            estimate_a=estimate_a,
            estimate_b=estimate_b
        )

        assert result.winner is None
        assert result.savings_amount is None
