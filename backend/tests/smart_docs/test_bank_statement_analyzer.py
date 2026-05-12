"""
Tests for BankStatementAnalyzerService

Covers:
- Large deposit identification and classification
- NSF/overdraft detection
- IRS payment detection and payment plan identification
- Payroll deposit analysis
- Recurring payment detection
- Structuring detection
- Risk score calculation
- Balance analysis
- Transaction extraction (regex)
- Date normalization and amount parsing
- Helper methods
- Edge cases: empty statements, single transaction, large numbers

All tests mock the database layer -- no real DB or AI calls.

Run:
    pytest backend/tests/smart_docs/test_bank_statement_analyzer.py -v
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch

from services.smart_docs.bank_statement_analyzer import (
    BankStatementAnalyzerService,
    BankStatementAnalysis,
    LargeDeposit,
    NSFEvent,
    RecurringPayment,
    IRSPayment,
    PayrollDeposit,
    get_bank_statement_analyzer,
    ZERO,
    TWO_PLACES,
    LARGE_DEPOSIT_THRESHOLD,
    STRUCTURING_THRESHOLD,
    NEAR_STRUCTURING_THRESHOLD,
    NSF_SEVERITY_MAP,
    PAYROLL_KEYWORDS,
    IRS_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchall.return_value = []
    execute_result.fetchone.return_value = None
    db.execute.return_value = execute_result
    return db


@pytest.fixture
def service(mock_db):
    return BankStatementAnalyzerService(mock_db)


def _credit_txn(date_str, amount, description="DEPOSIT"):
    return {
        "date": date_str,
        "description": description,
        "amount": Decimal(str(amount)),
        "type": "credit",
        "balance": None,
    }


def _debit_txn(date_str, amount, description="PURCHASE"):
    return {
        "date": date_str,
        "description": description,
        "amount": Decimal(str(amount)),
        "type": "debit",
        "balance": None,
    }


# ===========================================================================
# 1. HELPER METHODS
# ===========================================================================

class TestToDecimal:
    def test_none_returns_zero(self, service):
        assert service._to_decimal(None) == ZERO

    def test_dollar_string(self, service):
        assert service._to_decimal("$1,234.56") == Decimal("1234.56")

    def test_plain_number(self, service):
        assert service._to_decimal("5000.00") == Decimal("5000.00")

    def test_empty_string(self, service):
        assert service._to_decimal("") == ZERO

    def test_garbage(self, service):
        assert service._to_decimal("abc") == ZERO

    def test_negative(self, service):
        assert service._to_decimal("-500.50") == Decimal("-500.50")


class TestNormalizeDate:
    def test_mm_dd_yyyy(self, service):
        assert service._normalize_date("01/15/2026") == "2026-01-15"

    def test_mm_dd_yy(self, service):
        result = service._normalize_date("03/20/26")
        assert result is not None
        assert "03-20" in result or "2026-03-20" in result

    def test_yyyy_mm_dd(self, service):
        assert service._normalize_date("2026-03-15") == "2026-03-15"

    def test_mm_dd_yyyy_dash(self, service):
        assert service._normalize_date("01-15-2026") == "2026-01-15"

    def test_none(self, service):
        assert service._normalize_date(None) is None

    def test_empty(self, service):
        assert service._normalize_date("") is None

    def test_invalid(self, service):
        assert service._normalize_date("not-a-date") is None


class TestParseAmount:
    def test_positive(self, service):
        assert service._parse_amount("$1,234.56") == Decimal("1234.56")

    def test_negative_parens(self, service):
        result = service._parse_amount("($500.00)")
        assert result == Decimal("-500.00")

    def test_negative_dash(self, service):
        result = service._parse_amount("-$300.00")
        assert result == Decimal("-300.00")

    def test_none(self, service):
        assert service._parse_amount(None) is None

    def test_empty(self, service):
        assert service._parse_amount("") is None

    def test_no_decimal(self, service):
        result = service._parse_amount("5000")
        assert result == Decimal("5000.00")


class TestDetermineFrequency:
    def test_weekly(self, service):
        dates = [date(2026, 1, 1) + timedelta(weeks=i) for i in range(4)]
        assert service._determine_frequency(dates) == "WEEKLY"

    def test_biweekly(self, service):
        dates = [date(2026, 1, 1) + timedelta(weeks=2 * i) for i in range(4)]
        assert service._determine_frequency(dates) == "BIWEEKLY"

    def test_monthly(self, service):
        dates = [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
        assert service._determine_frequency(dates) == "MONTHLY"

    def test_single_date(self, service):
        assert service._determine_frequency([date(2026, 1, 1)]) == "MONTHLY"

    def test_empty(self, service):
        assert service._determine_frequency([]) == "MONTHLY"


class TestNormalizePayee:
    def test_strips_reference_numbers(self, service):
        result = service._normalize_payee("CHASE CARD SERVICES #12345")
        assert "12345" not in result
        assert "CHASE CARD" in result

    def test_strips_dates(self, service):
        result = service._normalize_payee("PAYMENT 01/15/2026 CONF:998877")
        assert "01/15/2026" not in result
        assert "998877" not in result

    def test_empty_string(self, service):
        assert service._normalize_payee("") == ""

    def test_collapses_whitespace(self, service):
        result = service._normalize_payee("SOME    PAYEE    NAME")
        assert "  " not in result


class TestExtractPayrollSource:
    def test_strips_direct_dep_prefix(self, service):
        result = service._extract_payroll_source("DIRECT DEP ACME CORP")
        assert "ACME" in result

    def test_strips_ach_prefix(self, service):
        result = service._extract_payroll_source("ACH CREDIT MY EMPLOYER")
        assert "MY EMPLOYER" in result or "CREDIT" in result

    def test_unknown_for_empty(self, service):
        result = service._extract_payroll_source("")
        assert result == "Unknown"


# ===========================================================================
# 2. LARGE DEPOSIT ANALYSIS
# ===========================================================================

class TestAnalyzeLargeDeposits:
    def test_payroll_deposit_identified(self, service):
        txns = [_credit_txn("2026-01-15", 5000, "PAYROLL DIRECT DEP ACME CORP")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 1
        assert results[0].is_payroll is True
        assert results[0].needs_sourcing is False

    def test_transfer_not_needing_sourcing(self, service):
        txns = [_credit_txn("2026-01-15", 3000, "ONLINE TRANSFER FROM SAVINGS")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 1
        assert results[0].is_transfer is True
        assert results[0].needs_sourcing is False

    def test_unsourced_deposit_flagged(self, service):
        txns = [_credit_txn("2026-01-15", 8000, "CHECK DEPOSIT")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 1
        assert results[0].needs_sourcing is True
        assert results[0].sourcing_explanation is not None

    def test_below_threshold_excluded(self, service):
        txns = [_credit_txn("2026-01-15", 400, "SMALL DEPOSIT")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 0

    def test_near_structuring_threshold_high_risk(self, service):
        txns = [_credit_txn("2026-01-15", 9500, "CASH DEPOSIT")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 1
        assert results[0].risk_level == "HIGH"

    def test_payroll_amount_match(self, service):
        """Deposit matching known payroll amount within 5% is classified as payroll."""
        txns = [
            _credit_txn("2026-01-01", 3000, "PAYROLL ACME CORP"),
            _credit_txn("2026-01-15", 3050, "UNKNOWN DEPOSIT"),  # within 5% of 3000
        ]
        results = service.analyze_large_deposits(txns, "John Doe")
        # The unknown deposit should be identified as payroll via amount matching
        assert len(results) == 2
        assert all(r.is_payroll for r in results)

    def test_sorted_by_amount_descending(self, service):
        txns = [
            _credit_txn("2026-01-01", 1000, "DEPOSIT A"),
            _credit_txn("2026-01-15", 5000, "DEPOSIT B"),
            _credit_txn("2026-01-20", 3000, "DEPOSIT C"),
        ]
        results = service.analyze_large_deposits(txns, "John Doe")
        amounts = [r.amount for r in results]
        assert amounts == sorted(amounts, reverse=True)

    def test_empty_transactions(self, service):
        results = service.analyze_large_deposits([], "John Doe")
        assert results == []

    def test_zelle_venmo_identified_as_transfer(self, service):
        txns = [_credit_txn("2026-01-15", 2000, "ZELLE PAYMENT FROM JOHN")]
        results = service.analyze_large_deposits(txns, "John Doe")
        assert len(results) == 1
        assert results[0].is_transfer is True


# ===========================================================================
# 3. NSF/OVERDRAFT ANALYSIS
# ===========================================================================

class TestAnalyzeNSFEvents:
    def test_nsf_fee_detected(self, service):
        txns = [_debit_txn("2026-01-15", 35, "NSF FEE")]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 1
        assert severity == "MEDIUM"
        assert total_fees == Decimal("35.00")
        assert events[0].fee_charged == Decimal("35.00")

    def test_overdraft_fee_detected(self, service):
        txns = [_debit_txn("2026-01-15", 30, "OVERDRAFT FEE CHARGED")]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 1
        assert total_fees == Decimal("30.00")

    def test_returned_item_no_fee(self, service):
        txns = [_debit_txn("2026-01-15", 200, "RETURNED ITEM")]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 1
        assert total_fees == ZERO
        assert events[0].fee_charged is None

    def test_zero_nsf_is_low(self, service):
        events, count, severity, total_fees = service.analyze_nsf_events([])
        assert count == 0
        assert severity == "LOW"

    def test_five_or_more_is_critical(self, service):
        txns = [_debit_txn(f"2026-01-{i+1:02d}", 35, "NSF FEE") for i in range(5)]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 5
        assert severity == "CRITICAL"

    def test_three_nsf_is_high(self, service):
        txns = [_debit_txn(f"2026-01-{i+1:02d}", 35, "NSF FEE") for i in range(3)]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 3
        assert severity == "HIGH"


# ===========================================================================
# 4. IRS PAYMENT ANALYSIS
# ===========================================================================

class TestAnalyzeIRSPayments:
    def test_irs_payment_detected(self, service):
        txns = [_debit_txn("2026-01-15", 500, "IRS PAYMENT EFTPS")]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert len(payments) == 1
        assert total == Decimal("500.00")
        assert payments[0].payment_type == "ESTIMATED_TAX"

    def test_us_treasury_detected(self, service):
        txns = [_debit_txn("2026-01-15", 1000, "USTREAS 310 TAX REF")]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert len(payments) == 1

    def test_payment_plan_detected(self, service):
        """3+ consistent IRS payments indicate a payment plan."""
        txns = [
            _debit_txn("2026-01-15", 500, "IRS PAYMENT PLAN"),
            _debit_txn("2026-02-15", 500, "IRS PAYMENT PLAN"),
            _debit_txn("2026-03-15", 500, "IRS PAYMENT PLAN"),
        ]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert payment_plan is True
        assert all(p.is_recurring for p in payments)
        assert total == Decimal("1500.00")

    def test_inconsistent_amounts_no_payment_plan(self, service):
        """Varying amounts don't trigger payment plan detection."""
        txns = [
            _debit_txn("2026-01-15", 500, "IRS PAYMENT"),
            _debit_txn("2026-02-15", 200, "IRS PAYMENT"),
            _debit_txn("2026-03-15", 800, "IRS PAYMENT"),
        ]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert payment_plan is False

    def test_no_irs_payments(self, service):
        txns = [_debit_txn("2026-01-15", 500, "GROCERY STORE")]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert len(payments) == 0
        assert total == ZERO

    def test_penalty_type_detected(self, service):
        txns = [_debit_txn("2026-01-15", 200, "IRS PENALTY PAYMENT")]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert payments[0].payment_type == "PENALTY"

    def test_credits_ignored(self, service):
        """Only debit transactions are checked for IRS payments."""
        txns = [_credit_txn("2026-01-15", 500, "IRS TAX REFUND")]
        payments, total, payment_plan = service.analyze_irs_payments(txns)
        assert len(payments) == 0


