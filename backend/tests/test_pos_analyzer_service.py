"""
Tests for POSAnalyzerService — Smart Document Collection POS Application Analyzer.

Tests cover document requirement generation based on loan type, occupancy,
employment status, special circumstances, co-borrower presence, and deduplication.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.smart_docs.pos_analyzer_service import (
    POSAnalyzerService,
    POSAnalysisResult,
    RequiredDocument,
    _CONFORMING_LIMIT_2025,
)
from models.smart_docs_models import DocType, RequestPriority, AppliesTo


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create a POSAnalyzerService with a mocked DB session."""
    return POSAnalyzerService(mock_db)


def _base_loan_data(**overrides):
    """Build minimal application_data dict with sensible defaults."""
    data = {
        "loan_id": 1,
        "loan_number": "TEST-001",
        "loan_type": "conventional",
        "program": "",
        "occupancy_type": "primary",
        "property_type": "single family",
        "property_state": "FL",
        "borrower_name": "John Doe",
        "coborrower_name": None,
        "borrower_email": "john@example.com",
        "co_borrower_email": None,
        "loan_amount": 400_000,
        "purchase_price": 500_000,
        "down_payment": 100_000,
        "ltv": 80.0,
        "cltv": 80.0,
        "loan_purpose": "purchase",
        "property_units": 1,
        "hoa_amount": 0,
        "user_metadata": {},
        "stage": "APPLICATION",
        "employment_status": "W2 Employee",
        "credit_score": 750,
        "notes": "",
        "first_time_buyer": False,
        "annual_income": 120_000,
    }
    data.update(overrides)
    return data


def _find_req(result, doc_type=None, title_contains=None, applies_to=None):
    """Helper to find a requirement in an analysis result by doc_type and/or title substring."""
    for req in result.requirements:
        type_match = doc_type is None or req.doc_type == doc_type
        title_match = title_contains is None or title_contains.lower() in req.title.lower()
        applies_match = applies_to is None or req.applies_to == applies_to
        if type_match and title_match and applies_match:
            return req
    return None


def _find_reqs(result, doc_type=None, title_contains=None, applies_to=None):
    """Return all matching requirements."""
    matches = []
    for req in result.requirements:
        type_match = doc_type is None or req.doc_type == doc_type
        title_match = title_contains is None or title_contains.lower() in req.title.lower()
        applies_match = applies_to is None or req.applies_to == applies_to
        if type_match and title_match and applies_match:
            matches.append(req)
    return matches


# =============================================================================
# 1. Conventional Loan Document Requirements
# =============================================================================

class TestConventionalLoan:
    """Conventional loan should require standard documents: ID, paystubs, W2s,
    bank statements, property docs."""

    def test_conventional_basic_requirements(self, service):
        data = _base_loan_data(loan_type="conventional")
        result = service.analyze_loan_application(1, application_data=data)

        assert result.success is True
        assert result.total_documents_needed > 0

        # Must have identity
        assert _find_req(result, doc_type=DocType.DRIVERS_LICENSE.value) is not None
        # Must have income docs
        assert _find_req(result, doc_type=DocType.PAYSTUB.value) is not None
        assert _find_req(result, doc_type=DocType.W2.value) is not None
        # Must have asset docs
        assert _find_req(result, doc_type=DocType.BANK_STATEMENT.value) is not None
        # Must have property docs
        assert _find_req(result, doc_type=DocType.APPRAISAL.value) is not None
        assert _find_req(result, doc_type=DocType.TITLE_REPORT.value) is not None
        assert _find_req(result, doc_type=DocType.HOMEOWNERS_INSURANCE.value) is not None

    def test_conventional_purchase_requires_contract(self, service):
        data = _base_loan_data(loan_type="conventional", loan_purpose="purchase")
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.PURCHASE_CONTRACT.value) is not None

    def test_conventional_refinance_no_purchase_contract(self, service):
        data = _base_loan_data(loan_type="conventional", loan_purpose="refinance")
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.PURCHASE_CONTRACT.value) is None

    def test_conventional_no_fha_or_va_docs(self, service):
        data = _base_loan_data(loan_type="conventional")
        result = service.analyze_loan_application(1, application_data=data)

        # Should NOT have FHA cert or VA COE
        assert _find_req(result, doc_type=DocType.FHA_CERT.value) is None
        assert _find_req(result, doc_type=DocType.VA_COE.value) is None
        assert _find_req(result, doc_type=DocType.DD214.value) is None

    def test_conventional_program_detected_from_keywords(self, service):
        """Various keyword patterns should all map to CONVENTIONAL."""
        for keyword in ["conventional", "conv", "fnma", "fannie", "freddie", "fhlmc"]:
            data = _base_loan_data(loan_type=keyword, loan_amount=400_000)
            result = service.analyze_loan_application(1, application_data=data)
            assert result.success is True
            # No FHA/VA/USDA-specific docs
            assert _find_req(result, doc_type=DocType.FHA_CERT.value) is None
            assert _find_req(result, doc_type=DocType.VA_COE.value) is None


