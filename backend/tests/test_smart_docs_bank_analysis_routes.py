"""
Test Smart Docs Bank Statement Analysis Routes

Integration tests for the bank statement analysis API endpoints under
/api/smart-docs/bank-analysis/*.  Tests cover:
  - POST analyze bank statements
  - GET analysis results
  - GET large deposit report
  - POST source a large deposit
  - GET NSF/overdraft report
  - GET IRS payment detection
  - GET income verification from deposits
  - GET undisclosed debt detection
  - GET risk summary
  - POST compare stated vs deposit income
  - GET analysis tasks
  - POST generate report
  - GET org-wide stats
  - POST reanalyze bank statements
  - Tenant isolation verification
  - NSF severity thresholds
  - Large deposit threshold / unsourced accounting

Uses pytest with FastAPI TestClient. Database calls and the bank-statement
analyzer service are mocked so tests run without a live database or AI
backend.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Prefix used by all endpoints under test
# ---------------------------------------------------------------------------
PREFIX = "/api/smart-docs/bank-analysis"


# ---------------------------------------------------------------------------
# Shared analysis data fixtures
# ---------------------------------------------------------------------------

def _make_analysis_data(
    *,
    large_deposits=None,
    nsf_events=None,
    irs_payments=None,
    payroll_deposits=None,
    recurring_obligations=None,
    risk_score=15.0,
    risk_level="low",
    risk_flags=None,
    recommendations=None,
    estimated_monthly_income=8500.0,
    income_consistency_rating="good",
    employer_names=None,
    deposit_frequency="biweekly",
    months_covered=3,
    overdraft_day_count=0,
    irs_payment_plan_detected=False,
):
    """Build a realistic cached analysis dict."""
    return {
        "large_deposits": large_deposits or [],
        "nsf_events": nsf_events or [],
        "irs_payments": irs_payments or [],
        "payroll_deposits": payroll_deposits or [],
        "recurring_obligations": recurring_obligations or [],
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_flags": risk_flags or [],
        "recommendations": recommendations or [],
        "estimated_monthly_income": estimated_monthly_income,
        "income_consistency_rating": income_consistency_rating,
        "employer_names": employer_names or ["Acme Corp"],
        "deposit_frequency": deposit_frequency,
        "months_covered": months_covered,
        "overdraft_day_count": overdraft_day_count,
        "irs_payment_plan_detected": irs_payment_plan_detected,
    }


SAMPLE_LARGE_DEPOSITS = [
    {
        "index": 0,
        "date": "2026-01-15",
        "amount": 5200.00,
        "description": "WIRE TRANSFER FROM SAVINGS",
        "risk_level": "medium",
        "sourcing_status": "unsourced",
        "explanation": None,
        "supporting_document_id": None,
        "sourced_by": None,
    },
    {
        "index": 1,
        "date": "2026-02-03",
        "amount": 12000.00,
        "description": "CHECK DEPOSIT",
        "risk_level": "high",
        "sourcing_status": "unsourced",
        "explanation": None,
        "supporting_document_id": None,
        "sourced_by": None,
    },
    {
        "index": 2,
        "date": "2026-02-20",
        "amount": 3000.00,
        "description": "VENMO TRANSFER",
        "risk_level": "low",
        "sourcing_status": "sourced",
        "explanation": "Gift from parent",
        "supporting_document_id": 42,
        "sourced_by": "LO Jane Doe",
    },
]

SAMPLE_NSF_EVENTS = [
    {
        "date": "2026-01-10",
        "amount": -250.00,
        "description": "NSF FEE - CHECK 1042",
        "fee_amount": 35.00,
        "severity": "medium",
    },
    {
        "date": "2026-02-01",
        "amount": -180.00,
        "description": "OVERDRAFT FEE",
        "fee_amount": 35.00,
        "severity": "medium",
    },
]

SAMPLE_IRS_PAYMENTS = [
    {
        "date": "2026-01-15",
        "amount": 1500.00,
        "description": "IRS USATAXPYMT",
        "payment_type": "estimated_tax",
    },
    {
        "date": "2026-04-15",
        "amount": 1500.00,
        "description": "IRS USATAXPYMT",
        "payment_type": "estimated_tax",
    },
]

SAMPLE_PAYROLL_DEPOSITS = [
    {
        "date": "2026-01-15",
        "amount": 4250.00,
        "employer_match": "ACME CORP",
        "frequency": "biweekly",
    },
    {
        "date": "2026-01-31",
        "amount": 4250.00,
        "employer_match": "ACME CORP",
        "frequency": "biweekly",
    },
]

SAMPLE_RECURRING_OBLIGATIONS = [
    {
        "payee": "ALLY FINANCIAL",
        "amount": 450.00,
        "frequency": "monthly",
        "category": "loan_payment",
        "months_observed": 3,
    },
    {
        "payee": "PROGRESSIVE INS",
        "amount": 180.00,
        "frequency": "monthly",
        "category": "insurance",
        "months_observed": 3,
    },
]

SAMPLE_RISK_FLAGS = [
    {
        "flag_type": "UNSOURCED_LARGE_DEPOSIT",
        "severity": "high",
        "description": "2 large deposits totaling $17,200.00 are unsourced",
        "recommendation": "Obtain sourcing documentation",
    },
]


# ---------------------------------------------------------------------------
# Helper to build a mock db.execute result row for loan-level queries
# ---------------------------------------------------------------------------

class _FakeRow:
    """Emulate a SQLAlchemy result row accessible by index and attribute."""

    def __init__(self, values):
        self._values = values

    def __getitem__(self, idx):
        return self._values[idx]

    def __getattr__(self, name):
        # fallback — not strictly needed but keeps things robust
        raise AttributeError(name)


# =============================================================================
# 1. POST /bank-analysis/analyze/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestAnalyzeBankStatements:
    """POST /bank-analysis/analyze/{loan_id}"""

    def test_analyze_success(self, authenticated_client, db_session):
        """Successful analysis returns loan_id, borrower_id, and analysis payload."""
        mock_result = MagicMock()
        mock_result.success = True
        analysis_payload = _make_analysis_data(large_deposits=SAMPLE_LARGE_DEPOSITS)
        mock_result.to_dict.return_value = analysis_payload

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = mock_result

        with patch(
            "routes.smart_docs_bank_analysis_routes._get_analyzer",
            return_value=mock_analyzer,
        ), patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/analyze/100?borrower_id=200",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["borrower_id"] == 200
        assert "analysis" in data
        assert "analyzed_at" in data

    def test_analyze_no_borrower_id_returns_422(self, authenticated_client):
        """Missing required borrower_id query param should return 422."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ):
            resp = authenticated_client.post(f"{PREFIX}/analyze/100")

        assert resp.status_code == 422

    def test_analyze_service_unavailable_returns_501(self, authenticated_client):
        """When analyzer service import fails, endpoint returns 501."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._get_analyzer",
            side_effect=__import__("fastapi").HTTPException(
                status_code=501,
                detail="Bank statement analyzer service is not yet available",
            ),
        ), patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/analyze/100?borrower_id=200",
            )

        assert resp.status_code == 501


# =============================================================================
# 2. GET /bank-analysis/results/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetAnalysisResults:
    """GET /bank-analysis/results/{loan_id}"""

    def test_results_found(self, authenticated_client):
        """Returns cached analysis when present."""
        analysis = _make_analysis_data()
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ), patch.object(
            # Mock the second db.execute call for bank_analysis_at
            type(authenticated_client),
            "__class__",
            create=True,
        ):
            # We need to mock the db.execute inside the route for bank_analysis_at.
            # The simplest approach: patch _get_cached_analysis and then patch
            # the db session's execute used for timestamp lookup.
            from unittest.mock import ANY

            mock_row = _FakeRow([ts])
            mock_execute_result = MagicMock()
            mock_execute_result.first.return_value = mock_row

            # Patch db_session.execute to return our mock
            original_execute = type(MagicMock()).execute

            with patch.object(
                type(MagicMock()),
                "execute",
                return_value=mock_execute_result,
            ):
                # Simpler: just mock at the route level by patching db_session
                pass

            # Instead, use a direct approach: mock the db dependency
            resp = authenticated_client.get(f"{PREFIX}/results/100")

        # The response should be 200 (analysis found) or could be 200
        # depending on how the db mock resolves. Let's verify the
        # _get_cached_analysis path is taken.
        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["analysis"] == analysis

    def test_results_not_found(self, authenticated_client):
        """Returns 404 when no analysis has been run."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=None,
        ):
            resp = authenticated_client.get(f"{PREFIX}/results/999")

        assert resp.status_code == 404
        assert "No bank statement analysis found" in resp.json()["detail"]


