"""
Test AUS Integration — DU and LPA submission business logic.

Tests the AUSIntegrationService mock responses, MISMO mapping,
income comparison, findings import, submission history, and
tenant isolation. All tests use mock mode (no live API calls).

Run:
    pytest tests/test_aus_integration.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# =============================================================================
# MISMO Mapping Tests
# =============================================================================

@pytest.mark.unit
class TestMISMOMapping:
    """Test MISMO 3.4 data mapping from loan data."""

    def test_loan_purpose_mapping(self):
        """Verify CRM loan purposes map to MISMO LoanPurposeType values."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        assert AUSIntegrationService._map_loan_purpose("purchase") == "Purchase"
        assert AUSIntegrationService._map_loan_purpose("refinance") == "Refinance"
        assert AUSIntegrationService._map_loan_purpose("cashout_refinance") == "CashOutRefinance"
        assert AUSIntegrationService._map_loan_purpose("cash_out") == "CashOutRefinance"
        assert AUSIntegrationService._map_loan_purpose("construction") == "Construction"
        assert AUSIntegrationService._map_loan_purpose(None) == "Purchase"
        assert AUSIntegrationService._map_loan_purpose("unknown_type") == "Purchase"

    def test_loan_type_mapping(self):
        """Verify CRM loan types map to MISMO MortgageType values."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        assert AUSIntegrationService._map_loan_type("conventional") == "Conventional"
        assert AUSIntegrationService._map_loan_type("fha") == "FHA"
        assert AUSIntegrationService._map_loan_type("va") == "VA"
        assert AUSIntegrationService._map_loan_type("usda") == "USDA"
        assert AUSIntegrationService._map_loan_type("jumbo") == "Jumbo"
        assert AUSIntegrationService._map_loan_type("non_qm") == "Other"
        assert AUSIntegrationService._map_loan_type(None) == "Conventional"

    def test_property_type_mapping(self):
        """Verify CRM property types map to MISMO PropertyType values."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        assert AUSIntegrationService._map_property_type("single_family") == "SingleFamily"
        assert AUSIntegrationService._map_property_type("condo") == "Condominium"
        assert AUSIntegrationService._map_property_type("townhouse") == "Townhouse"
        assert AUSIntegrationService._map_property_type("multi_family") == "TwoToFourFamily"
        assert AUSIntegrationService._map_property_type("manufactured") == "ManufacturedHousing"
        assert AUSIntegrationService._map_property_type(None) == "SingleFamily"

    def test_occupancy_type_mapping(self):
        """Verify CRM occupancy types map to MISMO OccupancyType values."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        assert AUSIntegrationService._map_occupancy_type("primary") == "PrimaryResidence"
        assert AUSIntegrationService._map_occupancy_type("second_home") == "SecondHome"
        assert AUSIntegrationService._map_occupancy_type("investment") == "InvestmentProperty"
        assert AUSIntegrationService._map_occupancy_type(None) == "PrimaryResidence"

    def test_mismo_structure_has_required_sections(self):
        """MISMO output must contain DEAL with required sub-sections."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        # Create a mock loan object
        mock_loan = MagicMock()
        mock_loan.loan_number = "TEST-001"
        mock_loan.loan_purpose = "purchase"
        mock_loan.loan_type = "conventional"
        mock_loan.amount = 350000
        mock_loan.rate = 6.75
        mock_loan.term = 360
        mock_loan.borrower_name = "John Doe"
        mock_loan.borrower_email = "john@example.com"
        mock_loan.borrower_phone = "555-0100"
        mock_loan.coborrower_name = None
        mock_loan.co_borrower_email = None
        mock_loan.property_address = "123 Main St"
        mock_loan.property_city = "Austin"
        mock_loan.property_state = "TX"
        mock_loan.property_zip = "78701"
        mock_loan.property_type = "single_family"
        mock_loan.occupancy_type = "primary"
        mock_loan.property_units = 1
        mock_loan.purchase_price = 400000
        mock_loan.appraisal_value = 410000
        mock_loan.monthly_payment = None
        mock_loan.second_loan_amount = None
        mock_loan.second_loan_payment = None
        mock_loan.rate_type = "Fixed"
        mock_loan.index_rate = None
        mock_loan.margin = None
        mock_loan.ltv = 87.5
        mock_loan.cltv = 87.5

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_loan

        service = AUSIntegrationService(mock_db)
        # Patch _load_income_data to return None (no income calc available)
        service._load_income_data = MagicMock(return_value=None)

        mismo = service.map_loan_to_mismo(loan_id=1, org_id=1)

        assert "DEAL" in mismo
        deal = mismo["DEAL"]
        assert "LOANS" in deal
        assert "PARTIES" in deal
        assert "COLLATERALS" in deal
        assert "LIABILITIES" in deal
        assert "ASSETS" in deal
        assert "INCOME" in deal
        assert "LOAN_PRODUCT" in deal
        assert "RATIOS" in deal

        # Verify loan details
        loan_data = deal["LOANS"]["LOAN"]
        assert loan_data["LoanIdentifier"] == "TEST-001"
        assert loan_data["BaseLoanAmount"] == 350000
        assert loan_data["NoteRatePercent"] == 6.75
        assert loan_data["LoanTermMonths"] == 360

        # Verify borrower
        borrower = deal["PARTIES"]["PARTY"][0]
        assert borrower["INDIVIDUAL"]["NAME"]["FirstName"] == "John"
        assert borrower["INDIVIDUAL"]["NAME"]["LastName"] == "Doe"

        # Verify property
        prop = deal["COLLATERALS"]["COLLATERAL"]["SUBJECT_PROPERTY"]
        assert prop["State"] == "TX"
        assert prop["PropertyType"] == "SingleFamily"

    def test_mismo_with_coborrower(self):
        """MISMO output should include coborrower when present."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_loan = MagicMock()
        mock_loan.loan_number = "TEST-002"
        mock_loan.loan_purpose = "purchase"
        mock_loan.loan_type = "fha"
        mock_loan.amount = 300000
        mock_loan.rate = 7.0
        mock_loan.term = 360
        mock_loan.borrower_name = "Jane Smith"
        mock_loan.borrower_email = "jane@example.com"
        mock_loan.borrower_phone = "555-0200"
        mock_loan.coborrower_name = "Bob Smith"
        mock_loan.co_borrower_email = "bob@example.com"
        mock_loan.property_address = "456 Oak Ave"
        mock_loan.property_city = "Dallas"
        mock_loan.property_state = "TX"
        mock_loan.property_zip = "75201"
        mock_loan.property_type = "condo"
        mock_loan.occupancy_type = "primary"
        mock_loan.property_units = 1
        mock_loan.purchase_price = 350000
        mock_loan.appraisal_value = 360000
        mock_loan.monthly_payment = None
        mock_loan.second_loan_amount = None
        mock_loan.second_loan_payment = None
        mock_loan.rate_type = "Fixed"
        mock_loan.index_rate = None
        mock_loan.margin = None
        mock_loan.ltv = 85.71
        mock_loan.cltv = 85.71

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_loan

        service = AUSIntegrationService(mock_db)
        service._load_income_data = MagicMock(return_value=None)

        mismo = service.map_loan_to_mismo(loan_id=2, org_id=1)

        borrower = mismo["DEAL"]["PARTIES"]["PARTY"][0]
        assert "COBORROWER" in borrower
        assert borrower["COBORROWER"]["NAME"]["FirstName"] == "Bob"
        assert borrower["COBORROWER"]["NAME"]["LastName"] == "Smith"

    def test_loan_not_found_raises_value_error(self):
        """map_loan_to_mismo should raise ValueError if loan does not exist."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AUSIntegrationService(mock_db)

        with pytest.raises(ValueError, match="Loan 999 not found"):
            service.map_loan_to_mismo(loan_id=999, org_id=1)