# =============================================================================
# 2. FHA Loan Additional Requirements
# =============================================================================

class TestFHALoan:
    """FHA loans require FHA case number and employment history verification
    in addition to standard docs."""

    def test_fha_has_case_number_cert(self, service):
        data = _base_loan_data(loan_type="fha")
        result = service.analyze_loan_application(1, application_data=data)

        cert = _find_req(result, doc_type=DocType.FHA_CERT.value)
        assert cert is not None
        assert cert.priority == RequestPriority.HIGH.value

    def test_fha_has_employment_history_verification(self, service):
        data = _base_loan_data(loan_type="fha")
        result = service.analyze_loan_application(1, application_data=data)

        emp_hist = _find_req(result, title_contains="FHA Employment History")
        assert emp_hist is not None
        assert emp_hist.category == "special"

    def test_fha_still_has_standard_docs(self, service):
        data = _base_loan_data(loan_type="fha")
        result = service.analyze_loan_application(1, application_data=data)

        assert _find_req(result, doc_type=DocType.DRIVERS_LICENSE.value) is not None
        assert _find_req(result, doc_type=DocType.PAYSTUB.value) is not None
        assert _find_req(result, doc_type=DocType.W2.value) is not None
        assert _find_req(result, doc_type=DocType.BANK_STATEMENT.value) is not None


# =============================================================================
# 3. VA Loan Requirements
# =============================================================================

class TestVALoan:
    """VA loans require Certificate of Eligibility and DD-214."""

    def test_va_requires_coe(self, service):
        data = _base_loan_data(loan_type="va")
        result = service.analyze_loan_application(1, application_data=data)

        coe = _find_req(result, doc_type=DocType.VA_COE.value)
        assert coe is not None
        assert coe.priority == RequestPriority.CRITICAL.value
        assert coe.category == "identity"

    def test_va_requires_dd214(self, service):
        data = _base_loan_data(loan_type="va")
        result = service.analyze_loan_application(1, application_data=data)

        dd214 = _find_req(result, doc_type=DocType.DD214.value)
        assert dd214 is not None
        assert dd214.priority == RequestPriority.HIGH.value
        assert dd214.category == "identity"

    def test_va_does_not_include_fha_cert(self, service):
        data = _base_loan_data(loan_type="va")
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.FHA_CERT.value) is None


# =============================================================================
# 4. USDA Loan Requirements
# =============================================================================

class TestUSDALoan:
    """USDA loans require property eligibility and household income verification."""

    def test_usda_requires_property_eligibility(self, service):
        data = _base_loan_data(loan_type="usda")
        result = service.analyze_loan_application(1, application_data=data)

        eligibility = _find_req(result, title_contains="USDA Property Eligibility")
        assert eligibility is not None
        assert eligibility.priority == RequestPriority.HIGH.value
        assert eligibility.category == "special"

    def test_usda_requires_household_income_docs(self, service):
        data = _base_loan_data(loan_type="usda")
        result = service.analyze_loan_application(1, application_data=data)

        household = _find_req(result, title_contains="Household Income Documentation")
        assert household is not None
        assert household.applies_to == AppliesTo.BOTH.value

    def test_usda_keyword_patterns(self, service):
        """Keywords 'usda', 'rural', 'rd' should all trigger USDA requirements."""
        for keyword in ["usda", "rural", "rd"]:
            data = _base_loan_data(loan_type=keyword)
            result = service.analyze_loan_application(1, application_data=data)
            assert _find_req(result, title_contains="USDA Property Eligibility") is not None


# =============================================================================
# 5. Self-Employed Borrower Requirements
# =============================================================================

