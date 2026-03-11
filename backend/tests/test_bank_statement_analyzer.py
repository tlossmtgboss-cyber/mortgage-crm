"""
Test Bank Statement Analyzer Service

Comprehensive tests for the BankStatementAnalyzerService covering all
analysis modules: large deposits, NSF/overdraft detection, IRS payments,
payroll verification, recurring payments, structuring detection, balance
analysis, risk scoring, and flag/task generation.

All database and AI (Anthropic) calls are mocked.
"""

import pytest
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from services.smart_docs.bank_statement_analyzer import (
    BankStatementAnalyzerService,
    BankStatementAnalysis,
    LargeDeposit,
    NSFEvent,
    RecurringPayment,
    IRSPayment,
    PayrollDeposit,
    get_bank_statement_analyzer,
    LARGE_DEPOSIT_THRESHOLD,
    STRUCTURING_THRESHOLD,
    NEAR_STRUCTURING_THRESHOLD,
    NSF_SEVERITY_MAP,
    PAYROLL_KEYWORDS,
    IRS_KEYWORDS,
    RECURRING_CATEGORIES,
    ZERO,
    TWO_PLACES,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    db.execute.return_value.fetchone.return_value = None
    return db


@pytest.fixture
def service(mock_db):
    """Create analyzer service with mocked DB and no Anthropic key."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        svc = BankStatementAnalyzerService(mock_db)
    return svc


@pytest.fixture
def service_with_ai(mock_db):
    """Create analyzer service with a mocked Anthropic API key."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key-123"}, clear=False):
        svc = BankStatementAnalyzerService(mock_db)
    return svc


def _txn(date_str, description, amount, txn_type="credit", balance=None):
    """Helper to build a transaction dict."""
    return {
        "date": date_str,
        "description": description,
        "amount": Decimal(str(amount)),
        "type": txn_type,
        "balance": Decimal(str(balance)) if balance is not None else None,
    }


def _make_analysis(**overrides):
    """Build a BankStatementAnalysis with sensible defaults, overridden as needed."""
    defaults = dict(
        loan_id=1,
        document_ids=[10],
        statement_period_start="2026-01-01",
        statement_period_end="2026-02-28",
        account_type="CHECKING",
        institution_name="Test Bank",
        beginning_balance=Decimal("5000.00"),
        ending_balance=Decimal("4500.00"),
        average_daily_balance=Decimal("4750.00"),
        lowest_balance=Decimal("1200.00"),
        lowest_balance_date="2026-01-15",
        large_deposits=[],
        total_large_deposits=ZERO,
        deposits_needing_sourcing=0,
        nsf_events=[],
        nsf_count=0,
        nsf_severity="LOW",
        total_nsf_fees=ZERO,
        overdraft_days=0,
        irs_payments=[],
        total_irs_payments=ZERO,
        irs_payment_plan_detected=False,
        payroll_deposits=[],
        estimated_monthly_income=None,
        income_consistency="CONSISTENT",
        recurring_payments=[],
        total_monthly_obligations=ZERO,
        undisclosed_obligations=[],
        risk_score=0,
        risk_level="LOW",
        flags=[],
        recommendations=[],
        tasks_to_create=[],
        ai_summary=None,
        ai_confidence=0,
    )
    defaults.update(overrides)
    return BankStatementAnalysis(**defaults)


# =============================================================================
# 1. LARGE DEPOSIT DETECTION
# =============================================================================