# =============================================================================
# 3. GET /bank-analysis/large-deposits/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetLargeDeposits:
    """GET /bank-analysis/large-deposits/{loan_id}"""

    def test_large_deposits_report(self, authenticated_client):
        """Returns deposits with correct unsourced counts."""
        analysis = _make_analysis_data(large_deposits=SAMPLE_LARGE_DEPOSITS)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/large-deposits/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["total_count"] == 3
        # Only deposits 0 and 1 are unsourced
        assert data["total_unsourced_count"] == 2
        assert data["total_unsourced_amount"] == 5200.00 + 12000.00

    def test_large_deposits_all_sourced(self, authenticated_client):
        """When all deposits are sourced, unsourced totals are zero."""
        sourced_deposits = [
            {**d, "sourcing_status": "sourced"} for d in SAMPLE_LARGE_DEPOSITS
        ]
        analysis = _make_analysis_data(large_deposits=sourced_deposits)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/large-deposits/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_unsourced_count"] == 0
        assert data["total_unsourced_amount"] == 0.0

    def test_large_deposits_no_analysis(self, authenticated_client):
        """Returns 404 when no analysis exists."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=None,
        ):
            resp = authenticated_client.get(f"{PREFIX}/large-deposits/100")

        assert resp.status_code == 404


# =============================================================================
# 4. GET /bank-analysis/nsf-events/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetNSFEvents:
    """GET /bank-analysis/nsf-events/{loan_id}"""

    def test_nsf_report_with_events(self, authenticated_client):
        """Returns NSF events with fee totals and severity."""
        analysis = _make_analysis_data(nsf_events=SAMPLE_NSF_EVENTS)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/nsf-events/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["total_nsf_count"] == 2
        assert data["total_fees"] == 70.00
        # 2 events with < $100 total fees => severity "low"
        assert data["severity_assessment"] == "low"

    def test_nsf_severity_none_when_no_events(self, authenticated_client):
        """Severity is 'none' when there are zero NSF events."""
        analysis = _make_analysis_data(nsf_events=[])

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/nsf-events/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["severity_assessment"] == "none"
        assert data["total_nsf_count"] == 0

    def test_nsf_severity_high_with_many_events(self, authenticated_client):
        """Severity is 'high' when there are more than 5 NSF events."""
        many_nsf = [
            {"date": f"2026-0{i+1}-01", "amount": -100, "description": "NSF", "fee_amount": 35, "severity": "medium"}
            for i in range(6)
        ]
        analysis = _make_analysis_data(nsf_events=many_nsf)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/nsf-events/100")

        assert resp.status_code == 200
        assert resp.json()["severity_assessment"] == "high"

    def test_nsf_severity_medium_with_moderate_events(self, authenticated_client):
        """Severity is 'medium' when there are 3-5 NSF events."""
        moderate_nsf = [
            {"date": f"2026-0{i+1}-01", "amount": -100, "description": "NSF", "fee_amount": 35, "severity": "medium"}
            for i in range(4)
        ]
        analysis = _make_analysis_data(nsf_events=moderate_nsf)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/nsf-events/100")

        assert resp.status_code == 200
        assert resp.json()["severity_assessment"] == "medium"


# =============================================================================
# 5. GET /bank-analysis/irs-payments/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetIRSPayments:
    """GET /bank-analysis/irs-payments/{loan_id}"""

    def test_irs_payments_found(self, authenticated_client):
        """Returns IRS payments with totals and flags."""
        analysis = _make_analysis_data(irs_payments=SAMPLE_IRS_PAYMENTS)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/irs-payments/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["total_irs_payments"] == 3000.00
        assert data["payment_count"] == 2
        # Both are estimated_tax type
        assert data["estimated_tax_payments"] is True
        assert data["payment_plan_detected"] is False

    def test_irs_no_payments(self, authenticated_client):
        """When no IRS payments found, totals are zero."""
        analysis = _make_analysis_data(irs_payments=[])

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/irs-payments/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_irs_payments"] == 0
        assert data["payment_count"] == 0
        assert data["estimated_tax_payments"] is False

    def test_irs_payment_plan_detected(self, authenticated_client):
        """Payment plan flag is surfaced when detected in analysis."""
        analysis = _make_analysis_data(
            irs_payments=SAMPLE_IRS_PAYMENTS,
            irs_payment_plan_detected=True,
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/irs-payments/100")

        assert resp.status_code == 200
        assert resp.json()["payment_plan_detected"] is True


# =============================================================================
# 6. GET /bank-analysis/income-verification/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetIncomeVerification:
    """GET /bank-analysis/income-verification/{loan_id}"""

    def test_income_verification_with_stated_income(self, authenticated_client, db_session):
        """Returns variance when stated monthly income is available on the loan."""
        analysis = _make_analysis_data(
            payroll_deposits=SAMPLE_PAYROLL_DEPOSITS,
            estimated_monthly_income=8500.0,
        )

        # Mock the loan row for stated income lookup
        mock_row = _FakeRow([None, 9000.0])  # borrower_income=None, borrower_monthly_income=9000
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/income-verification/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["estimated_monthly_income"] == 8500.0
        assert data["stated_monthly_income"] == 9000.0
        # variance = (8500 - 9000) / 9000 * 100 = -5.56%
        assert data["income_variance_pct"] is not None
        assert data["income_variance_pct"] < 0
        assert data["consistency_rating"] == "good"
        assert "Acme Corp" in data["employer_names"]
        assert data["deposit_frequency"] == "biweekly"

    def test_income_verification_no_stated_income(self, authenticated_client, db_session):
        """When no stated income on loan, variance is None."""
        analysis = _make_analysis_data(estimated_monthly_income=8500.0)

        mock_row = _FakeRow([None, None])
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/income-verification/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["stated_monthly_income"] is None
        assert data["income_variance_pct"] is None


# =============================================================================
# 7. GET /bank-analysis/undisclosed-debts/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetUndisclosedDebts:
    """GET /bank-analysis/undisclosed-debts/{loan_id}"""

    def test_undisclosed_debts_found(self, authenticated_client):
        """Returns undisclosed recurring obligations with DTI impact."""
        analysis = _make_analysis_data(
            recurring_obligations=SAMPLE_RECURRING_OBLIGATIONS,
            estimated_monthly_income=8500.0,
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/undisclosed-debts/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["total_count"] == 2
        assert data["total_monthly_obligations"] == 630.0
        # DTI impact = 630 / 8500 * 100 = 7.41%
        assert data["potential_dti_impact"] is not None
        assert 7.0 <= data["potential_dti_impact"] <= 8.0

    def test_undisclosed_debts_none(self, authenticated_client):
        """When no undisclosed debts, returns empty list."""
        analysis = _make_analysis_data(recurring_obligations=[])

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/undisclosed-debts/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["potential_dti_impact"] is None


# =============================================================================
# 8. POST /bank-analysis/compare-income/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestCompareIncome:
    """POST /bank-analysis/compare-income/{loan_id}"""

    def test_compare_consistent_income(self, authenticated_client):
        """Variance <= 5% is assessed as 'consistent'."""
        analysis = _make_analysis_data(estimated_monthly_income=10000.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 9800.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assessment"] == "consistent"
        assert data["severity"] == "low"
        assert data["recommendation"] is None

    def test_compare_significant_overstated(self, authenticated_client):
        """Stated income >> deposit income triggers 'significant_variance' / high severity."""
        analysis = _make_analysis_data(estimated_monthly_income=5000.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 10000.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assessment"] == "significant_variance"
        assert data["severity"] == "high"
        assert data["recommendation"] is not None
        assert "exceeds deposit income" in data["recommendation"]

    def test_compare_significant_deposit_exceeds_stated(self, authenticated_client):
        """Deposit income >> stated income triggers recommendation about additional sources."""
        analysis = _make_analysis_data(estimated_monthly_income=15000.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 10000.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["variance_pct"] > 25
        assert "exceeds stated income" in data["recommendation"]

    def test_compare_no_analysis_returns_404(self, authenticated_client):
        """Returns 404 when no cached analysis exists."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=None,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 8000.0},
            )

        assert resp.status_code == 404

    def test_compare_no_deposit_income_returns_422(self, authenticated_client):
        """Returns 422 when analysis has no estimated income."""
        analysis = _make_analysis_data(estimated_monthly_income=0.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 8000.0},
            )

        assert resp.status_code == 422

    def test_compare_invalid_stated_income_returns_422(self, authenticated_client):
        """stated_monthly_income must be > 0 per schema validation."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": -500.0},
            )

        assert resp.status_code == 422


# =============================================================================
# 9. GET /bank-analysis/risk-summary/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetRiskSummary:
    """GET /bank-analysis/risk-summary/{loan_id}"""

    def test_risk_summary_with_flags(self, authenticated_client):
        """Returns aggregated risk data from analysis."""
        analysis = _make_analysis_data(
            large_deposits=SAMPLE_LARGE_DEPOSITS,
            nsf_events=SAMPLE_NSF_EVENTS,
            irs_payments=SAMPLE_IRS_PAYMENTS,
            recurring_obligations=SAMPLE_RECURRING_OBLIGATIONS,
            risk_score=45.0,
            risk_level="medium",
            risk_flags=SAMPLE_RISK_FLAGS,
            recommendations=["Source large deposits", "Obtain NSF LOE"],
            income_consistency_rating="good",
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/risk-summary/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_risk_score"] == 45.0
        assert data["risk_level"] == "medium"
        assert data["large_deposit_count"] == 3
        assert data["nsf_event_count"] == 2
        assert data["irs_payment_count"] == 2
        assert data["undisclosed_debt_count"] == 2
        assert data["income_consistency"] == "good"
        assert len(data["flags"]) == 1
        assert len(data["recommendations"]) == 2


# =============================================================================
# 10. GET /bank-analysis/tasks/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGetAnalysisTasks:
    """GET /bank-analysis/tasks/{loan_id}"""

    def test_tasks_generated_from_analysis(self, authenticated_client):
        """Tasks are generated for unsourced deposits, NSF, IRS, and undisclosed debts."""
        analysis = _make_analysis_data(
            large_deposits=SAMPLE_LARGE_DEPOSITS,
            nsf_events=SAMPLE_NSF_EVENTS,
            irs_payments=SAMPLE_IRS_PAYMENTS,
            recurring_obligations=SAMPLE_RECURRING_OBLIGATIONS,
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100")

        assert resp.status_code == 200
        data = resp.json()
        # 2 unsourced deposit tasks + 1 NSF task + 1 IRS task + 1 undisclosed debt task = 5
        assert data["total_count"] == 5
        task_types = [t["task_type"] for t in data["tasks"]]
        assert "sourcing_letter" in task_types
        assert "nsf_explanation" in task_types
        assert "irs_docs" in task_types
        assert "loe_needed" in task_types
        assert data["pending_count"] == 5

    def test_tasks_status_filter(self, authenticated_client):
        """Filtering by status=completed returns empty when all tasks are pending."""
        analysis = _make_analysis_data(
            large_deposits=SAMPLE_LARGE_DEPOSITS,
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100?status=completed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0

    def test_tasks_no_issues_returns_empty(self, authenticated_client):
        """When analysis has no issues, no tasks are generated."""
        analysis = _make_analysis_data()

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100")

        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0


# =============================================================================
# 11. POST /bank-analysis/large-deposits/{deposit_index}/source
# =============================================================================

@pytest.mark.unit
class TestSourceLargeDeposit:
    """POST /bank-analysis/large-deposits/{deposit_index}/source"""

    def test_source_deposit_success(self, authenticated_client, db_session):
        """Successfully sourcing a deposit updates its status."""
        analysis = _make_analysis_data(large_deposits=list(SAMPLE_LARGE_DEPOSITS))

        mock_execute = MagicMock()
        db_session.execute = mock_execute
        db_session.commit = MagicMock()

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/large-deposits/0/source?loan_id=100",
                json={
                    "explanation": "Transfer from savings account at Chase",
                    "supporting_document_id": 55,
                    "sourced_by": "LO John Smith",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sourced"
        assert data["deposit_index"] == 0
        assert data["explanation"] == "Transfer from savings account at Chase"
        assert data["supporting_document_id"] == 55
        assert data["sourced_by"] == "LO John Smith"

    def test_source_deposit_invalid_index(self, authenticated_client):
        """Invalid deposit index returns 404."""
        analysis = _make_analysis_data(large_deposits=SAMPLE_LARGE_DEPOSITS)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/large-deposits/99/source?loan_id=100",
                json={
                    "explanation": "Gift from parent",
                    "sourced_by": "LO",
                },
            )

        assert resp.status_code == 404
        assert "Deposit index 99 not found" in resp.json()["detail"]


# =============================================================================
# 12. POST /bank-analysis/reanalyze/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestReanalyzeBankStatements:
    """POST /bank-analysis/reanalyze/{loan_id}"""

    def test_reanalyze_success(self, authenticated_client, db_session):
        """Reanalysis passes force_refresh=True to the analyzer."""
        mock_result = MagicMock()
        mock_result.success = True
        analysis_payload = _make_analysis_data()
        mock_result.to_dict.return_value = analysis_payload

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = mock_result

        db_session.execute = MagicMock()
        db_session.commit = MagicMock()

        with patch(
            "routes.smart_docs_bank_analysis_routes._get_analyzer",
            return_value=mock_analyzer,
        ), patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/reanalyze/100?borrower_id=200",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert data["borrower_id"] == 200
        assert "reanalyzed_at" in data

        # Verify force_refresh was passed
        mock_analyzer.analyze.assert_called_once_with(
            loan_id=100,
            borrower_id=200,
            force_refresh=True,
        )


# =============================================================================
# 13. POST /bank-analysis/generate-report/{loan_id}
# =============================================================================

@pytest.mark.unit
class TestGenerateReport:
    """POST /bank-analysis/generate-report/{loan_id}"""

    def test_generate_report_success(self, authenticated_client, db_session):
        """Successful report generation returns a URL."""
        analysis = _make_analysis_data()

        mock_loan_row = _FakeRow(["2026-001234", "John Smith", "conventional", 400000])
        mock_execute_result = MagicMock()
        mock_execute_result.first.return_value = mock_loan_row
        db_session.execute = MagicMock(return_value=mock_execute_result)

        mock_pdf_service = MagicMock()
        mock_pdf_service.generate_bank_analysis_report.return_value = "https://s3.example.com/report.pdf"

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ), patch(
            "routes.smart_docs_bank_analysis_routes.get_pdf_generation_service",
            create=True,
        ) as mock_get_pdf:
            # Patch the import inside the function
            import routes.smart_docs_bank_analysis_routes as route_module

            with patch.dict("sys.modules", {
                "services.smart_docs.pdf_generation_service": MagicMock(
                    get_pdf_generation_service=MagicMock(return_value=mock_pdf_service)
                )
            }):
                resp = authenticated_client.post(f"{PREFIX}/generate-report/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["loan_id"] == 100
        assert "report_url" in data
        assert "generated_at" in data

    def test_generate_report_no_analysis(self, authenticated_client):
        """Returns 404 when no analysis data exists."""
        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=None,
        ):
            resp = authenticated_client.post(f"{PREFIX}/generate-report/100")

        assert resp.status_code == 404


# =============================================================================
# 14. GET /bank-analysis/stats
# =============================================================================

@pytest.mark.unit
class TestGetBankAnalysisStats:
    """GET /bank-analysis/stats"""

    def test_stats_with_data(self, authenticated_client, db_session):
        """Returns aggregate stats across all analyzed loans."""
        mock_row = _FakeRow([10, 32.5, 3, 2.1, 1.5, 0.8, 0.4])
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        with patch(
            "routes.smart_docs_bank_analysis_routes.get_current_user",
        ):
            resp = authenticated_client.get(f"{PREFIX}/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_analyzed"] == 10
        assert data["avg_risk_score"] == 32.5
        assert data["high_risk_count"] == 3

    def test_stats_no_analyzed_loans(self, authenticated_client, db_session):
        """Returns zeros when no loans have been analyzed."""
        mock_row = _FakeRow([0, None, 0, None, None, None, None])
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        resp = authenticated_client.get(f"{PREFIX}/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_analyzed"] == 0
        assert data["avg_risk_score"] == 0.0


# =============================================================================
# 15. Tenant Isolation Verification
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Verify _verify_loan_tenant blocks cross-org access."""

    def test_tenant_mismatch_returns_404(self, authenticated_client, db_session, mock_user):
        """User from org_id=1 cannot access loan belonging to org_id=99."""
        # Ensure mock_user has an org and is not a platform admin
        mock_user.organization_id = 1
        mock_user.permission_role = "loan_officer"

        # Mock db.execute to return a loan with different org
        mock_row = _FakeRow([99])  # loan's organization_id = 99
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        # Call the tenant verification helper directly
        from routes.smart_docs_bank_analysis_routes import _verify_loan_tenant
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db_session, 500, mock_user)

        assert exc_info.value.status_code == 404

    def test_platform_admin_bypasses_tenant_check(self, authenticated_client, db_session, mock_user):
        """Platform admin can access any loan regardless of org."""
        mock_user.organization_id = 1
        mock_user.permission_role = "admin"

        # Should NOT raise even though we don't mock the DB query
        # because the function short-circuits for admins
        from routes.smart_docs_bank_analysis_routes import _verify_loan_tenant
        # No exception should be raised
        _verify_loan_tenant(db_session, 500, mock_user)

    def test_same_org_passes_tenant_check(self, authenticated_client, db_session, mock_user):
        """User from the same org as the loan passes tenant verification."""
        mock_user.organization_id = 1
        mock_user.permission_role = "loan_officer"

        mock_row = _FakeRow([1])  # same org
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db_session.execute = MagicMock(return_value=mock_result)

        from routes.smart_docs_bank_analysis_routes import _verify_loan_tenant
        # No exception should be raised
        _verify_loan_tenant(db_session, 500, mock_user)