class TestSelfEmployed:
    """Self-employed borrowers need tax returns, P&L, balance sheet, and
    business tax returns."""

    def test_self_employed_requires_personal_tax_returns(self, service):
        data = _base_loan_data(employment_status="Self-Employed")
        result = service.analyze_loan_application(1, application_data=data)

        tax = _find_req(result, doc_type=DocType.TAX_RETURN.value,
                        applies_to=AppliesTo.BORROWER.value)
        assert tax is not None
        assert tax.priority == RequestPriority.CRITICAL.value
        assert tax.required_count == 2  # 2 years

    def test_self_employed_requires_business_tax_returns(self, service):
        data = _base_loan_data(employment_status="Self-Employed")
        result = service.analyze_loan_application(1, application_data=data)

        biz_tax = _find_req(result, doc_type=DocType.BUSINESS_TAX_RETURN.value)
        assert biz_tax is not None
        assert biz_tax.priority == RequestPriority.CRITICAL.value
        assert biz_tax.required_count == 2

    def test_self_employed_requires_profit_loss(self, service):
        data = _base_loan_data(employment_status="Self-Employed")
        result = service.analyze_loan_application(1, application_data=data)

        pnl = _find_req(result, doc_type=DocType.PROFIT_LOSS.value)
        assert pnl is not None
        assert pnl.freshness_days == 90
        assert pnl.auto_renew is True

    def test_self_employed_requires_balance_sheet(self, service):
        data = _base_loan_data(employment_status="Self-Employed")
        result = service.analyze_loan_application(1, application_data=data)

        balance = _find_req(result, doc_type=DocType.BALANCE_SHEET.value)
        assert balance is not None
        assert balance.priority == RequestPriority.NORMAL.value

    def test_self_employed_detection_from_keywords(self, service):
        """Various employment_status keywords should trigger self-employed path."""
        keywords = ["self-employed", "business owner", "1099 contractor",
                     "freelancer", "independent contractor"]
        for kw in keywords:
            data = _base_loan_data(employment_status=kw)
            result = service.analyze_loan_application(1, application_data=data)
            assert _find_req(result, doc_type=DocType.BUSINESS_TAX_RETURN.value) is not None, \
                f"Keyword '{kw}' did not trigger self-employed requirements"

    def test_self_employed_via_notes(self, service):
        """Self-employment should also be detected from notes field."""
        data = _base_loan_data(
            employment_status="",
            notes="Borrower is self employed, runs a landscaping company",
        )
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.BUSINESS_TAX_RETURN.value) is not None

    def test_self_employed_via_metadata(self, service):
        """Self-employment detected from user_metadata flag."""
        data = _base_loan_data(
            employment_status="",
            user_metadata={"is_self_employed": True},
        )
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.BUSINESS_TAX_RETURN.value) is not None


# =============================================================================
# 6. W2 Employee Requirements
# =============================================================================

class TestW2Employee:
    """W2 employees need paystubs and W2 forms. Variable income triggers tax returns."""

    def test_w2_requires_paystubs(self, service):
        data = _base_loan_data(employment_status="W2 Employee")
        result = service.analyze_loan_application(1, application_data=data)

        paystub = _find_req(result, doc_type=DocType.PAYSTUB.value,
                            applies_to=AppliesTo.BORROWER.value)
        assert paystub is not None
        assert paystub.priority == RequestPriority.CRITICAL.value
        assert paystub.freshness_days == 30
        assert paystub.auto_renew is True

    def test_w2_requires_w2_forms(self, service):
        data = _base_loan_data(employment_status="W2 Employee")
        result = service.analyze_loan_application(1, application_data=data)

        w2 = _find_req(result, doc_type=DocType.W2.value,
                       applies_to=AppliesTo.BORROWER.value)
        assert w2 is not None
        assert w2.required_count == 2  # 2 years

    def test_w2_no_business_docs(self, service):
        """W2 employees should NOT have business tax returns or P&L."""
        data = _base_loan_data(employment_status="W2 Employee")
        result = service.analyze_loan_application(1, application_data=data)

        assert _find_req(result, doc_type=DocType.BUSINESS_TAX_RETURN.value) is None
        assert _find_req(result, doc_type=DocType.PROFIT_LOSS.value) is None
        assert _find_req(result, doc_type=DocType.BALANCE_SHEET.value) is None

    def test_w2_variable_income_triggers_tax_returns(self, service):
        """If notes mention commission/bonus, tax returns should be added."""
        data = _base_loan_data(
            employment_status="W2 Employee",
            notes="Borrower receives commission income, about 30% of total"
        )
        result = service.analyze_loan_application(1, application_data=data)

        tax = _find_req(result, doc_type=DocType.TAX_RETURN.value,
                        title_contains="Variable Income")
        assert tax is not None
        assert tax.priority == RequestPriority.HIGH.value


# =============================================================================
# 7. Gift Funds Documentation Requirements
# =============================================================================

class TestGiftFunds:
    """Gift funds trigger a gift letter requirement."""

    def test_gift_funds_flag_triggers_gift_letter(self, service):
        data = _base_loan_data(has_gift_funds=True)
        result = service.analyze_loan_application(1, application_data=data)

        gift = _find_req(result, doc_type=DocType.GIFT_LETTER.value)
        assert gift is not None
        assert gift.priority == RequestPriority.CRITICAL.value
        assert gift.category == "assets"

    def test_gift_funds_detected_from_notes(self, service):
        data = _base_loan_data(notes="Borrower will receive a gift from parents for down payment")
        result = service.analyze_loan_application(1, application_data=data)

        gift = _find_req(result, doc_type=DocType.GIFT_LETTER.value)
        assert gift is not None

    def test_gift_funds_detected_from_metadata(self, service):
        data = _base_loan_data(user_metadata={"has_gift_funds": True})
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.GIFT_LETTER.value) is not None

    def test_no_gift_letter_when_no_gift_funds(self, service):
        data = _base_loan_data(has_gift_funds=False, notes="")
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.GIFT_LETTER.value) is None