# ===========================================================================
# 5. PAYROLL DEPOSIT ANALYSIS
# ===========================================================================

class TestAnalyzePayrollDeposits:
    def test_payroll_keywords_detected(self, service):
        txns = [
            _credit_txn("2026-01-01", 3000, "PAYROLL ACME CORP"),
            _credit_txn("2026-01-15", 3000, "PAYROLL ACME CORP"),
        ]
        deposits, est_monthly, consistency = service.analyze_payroll_deposits(txns)
        assert len(deposits) == 2
        assert consistency == "CONSISTENT"
        assert est_monthly is not None
        assert est_monthly > ZERO

    def test_variable_payroll(self, service):
        """Amounts varying by >5% but <15% from average are VARIABLE."""
        # avg=3250, max_variance=250/3250=7.7% which is >5% and <15%
        txns = [
            _credit_txn("2026-01-01", 3000, "PAYROLL ACME"),
            _credit_txn("2026-01-15", 3500, "PAYROLL ACME"),
        ]
        deposits, est_monthly, consistency = service.analyze_payroll_deposits(txns)
        assert consistency == "VARIABLE"

    def test_irregular_payroll(self, service):
        """Amounts varying by >15% are IRREGULAR."""
        txns = [
            _credit_txn("2026-01-01", 3000, "PAYROLL ACME"),
            _credit_txn("2026-01-15", 5000, "PAYROLL ACME"),  # 66% higher
        ]
        deposits, est_monthly, consistency = service.analyze_payroll_deposits(txns)
        assert consistency == "IRREGULAR"

    def test_no_payroll(self, service):
        txns = [_credit_txn("2026-01-15", 3000, "RANDOM DEPOSIT")]
        deposits, est_monthly, consistency = service.analyze_payroll_deposits(txns)
        assert len(deposits) == 0
        assert est_monthly is None
        assert consistency == "IRREGULAR"

    def test_monthly_income_estimation_biweekly(self, service):
        """Biweekly payroll: avg * 26 / 12."""
        txns = [
            _credit_txn("2026-01-01", 3000, "PAYROLL CORP"),
            _credit_txn("2026-01-15", 3000, "PAYROLL CORP"),
            _credit_txn("2026-01-29", 3000, "PAYROLL CORP"),
            _credit_txn("2026-02-12", 3000, "PAYROLL CORP"),
        ]
        deposits, est_monthly, consistency = service.analyze_payroll_deposits(txns)
        assert est_monthly is not None
        # Biweekly: 3000 * 26 / 12 = 6500
        assert est_monthly == Decimal("6500.00")