# =============================================================================
# 16. Large Deposit Threshold and Unsourced Amount Accounting
# =============================================================================

@pytest.mark.unit
class TestLargeDepositAccounting:
    """Verify unsourced amount and count calculations across edge cases."""

    def test_empty_deposits_list(self, authenticated_client):
        """No large deposits yields zero totals."""
        analysis = _make_analysis_data(large_deposits=[])

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/large-deposits/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["total_unsourced_count"] == 0
        assert data["total_unsourced_amount"] == 0.0

    def test_mixed_sourcing_statuses(self, authenticated_client):
        """Correctly counts unsourced vs sourced vs waived deposits."""
        deposits = [
            {"index": 0, "amount": 5000, "sourcing_status": "unsourced"},
            {"index": 1, "amount": 3000, "sourcing_status": "sourced"},
            {"index": 2, "amount": 7500, "sourcing_status": "waived"},
            {"index": 3, "amount": 2000, "sourcing_status": "unsourced"},
        ]
        analysis = _make_analysis_data(large_deposits=deposits)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/large-deposits/100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 4
        # "waived" is not "sourced" so it counts as unsourced in the filter
        assert data["total_unsourced_count"] == 3
        assert data["total_unsourced_amount"] == 5000 + 7500 + 2000


# =============================================================================
# 17. Compare Income - Moderate Variance Assessment
# =============================================================================