# =============================================================================
# 8. Bankruptcy Documentation Requirements
# =============================================================================

class TestBankruptcy:
    """Bankruptcy triggers bankruptcy discharge papers requirement."""

    def test_bankruptcy_flag_triggers_discharge_papers(self, service):
        data = _base_loan_data(has_bankruptcy=True)
        result = service.analyze_loan_application(1, application_data=data)

        bk = _find_req(result, doc_type=DocType.BANKRUPTCY_DISCHARGE.value)
        assert bk is not None
        assert bk.priority == RequestPriority.HIGH.value
        assert bk.category == "credit"

    def test_bankruptcy_detected_from_notes(self, service):
        data = _base_loan_data(notes="Borrower filed chapter 7 bankruptcy in 2020")
        result = service.analyze_loan_application(1, application_data=data)

        bk = _find_req(result, doc_type=DocType.BANKRUPTCY_DISCHARGE.value)
        assert bk is not None

    def test_bankruptcy_detected_from_metadata(self, service):
        data = _base_loan_data(user_metadata={"has_bankruptcy": True})
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.BANKRUPTCY_DISCHARGE.value) is not None

    def test_no_bankruptcy_docs_when_clean(self, service):
        data = _base_loan_data(has_bankruptcy=False, notes="")
        result = service.analyze_loan_application(1, application_data=data)
        assert _find_req(result, doc_type=DocType.BANKRUPTCY_DISCHARGE.value) is None


# =============================================================================
# 9. Investment Property Additional Docs
# =============================================================================

class TestInvestmentProperty:
    """Investment properties require lease agreements, Schedule E tax returns,
    and reserve verification."""

    def test_investment_requires_lease_agreements(self, service):
        data = _base_loan_data(occupancy_type="investment")
        result = service.analyze_loan_application(1, application_data=data)

        lease = _find_req(result, doc_type=DocType.LEASE_AGREEMENT.value,
                          title_contains="Current Lease")
        assert lease is not None
        assert lease.category == "special"

    def test_investment_requires_schedule_e_tax_returns(self, service):
        data = _base_loan_data(occupancy_type="investment")
        result = service.analyze_loan_application(1, application_data=data)

        schedule_e = _find_req(result, doc_type=DocType.TAX_RETURN.value,
                               title_contains="Schedule E")
        assert schedule_e is not None
        assert schedule_e.required_count == 2

    def test_investment_requires_reserve_verification(self, service):
        data = _base_loan_data(occupancy_type="investment")
        result = service.analyze_loan_application(1, application_data=data)

        reserves = _find_req(result, title_contains="Reserve Verification")
        assert reserves is not None
        assert reserves.doc_type == DocType.BANK_STATEMENT.value

    def test_investment_keyword_patterns(self, service):
        """Keywords 'investment', 'non-owner', 'rental', 'noo' should all
        trigger investment requirements."""
        for kw in ["investment", "non-owner", "rental", "noo"]:
            data = _base_loan_data(occupancy_type=kw)
            result = service.analyze_loan_application(1, application_data=data)
            lease = _find_req(result, doc_type=DocType.LEASE_AGREEMENT.value,
                              title_contains="Current Lease")
            assert lease is not None, f"Keyword '{kw}' did not trigger investment docs"


# =============================================================================
# 10. Co-Borrower Document Requirements
# =============================================================================

class TestCoBorrower:
    """When a co-borrower is present, additional identity, income, and asset
    documents are required."""

    def test_coborrower_requires_separate_id(self, service):
        data = _base_loan_data(coborrower_name="Jane Doe")
        result = service.analyze_loan_application(1, application_data=data)

        co_id = _find_req(result, doc_type=DocType.DRIVERS_LICENSE.value,
                          applies_to=AppliesTo.CO_BORROWER.value)
        assert co_id is not None
        assert co_id.priority == RequestPriority.CRITICAL.value

    def test_coborrower_requires_paystubs(self, service):
        data = _base_loan_data(coborrower_name="Jane Doe")
        result = service.analyze_loan_application(1, application_data=data)

        co_pay = _find_req(result, doc_type=DocType.PAYSTUB.value,
                           applies_to=AppliesTo.CO_BORROWER.value)
        assert co_pay is not None
        assert co_pay.freshness_days == 30

    def test_coborrower_requires_w2s(self, service):
        data = _base_loan_data(coborrower_name="Jane Doe")
        result = service.analyze_loan_application(1, application_data=data)

        co_w2 = _find_req(result, doc_type=DocType.W2.value,
                          applies_to=AppliesTo.CO_BORROWER.value)
        assert co_w2 is not None
        assert co_w2.required_count == 2

    def test_coborrower_requires_bank_statements(self, service):
        data = _base_loan_data(coborrower_name="Jane Doe")
        result = service.analyze_loan_application(1, application_data=data)

        co_bank = _find_req(result, doc_type=DocType.BANK_STATEMENT.value,
                            applies_to=AppliesTo.CO_BORROWER.value)
        assert co_bank is not None

    def test_no_coborrower_docs_when_solo(self, service):
        data = _base_loan_data(coborrower_name=None)
        result = service.analyze_loan_application(1, application_data=data)

        co_docs = _find_reqs(result, applies_to=AppliesTo.CO_BORROWER.value)
        assert len(co_docs) == 0

    def test_analysis_notes_mention_coborrower(self, service):
        data = _base_loan_data(coborrower_name="Jane Doe")
        result = service.analyze_loan_application(1, application_data=data)

        coborrower_notes = [n for n in result.analysis_notes if "co-borrower" in n.lower()]
        assert len(coborrower_notes) > 0