# ===========================================================================
# 6. RECURRING PAYMENT ANALYSIS
# ===========================================================================

class TestAnalyzeRecurringPayments:
    def test_auto_loan_detected(self, service):
        txns = [
            _debit_txn("2026-01-15", 450, "ALLY AUTO LOAN PAYMENT"),
            _debit_txn("2026-02-15", 450, "ALLY AUTO LOAN PAYMENT"),
        ]
        results = service.analyze_recurring_payments(txns)
        assert len(results) >= 1
        assert any(r.category == "auto_loan" for r in results)

    def test_student_loan_detected(self, service):
        txns = [
            _debit_txn("2026-01-15", 300, "NAVIENT STUDENT LOAN"),
            _debit_txn("2026-02-15", 300, "NAVIENT STUDENT LOAN"),
        ]
        results = service.analyze_recurring_payments(txns)
        assert any(r.category == "student_loan" for r in results)

    def test_single_occurrence_excluded(self, service):
        """Need at least 2 occurrences to be considered recurring."""
        txns = [_debit_txn("2026-01-15", 450, "ALLY AUTO LOAN")]
        results = service.analyze_recurring_payments(txns)
        assert len(results) == 0

    def test_mortgage_is_disclosed(self, service):
        """Mortgage/rent is in expected_categories, so is_disclosed=True."""
        txns = [
            _debit_txn("2026-01-01", 2000, "MORTGAGE PAYMENT"),
            _debit_txn("2026-02-01", 2000, "MORTGAGE PAYMENT"),
        ]
        results = service.analyze_recurring_payments(txns)
        mortgage = [r for r in results if r.category == "mortgage_rent"]
        assert len(mortgage) >= 1
        assert mortgage[0].is_disclosed is True

    def test_auto_loan_is_undisclosed(self, service):
        """Auto loan is NOT in expected_categories, so is_disclosed=False."""
        txns = [
            _debit_txn("2026-01-15", 450, "TOYOTA FINANCIAL SERVICES"),
            _debit_txn("2026-02-15", 450, "TOYOTA FINANCIAL SERVICES"),
        ]
        results = service.analyze_recurring_payments(txns)
        auto = [r for r in results if r.category == "auto_loan"]
        assert len(auto) >= 1
        assert auto[0].is_disclosed is False

    def test_high_variance_excluded(self, service):
        """Payments with >50% variance are not considered recurring."""
        txns = [
            _debit_txn("2026-01-15", 100, "SOME VENDOR"),
            _debit_txn("2026-02-15", 500, "SOME VENDOR"),
        ]
        results = service.analyze_recurring_payments(txns)
        # Average = 300, max variance = |500-300|/300 = 66.7% > 50%
        assert len(results) == 0

    def test_empty_transactions(self, service):
        results = service.analyze_recurring_payments([])
        assert results == []