# =============================================================================
# DU Submission Tests (Mock)
# =============================================================================

@pytest.mark.unit
class TestDUSubmission:
    """Test Desktop Underwriter mock submission."""

    def _make_service_and_loan(self):
        """Helper to create a service with a mock loan."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_loan = MagicMock()
        mock_loan.loan_number = "DU-TEST-001"
        mock_loan.loan_purpose = "purchase"
        mock_loan.loan_type = "conventional"
        mock_loan.amount = 400000
        mock_loan.rate = 6.5
        mock_loan.term = 360
        mock_loan.borrower_name = "Alice Johnson"
        mock_loan.borrower_email = "alice@example.com"
        mock_loan.borrower_phone = "555-0300"
        mock_loan.coborrower_name = None
        mock_loan.co_borrower_email = None
        mock_loan.property_address = "789 Pine Rd"
        mock_loan.property_city = "Houston"
        mock_loan.property_state = "TX"
        mock_loan.property_zip = "77001"
        mock_loan.property_type = "single_family"
        mock_loan.occupancy_type = "primary"
        mock_loan.property_units = 1
        mock_loan.purchase_price = 500000
        mock_loan.appraisal_value = 510000
        mock_loan.monthly_payment = None
        mock_loan.second_loan_amount = None
        mock_loan.second_loan_payment = None
        mock_loan.rate_type = "Fixed"
        mock_loan.index_rate = None
        mock_loan.margin = None
        mock_loan.ltv = 80.0
        mock_loan.cltv = 80.0

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_loan

        service = AUSIntegrationService(mock_db)
        # Ensure mock mode (no API URL)
        service.du_api_url = ""
        service.lpa_api_url = ""
        service._load_income_data = MagicMock(return_value=None)

        return service

    def test_du_submission_returns_result(self):
        """DU mock submission should return a valid AUSSubmissionResult."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        assert result.aus_type == "DU"
        assert result.case_id.startswith("DU-")
        assert result.recommendation in ("Approve/Eligible", "Refer", "Caution", "Out of Scope")
        assert result.risk_class in ("Accept", "Refer with Caution")
        assert len(result.conditions) > 0
        assert len(result.findings) > 0
        assert result.submitted_at is not None

    def test_du_conditions_have_required_fields(self):
        """Each DU condition must have condition_id, category, description, status."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        for cond in result.conditions:
            d = cond.to_dict()
            assert "condition_id" in d
            assert "category" in d
            assert "description" in d
            assert "status" in d
            assert d["condition_id"].startswith("DU-C-")

    def test_du_findings_have_required_fields(self):
        """Each DU finding must have finding_id, code, message, severity."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        for finding in result.findings:
            d = finding.to_dict()
            assert "finding_id" in d
            assert "code" in d
            assert "message" in d
            assert "severity" in d
            assert d["severity"] in ("info", "warning", "error")

    def test_du_income_used_is_populated(self):
        """DU mock should return income_used with total and sources."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        assert "total_monthly_income" in result.income_used
        assert "total_annual_income" in result.income_used
        assert "sources" in result.income_used
        assert len(result.income_used["sources"]) > 0

    def test_du_to_dict_serialization(self):
        """AUSSubmissionResult.to_dict() should produce a serializable dict."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["aus_type"] == "DU"
        assert isinstance(d["conditions"], list)
        assert isinstance(d["findings"], list)
        assert isinstance(d["submitted_at"], str)

    def test_du_low_ltv_gets_approve(self):
        """Loan with LTV <= 80% should get Approve/Eligible from mock DU."""
        service = self._make_service_and_loan()
        result = service.submit_to_du(loan_id=1, org_id=1)

        # Our mock loan has 400k/500k = 80% LTV
        assert result.recommendation == "Approve/Eligible"
        assert result.risk_class == "Accept"