# =============================================================================
# 11. Occupancy Type Differences
# =============================================================================

class TestOccupancyDifferences:
    """Primary, second home, and investment occupancies produce different requirements."""

    def test_primary_no_investment_docs(self, service):
        data = _base_loan_data(occupancy_type="primary")
        result = service.analyze_loan_application(1, application_data=data)

        # Should not have investment-specific lease or reserve docs
        assert _find_req(result, title_contains="Reserve Verification") is None
        assert _find_req(result, title_contains="Schedule E") is None

    def test_second_home_no_investment_docs(self, service):
        data = _base_loan_data(occupancy_type="second home")
        result = service.analyze_loan_application(1, application_data=data)

        assert _find_req(result, title_contains="Reserve Verification") is None

    def test_investment_has_more_docs_than_primary(self, service):
        primary_data = _base_loan_data(occupancy_type="primary")
        investment_data = _base_loan_data(occupancy_type="investment")

        primary_result = service.analyze_loan_application(1, application_data=primary_data)
        investment_result = service.analyze_loan_application(1, application_data=investment_data)

        assert investment_result.total_documents_needed > primary_result.total_documents_needed

    def test_second_home_detected_from_keywords(self, service):
        for kw in ["second home", "second_home", "vacation"]:
            data = _base_loan_data(occupancy_type=kw)
            normalized = service._normalize_loan_data(data)
            assert normalized["occupancy_normalized"] == "SECOND_HOME", \
                f"Keyword '{kw}' did not normalize to SECOND_HOME"


# =============================================================================
# 12. Retirement Income Documentation
# =============================================================================

class TestRetirementIncome:
    """Retired borrowers need pension/SS award letter, tax returns, and
    retirement account statements."""

    def test_retired_requires_award_letter(self, service):
        data = _base_loan_data(employment_status="retired")
        result = service.analyze_loan_application(1, application_data=data)

        award = _find_req(result, title_contains="Pension / Social Security Award")
        assert award is not None
        assert award.priority == RequestPriority.CRITICAL.value
        assert award.category == "income"

    def test_retired_requires_tax_return(self, service):
        data = _base_loan_data(employment_status="retired")
        result = service.analyze_loan_application(1, application_data=data)

        tax = _find_req(result, doc_type=DocType.TAX_RETURN.value,
                        applies_to=AppliesTo.BORROWER.value)
        assert tax is not None
        assert tax.required_count == 1  # Only 1 year for retirees

    def test_retired_requires_account_statements(self, service):
        data = _base_loan_data(employment_status="retired")
        result = service.analyze_loan_application(1, application_data=data)

        stmts = _find_req(result, doc_type=DocType.INVESTMENT_STATEMENT.value,
                          title_contains="Retirement Account")
        assert stmts is not None
        assert stmts.freshness_days == 90
        assert stmts.auto_renew is True

    def test_retired_no_paystubs_or_w2(self, service):
        """Retired borrowers should not have W2-style paystub/W2 requirements."""
        data = _base_loan_data(employment_status="retired")
        result = service.analyze_loan_application(1, application_data=data)

        # Should not have W2 income reqs (paystubs and W2 forms are W2-specific)
        borrower_paystubs = _find_req(result, doc_type=DocType.PAYSTUB.value,
                                      applies_to=AppliesTo.BORROWER.value)
        borrower_w2 = _find_req(result, doc_type=DocType.W2.value,
                                applies_to=AppliesTo.BORROWER.value)
        assert borrower_paystubs is None
        assert borrower_w2 is None

    def test_retired_detection_from_pension_keyword(self, service):
        data = _base_loan_data(employment_status="pension recipient")
        normalized = service._normalize_loan_data(data)
        assert normalized["income_classification"] == "RETIRED"