# ===========================================================================
# 7. STRUCTURING DETECTION
# ===========================================================================

class TestDetectStructuring:
    def test_near_threshold_deposit(self, service):
        txns = [_credit_txn("2026-01-15", 9500, "CASH DEPOSIT")]
        flags = service._detect_structuring(txns)
        assert len(flags) >= 1
        assert "STRUCTURING_INDICATOR" in flags[0]

    def test_multiple_same_day_over_threshold(self, service):
        txns = [
            _credit_txn("2026-01-15", 6000, "DEPOSIT A"),
            _credit_txn("2026-01-15", 5000, "DEPOSIT B"),
        ]
        flags = service._detect_structuring(txns)
        assert any("Multiple deposits" in f for f in flags)

    def test_round_number_deposits(self, service):
        """3+ round-number deposits flagged as structuring."""
        txns = [
            _credit_txn("2026-01-01", 5000, "CASH"),
            _credit_txn("2026-01-15", 3000, "CASH"),
            _credit_txn("2026-02-01", 4000, "CASH"),
        ]
        flags = service._detect_structuring(txns)
        assert any("round-number" in f for f in flags)

    def test_two_round_deposits_not_flagged(self, service):
        """Only 2 round deposits is below threshold."""
        txns = [
            _credit_txn("2026-01-01", 5000, "CASH"),
            _credit_txn("2026-01-15", 3000, "CASH"),
        ]
        flags = service._detect_structuring(txns)
        round_flags = [f for f in flags if "round-number" in f]
        assert len(round_flags) == 0

    def test_no_structuring_clean_deposits(self, service):
        txns = [
            _credit_txn("2026-01-01", 3500.42, "PAYROLL"),
            _credit_txn("2026-01-15", 3500.42, "PAYROLL"),
        ]
        flags = service._detect_structuring(txns)
        assert len(flags) == 0

    def test_empty_transactions(self, service):
        assert service._detect_structuring([]) == []