# =============================================================================
# LPA Submission Tests (Mock)
# =============================================================================

@pytest.mark.unit
class TestLPASubmission:
    """Test Loan Product Advisor mock submission."""

    def _make_service_and_loan(self):
        """Helper to create a service with a mock loan."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_loan = MagicMock()
        mock_loan.loan_number = "LPA-TEST-001"
        mock_loan.loan_purpose = "refinance"
        mock_loan.loan_type = "conventional"
        mock_loan.amount = 250000
        mock_loan.rate = 6.25
        mock_loan.term = 360
        mock_loan.borrower_name = "Carlos Rivera"
        mock_loan.borrower_email = "carlos@example.com"
        mock_loan.borrower_phone = "555-0400"
        mock_loan.coborrower_name = None
        mock_loan.co_borrower_email = None
        mock_loan.property_address = "321 Elm St"
        mock_loan.property_city = "San Antonio"
        mock_loan.property_state = "TX"
        mock_loan.property_zip = "78201"
        mock_loan.property_type = "townhouse"
        mock_loan.occupancy_type = "primary"
        mock_loan.property_units = 1
        mock_loan.purchase_price = 320000
        mock_loan.appraisal_value = 330000
        mock_loan.monthly_payment = 1500
        mock_loan.second_loan_amount = None
        mock_loan.second_loan_payment = None
        mock_loan.rate_type = "Fixed"
        mock_loan.index_rate = None
        mock_loan.margin = None
        mock_loan.ltv = 78.13
        mock_loan.cltv = 78.13

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_loan

        service = AUSIntegrationService(mock_db)
        service.du_api_url = ""
        service.lpa_api_url = ""
        service._load_income_data = MagicMock(return_value=None)

        return service

    def test_lpa_submission_returns_result(self):
        """LPA mock submission should return a valid AUSSubmissionResult."""
        service = self._make_service_and_loan()
        result = service.submit_to_lpa(loan_id=1, org_id=1)

        assert result.aus_type == "LPA"
        assert result.case_id.startswith("LPA-")
        assert result.recommendation in ("Accept", "Caution")
        assert len(result.conditions) > 0
        assert len(result.findings) > 0

    def test_lpa_conditions_have_category(self):
        """Each LPA condition must have a category field."""
        service = self._make_service_and_loan()
        result = service.submit_to_lpa(loan_id=1, org_id=1)

        for cond in result.conditions:
            assert cond.category in (
                "prior_to_closing", "prior_to_funding", "prior_to_docs"
            )

    def test_lpa_findings_have_lpa_prefix(self):
        """LPA findings should have LPA-prefixed codes."""
        service = self._make_service_and_loan()
        result = service.submit_to_lpa(loan_id=1, org_id=1)

        for finding in result.findings:
            assert finding.code.startswith("LPA")


# =============================================================================
# Findings Import Tests
# =============================================================================

@pytest.mark.unit
class TestFindingsImport:
    """Test importing AUS findings into CRM compliance alerts."""

    def test_import_creates_compliance_alerts(self):
        """import_findings should create ComplianceAlert records."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        findings = {
            "conditions": [
                {"condition_id": "DU-C-001", "category": "prior_to_closing", "description": "Verify employment"},
                {"condition_id": "DU-C-002", "category": "prior_to_docs", "description": "Title commitment"},
            ],
            "findings": [
                {"finding_id": "DU-F-001", "code": "DU001", "message": "Warning message", "severity": "warning"},
                {"finding_id": "DU-F-002", "code": "DU002", "message": "Info message", "severity": "info"},
            ],
        }

        result = service.import_findings(loan_id=1, findings=findings, source="DU")

        assert result["conditions_imported"] == 2
        # Only warning/error findings create alerts, not info
        assert result["findings_imported"] == 1
        assert result["total_alerts_created"] == 3
        assert mock_db.add.call_count == 3
        assert mock_db.flush.called

    def test_import_with_empty_findings(self):
        """import_findings with no findings should create 0 alerts."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        result = service.import_findings(
            loan_id=1,
            findings={"conditions": [], "findings": []},
            source="LPA",
        )

        assert result["total_alerts_created"] == 0
        assert mock_db.add.call_count == 0


# =============================================================================
# Income Comparison Tests
# =============================================================================

@pytest.mark.unit
class TestIncomeComparison:
    """Test comparing CRM income calculation to AUS income."""

    def test_aligned_income_returns_aligned_status(self):
        """When income totals are within 5%, status should be 'aligned'."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        our_income = {
            "total_monthly_income": 8500.00,
            "sources": [
                {"source_type": "w2_employment", "monthly_amount": 7000.00},
                {"source_type": "bonus", "monthly_amount": 1500.00},
            ],
        }

        findings = {
            "income_used": {
                "total_monthly_income": 8400.00,
                "sources": [
                    {"source_type": "w2_employment", "monthly_amount": 6900.00},
                    {"source_type": "bonus", "monthly_amount": 1500.00},
                ],
            },
        }

        result = service.compare_income_to_findings(
            loan_id=1, our_income=our_income, findings=findings
        )

        assert result["summary"]["status"] == "aligned"
        assert abs(result["summary"]["variance_pct"]) < 5.0

    def test_discrepant_income_returns_discrepancy_status(self):
        """When income totals differ by > 5%, status should be 'discrepancy'."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        our_income = {
            "total_monthly_income": 10000.00,
            "sources": [
                {"source_type": "w2_employment", "monthly_amount": 10000.00},
            ],
        }

        findings = {
            "income_used": {
                "total_monthly_income": 8000.00,
                "sources": [
                    {"source_type": "w2_employment", "monthly_amount": 8000.00},
                ],
            },
        }

        result = service.compare_income_to_findings(
            loan_id=1, our_income=our_income, findings=findings
        )

        assert result["summary"]["status"] == "discrepancy"
        assert result["summary"]["variance_pct"] == 25.0
        assert len(result["flags"]) > 0

    def test_source_not_in_aus_flagged(self):
        """Income source in CRM but not in AUS should be flagged."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        our_income = {
            "total_monthly_income": 9000.00,
            "sources": [
                {"source_type": "w2_employment", "monthly_amount": 7000.00},
                {"source_type": "rental", "monthly_amount": 2000.00},
            ],
        }

        findings = {
            "income_used": {
                "total_monthly_income": 7000.00,
                "sources": [
                    {"source_type": "w2_employment", "monthly_amount": 7000.00},
                ],
            },
        }

        result = service.compare_income_to_findings(
            loan_id=1, our_income=our_income, findings=findings
        )

        # Rental income exists in our calc but not in AUS
        rental_variance = next(
            sv for sv in result["source_variances"] if sv["source_type"] == "rental"
        )
        assert rental_variance["status"] == "not_in_aus"
        assert rental_variance["aus_amount"] == 0

    def test_zero_aus_income_no_division_error(self):
        """When AUS total is 0, variance_pct should be 0 (no ZeroDivisionError)."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        service = AUSIntegrationService(mock_db)

        our_income = {"total_monthly_income": 5000.00, "sources": []}
        findings = {"income_used": {"total_monthly_income": 0, "sources": []}}

        result = service.compare_income_to_findings(
            loan_id=1, our_income=our_income, findings=findings
        )

        assert result["summary"]["variance_pct"] == 0.0


# =============================================================================
# Submission History Tests
# =============================================================================

@pytest.mark.unit
class TestSubmissionHistory:
    """Test AUS submission history retrieval."""

    def test_history_returns_ordered_submissions(self):
        """Submission history should be ordered by submitted_at descending."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_sub_1 = MagicMock()
        mock_sub_1.id = 1
        mock_sub_1.aus_type = "DU"
        mock_sub_1.case_id = "DU-0001"
        mock_sub_1.recommendation = "Approve/Eligible"
        mock_sub_1.risk_class = "Accept"
        mock_sub_1.submission_status = "complete"
        mock_sub_1.submitted_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mock_sub_1.completed_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mock_sub_1.submitted_by_user_id = 42
        mock_sub_1.conditions = [{"condition_id": "C1"}]
        mock_sub_1.findings = [{"finding_id": "F1"}, {"finding_id": "F2"}]
        mock_sub_1.income_variance = None

        mock_sub_2 = MagicMock()
        mock_sub_2.id = 2
        mock_sub_2.aus_type = "LPA"
        mock_sub_2.case_id = "LPA-0001"
        mock_sub_2.recommendation = "Accept"
        mock_sub_2.risk_class = "Accept"
        mock_sub_2.submission_status = "complete"
        mock_sub_2.submitted_at = datetime(2026, 3, 5, tzinfo=timezone.utc)
        mock_sub_2.completed_at = datetime(2026, 3, 5, tzinfo=timezone.utc)
        mock_sub_2.submitted_by_user_id = 42
        mock_sub_2.conditions = [{"condition_id": "C1"}, {"condition_id": "C2"}]
        mock_sub_2.findings = []
        mock_sub_2.income_variance = {"status": "aligned"}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_sub_2, mock_sub_1  # Most recent first
        ]

        service = AUSIntegrationService(mock_db)
        history = service.get_submission_history(loan_id=1, org_id=1)

        assert len(history) == 2
        assert history[0]["id"] == 2  # Most recent first
        assert history[0]["aus_type"] == "LPA"
        assert history[0]["conditions_count"] == 2
        assert history[0]["findings_count"] == 0
        assert history[0]["has_income_variance"] is True
        assert history[1]["id"] == 1
        assert history[1]["conditions_count"] == 1
        assert history[1]["findings_count"] == 2
        assert history[1]["has_income_variance"] is False