# =============================================================================
# 13. Document Priority Assignment
# =============================================================================

class TestDocumentPriority:
    """Verify that priorities are correctly assigned for different document types."""

    def test_government_id_is_critical(self, service):
        data = _base_loan_data()
        result = service.analyze_loan_application(1, application_data=data)

        gov_id = _find_req(result, doc_type=DocType.DRIVERS_LICENSE.value)
        assert gov_id.priority == RequestPriority.CRITICAL.value

    def test_paystubs_are_critical(self, service):
        data = _base_loan_data()
        result = service.analyze_loan_application(1, application_data=data)

        paystub = _find_req(result, doc_type=DocType.PAYSTUB.value,
                            applies_to=AppliesTo.BORROWER.value)
        assert paystub.priority == RequestPriority.CRITICAL.value

    def test_bank_statements_are_critical(self, service):
        data = _base_loan_data()
        result = service.analyze_loan_application(1, application_data=data)

        bank = _find_req(result, doc_type=DocType.BANK_STATEMENT.value,
                         applies_to=AppliesTo.BORROWER.value)
        assert bank.priority == RequestPriority.CRITICAL.value

    def test_investment_statements_are_normal(self, service):
        data = _base_loan_data()
        result = service.analyze_loan_application(1, application_data=data)

        inv = _find_req(result, doc_type=DocType.INVESTMENT_STATEMENT.value,
                        applies_to=AppliesTo.BORROWER.value)
        assert inv.priority == RequestPriority.NORMAL.value

    def test_purchase_contract_is_critical(self, service):
        data = _base_loan_data(loan_purpose="purchase")
        result = service.analyze_loan_application(1, application_data=data)

        contract = _find_req(result, doc_type=DocType.PURCHASE_CONTRACT.value)
        assert contract.priority == RequestPriority.CRITICAL.value

    def test_va_coe_is_critical(self, service):
        data = _base_loan_data(loan_type="va")
        result = service.analyze_loan_application(1, application_data=data)

        coe = _find_req(result, doc_type=DocType.VA_COE.value)
        assert coe.priority == RequestPriority.CRITICAL.value

    def test_self_employed_balance_sheet_is_normal(self, service):
        data = _base_loan_data(employment_status="self-employed")
        result = service.analyze_loan_application(1, application_data=data)

        bs = _find_req(result, doc_type=DocType.BALANCE_SHEET.value)
        assert bs.priority == RequestPriority.NORMAL.value


# =============================================================================
# 14. Requirements Deduplication
# =============================================================================

class TestDeduplication:
    """The service deduplicates requirements, keeping the highest-priority version."""

    def test_dedup_keeps_higher_priority(self, service):
        """When two reqs have the same doc_type + applies_to, keep the higher priority."""
        reqs = [
            RequiredDocument(
                doc_type=DocType.BANK_STATEMENT.value,
                title="Bank Statements (Normal)",
                description="desc", instructions="inst", category="assets",
                priority=RequestPriority.NORMAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2, freshness_days=60, auto_renew=False,
                payroll_frequency=None, reason="reason1",
            ),
            RequiredDocument(
                doc_type=DocType.BANK_STATEMENT.value,
                title="Bank Statements (Critical)",
                description="desc", instructions="inst", category="assets",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2, freshness_days=60, auto_renew=False,
                payroll_frequency=None, reason="reason2",
            ),
        ]
        deduped = service._deduplicate_requirements(reqs)
        assert len(deduped) == 1
        assert deduped[0].priority == RequestPriority.CRITICAL.value

    def test_dedup_different_applies_to_kept_separate(self, service):
        """Same doc_type but different applies_to should not be deduped."""
        reqs = [
            RequiredDocument(
                doc_type=DocType.PAYSTUB.value,
                title="Borrower Paystubs", description="desc", instructions="inst",
                category="income", priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2, freshness_days=30, auto_renew=True,
                payroll_frequency=None, reason="reason1",
            ),
            RequiredDocument(
                doc_type=DocType.PAYSTUB.value,
                title="Co-Borrower Paystubs", description="desc", instructions="inst",
                category="income", priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.CO_BORROWER.value,
                required_count=2, freshness_days=30, auto_renew=True,
                payroll_frequency=None, reason="reason2",
            ),
        ]
        deduped = service._deduplicate_requirements(reqs)
        assert len(deduped) == 2

    def test_dedup_other_type_uses_title_in_key(self, service):
        """DocType.OTHER entries with different titles should NOT be deduped."""
        reqs = [
            RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="Divorce Decree", description="desc", instructions="inst",
                category="credit", priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1, freshness_days=None, auto_renew=False,
                payroll_frequency=None, reason="reason1",
            ),
            RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="Employment Offer Letter", description="desc", instructions="inst",
                category="income", priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1, freshness_days=None, auto_renew=False,
                payroll_frequency=None, reason="reason2",
            ),
        ]
        deduped = service._deduplicate_requirements(reqs)
        assert len(deduped) == 2

    def test_dedup_same_priority_keeps_higher_count(self, service):
        """When priority is equal, keep the one with higher required_count."""
        reqs = [
            RequiredDocument(
                doc_type=DocType.W2.value,
                title="W2 (1)", description="desc", instructions="inst",
                category="income", priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1, freshness_days=None, auto_renew=False,
                payroll_frequency=None, reason="reason1",
            ),
            RequiredDocument(
                doc_type=DocType.W2.value,
                title="W2 (2)", description="desc", instructions="inst",
                category="income", priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2, freshness_days=None, auto_renew=False,
                payroll_frequency=None, reason="reason2",
            ),
        ]
        deduped = service._deduplicate_requirements(reqs)
        assert len(deduped) == 1
        assert deduped[0].required_count == 2

    def test_full_analysis_has_no_exact_duplicates(self, service):
        """A full analysis with coborrower, gift funds, and bankruptcy should
        not produce any exact (doc_type, applies_to) duplicates for non-OTHER types."""
        data = _base_loan_data(
            coborrower_name="Jane Doe",
            has_gift_funds=True,
            has_bankruptcy=True,
            loan_purpose="purchase",
        )
        result = service.analyze_loan_application(1, application_data=data)

        seen_keys = set()
        for req in result.requirements:
            if req.doc_type == DocType.OTHER.value:
                key = f"{req.doc_type}:{req.applies_to}:{req.title}"
            else:
                key = f"{req.doc_type}:{req.applies_to}"
            assert key not in seen_keys, f"Duplicate requirement found: {key}"
            seen_keys.add(key)