# ===========================================================================
# 8. RISK SCORE CALCULATION
# ===========================================================================

class TestCalculateRiskScore:
    def _make_analysis(self, **kwargs):
        defaults = dict(
            loan_id=1, document_ids=[], statement_period_start=None,
            statement_period_end=None, account_type="CHECKING",
            institution_name=None, beginning_balance=None, ending_balance=None,
            average_daily_balance=None, lowest_balance=None, lowest_balance_date=None,
            large_deposits=[], total_large_deposits=ZERO, deposits_needing_sourcing=0,
            nsf_events=[], nsf_count=0, nsf_severity="LOW", total_nsf_fees=ZERO,
            overdraft_days=0, irs_payments=[], total_irs_payments=ZERO,
            irs_payment_plan_detected=False, payroll_deposits=[],
            estimated_monthly_income=None, income_consistency="CONSISTENT",
            recurring_payments=[], total_monthly_obligations=ZERO,
            undisclosed_obligations=[], risk_score=0, risk_level="LOW",
            flags=[], recommendations=[], tasks_to_create=[],
            ai_summary=None, ai_confidence=0,
        )
        defaults.update(kwargs)
        return BankStatementAnalysis(**defaults)

    def test_clean_analysis_is_low(self, service):
        analysis = self._make_analysis()
        score, level = service._calculate_risk_score(analysis)
        assert score == 0
        assert level == "LOW"

    def test_nsf_contributes_to_score(self, service):
        analysis = self._make_analysis(nsf_count=3)
        score, level = service._calculate_risk_score(analysis)
        assert score >= 15  # 3 * 5

    def test_large_deposits_contribute(self, service):
        analysis = self._make_analysis(deposits_needing_sourcing=3)
        score, level = service._calculate_risk_score(analysis)
        assert score >= 24  # 3 * 8

    def test_irs_payment_plan_adds_15(self, service):
        analysis = self._make_analysis(irs_payment_plan_detected=True)
        score, level = service._calculate_risk_score(analysis)
        assert score >= 15

    def test_structuring_adds_20(self, service):
        analysis = self._make_analysis(flags=["STRUCTURING_INDICATOR: something"])
        score, level = service._calculate_risk_score(analysis)
        assert score >= 20

    def test_critical_threshold(self, service):
        """Score >= 70 is CRITICAL."""
        analysis = self._make_analysis(
            nsf_count=5,  # 25
            deposits_needing_sourcing=4,  # 30 (capped)
            irs_payment_plan_detected=True,  # 15
            flags=["STRUCTURING_INDICATOR: test"],  # 20
        )
        score, level = service._calculate_risk_score(analysis)
        assert score >= 70
        assert level == "CRITICAL"

    def test_score_capped_at_100(self, service):
        analysis = self._make_analysis(
            nsf_count=10, deposits_needing_sourcing=10,
            irs_payment_plan_detected=True,
            flags=["STRUCTURING_INDICATOR: test"],
            undisclosed_obligations=[MagicMock()] * 10,
            overdraft_days=20,
        )
        score, level = service._calculate_risk_score(analysis)
        assert score <= 100