@pytest.mark.unit
class TestLargeDepositDetection:
    """Large deposits >= $500 requiring sourcing per Fannie Mae B3-4.2-01."""

    def test_deposit_above_threshold_flagged(self, service):
        """A non-payroll credit >= $500 must be flagged as needing sourcing."""
        txns = [
            _txn("2026-01-10", "WIRE FROM JOHN SMITH", 5000),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 1
        assert result[0].needs_sourcing is True
        assert result[0].is_payroll is False
        assert result[0].amount == Decimal("5000.00")

    def test_payroll_deposit_not_flagged_for_sourcing(self, service):
        """Deposits matching payroll keywords should NOT need sourcing."""
        txns = [
            _txn("2026-01-15", "ADP PAYROLL - ACME INC", 3500),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 1
        assert result[0].is_payroll is True
        assert result[0].needs_sourcing is False
        assert result[0].risk_level == "LOW"

    def test_transfer_deposit_not_flagged_for_sourcing(self, service):
        """Internal transfers (Zelle, Venmo, xfer) should not need sourcing."""
        txns = [
            _txn("2026-01-20", "Online Transfer from Savings", 2000),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 1
        assert result[0].is_transfer is True
        assert result[0].needs_sourcing is False

    def test_deposit_below_threshold_excluded(self, service):
        """Credits below $500 should not appear in the large deposit list."""
        txns = [
            _txn("2026-01-05", "Refund", 200),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 0

    def test_deposit_near_structuring_threshold_high_risk(self, service):
        """A non-payroll deposit >= $9,000 gets HIGH risk level."""
        txns = [
            _txn("2026-01-10", "CASHIERS CHECK", 9500),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 1
        assert result[0].risk_level == "HIGH"
        assert result[0].needs_sourcing is True

    def test_consistent_payroll_amount_identified(self, service):
        """A large deposit whose amount is within 5% of a known payroll deposit
        should be classified as payroll even without payroll keywords."""
        txns = [
            _txn("2026-01-01", "ADP PAYROLL - ACME", 3000),
            _txn("2026-01-15", "ADP PAYROLL - ACME", 3000),
            # Same amount, no keyword -- should still be identified as payroll
            _txn("2026-02-01", "ACH CREDIT ACME INC", 3010),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        acme_no_keyword = [r for r in result if "ACH CREDIT" in r.description]
        assert len(acme_no_keyword) == 1
        assert acme_no_keyword[0].is_payroll is True
        assert acme_no_keyword[0].needs_sourcing is False

    def test_multiple_large_deposits_sorted_by_amount_desc(self, service):
        """Results should be sorted by amount, largest first."""
        txns = [
            _txn("2026-01-10", "DEPOSIT A", 1000),
            _txn("2026-01-11", "DEPOSIT B", 8000),
            _txn("2026-01-12", "DEPOSIT C", 3000),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        amounts = [r.amount for r in result]
        assert amounts == sorted(amounts, reverse=True)


# =============================================================================
# 2. NSF / OVERDRAFT DETECTION
# =============================================================================

@pytest.mark.unit
class TestNSFDetection:
    """NSF/overdraft event identification and severity classification."""

    def test_nsf_keyword_detected(self, service):
        """Transactions with 'NSF' in description should be flagged."""
        txns = [
            _txn("2026-01-05", "NSF FEE", 35, "debit"),
        ]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 1
        assert len(events) == 1
        assert events[0].description == "NSF FEE"

    def test_overdraft_fee_counted(self, service):
        """Overdraft fee transactions should accumulate in total_fees."""
        txns = [
            _txn("2026-01-05", "OVERDRAFT FEE", 35, "debit"),
            _txn("2026-01-10", "OD FEE", 35, "debit"),
        ]
        events, count, severity, total_fees = service.analyze_nsf_events(txns)
        assert count == 2
        assert total_fees == Decimal("70.00")

    def test_nsf_severity_zero_is_low(self, service):
        """Zero NSF events should yield LOW severity."""
        _, _, severity, _ = service.analyze_nsf_events([])
        assert severity == "LOW"

    def test_nsf_severity_one_is_medium(self, service):
        """One NSF event should yield MEDIUM severity."""
        txns = [_txn("2026-01-05", "NSF ITEM", 100, "debit")]
        _, count, severity, _ = service.analyze_nsf_events(txns)
        assert count == 1
        assert severity == "MEDIUM"

    def test_nsf_severity_five_or_more_is_critical(self, service):
        """Five or more NSF events should yield CRITICAL severity."""
        txns = [
            _txn(f"2026-01-{i:02d}", f"NSF FEE #{i}", 35, "debit")
            for i in range(1, 7)
        ]
        _, count, severity, _ = service.analyze_nsf_events(txns)
        assert count == 6
        assert severity == "CRITICAL"

    def test_nsf_with_resulting_balance(self, service):
        """NSF events should capture the resulting balance if available."""
        txns = [
            _txn("2026-01-05", "RETURNED ITEM - NSF", 200, "debit", balance=-50),
        ]
        events, _, _, _ = service.analyze_nsf_events(txns)
        assert events[0].resulting_balance == Decimal("-50.00")


# =============================================================================
# 3. IRS PAYMENT DETECTION
# =============================================================================

@pytest.mark.unit
class TestIRSPaymentDetection:
    """IRS payment identification including estimated taxes and payment plans."""

    def test_irs_debit_detected(self, service):
        """Debits mentioning 'IRS' should be captured as IRS payments."""
        txns = [
            _txn("2026-01-15", "IRS PAYMENT", 2500, "debit"),
        ]
        payments, total, plan = service.analyze_irs_payments(txns)
        assert len(payments) == 1
        assert total == Decimal("2500.00")
        assert plan is False

    def test_estimated_tax_classification(self, service):
        """Payments mentioning 'estimated' or 'eftps' should be classified ESTIMATED_TAX."""
        txns = [
            _txn("2026-01-15", "EFTPS TAX PAYMENT", 5000, "debit"),
        ]
        payments, _, _ = service.analyze_irs_payments(txns)
        assert payments[0].payment_type == "ESTIMATED_TAX"

    def test_irs_payment_plan_detected_three_consistent(self, service):
        """Three or more IRS payments of similar amounts should flag a payment plan."""
        txns = [
            _txn("2026-01-15", "IRS PAYMENT PLAN", 500, "debit"),
            _txn("2026-02-15", "IRS PAYMENT PLAN", 510, "debit"),
            _txn("2026-03-15", "IRS PAYMENT PLAN", 495, "debit"),
        ]
        payments, total, plan = service.analyze_irs_payments(txns)
        assert plan is True
        assert all(p.is_recurring for p in payments)
        # With consistent amounts, type should be set to PAYMENT_PLAN
        for p in payments:
            assert p.payment_type == "PAYMENT_PLAN"

    def test_irs_credit_ignored(self, service):
        """Credit transactions mentioning IRS (refunds) should not be flagged."""
        txns = [
            _txn("2026-03-01", "IRS TAX REFUND", 3000, "credit"),
        ]
        payments, total, _ = service.analyze_irs_payments(txns)
        assert len(payments) == 0
        assert total == ZERO

    def test_estimated_quarterly_taxes_recurring(self, service):
        """Two+ estimated tax payments should be marked as recurring."""
        txns = [
            _txn("2026-01-15", "EFTPS ESTIMATED TAX Q4", 2500, "debit"),
            _txn("2026-04-15", "EFTPS ESTIMATED TAX Q1", 2500, "debit"),
        ]
        payments, _, plan = service.analyze_irs_payments(txns)
        # Not a payment plan (amounts match but classified as estimated)
        assert plan is False
        # But estimated payments should be marked recurring
        estimated = [p for p in payments if p.payment_type == "ESTIMATED_TAX"]
        assert len(estimated) == 2
        assert all(p.is_recurring for p in estimated)

    def test_irs_penalty_classification(self, service):
        """Payments mentioning 'penalty' should be classified as PENALTY."""
        txns = [
            _txn("2026-01-15", "IRS PENALTY PAYMENT", 750, "debit"),
        ]
        payments, _, _ = service.analyze_irs_payments(txns)
        assert payments[0].payment_type == "PENALTY"


# =============================================================================
# 4. PAYROLL DEPOSIT VERIFICATION
# =============================================================================

@pytest.mark.unit
class TestPayrollDepositVerification:
    """Payroll deposit identification, frequency detection, and consistency."""

    def test_payroll_keyword_match(self, service):
        """Credits with payroll keywords should be identified as payroll."""
        txns = [
            _txn("2026-01-15", "PAYROLL ACME CORP", 3000, "credit"),
            _txn("2026-01-31", "PAYROLL ACME CORP", 3000, "credit"),
        ]
        deposits, est_income, consistency = service.analyze_payroll_deposits(txns)
        assert len(deposits) == 2
        assert all(d.source != "Unknown" for d in deposits)

    def test_no_payroll_returns_irregular(self, service):
        """If no payroll keywords found, return empty list and IRREGULAR."""
        txns = [
            _txn("2026-01-05", "ATM WITHDRAWAL", 200, "debit"),
        ]
        deposits, est_income, consistency = service.analyze_payroll_deposits(txns)
        assert deposits == []
        assert est_income is None
        assert consistency == "IRREGULAR"

    def test_consistent_amounts_labeled_consistent(self, service):
        """Payroll deposits within 5% variance should be CONSISTENT."""
        txns = [
            _txn("2026-01-01", "DIRECT DEPOSIT ACME", 3000, "credit"),
            _txn("2026-01-15", "DIRECT DEPOSIT ACME", 3000, "credit"),
            _txn("2026-02-01", "DIRECT DEPOSIT ACME", 3010, "credit"),
        ]
        deposits, _, consistency = service.analyze_payroll_deposits(txns)
        assert consistency == "CONSISTENT"

    def test_variable_amounts_labeled_variable(self, service):
        """Payroll deposits with 5-15% variance should be VARIABLE."""
        txns = [
            _txn("2026-01-01", "PAYROLL ACME CORP", 3000, "credit"),
            _txn("2026-01-15", "PAYROLL ACME CORP", 3400, "credit"),
        ]
        _, _, consistency = service.analyze_payroll_deposits(txns)
        assert consistency == "VARIABLE"

    def test_irregular_amounts_labeled_irregular(self, service):
        """Payroll deposits with > 15% variance should be IRREGULAR."""
        txns = [
            _txn("2026-01-01", "PAYROLL TIPS INC", 2000, "credit"),
            _txn("2026-01-15", "PAYROLL TIPS INC", 5000, "credit"),
        ]
        _, _, consistency = service.analyze_payroll_deposits(txns)
        assert consistency == "IRREGULAR"

    def test_monthly_income_estimated_biweekly(self, service):
        """Biweekly payroll should estimate monthly as (amount * 26 / 12)."""
        # Two deposits ~14 days apart -> biweekly
        txns = [
            _txn("2026-01-01", "DIRECT DEP ACME", 2000, "credit"),
            _txn("2026-01-15", "DIRECT DEP ACME", 2000, "credit"),
        ]
        deposits, est_income, _ = service.analyze_payroll_deposits(txns)
        assert est_income is not None
        # For biweekly: 2000 * 26 / 12 = 4333.33
        expected = (Decimal("2000") * 26 / 12).quantize(TWO_PLACES)
        assert est_income == expected


# =============================================================================
# 5. INCOME DEPOSIT PATTERN RECOGNITION
# =============================================================================

@pytest.mark.unit
class TestIncomeDepositPatterns:
    """Frequency determination from deposit date intervals."""

    def test_weekly_frequency(self, service):
        """Deposits ~7 days apart should be classified as WEEKLY."""
        dates = [date(2026, 1, 1) + timedelta(days=7 * i) for i in range(4)]
        assert service._determine_frequency(dates) == "WEEKLY"

    def test_biweekly_frequency(self, service):
        """Deposits ~14 days apart should be classified as BIWEEKLY."""
        dates = [date(2026, 1, 1) + timedelta(days=14 * i) for i in range(4)]
        assert service._determine_frequency(dates) == "BIWEEKLY"

    def test_monthly_frequency(self, service):
        """Deposits ~30 days apart should be classified as MONTHLY."""
        dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
        assert service._determine_frequency(dates) == "MONTHLY"

    def test_single_date_defaults_to_monthly(self, service):
        """A single date cannot determine frequency; defaults to MONTHLY."""
        assert service._determine_frequency([date(2026, 1, 1)]) == "MONTHLY"


# =============================================================================
# 6. UNDISCLOSED DEBT DETECTION
# =============================================================================

@pytest.mark.unit
class TestUndisclosedDebtDetection:
    """Recurring payments to unknown creditors that may represent undisclosed obligations."""

    def test_recurring_auto_loan_detected(self, service):
        """Repeated payments to an auto lender should be detected as recurring."""
        txns = [
            _txn("2026-01-05", "TOYOTA FINANCIAL SERVICES", 450, "debit"),
            _txn("2026-02-05", "TOYOTA FINANCIAL SERVICES", 450, "debit"),
            _txn("2026-03-05", "TOYOTA FINANCIAL SERVICES", 450, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        assert len(result) >= 1
        auto_payments = [r for r in result if r.category == "auto_loan"]
        assert len(auto_payments) == 1
        assert auto_payments[0].average_amount == Decimal("450.00")
        assert auto_payments[0].is_disclosed is False  # auto_loan is not in expected_categories

    def test_rent_payment_is_disclosed(self, service):
        """Rent/mortgage payments fall into expected_categories and are marked disclosed."""
        txns = [
            _txn("2026-01-01", "RENT PAYMENT APT 4B", 1500, "debit"),
            _txn("2026-02-01", "RENT PAYMENT APT 4B", 1500, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        rent_payments = [r for r in result if r.category == "mortgage_rent"]
        assert len(rent_payments) == 1
        assert rent_payments[0].is_disclosed is True

    def test_single_occurrence_not_recurring(self, service):
        """A payee appearing only once should NOT be flagged as recurring."""
        txns = [
            _txn("2026-01-15", "NAVIENT STUDENT LOAN", 300, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        assert len(result) == 0

    def test_child_support_detected(self, service):
        """Recurring payments matching child_support keywords should be categorized."""
        txns = [
            _txn("2026-01-01", "CHILD SUPPORT PAYMENT", 800, "debit"),
            _txn("2026-02-01", "CHILD SUPPORT PAYMENT", 800, "debit"),
            _txn("2026-03-01", "CHILD SUPPORT PAYMENT", 800, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        cs_payments = [r for r in result if r.category == "child_support"]
        assert len(cs_payments) == 1
        assert cs_payments[0].is_disclosed is False

    def test_alimony_detected(self, service):
        """Recurring alimony/spousal support payments should be detected."""
        txns = [
            _txn("2026-01-01", "SPOUSAL SUPPORT PMT", 1200, "debit"),
            _txn("2026-02-01", "SPOUSAL SUPPORT PMT", 1200, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        alimony_payments = [r for r in result if r.category == "alimony"]
        assert len(alimony_payments) == 1

    def test_high_variance_debits_excluded(self, service):
        """Recurring payments with > 50% amount variance should be excluded."""
        txns = [
            _txn("2026-01-05", "RANDOM VENDOR", 100, "debit"),
            _txn("2026-02-05", "RANDOM VENDOR", 500, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        # 100 vs 500 => variance > 50%, so it should be excluded
        random_vendor = [r for r in result if "RANDOM VENDOR" in r.payee]
        assert len(random_vendor) == 0


# =============================================================================
# 7. STRUCTURING DETECTION
# =============================================================================

@pytest.mark.unit
class TestStructuringDetection:
    """Deposits just under $10,000 CTR threshold indicating potential structuring."""

    def test_deposit_just_below_10k_flagged(self, service):
        """A deposit between $9,000 and $9,999 should generate a structuring flag."""
        txns = [
            _txn("2026-01-10", "CASH DEPOSIT", 9500, "credit"),
        ]
        flags = service._detect_structuring(txns)
        assert len(flags) == 1
        assert "STRUCTURING_INDICATOR" in flags[0]
        assert "9,500" in flags[0]

    def test_multiple_same_day_deposits_over_10k(self, service):
        """Multiple deposits on the same day summing to >= $10,000 should flag."""
        txns = [
            _txn("2026-01-10", "DEPOSIT A", 6000, "credit"),
            _txn("2026-01-10", "DEPOSIT B", 5000, "credit"),
        ]
        flags = service._detect_structuring(txns)
        same_day_flags = [f for f in flags if "Multiple deposits" in f]
        assert len(same_day_flags) == 1

    def test_round_number_deposits_pattern(self, service):
        """Three or more round-number cash deposits ($1,000 multiples) should flag."""
        txns = [
            _txn("2026-01-05", "CASH DEPOSIT", 3000, "credit"),
            _txn("2026-01-15", "CASH DEPOSIT", 5000, "credit"),
            _txn("2026-02-05", "CASH DEPOSIT", 2000, "credit"),
        ]
        flags = service._detect_structuring(txns)
        round_flags = [f for f in flags if "round-number" in f]
        assert len(round_flags) == 1

    def test_normal_deposits_no_structuring_flag(self, service):
        """Ordinary deposits well below threshold should not flag for structuring."""
        txns = [
            _txn("2026-01-10", "REFUND", 150, "credit"),
            _txn("2026-01-20", "REIMBURSEMENT", 250.75, "credit"),
        ]
        flags = service._detect_structuring(txns)
        assert len(flags) == 0

    def test_debit_transactions_ignored_for_structuring(self, service):
        """Structuring detection should only look at credit transactions."""
        txns = [
            _txn("2026-01-10", "PAYMENT", 9500, "debit"),
        ]
        flags = service._detect_structuring(txns)
        assert len(flags) == 0


# =============================================================================
# 8. AVERAGE DAILY BALANCE CALCULATION
# =============================================================================

@pytest.mark.unit
class TestAverageDailyBalance:
    """Balance analysis from transaction data and metadata."""

    def test_average_daily_balance_from_metadata(self, service):
        """If metadata contains average_daily_balance, use it directly."""
        metadata = {"average_daily_balance": Decimal("5000.00")}
        result = service._analyze_balances([], metadata)
        assert result["average_daily"] == Decimal("5000.00")

    def test_average_daily_balance_computed_from_transactions(self, service):
        """If metadata lacks ADB, compute it from transaction balances."""
        txns = [
            _txn("2026-01-01", "Opening", 100, "credit", balance=5000),
            _txn("2026-01-15", "Deposit", 1000, "credit", balance=6000),
            _txn("2026-01-31", "Payment", 500, "debit", balance=4000),
        ]
        result = service._analyze_balances(txns, {})
        # Average of 5000, 6000, 4000 = 5000
        assert result["average_daily"] == Decimal("5000.00")

    def test_lowest_balance_identified(self, service):
        """The lowest balance and its date should be identified from transactions."""
        txns = [
            _txn("2026-01-05", "TXN A", 100, "credit", balance=3000),
            _txn("2026-01-15", "TXN B", 2500, "debit", balance=500),
            _txn("2026-01-25", "TXN C", 1000, "credit", balance=1500),
        ]
        result = service._analyze_balances(txns, {})
        assert result["lowest"] == Decimal("500.00")
        assert result["lowest_date"] == "2026-01-15"

    def test_beginning_ending_balance_from_transactions(self, service):
        """Beginning and ending balance should be inferred from first/last transactions."""
        txns = [
            _txn("2026-01-01", "First", 100, "credit", balance=2000),
            _txn("2026-01-31", "Last", 50, "debit", balance=3500),
        ]
        result = service._analyze_balances(txns, {})
        assert result["beginning"] == Decimal("2000.00")
        assert result["ending"] == Decimal("3500.00")


# =============================================================================
# 9. MONTHLY CASH FLOW ANALYSIS
# =============================================================================

@pytest.mark.unit
class TestMonthlyCashFlowAnalysis:
    """Risk scoring captures the overall cash flow health of the account."""

    def test_risk_score_zero_for_clean_analysis(self, service):
        """An analysis with no issues should yield a risk score of 0 and LOW risk."""
        analysis = _make_analysis()
        score, level = service._calculate_risk_score(analysis)
        assert score == 0
        assert level == "LOW"

    def test_risk_score_increases_with_nsf(self, service):
        """Each NSF event adds 5 points to risk score (capped at 25)."""
        analysis = _make_analysis(nsf_count=3)
        score, _ = service._calculate_risk_score(analysis)
        assert score >= 15  # 3 * 5

    def test_risk_score_capped_at_100(self, service):
        """Risk score should never exceed 100."""
        analysis = _make_analysis(
            nsf_count=10,
            deposits_needing_sourcing=10,
            irs_payment_plan_detected=True,
            flags=["STRUCTURING_INDICATOR: something"],
            undisclosed_obligations=[
                RecurringPayment(
                    category="auto_loan", payee="AUTO", average_amount=Decimal("400"),
                    frequency="MONTHLY", occurrences=3, total_amount=Decimal("1200"),
                    is_disclosed=False, dates=["2026-01-01"],
                )
                for _ in range(10)
            ],
            overdraft_days=20,
        )
        score, level = service._calculate_risk_score(analysis)
        assert score <= 100
        assert level == "CRITICAL"

    def test_critical_risk_at_70_plus(self, service):
        """Risk score >= 70 should be classified as CRITICAL."""
        # NSF(25) + deposits(30) + IRS(15) = 70
        analysis = _make_analysis(
            nsf_count=5,
            deposits_needing_sourcing=4,
            irs_payment_plan_detected=True,
        )
        score, level = service._calculate_risk_score(analysis)
        assert score >= 70
        assert level == "CRITICAL"

    def test_high_risk_at_45_plus(self, service):
        """Risk score between 45-69 should be HIGH."""
        # NSF(25) + deposits(24) = 49
        analysis = _make_analysis(nsf_count=5, deposits_needing_sourcing=3)
        score, level = service._calculate_risk_score(analysis)
        assert 45 <= score < 70
        assert level == "HIGH"


# =============================================================================
# 10. WIRE TRANSFER TRACKING
# =============================================================================

@pytest.mark.unit
class TestWireTransferTracking:
    """Wire transfers should be identified and appropriately classified."""

    def test_wire_transfer_flagged_as_large_deposit(self, service):
        """A wire transfer >= $500 should appear in large deposits."""
        txns = [
            _txn("2026-01-10", "WIRE FROM JOHN DOE", 25000, "credit"),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert len(result) == 1
        assert result[0].amount == Decimal("25000.00")
        # Wire transfers are not payroll and not internal transfers
        assert result[0].is_payroll is False

    def test_wire_transfer_needs_sourcing(self, service):
        """Non-payroll wires should require sourcing documentation."""
        txns = [
            _txn("2026-01-10", "INCOMING WIRE - REF 12345", 15000, "credit"),
        ]
        result = service.analyze_large_deposits(txns, "Jane Doe")
        assert result[0].needs_sourcing is True
        assert result[0].sourcing_explanation is not None


# =============================================================================
# 11. GAMBLING TRANSACTION FLAGGING
# =============================================================================

@pytest.mark.unit
class TestGamblingTransactionFlagging:
    """Gambling-related transactions detected via recurring payment analysis."""

    def test_gambling_recurring_payments_flagged_as_undisclosed(self, service):
        """Regular debits to a gambling-related payee should be caught as 'other'
        undisclosed obligations if they recur (category=other, is_disclosed=False)."""
        txns = [
            _txn("2026-01-05", "DRAFTKINGS DEPOSIT", 200, "debit"),
            _txn("2026-01-15", "DRAFTKINGS DEPOSIT", 200, "debit"),
            _txn("2026-02-05", "DRAFTKINGS DEPOSIT", 200, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        gambling = [r for r in result if "DRAFTKINGS" in r.payee]
        assert len(gambling) == 1
        assert gambling[0].category == "other"
        assert gambling[0].is_disclosed is False


# =============================================================================
# 12. CHILD SUPPORT / ALIMONY PAYMENT DETECTION
# =============================================================================

@pytest.mark.unit
class TestChildSupportAlimonyDetection:
    """Detection covered in TestUndisclosedDebtDetection; additional edge cases here."""

    def test_domestic_relations_keyword_matches_child_support(self, service):
        """'DOMESTIC REL' keyword should map to child_support category."""
        txns = [
            _txn("2026-01-01", "DOMESTIC REL DISBURSEMENT", 600, "debit"),
            _txn("2026-02-01", "DOMESTIC REL DISBURSEMENT", 600, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        cs = [r for r in result if r.category == "child_support"]
        assert len(cs) == 1

    def test_family_support_keyword_matches(self, service):
        """'FAMILY SUPPORT' should map to child_support category."""
        txns = [
            _txn("2026-01-01", "FAMILY SUPPORT AGENCY PMT", 750, "debit"),
            _txn("2026-02-01", "FAMILY SUPPORT AGENCY PMT", 750, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        cs = [r for r in result if r.category == "child_support"]
        assert len(cs) == 1


# =============================================================================
# 13. RENT PAYMENT VERIFICATION FOR RENTERS
# =============================================================================

@pytest.mark.unit
class TestRentPaymentVerification:
    """Rent payments should be identified and marked as disclosed/expected."""

    def test_rent_payment_detected_and_disclosed(self, service):
        """Regular rent payments should be category mortgage_rent and disclosed."""
        txns = [
            _txn("2026-01-01", "RENT PAYMENT - GREYSTAR", 1800, "debit"),
            _txn("2026-02-01", "RENT PAYMENT - GREYSTAR", 1800, "debit"),
            _txn("2026-03-01", "RENT PAYMENT - GREYSTAR", 1800, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        rent = [r for r in result if r.category == "mortgage_rent"]
        assert len(rent) == 1
        assert rent[0].is_disclosed is True
        assert rent[0].average_amount == Decimal("1800.00")
        assert rent[0].frequency == "MONTHLY"

    def test_hoa_payment_identified(self, service):
        """HOA payments should also be categorized under mortgage_rent."""
        txns = [
            _txn("2026-01-05", "HOA MONTHLY ASSESSMENT", 350, "debit"),
            _txn("2026-02-05", "HOA MONTHLY ASSESSMENT", 350, "debit"),
        ]
        result = service.analyze_recurring_payments(txns)
        hoa = [r for r in result if r.category == "mortgage_rent"]
        assert len(hoa) == 1


# =============================================================================
# 14. MULTI-ACCOUNT AGGREGATION
# =============================================================================

@pytest.mark.unit
class TestMultiAccountAggregation:
    """The analyze_statements entry point gathers docs from multiple statements."""

    def test_analyze_statements_no_docs_returns_error(self, service, mock_db):
        """When no bank statement documents exist, return an error result."""
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.fetchone.return_value = None
        result = service.analyze_statements(loan_id=1, borrower_id=7)
        assert result.success is False
        assert "NO_BANK_STATEMENTS" in result.flags
        assert result.error is not None

    def test_analyze_statements_multiple_docs_aggregated(self, service, mock_db):
        """Transactions from multiple documents should be merged and analyzed."""
        # Mock _gather_statements to return two doc dicts
        doc1 = {
            "doc_id": 10,
            "doc_type": "BANK_STATEMENT",
            "ocr_text": "01/05/2026 PAYROLL ACME 3000.00\n01/10/2026 NSF FEE 35.00",
            "uploaded_at": datetime(2026, 2, 1),
            "file_name": "stmt_jan.pdf",
            "extracted_dates": {},
            "extracted_fields": {"bank_name": "Test Bank"},
            "confidence_scores": {},
            "overall_confidence": 85,
        }
        doc2 = {
            "doc_id": 11,
            "doc_type": "BANK_STATEMENT",
            "ocr_text": "02/05/2026 PAYROLL ACME 3000.00",
            "uploaded_at": datetime(2026, 3, 1),
            "file_name": "stmt_feb.pdf",
            "extracted_dates": {},
            "extracted_fields": {},
            "confidence_scores": {},
            "overall_confidence": 90,
        }

        # Mock borrower name lookup
        borrower_row = MagicMock()
        borrower_row.borrower_name = "Jane Doe"

        # Mock save to return a calculation ID
        calc_row = MagicMock()
        calc_row.fetchone.return_value = [42]

        call_count = [0]

        def mock_execute(query, params=None):
            call_count[0] += 1
            result = MagicMock()
            query_str = str(query) if hasattr(query, 'text') else str(query)
            if "borrower_name" in query_str:
                result.fetchone.return_value = borrower_row
            elif "RETURNING id" in query_str:
                result.fetchone.return_value = [42]
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = None
            return result

        mock_db.execute.side_effect = mock_execute

        with patch.object(service, "_gather_statements", return_value=[doc1, doc2]):
            with patch.object(service, "_extract_transactions_with_ai", return_value=[]):
                result = service.analyze_statements(loan_id=1, borrower_id=7)

        assert result.success is True
        assert 10 in result.document_ids
        assert 11 in result.document_ids


# =============================================================================
# 15. STATEMENT PERIOD VALIDATION
# =============================================================================

@pytest.mark.unit
class TestStatementPeriodValidation:
    """Statement metadata extraction including period dates."""

    def test_period_extracted_from_extracted_fields(self, service):
        """Period start/end should be extracted from document extracted_fields."""
        docs = [
            {
                "extracted_fields": {
                    "statement_start_date": "2026-01-01",
                    "statement_end_date": "2026-01-31",
                    "bank_name": "Chase",
                    "account_type": "checking",
                },
                "extracted_dates": {},
            }
        ]
        metadata = service._extract_metadata(docs)
        assert metadata["period_start"] == "2026-01-01"
        assert metadata["period_end"] == "2026-01-31"
        assert metadata["institution"] == "Chase"

    def test_period_extracted_from_extracted_dates_fallback(self, service):
        """If extracted_fields lacks dates, fall back to extracted_dates keys."""
        docs = [
            {
                "extracted_fields": {},
                "extracted_dates": {
                    "statementStart": "2025-12-01",
                    "statementEnd": "2025-12-31",
                },
            }
        ]
        metadata = service._extract_metadata(docs)
        assert metadata["period_start"] == "2025-12-01"
        assert metadata["period_end"] == "2025-12-31"

    def test_default_account_type_is_checking(self, service):
        """If no account_type in metadata, default to CHECKING."""
        docs = [{"extracted_fields": {}, "extracted_dates": {}}]
        metadata = service._extract_metadata(docs)
        assert metadata["account_type"] == "CHECKING"

    def test_savings_account_type_detected(self, service):
        """Account type containing 'SAVINGS' should be classified as SAVINGS."""
        docs = [
            {
                "extracted_fields": {"account_type": "Savings Account"},
                "extracted_dates": {},
            }
        ]
        metadata = service._extract_metadata(docs)
        assert metadata["account_type"] == "SAVINGS"


# =============================================================================
# ADDITIONAL TESTS: FLAGS, TASKS, HELPERS
# =============================================================================

@pytest.mark.unit
class TestFlagGeneration:
    """Flag generation from analysis results."""

    def test_low_balance_flag(self, service):
        """A lowest balance below $100 should generate a LOW_BALANCE flag."""
        analysis = _make_analysis(
            lowest_balance=Decimal("50.00"),
            lowest_balance_date="2026-01-20",
        )
        flags = service._generate_flags(analysis)
        low_balance_flags = [f for f in flags if "LOW_BALANCE" in f]
        assert len(low_balance_flags) == 1
        assert "$50.00" in low_balance_flags[0]

    def test_negative_balance_flag(self, service):
        """Overdraft days > 0 should generate a NEGATIVE_BALANCE flag."""
        analysis = _make_analysis(overdraft_days=3)
        flags = service._generate_flags(analysis)
        neg_flags = [f for f in flags if "NEGATIVE_BALANCE" in f]
        assert len(neg_flags) == 1
        assert "3 day(s)" in neg_flags[0]

    def test_irregular_income_flag(self, service):
        """IRREGULAR income consistency should generate an IRREGULAR_INCOME flag."""
        analysis = _make_analysis(income_consistency="IRREGULAR")
        flags = service._generate_flags(analysis)
        irregular_flags = [f for f in flags if "IRREGULAR_INCOME" in f]
        assert len(irregular_flags) == 1


@pytest.mark.unit
class TestTaskGeneration:
    """Task creation from analysis findings."""

    def test_task_created_for_unsourced_deposit(self, service):
        """Each large deposit needing sourcing should generate a task."""
        analysis = _make_analysis(
            large_deposits=[
                LargeDeposit(
                    date="2026-01-10", amount=Decimal("7500"), description="WIRE IN",
                    is_payroll=False, is_transfer=False, needs_sourcing=True,
                    sourcing_explanation="...", risk_level="MEDIUM", notes="",
                ),
            ],
        )
        tasks = service._generate_tasks(analysis)
        deposit_tasks = [t for t in tasks if t["task_type"] == "review_large_deposit"]
        assert len(deposit_tasks) >= 1
        assert "$7,500" in deposit_tasks[0]["title"]

    def test_task_created_for_nsf_events(self, service):
        """NSF events should generate a single consolidated task."""
        analysis = _make_analysis(
            nsf_count=3,
            nsf_severity="HIGH",
            total_nsf_fees=Decimal("105.00"),
            nsf_events=[
                NSFEvent(date="2026-01-05", amount=Decimal("35"), description="NSF",
                         resulting_balance=None, fee_charged=Decimal("35"))
                for _ in range(3)
            ],
        )
        tasks = service._generate_tasks(analysis)
        nsf_tasks = [t for t in tasks if "NSF" in t["title"]]
        assert len(nsf_tasks) == 1
        assert nsf_tasks[0]["priority"] == "high"

    def test_task_created_for_irs_payment_plan(self, service):
        """An IRS payment plan should generate a critical-priority task."""
        analysis = _make_analysis(
            irs_payment_plan_detected=True,
            total_irs_payments=Decimal("3000"),
            irs_payments=[
                IRSPayment(date="2026-01-15", amount=Decimal("1000"),
                           description="IRS", payment_type="PAYMENT_PLAN",
                           is_recurring=True),
            ],
        )
        tasks = service._generate_tasks(analysis)
        irs_tasks = [t for t in tasks if "IRS" in t["title"]]
        assert len(irs_tasks) == 1
        assert irs_tasks[0]["priority"] == "critical"


@pytest.mark.unit
class TestOverdraftDayCounting:
    """Counting days with negative balance."""

    def test_overdraft_days_counted(self, service):
        """Each unique date with a negative balance should count as one overdraft day."""
        txns = [
            _txn("2026-01-05", "TXN A", 100, "debit", balance=-50),
            _txn("2026-01-05", "TXN B", 50, "debit", balance=-100),
            _txn("2026-01-06", "TXN C", 200, "credit", balance=-10),
            _txn("2026-01-07", "TXN D", 500, "credit", balance=490),
        ]
        days = service._count_overdraft_days(txns)
        # Jan 5 and Jan 6 have negative balances (2 unique dates)
        assert days == 2

    def test_no_overdraft_days_for_positive_balances(self, service):
        """All positive balances should yield 0 overdraft days."""
        txns = [
            _txn("2026-01-05", "TXN A", 100, "credit", balance=1000),
            _txn("2026-01-10", "TXN B", 50, "debit", balance=950),
        ]
        days = service._count_overdraft_days(txns)
        assert days == 0


@pytest.mark.unit
class TestHelperMethods:
    """Date normalization, amount parsing, payee normalization."""

    def test_normalize_date_mm_dd_yyyy(self, service):
        assert service._normalize_date("01/15/2026") == "2026-01-15"

    def test_normalize_date_mm_dd_yy(self, service):
        assert service._normalize_date("01/15/26") == "2026-01-15"

    def test_normalize_date_iso(self, service):
        assert service._normalize_date("2026-01-15") == "2026-01-15"

    def test_normalize_date_invalid(self, service):
        assert service._normalize_date("not-a-date") is None

    def test_normalize_date_none(self, service):
        assert service._normalize_date(None) is None

    def test_parse_amount_positive(self, service):
        assert service._parse_amount("$1,234.56") == Decimal("1234.56")

    def test_parse_amount_negative_parens(self, service):
        result = service._parse_amount("($500.00)")
        assert result == Decimal("-500.00")

    def test_parse_amount_negative_minus(self, service):
        result = service._parse_amount("-$250.00")
        assert result == Decimal("-250.00")

    def test_parse_amount_none(self, service):
        assert service._parse_amount(None) is None

    def test_to_decimal_from_string(self, service):
        assert service._to_decimal("$1,500.00") == Decimal("1500.00")

    def test_to_decimal_from_none(self, service):
        assert service._to_decimal(None) == ZERO

    def test_to_decimal_from_float(self, service):
        result = service._to_decimal(123.45)
        assert result == Decimal("123.45")

    def test_normalize_payee_strips_ref_numbers(self, service):
        result = service._normalize_payee("CHASE CARD #123456 REF: 789")
        assert "#" not in result
        assert "123456" not in result

    def test_extract_payroll_source_strips_prefix(self, service):
        result = service._extract_payroll_source("DIRECT DEPOSIT ACME CORP - PAYROLL")
        assert result == "ACME CORP"


@pytest.mark.unit
class TestTemplateAISummary:
    """Template-based summary when AI is unavailable."""

    def test_clean_analysis_summary(self, service):
        """An analysis with no issues should produce 'no significant concerns'."""
        analysis = _make_analysis(
            ending_balance=Decimal("5000.00"),
            risk_score=0,
            risk_level="LOW",
        )
        summary = service._generate_template_summary(analysis)
        assert "no significant concerns" in summary.lower()
        assert "LOW" in summary

    def test_summary_includes_institution_name(self, service):
        """Summary should mention the institution name when available."""
        analysis = _make_analysis(institution_name="Wells Fargo")
        summary = service._generate_template_summary(analysis)
        assert "Wells Fargo" in summary

    def test_summary_includes_nsf_count(self, service):
        """Summary should mention NSF events when present."""
        analysis = _make_analysis(nsf_count=2, nsf_severity="MEDIUM")
        summary = service._generate_template_summary(analysis)
        assert "2 NSF" in summary or "2 nsf" in summary.lower()


@pytest.mark.unit
class TestGetBankStatementAnalyzer:
    """Factory function test."""

    def test_returns_service_instance(self, mock_db):
        """get_bank_statement_analyzer should return a BankStatementAnalyzerService."""
        svc = get_bank_statement_analyzer(mock_db)
        assert isinstance(svc, BankStatementAnalyzerService)
        assert svc.db is mock_db