# =============================================================================
# Additional Coverage: Normalization, Jumbo, Condo, Call Intelligence, Errors
# =============================================================================

class TestNormalization:
    """Test the _normalize_loan_data method for various edge cases."""

    def test_jumbo_auto_detected_from_loan_amount(self, service):
        """Loan amount above conforming limit should auto-detect as JUMBO."""
        data = _base_loan_data(
            loan_type="",
            loan_amount=_CONFORMING_LIMIT_2025 + 1,
        )
        normalized = service._normalize_loan_data(data)
        assert normalized["program_type"] == "JUMBO"

    def test_jumbo_requires_extended_bank_statements(self, service):
        data = _base_loan_data(loan_type="jumbo")
        result = service.analyze_loan_application(1, application_data=data)

        bank = _find_req(result, doc_type=DocType.BANK_STATEMENT.value,
                         applies_to=AppliesTo.BORROWER.value)
        assert bank is not None
        assert bank.required_count == 12  # 12 months for jumbo

    def test_condo_requires_hoa_docs(self, service):
        data = _base_loan_data(property_type="condo")
        result = service.analyze_loan_application(1, application_data=data)

        hoa = _find_req(result, title_contains="Condominium Questionnaire")
        assert hoa is not None
        assert hoa.category == "property"

    def test_multi_family_requires_lease_agreements(self, service):
        data = _base_loan_data(property_type="duplex")
        result = service.analyze_loan_application(1, application_data=data)

        lease = _find_req(result, doc_type=DocType.LEASE_AGREEMENT.value,
                          title_contains="Rental Units")
        assert lease is not None

    def test_manufactured_home_detected(self, service):
        data = _base_loan_data(property_type="manufactured")
        normalized = service._normalize_loan_data(data)
        assert normalized["property_normalized"] == "MANUFACTURED"

    def test_purchase_vs_refinance_detection(self, service):
        purchase_data = _base_loan_data(loan_purpose="purchase")
        normalized_p = service._normalize_loan_data(purchase_data)
        assert normalized_p["is_purchase"] is True
        assert normalized_p["is_refinance"] is False

        refi_data = _base_loan_data(loan_purpose="cash out refinance")
        normalized_r = service._normalize_loan_data(refi_data)
        assert normalized_r["is_refinance"] is True

    def test_military_income_classification(self, service):
        data = _base_loan_data(employment_status="active duty military")
        normalized = service._normalize_loan_data(data)
        assert normalized["income_classification"] == "MILITARY"


class TestNonQM:
    """Non-QM programs require extended bank statements for income qualification."""

    def test_non_qm_requires_12_month_bank_statements(self, service):
        data = _base_loan_data(loan_type="non-qm")
        result = service.analyze_loan_application(1, application_data=data)

        non_qm_stmts = _find_req(result, doc_type=DocType.BANK_STATEMENT.value,
                                  title_contains="Income Qualification")
        assert non_qm_stmts is not None
        assert non_qm_stmts.required_count == 12
        assert non_qm_stmts.priority == RequestPriority.CRITICAL.value

    def test_non_qm_detected_from_keywords(self, service):
        for kw in ["non-qm", "bank statement", "dscr", "asset depletion"]:
            data = _base_loan_data(loan_type=kw)
            normalized = service._normalize_loan_data(data)
            assert normalized["program_type"] == "NON_QM", \
                f"Keyword '{kw}' did not map to NON_QM"