# =============================================================================
# Tenant Isolation Tests
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Test that AUS operations enforce organization_id filtering."""

    def test_mismo_mapping_filters_by_org_id(self):
        """map_loan_to_mismo should filter by organization_id."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        # Simulate loan not found for this org
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AUSIntegrationService(mock_db)

        with pytest.raises(ValueError, match="not found for organization"):
            service.map_loan_to_mismo(loan_id=1, org_id=999)

        # Verify the filter was called (the important thing is that org_id
        # is included in the filter chain)
        mock_db.query.return_value.filter.assert_called_once()

    def test_submission_history_filters_by_org_id(self):
        """get_submission_history should filter by organization_id."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        service = AUSIntegrationService(mock_db)
        history = service.get_submission_history(loan_id=1, org_id=5)

        assert history == []
        mock_db.query.return_value.filter.assert_called_once()


# =============================================================================
# Data Class Tests
# =============================================================================

@pytest.mark.unit
class TestDataClasses:
    """Test AUS data class serialization."""

    def test_aus_condition_to_dict(self):
        """AUSCondition.to_dict() should include all fields."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSCondition,
        )

        cond = AUSCondition(
            condition_id="DU-C-001",
            category="prior_to_closing",
            description="Verify employment",
            status="open",
        )
        d = cond.to_dict()
        assert d == {
            "condition_id": "DU-C-001",
            "category": "prior_to_closing",
            "description": "Verify employment",
            "status": "open",
        }

    def test_aus_finding_to_dict(self):
        """AUSFinding.to_dict() should include all fields."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSFinding,
        )

        finding = AUSFinding(
            finding_id="LPA-F-003",
            code="LPA003",
            message="Credit evaluation complete",
            severity="info",
        )
        d = finding.to_dict()
        assert d == {
            "finding_id": "LPA-F-003",
            "code": "LPA003",
            "message": "Credit evaluation complete",
            "severity": "info",
        }

    def test_aus_submission_result_to_dict(self):
        """AUSSubmissionResult.to_dict() should produce a complete dict."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSSubmissionResult,
            AUSCondition,
            AUSFinding,
        )

        result = AUSSubmissionResult(
            case_id="DU-TEST",
            aus_type="DU",
            recommendation="Approve/Eligible",
            risk_class="Accept",
            conditions=[
                AUSCondition("C1", "prior_to_closing", "Test condition"),
            ],
            findings=[
                AUSFinding("F1", "DU001", "Test finding", "info"),
            ],
            income_used={"total_monthly_income": 8000},
        )

        d = result.to_dict()
        assert d["case_id"] == "DU-TEST"
        assert d["aus_type"] == "DU"
        assert d["recommendation"] == "Approve/Eligible"
        assert len(d["conditions"]) == 1
        assert len(d["findings"]) == 1
        assert d["income_used"]["total_monthly_income"] == 8000
        assert isinstance(d["submitted_at"], str)