# ===========================================================================
# 9. BALANCE ANALYSIS
# ===========================================================================

class TestAnalyzeBalances:
    def test_metadata_balances(self, service):
        metadata = {
            "beginning_balance": Decimal("10000"),
            "ending_balance": Decimal("12000"),
            "average_daily_balance": Decimal("11000"),
        }
        result = service._analyze_balances([], metadata)
        assert result["beginning"] == Decimal("10000")
        assert result["ending"] == Decimal("12000")
        assert result["average_daily"] == Decimal("11000")

    def test_balances_from_transactions(self, service):
        txns = [
            {"date": "2026-01-01", "balance": Decimal("5000"), "type": "credit", "amount": Decimal("100")},
            {"date": "2026-01-15", "balance": Decimal("3000"), "type": "debit", "amount": Decimal("100")},
            {"date": "2026-01-30", "balance": Decimal("8000"), "type": "credit", "amount": Decimal("100")},
        ]
        result = service._analyze_balances(txns, {})
        assert result["lowest"] == Decimal("3000")
        assert result["lowest_date"] == "2026-01-15"
        assert result["beginning"] == Decimal("5000")
        assert result["ending"] == Decimal("8000")

    def test_empty_transactions_and_metadata(self, service):
        result = service._analyze_balances([], {})
        assert result["lowest"] is None
        assert result["beginning"] is None


class TestCountOverdraftDays:
    def test_negative_balances(self, service):
        txns = [
            {"date": "2026-01-01", "balance": Decimal("-100"), "type": "debit", "amount": Decimal("100")},
            {"date": "2026-01-02", "balance": Decimal("-50"), "type": "debit", "amount": Decimal("100")},
            {"date": "2026-01-03", "balance": Decimal("500"), "type": "credit", "amount": Decimal("100")},
        ]
        assert service._count_overdraft_days(txns) == 2

    def test_no_overdrafts(self, service):
        txns = [
            {"date": "2026-01-01", "balance": Decimal("500"), "type": "credit", "amount": Decimal("100")},
        ]
        assert service._count_overdraft_days(txns) == 0

    def test_same_date_counted_once(self, service):
        txns = [
            {"date": "2026-01-01", "balance": Decimal("-100"), "type": "debit", "amount": Decimal("50")},
            {"date": "2026-01-01", "balance": Decimal("-50"), "type": "debit", "amount": Decimal("50")},
        ]
        assert service._count_overdraft_days(txns) == 1


# ===========================================================================
# 10. FLAG GENERATION
# ===========================================================================