class TestCallIntelligence:
    """Test analyze_from_call_intelligence pattern matching."""

    def test_job_change_mentioned(self, service):
        notes = [{"content": "Borrower mentioned they just changed jobs last month"}]
        reqs = service.analyze_from_call_intelligence(1, notes)

        paystub_reqs = [r for r in reqs if r.doc_type == DocType.PAYSTUB.value]
        assert len(paystub_reqs) >= 1

    def test_gift_funds_mentioned(self, service):
        notes = [{"content": "Parent is giving gift funds for the down payment"}]
        reqs = service.analyze_from_call_intelligence(1, notes)

        gift_reqs = [r for r in reqs if r.doc_type == DocType.GIFT_LETTER.value]
        assert len(gift_reqs) == 1

    def test_bankruptcy_mentioned(self, service):
        notes = [{"content": "Borrower filed chapter 7 bankruptcy three years ago"}]
        reqs = service.analyze_from_call_intelligence(1, notes)

        bk_reqs = [r for r in reqs if r.doc_type == DocType.BANKRUPTCY_DISCHARGE.value]
        assert len(bk_reqs) == 1

    def test_empty_notes_returns_empty(self, service):
        reqs = service.analyze_from_call_intelligence(1, [])
        assert reqs == []

    def test_retirement_income_mentioned(self, service):
        notes = [{"content": "Borrower is retired and receives pension income monthly"}]
        reqs = service.analyze_from_call_intelligence(1, notes)

        pension_reqs = [r for r in reqs if "Pension" in r.title or "Retirement" in r.title]
        assert len(pension_reqs) >= 1


class TestCategoryBreakdown:
    """Verify the categories dict in the analysis result counts correctly."""

    def test_categories_sum_to_total(self, service):
        data = _base_loan_data(
            coborrower_name="Jane Doe",
            has_gift_funds=True,
            loan_purpose="purchase",
        )
        result = service.analyze_loan_application(1, application_data=data)

        category_sum = sum(result.categories.values())
        assert category_sum == result.total_documents_needed

    def test_identity_category_present(self, service):
        data = _base_loan_data()
        result = service.analyze_loan_application(1, application_data=data)
        assert "identity" in result.categories
        assert result.categories["identity"] >= 1


class TestErrorHandling:
    """Test error handling when loan data is missing or invalid."""

    def test_loan_not_found_returns_failure(self, service, mock_db):
        """When DB returns no loan, result should indicate failure."""
        mock_db.execute.return_value.fetchone.return_value = None
        result = service.analyze_loan_application(999)

        assert result.success is False
        assert result.error is not None
        assert "999" in result.error

    def test_analysis_with_minimal_data(self, service):
        """Minimal application_data should still succeed with defaults."""
        data = {"loan_id": 1}
        result = service.analyze_loan_application(1, application_data=data)

        assert result.success is True
        # Should at least require an ID
        assert result.total_documents_needed > 0


class TestStateNotes:
    """Test that state-specific notes appear in analysis."""

    def test_texas_note_added(self, service):
        data = _base_loan_data(property_state="TX")
        result = service.analyze_loan_application(1, application_data=data)

        tx_notes = [n for n in result.analysis_notes if "Texas" in n]
        assert len(tx_notes) > 0

    def test_california_note_added(self, service):
        data = _base_loan_data(property_state="CA")
        result = service.analyze_loan_application(1, application_data=data)

        ca_notes = [n for n in result.analysis_notes if "California" in n]
        assert len(ca_notes) > 0

    def test_non_special_state_no_extra_note(self, service):
        data = _base_loan_data(property_state="FL")
        result = service.analyze_loan_application(1, application_data=data)

        state_notes = [n for n in result.analysis_notes if "State note:" in n]
        assert len(state_notes) == 0


class TestFirstTimeBuyer:
    """First-time buyers need rental payment history verification."""

    def test_first_time_buyer_requires_rental_history(self, service):
        data = _base_loan_data(first_time_buyer=True)
        result = service.analyze_loan_application(1, application_data=data)

        rental = _find_req(result, title_contains="Rental Payment History")
        assert rental is not None
        assert rental.category == "credit"

    def test_non_first_time_no_rental_history(self, service):
        data = _base_loan_data(first_time_buyer=False)
        result = service.analyze_loan_application(1, application_data=data)

        rental = _find_req(result, title_contains="Rental Payment History")
        assert rental is None