@pytest.mark.unit
class TestCompareIncomeModerateVariance:
    """Edge cases for the compare-income variance assessment bands."""

    def test_minor_variance_band(self, authenticated_client):
        """Variance between 5-15% is 'minor_variance' / low severity."""
        # estimated = 10000, stated = 8800 => variance = 13.6%
        analysis = _make_analysis_data(estimated_monthly_income=10000.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 8800.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assessment"] == "minor_variance"
        assert data["severity"] == "low"

    def test_moderate_variance_band(self, authenticated_client):
        """Variance between 15-25% is 'moderate_variance' / medium severity."""
        # estimated = 10000, stated = 8000 => variance = 25%
        # Actually at exactly 25% it tips to significant. Use 8100 => 23.5%
        analysis = _make_analysis_data(estimated_monthly_income=10000.0)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.post(
                f"{PREFIX}/compare-income/100",
                json={"stated_monthly_income": 8100.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assessment"] == "moderate_variance"
        assert data["severity"] == "medium"


# =============================================================================
# 18. Task Priority Logic
# =============================================================================

@pytest.mark.unit
class TestTaskPriorityLogic:
    """Verify task priority assignment based on risk levels and counts."""

    def test_high_risk_deposit_generates_high_priority_task(self, authenticated_client):
        """Unsourced deposit with risk_level=high creates high-priority task."""
        deposits = [
            {
                "index": 0,
                "amount": 25000,
                "date": "2026-01-15",
                "risk_level": "high",
                "sourcing_status": "unsourced",
            },
        ]
        analysis = _make_analysis_data(large_deposits=deposits)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100")

        assert resp.status_code == 200
        data = resp.json()
        sourcing_tasks = [t for t in data["tasks"] if t["task_type"] == "sourcing_letter"]
        assert len(sourcing_tasks) == 1
        assert sourcing_tasks[0]["priority"] == "high"
        assert data["high_priority_count"] >= 1

    def test_many_nsf_events_generate_high_priority_task(self, authenticated_client):
        """More than 3 NSF events create a high-priority NSF explanation task."""
        nsf_events = [
            {"date": f"2026-0{i+1}-01", "amount": -100, "description": "NSF", "fee_amount": 35, "severity": "medium"}
            for i in range(5)
        ]
        analysis = _make_analysis_data(nsf_events=nsf_events)

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100")

        assert resp.status_code == 200
        data = resp.json()
        nsf_tasks = [t for t in data["tasks"] if t["task_type"] == "nsf_explanation"]
        assert len(nsf_tasks) == 1
        assert nsf_tasks[0]["priority"] == "high"

    def test_irs_payment_plan_generates_high_priority(self, authenticated_client):
        """Detected IRS payment plan creates high-priority documentation task."""
        analysis = _make_analysis_data(
            irs_payments=SAMPLE_IRS_PAYMENTS,
            irs_payment_plan_detected=True,
        )

        with patch(
            "routes.smart_docs_bank_analysis_routes._verify_loan_tenant",
        ), patch(
            "routes.smart_docs_bank_analysis_routes._get_cached_analysis",
            return_value=analysis,
        ):
            resp = authenticated_client.get(f"{PREFIX}/tasks/100")

        assert resp.status_code == 200
        data = resp.json()
        irs_tasks = [t for t in data["tasks"] if t["task_type"] == "irs_docs"]
        assert len(irs_tasks) == 1
        assert irs_tasks[0]["priority"] == "high"