class TestGenerateFlags:
    def _make_analysis(self, **kwargs):
        defaults = dict(
            loan_id=1, document_ids=[], statement_period_start=None,
            statement_period_end=None, account_type="CHECKING",
            institution_name=None, beginning_balance=None, ending_balance=None,
            average_daily_balance=None, lowest_balance=None, lowest_balance_date=None,
            large_deposits=[], total_large_deposits=ZERO, deposits_needing_sourcing=0,
            nsf_events=[], nsf_count=0, nsf_severity="LOW", total_nsf_fees=ZERO,
            overdraft_days=0, irs_payments=[], total_irs_payments=ZERO,
            irs_payment_plan_detected=False, payroll_deposits=[],
            estimated_monthly_income=None, income_consistency="CONSISTENT",
            recurring_payments=[], total_monthly_obligations=ZERO,
            undisclosed_obligations=[], risk_score=0, risk_level="LOW",
            flags=[], recommendations=[], tasks_to_create=[],
            ai_summary=None, ai_confidence=0,
        )
        defaults.update(kwargs)
        return BankStatementAnalysis(**defaults)

    def test_large_deposit_flag(self, service):
        ld = LargeDeposit(
            date="2026-01-15", amount=Decimal("5000"), description="CHECK DEPOSIT",
            is_payroll=False, is_transfer=False, needs_sourcing=True,
            sourcing_explanation="...", risk_level="MEDIUM", notes="",
        )
        analysis = self._make_analysis(large_deposits=[ld])
        flags = service._generate_flags(analysis)
        assert any("LARGE_DEPOSIT" in f for f in flags)

    def test_nsf_flag(self, service):
        analysis = self._make_analysis(nsf_count=2, total_nsf_fees=Decimal("70"))
        flags = service._generate_flags(analysis)
        assert any("NSF_OVERDRAFT" in f for f in flags)

    def test_irs_payment_plan_flag(self, service):
        analysis = self._make_analysis(
            irs_payment_plan_detected=True,
            total_irs_payments=Decimal("1500"),
            irs_payments=[MagicMock()],
        )
        flags = service._generate_flags(analysis)
        assert any("IRS_PAYMENT_PLAN" in f for f in flags)

    def test_low_balance_flag(self, service):
        analysis = self._make_analysis(
            lowest_balance=Decimal("50"),
            lowest_balance_date="2026-01-15",
        )
        flags = service._generate_flags(analysis)
        assert any("LOW_BALANCE" in f for f in flags)

    def test_overdraft_days_flag(self, service):
        analysis = self._make_analysis(overdraft_days=3)
        flags = service._generate_flags(analysis)
        assert any("NEGATIVE_BALANCE" in f for f in flags)

    def test_irregular_income_flag(self, service):
        analysis = self._make_analysis(income_consistency="IRREGULAR")
        flags = service._generate_flags(analysis)
        assert any("IRREGULAR_INCOME" in f for f in flags)


# ===========================================================================
# 11. TASK GENERATION
# ===========================================================================

class TestGenerateTasks:
    def _make_analysis(self, **kwargs):
        defaults = dict(
            loan_id=1, document_ids=[], statement_period_start=None,
            statement_period_end=None, account_type="CHECKING",
            institution_name=None, beginning_balance=None, ending_balance=None,
            average_daily_balance=None, lowest_balance=None, lowest_balance_date=None,
            large_deposits=[], total_large_deposits=ZERO, deposits_needing_sourcing=0,
            nsf_events=[], nsf_count=0, nsf_severity="LOW", total_nsf_fees=ZERO,
            overdraft_days=0, irs_payments=[], total_irs_payments=ZERO,
            irs_payment_plan_detected=False, payroll_deposits=[],
            estimated_monthly_income=None, income_consistency="CONSISTENT",
            recurring_payments=[], total_monthly_obligations=ZERO,
            undisclosed_obligations=[], risk_score=0, risk_level="LOW",
            flags=[], recommendations=[], tasks_to_create=[],
            ai_summary=None, ai_confidence=0,
        )
        defaults.update(kwargs)
        return BankStatementAnalysis(**defaults)

    def test_large_deposit_task(self, service):
        ld = LargeDeposit(
            date="2026-01-15", amount=Decimal("8000"), description="CHECK",
            is_payroll=False, is_transfer=False, needs_sourcing=True,
            sourcing_explanation="...", risk_level="MEDIUM", notes="",
        )
        analysis = self._make_analysis(large_deposits=[ld])
        tasks = service._generate_tasks(analysis)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "review_large_deposit"

    def test_nsf_task(self, service):
        analysis = self._make_analysis(
            nsf_count=2, nsf_severity="HIGH", total_nsf_fees=Decimal("70")
        )
        tasks = service._generate_tasks(analysis)
        nsf_tasks = [t for t in tasks if "NSF" in t["title"]]
        assert len(nsf_tasks) >= 1

    def test_irs_payment_plan_task(self, service):
        analysis = self._make_analysis(
            irs_payment_plan_detected=True,
            total_irs_payments=Decimal("1500"),
        )
        tasks = service._generate_tasks(analysis)
        irs_tasks = [t for t in tasks if "IRS" in t["title"]]
        assert len(irs_tasks) >= 1
        assert irs_tasks[0]["priority"] == "critical"

    def test_undisclosed_obligation_task(self, service):
        rp = RecurringPayment(
            category="auto_loan", payee="ALLY AUTO",
            average_amount=Decimal("450.00"), frequency="MONTHLY",
            occurrences=3, total_amount=Decimal("1350.00"),
            is_disclosed=False, dates=["2026-01-15", "2026-02-15", "2026-03-15"],
        )
        analysis = self._make_analysis(undisclosed_obligations=[rp])
        tasks = service._generate_tasks(analysis)
        assert len(tasks) >= 1
        assert "undisclosed" in tasks[0]["title"].lower()