# =============================================================================
# Variance Flags Tests
# =============================================================================

@pytest.mark.unit
class TestVarianceFlags:
    """Test variance flag generation logic."""

    def test_large_variance_flag(self):
        """Variance > 10% should produce a manual review flag."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        flags = AUSIntegrationService._build_variance_flags(
            variance_pct=15.0,
            has_source_issues=False,
            source_variances=[],
        )
        assert any("10% threshold" in f for f in flags)

    def test_moderate_variance_flag(self):
        """Variance between 5-10% should produce a verification flag."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        flags = AUSIntegrationService._build_variance_flags(
            variance_pct=7.5,
            has_source_issues=False,
            source_variances=[],
        )
        assert any("5%" in f for f in flags)

    def test_not_in_aus_flag(self):
        """Income source not in AUS should produce a flag."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        flags = AUSIntegrationService._build_variance_flags(
            variance_pct=3.0,
            has_source_issues=False,
            source_variances=[
                {"source_type": "rental", "status": "not_in_aus", "our_amount": 2000, "aus_amount": 0, "variance_pct": 100},
            ],
        )
        assert any("not recognized" in f for f in flags)
        assert any("rental" in f for f in flags)

    def test_no_flags_when_aligned(self):
        """No flags should be generated when everything is aligned."""
        from services.smart_docs.integrations.aus_integration_service import (
            AUSIntegrationService,
        )

        flags = AUSIntegrationService._build_variance_flags(
            variance_pct=1.0,
            has_source_issues=False,
            source_variances=[
                {"source_type": "w2_employment", "status": "match", "our_amount": 7000, "aus_amount": 7050, "variance_pct": -0.7},
            ],
        )
        assert len(flags) == 0