# ===========================================================================
# 12. TEMPLATE SUMMARY
# ===========================================================================

class TestTemplateSummary:
    def _make_analysis(self, **kwargs):
        defaults = dict(
            loan_id=1, document_ids=[], statement_period_start=None,
            statement_period_end=None, account_type="CHECKING",
            institution_name=None, beginning_balance=None, ending_balance=None,
            average_daily_balance=None, lowest_balance=None, lowest_balance_date=None,
            large_deposits=[], total_large_deposits=ZERO, deposits_needing_sourcing=0,
            nsf_events=[], nsf_count=0, nsf_severity="LOW", total_nsf_fees=ZERO,
            overdraft_days=0, irs_payments=[], total_irs_payments=ZERO,
            irs_payment_plan_detected=False, payroll_deposits=[],
            estimated_monthly_income=None, income_consistency="CONSISTENT",
            recurring_payments=[], total_monthly_obligations=ZERO,
            undisclosed_obligations=[], risk_score=0, risk_level="LOW",
            flags=[], recommendations=[], tasks_to_create=[],
            ai_summary=None, ai_confidence=0,
        )
        defaults.update(kwargs)
        return BankStatementAnalysis(**defaults)

    def test_clean_summary(self, service):
        analysis = self._make_analysis(risk_score=0, risk_level="LOW")
        summary = service._generate_template_summary(analysis)
        assert "No significant concerns" in summary

    def test_summary_with_issues(self, service):
        analysis = self._make_analysis(
            institution_name="First National Bank",
            ending_balance=Decimal("5000"),
            deposits_needing_sourcing=2,
            total_large_deposits=Decimal("15000"),
            nsf_count=1,
            nsf_severity="MEDIUM",
            risk_score=30,
            risk_level="MEDIUM",
        )
        summary = service._generate_template_summary(analysis)
        assert "First National Bank" in summary
        assert "MEDIUM" in summary


# ===========================================================================
# 13. FACTORY FUNCTION
# ===========================================================================

class TestFactory:
    def test_get_bank_statement_analyzer(self, mock_db):
        svc = get_bank_statement_analyzer(mock_db)
        assert isinstance(svc, BankStatementAnalyzerService)


# ===========================================================================
# 14. TRANSACTION EXTRACTION (REGEX)
# ===========================================================================

class TestExtractTransactions:
    def test_simple_format(self, service):
        """Parse MM/DD/YYYY description amount format."""
        ocr = "01/15/2026  DIRECT DEP ACME CORP  $3,500.42\n"
        txns = service._extract_transactions(ocr)
        assert len(txns) >= 1
        assert txns[0]["amount"] == Decimal("3500.42")

    def test_deduplication(self, service):
        """Identical lines are deduplicated."""
        ocr = (
            "01/15/2026  PAYROLL  $3,000.00\n"
            "01/15/2026  PAYROLL  $3,000.00\n"
        )
        txns = service._extract_transactions(ocr)
        # Should be deduplicated to 1
        credit_txns = [t for t in txns if t["amount"] == Decimal("3000.00")]
        assert len(credit_txns) == 1

    def test_empty_text(self, service):
        assert service._extract_transactions("") == []

    def test_negative_amount(self, service):
        ocr = "01/15/2026  PURCHASE  -$150.00\n"
        txns = service._extract_transactions(ocr)
        if txns:
            assert txns[0]["type"] == "debit"

    def test_sorted_by_date(self, service):
        ocr = (
            "03/15/2026  LATER TXN  $100.00\n"
            "01/15/2026  EARLIER TXN  $200.00\n"
        )
        txns = service._extract_transactions(ocr)
        if len(txns) >= 2:
            assert txns[0]["date"] <= txns[1]["date"]
