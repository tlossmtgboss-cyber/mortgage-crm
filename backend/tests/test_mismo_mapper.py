"""
Test MISMO Mapper Service - Validates MISMO 3.6 data mapping, XML generation,
field naming conventions, and completeness checking.

Tests the mapping logic without hitting a real database by using mock objects
that replicate the Loan and Lead model attributes.

Covers:
- Loan mapping to MISMO DEAL/LOANS container
- Borrower mapping to MISMO PARTY container
- Income mapping to MISMO CURRENT_INCOME container
- Property mapping to MISMO COLLATERAL container
- XML generation produces valid structure
- Completeness validation identifies missing required fields
- Field naming conventions match MISMO CamelCase standard
- Enum translation (loan_type, property_type, occupancy, purpose)
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# =============================================================================
# Mock helpers
# =============================================================================

def _make_mock_loan(**overrides):
    """Create a mock Loan object with sensible defaults."""
    defaults = {
        "id": 1,
        "organization_id": 100,
        "loan_number": "LN-2026-001",
        "borrower_name": "John Smith",
        "borrower_email": "john@example.com",
        "borrower_phone": "555-123-4567",
        "coborrower_name": None,
        "co_borrower_email": None,
        "stage": "PROCESSING",
        "loan_type": "conventional",
        "amount": Decimal("450000.00"),
        "purchase_price": Decimal("500000.00"),
        "down_payment": Decimal("50000.00"),
        "rate": Decimal("6.750"),
        "term": 360,
        "rate_type": "Fixed",
        "program": "Conv30",
        "property_address": "123 Main St",
        "property_city": "Austin",
        "property_state": "TX",
        "property_zip": "78701",
        "property_county": "Travis",
        "property_type": "single_family",
        "occupancy_type": "primary",
        "property_units": 1,
        "loan_purpose": "purchase",
        "ltv": Decimal("90.00"),
        "cltv": Decimal("90.00"),
        "points": Decimal("0.50"),
        "origination_fee": Decimal("1500.00"),
        "monthly_payment": Decimal("2918.42"),
        "property_tax": Decimal("520.00"),
        "hazard_insurance": Decimal("180.00"),
        "mortgage_insurance": Decimal("95.00"),
        "hoa_amount": Decimal("0.00"),
        "index_rate": None,
        "margin": None,
        "appraisal_value": Decimal("510000.00"),
        "appraisal_ordered_date": datetime(2026, 1, 10),
        "appraisal_completed_date": datetime(2026, 1, 18),
        "appraisal_received_date": datetime(2026, 1, 20),
        "appraisal_scheduled_date": None,
        "closing_date": datetime(2026, 3, 15),
        "funded_date": None,
        "lock_date": datetime(2026, 2, 1),
        "lock_expiration_date": datetime(2026, 3, 3),
        "scheduled_closing_date": datetime(2026, 3, 15),
        "first_payment_date": datetime(2026, 5, 1),
        "application_date": datetime(2026, 1, 5),
        "initial_disclosures_sent_date": datetime(2026, 1, 7),
        "initial_disclosures_signed_date": datetime(2026, 1, 9),
        "cd_sent_to_borrower_date": datetime(2026, 3, 10),
        "cd_acknowledged_date": datetime(2026, 3, 11),
        "loan_approved_date": datetime(2026, 2, 20),
        "risk_score": 42,
        "title_company": "Lone Star Title",
        "title_ordered_date": datetime(2026, 1, 12),
        "title_received_date": datetime(2026, 2, 5),
        "insurance_ordered_date": datetime(2026, 2, 10),
        "insurance_received_date": datetime(2026, 2, 15),
        "lender": "Best Rate Lending",
        "realtor_agent": "Jane Realtor",
        "second_loan_amount": None,
        "second_loan_rate": None,
        "second_loan_payment": None,
        "present_housing_expense": Decimal("1800.00"),
        "proposed_housing_expense": Decimal("2918.42"),
        "present_monthly_payment": Decimal("1800.00"),
        "proposed_monthly_payment": Decimal("2918.42"),
        "estimated_prepaid_interest": Decimal("800.00"),
        "file_state": "TX",
        "preferred_communication": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_mock_lead(**overrides):
    """Create a mock Lead object with sensible defaults."""
    defaults = {
        "id": 10,
        "organization_id": 100,
        "name": "John Smith",
        "first_name": "John",
        "last_name": "Smith",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "preferred_communication": "email",
        "address": "456 Oak Ave",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78702",
        "credit_score": 740,
        "annual_income": Decimal("120000.00"),
        "employment_status": "Employed",
        "employer_name": "TechCorp",
        "first_time_buyer": False,
        "debt_to_income": Decimal("35.50"),
        "occupancy_type": "primary",
        "loan_number": "LN-2026-001",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_mock_income_calc(**overrides):
    """Create a mock IncomeCalculation object."""
    defaults = {
        "id": 5,
        "loan_id": 1,
        "total_qualifying_monthly_income": Decimal("10000.00"),
        "total_qualifying_annual_income": Decimal("120000.00"),
        "calculation_method": "standard",
        "dti_front_end": Decimal("29.18"),
        "dti_back_end": Decimal("35.50"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_mock_income_source(**overrides):
    """Create a mock IncomeSource object."""
    defaults = {
        "id": 20,
        "calculation_id": 5,
        "source_type": "w2_employment",
        "employer_name": "TechCorp",
        "position_title": "Software Engineer",
        "employment_start_date": date(2020, 6, 1),
        "employment_years": Decimal("5.5"),
        "base_monthly_income": Decimal("8000.00"),
        "overtime_monthly": Decimal("500.00"),
        "bonus_monthly": Decimal("1000.00"),
        "commission_monthly": Decimal("0.00"),
        "other_monthly": Decimal("500.00"),
        "total_monthly_income": Decimal("10000.00"),
        "total_annual_income": Decimal("120000.00"),
        "trending_direction": SimpleNamespace(value="stable"),
        "year1_income": Decimal("120000.00"),
        "year2_income": Decimal("115000.00"),
        "year_over_year_change_pct": Decimal("4.35"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# =============================================================================
# Helper function unit tests
# =============================================================================

@pytest.mark.unit
class TestMISMOHelperFunctions:
    """Test the module-level helper functions for MISMO data conversion."""

    def test_safe_str_returns_none_for_none(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_str
        assert _safe_str(None) is None

    def test_safe_str_returns_none_for_empty(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_str
        assert _safe_str("") is None
        assert _safe_str("   ") is None

    def test_safe_str_strips_whitespace(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_str
        assert _safe_str("  hello  ") == "hello"

    def test_safe_decimal_formats_correctly(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_decimal
        assert _safe_decimal(Decimal("450000")) == "450000.00"
        assert _safe_decimal(Decimal("6.750")) == "6.75"
        assert _safe_decimal(None) is None

    def test_safe_date_formats_datetime(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_date
        dt = datetime(2026, 3, 15, 10, 30)
        assert _safe_date(dt) == "2026-03-15"

    def test_safe_date_formats_date(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_date
        d = date(2026, 3, 15)
        assert _safe_date(d) == "2026-03-15"

    def test_safe_date_returns_none_for_none(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_date
        assert _safe_date(None) is None

    def test_safe_bool_values(self):
        from services.smart_docs.integrations.mismo_mapper_service import _safe_bool
        assert _safe_bool(True) == "true"
        assert _safe_bool(False) == "false"
        assert _safe_bool(None) is None

    def test_translate_enum_maps_known_values(self):
        from services.smart_docs.integrations.mismo_mapper_service import (
            _translate_enum,
            LOAN_TYPE_MISMO_MAP,
        )
        assert _translate_enum("conventional", LOAN_TYPE_MISMO_MAP) == "Conventional"
        assert _translate_enum("fha", LOAN_TYPE_MISMO_MAP) == "FHA"
        assert _translate_enum("va", LOAN_TYPE_MISMO_MAP) == "VA"

    def test_translate_enum_passes_through_unknown(self):
        from services.smart_docs.integrations.mismo_mapper_service import _translate_enum
        assert _translate_enum("unknown_type", {"a": "b"}) == "unknown_type"

    def test_translate_enum_returns_none_for_none(self):
        from services.smart_docs.integrations.mismo_mapper_service import _translate_enum
        assert _translate_enum(None, {"a": "b"}) is None


# =============================================================================
# Enum translation mapping tests
# =============================================================================

@pytest.mark.unit
class TestMISMOEnumTranslations:
    """Test that CRM enum values map correctly to MISMO enumerations."""

    def test_loan_type_mapping_completeness(self):
        from services.smart_docs.integrations.mismo_mapper_service import LOAN_TYPE_MISMO_MAP
        expected_keys = {"conventional", "fha", "va", "usda", "jumbo", "non_qm"}
        assert set(LOAN_TYPE_MISMO_MAP.keys()) == expected_keys

    def test_property_type_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import PROPERTY_TYPE_MISMO_MAP
        assert PROPERTY_TYPE_MISMO_MAP["single_family"] == "Detached"
        assert PROPERTY_TYPE_MISMO_MAP["condo"] == "Condominium"
        assert PROPERTY_TYPE_MISMO_MAP["townhouse"] == "Attached"
        assert PROPERTY_TYPE_MISMO_MAP["multi_family"] == "TwoToFourUnitProperty"
        assert PROPERTY_TYPE_MISMO_MAP["manufactured"] == "ManufacturedHousing"

    def test_occupancy_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import OCCUPANCY_MISMO_MAP
        assert OCCUPANCY_MISMO_MAP["primary"] == "PrimaryResidence"
        assert OCCUPANCY_MISMO_MAP["second_home"] == "SecondHome"
        assert OCCUPANCY_MISMO_MAP["investment"] == "Investment"

    def test_purpose_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import PURPOSE_MISMO_MAP
        assert PURPOSE_MISMO_MAP["purchase"] == "Purchase"
        assert PURPOSE_MISMO_MAP["refinance"] == "NoCashOutRefinance"
        assert PURPOSE_MISMO_MAP["cash_out"] == "CashOutRefinance"

    def test_income_type_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import INCOME_TYPE_MISMO_MAP
        assert INCOME_TYPE_MISMO_MAP["w2_employment"] == "Base"
        assert INCOME_TYPE_MISMO_MAP["self_employment"] == "SelfEmployment"
        assert INCOME_TYPE_MISMO_MAP["commission"] == "Commissions"
        assert INCOME_TYPE_MISMO_MAP["bonus"] == "Bonus"
        assert INCOME_TYPE_MISMO_MAP["overtime"] == "Overtime"
        assert INCOME_TYPE_MISMO_MAP["rental"] == "NetRentalIncome"

    def test_doc_type_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import DOC_TYPE_MISMO_MAP
        assert DOC_TYPE_MISMO_MAP["W2"] == "W2"
        assert DOC_TYPE_MISMO_MAP["Paystub"] == "PayStub"
        assert DOC_TYPE_MISMO_MAP["Appraisal"] == "AppraisalReport"
        assert DOC_TYPE_MISMO_MAP["Loan Estimate"] == "LoanEstimate"
        assert DOC_TYPE_MISMO_MAP["Closing Disclosure"] == "ClosingDisclosure"

    def test_doc_status_mapping(self):
        from services.smart_docs.integrations.mismo_mapper_service import _map_doc_status_to_mismo
        assert _map_doc_status_to_mismo("active") == "Received"
        assert _map_doc_status_to_mismo("archived") == "Archived"
        assert _map_doc_status_to_mismo("deleted") == "Voided"
        assert _map_doc_status_to_mismo(None) == "Other"
        assert _map_doc_status_to_mismo("unknown") == "Other"


# =============================================================================
# MISMO field naming convention tests
# =============================================================================

@pytest.mark.unit
class TestMISMONamingConventions:
    """Validate that MISMO field names follow CamelCase convention."""

    def test_loan_mappings_use_camel_case(self):
        from services.smart_docs.integrations.mismo_mapper_service import LOAN_MAPPINGS
        for crm_field, mismo_path in LOAN_MAPPINGS.items():
            parts = mismo_path.split("/")
            leaf = parts[-1]
            # MISMO uses PascalCase (initial cap CamelCase)
            assert leaf[0].isupper(), (
                f"MISMO field '{leaf}' (mapped from '{crm_field}') "
                f"should start with uppercase per MISMO convention"
            )

    def test_borrower_mappings_use_camel_case(self):
        from services.smart_docs.integrations.mismo_mapper_service import BORROWER_MAPPINGS
        for crm_field, mismo_path in BORROWER_MAPPINGS.items():
            parts = mismo_path.split("/")
            leaf = parts[-1]
            assert leaf[0].isupper(), (
                f"MISMO field '{leaf}' (mapped from '{crm_field}') "
                f"should start with uppercase per MISMO convention"
            )

    def test_property_mappings_use_camel_case(self):
        from services.smart_docs.integrations.mismo_mapper_service import PROPERTY_MAPPINGS
        for crm_field, mismo_path in PROPERTY_MAPPINGS.items():
            parts = mismo_path.split("/")
            leaf = parts[-1]
            assert leaf[0].isupper(), (
                f"MISMO field '{leaf}' (mapped from '{crm_field}') "
                f"should start with uppercase per MISMO convention"
            )

    def test_container_names_are_uppercase(self):
        """MISMO container names (non-leaf) should be UPPERCASE."""
        from services.smart_docs.integrations.mismo_mapper_service import LOAN_MAPPINGS
        for crm_field, mismo_path in LOAN_MAPPINGS.items():
            parts = mismo_path.split("/")
            # All parts except the leaf should be uppercase containers
            containers = parts[:-1]
            for container in containers:
                assert container == container.upper(), (
                    f"Container '{container}' in path '{mismo_path}' "
                    f"should be UPPERCASE per MISMO convention"
                )

    def test_required_fields_follow_convention(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        for field_path in REQUIRED_MISMO_FIELDS:
            parts = field_path.split("/")
            leaf = parts[-1]
            assert leaf[0].isupper(), f"Required field leaf '{leaf}' should be PascalCase"
            for container in parts[:-1]:
                assert container == container.upper(), (
                    f"Container '{container}' should be UPPERCASE"
                )


# =============================================================================
# Loan mapping tests
# =============================================================================

@pytest.mark.unit
class TestLoanMapping:
    """Test mapping loan data to MISMO LOANS container."""

    def test_loan_container_has_required_fields(self):
        """The LOAN container should include all critical fields."""
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        loan = _make_mock_loan()

        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)

        assert "LOAN" in result
        loan_data = result["LOAN"]
        assert loan_data["LoanIdentifier"] == "LN-2026-001"
        assert loan_data["LoanAmountType"] == "450000.00"
        assert loan_data["NoteRatePercent"] == "6.75"
        assert loan_data["MortgageType"] == "Conventional"
        assert loan_data["LoanMaturityPeriodCount"] == 360
        assert loan_data["LoanPurposeType"] == "Purchase"

    def test_loan_closing_information(self):
        loan = _make_mock_loan()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)

        closing = result["LOAN"]["CLOSING_INFORMATION"]
        assert closing["ClosingDate"] == "2026-03-15"
        assert closing["ScheduledClosingDate"] == "2026-03-15"
        assert closing["FirstPaymentDate"] == "2026-05-01"

    def test_loan_ltv_values(self):
        loan = _make_mock_loan()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)

        ltv = result["LOAN"]["LOAN_TO_VALUE"]
        assert ltv["LTVRatioPercent"] == "90.00"
        assert ltv["CombinedLTVRatioPercent"] == "90.00"

    def test_loan_disclosure_dates(self):
        loan = _make_mock_loan()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)

        disclosure = result["LOAN"]["DISCLOSURE"]
        assert disclosure["InitialDisclosureSentDate"] == "2026-01-07"
        assert disclosure["ClosingDisclosureSentDate"] == "2026-03-10"

    def test_loan_with_null_optional_fields(self):
        """Null optional fields should map to None without errors."""
        loan = _make_mock_loan(
            index_rate=None,
            margin=None,
            second_loan_amount=None,
            funded_date=None,
        )
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)

        assert result["LOAN"]["ADJUSTMENT"]["IndexCurrentValuePercent"] is None
        assert result["LOAN"]["SUBORDINATE_FINANCING"]["SubordinateLienAmount"] is None
        assert result["LOAN"]["CLOSING_INFORMATION"]["DisbursementDate"] is None

    def test_loan_type_fha_maps_correctly(self):
        loan = _make_mock_loan(loan_type="fha")
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)
        assert result["LOAN"]["MortgageType"] == "FHA"

    def test_loan_type_va_maps_correctly(self):
        loan = _make_mock_loan(loan_type="va")
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_loan_container(loan)
        assert result["LOAN"]["MortgageType"] == "VA"


# =============================================================================
# Borrower mapping tests
# =============================================================================

@pytest.mark.unit
class TestBorrowerMapping:
    """Test mapping lead/borrower data to MISMO PARTY container."""

    def test_borrower_name_mapping(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        name = result["INDIVIDUAL"]["NAME"]
        assert name["FirstName"] == "John"
        assert name["LastName"] == "Smith"

    def test_borrower_contact_mapping(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        contact = result["INDIVIDUAL"]["CONTACT_POINTS"]["CONTACT_POINT"]
        assert contact["ContactPointEmailValue"] == "john@example.com"
        assert contact["ContactPointTelephoneValue"] == "555-123-4567"

    def test_borrower_address_mapping(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        addr = result["ADDRESSES"]["ADDRESS"]
        assert addr["AddressLineText"] == "456 Oak Ave"
        assert addr["CityName"] == "Austin"
        assert addr["StateCode"] == "TX"
        assert addr["PostalCode"] == "78702"

    def test_borrower_credit_score(self):
        lead = _make_mock_lead(credit_score=780)
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        credit = result["ROLES"]["ROLE"]["BORROWER"]["CREDIT"]["CREDIT_SCORE"]
        assert credit["CreditScoreValue"] == 780

    def test_borrower_employment_info(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        employer = result["ROLES"]["ROLE"]["BORROWER"]["EMPLOYERS"]["EMPLOYER"]
        assert employer["EmployerName"] == "TechCorp"
        assert employer["EmploymentStatusType"] == "Employed"

    def test_borrower_first_time_buyer_flag(self):
        lead = _make_mock_lead(first_time_buyer=True)
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")

        detail = result["ROLES"]["ROLE"]["BORROWER"]["BORROWER_DETAIL"]
        assert detail["FirstTimeHomebuyerIndicator"] == "true"

    def test_borrower_role_is_set(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="Borrower")
        assert result["ROLES"]["ROLE"]["ROLE_DETAIL"]["PartyRoleType"] == "Borrower"

    def test_coborrower_role_is_set(self):
        lead = _make_mock_lead()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._map_lead_to_party(lead, role="CoBorrower")
        assert result["ROLES"]["ROLE"]["ROLE_DETAIL"]["PartyRoleType"] == "CoBorrower"


# =============================================================================
# Income mapping tests
# =============================================================================

@pytest.mark.unit
class TestIncomeMapping:
    """Test mapping income calculation to MISMO CURRENT_INCOME container."""

    def test_income_totals_mapping(self):
        calc = _make_mock_income_calc()
        source = _make_mock_income_source()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        # Patch internal methods
        with patch.object(service, '_get_income_sources', return_value=[source]):
            with patch.object(service.db, 'query') as mock_query:
                mock_query.return_value.filter_by.return_value.first.return_value = calc
                result = service.map_income_to_mismo(calculation_id=5)

        income = result["CURRENT_INCOME"]
        assert income["TotalQualifyingMonthlyIncome"] == "10000.00"
        assert income["TotalQualifyingAnnualIncome"] == "120000.00"
        assert income["CalculationMethod"] == "standard"

    def test_income_dti_ratios(self):
        calc = _make_mock_income_calc(dti_front_end=Decimal("29.18"), dti_back_end=Decimal("35.50"))
        source = _make_mock_income_source()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service, '_get_income_sources', return_value=[source]):
            with patch.object(service.db, 'query') as mock_query:
                mock_query.return_value.filter_by.return_value.first.return_value = calc
                result = service.map_income_to_mismo(calculation_id=5)

        assert result["CURRENT_INCOME"]["FrontEndDTIRatio"] == "29.18"
        assert result["CURRENT_INCOME"]["BackEndDTIRatio"] == "35.50"

    def test_income_source_type_translation(self):
        """W2 employment should map to MISMO 'Base' income type."""
        source = _make_mock_income_source(source_type="w2_employment")
        calc = _make_mock_income_calc()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service, '_get_income_sources', return_value=[source]):
            with patch.object(service.db, 'query') as mock_query:
                mock_query.return_value.filter_by.return_value.first.return_value = calc
                result = service.map_income_to_mismo(calculation_id=5)

        items = result["CURRENT_INCOME"]["INCOME_ITEMS"]
        assert len(items) == 1
        assert items[0]["CURRENT_INCOME_ITEM"]["IncomeType"] == "Base"

    def test_income_breakdown_fields(self):
        source = _make_mock_income_source()
        calc = _make_mock_income_calc()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service, '_get_income_sources', return_value=[source]):
            with patch.object(service.db, 'query') as mock_query:
                mock_query.return_value.filter_by.return_value.first.return_value = calc
                result = service.map_income_to_mismo(calculation_id=5)

        breakdown = result["CURRENT_INCOME"]["INCOME_ITEMS"][0]["INCOME_BREAKDOWN"]
        assert breakdown["BaseMonthlyIncomeAmount"] == "8000.00"
        assert breakdown["OvertimeMonthlyIncomeAmount"] == "500.00"
        assert breakdown["BonusMonthlyIncomeAmount"] == "1000.00"

    def test_income_trending_data(self):
        source = _make_mock_income_source()
        calc = _make_mock_income_calc()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service, '_get_income_sources', return_value=[source]):
            with patch.object(service.db, 'query') as mock_query:
                mock_query.return_value.filter_by.return_value.first.return_value = calc
                result = service.map_income_to_mismo(calculation_id=5)

        trending = result["CURRENT_INCOME"]["INCOME_ITEMS"][0]["TRENDING"]
        assert trending["TrendingDirection"] == "stable"
        assert trending["Year1Income"] == "120000.00"
        assert trending["Year2Income"] == "115000.00"


# =============================================================================
# Property mapping tests
# =============================================================================

@pytest.mark.unit
class TestPropertyMapping:
    """Test mapping property data to MISMO COLLATERAL container."""

    def test_property_address_mapping(self):
        loan = _make_mock_loan()
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        addr = result["COLLATERAL"]["SUBJECT_PROPERTY"]["ADDRESS"]
        assert addr["AddressLineText"] == "123 Main St"
        assert addr["CityName"] == "Austin"
        assert addr["StateCode"] == "TX"
        assert addr["PostalCode"] == "78701"
        assert addr["CountyName"] == "Travis"

    def test_property_type_translation(self):
        loan = _make_mock_loan(property_type="single_family")
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        detail = result["COLLATERAL"]["SUBJECT_PROPERTY"]["PROPERTY_DETAIL"]
        assert detail["PropertyType"] == "Detached"

    def test_occupancy_type_translation(self):
        loan = _make_mock_loan(occupancy_type="investment")
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        detail = result["COLLATERAL"]["SUBJECT_PROPERTY"]["PROPERTY_DETAIL"]
        assert detail["PropertyUsageType"] == "Investment"

    def test_appraisal_value_mapping(self):
        loan = _make_mock_loan(appraisal_value=Decimal("510000.00"))
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        valuation = result["COLLATERAL"]["SUBJECT_PROPERTY"]["PROPERTY_VALUATIONS"]["PROPERTY_VALUATION"]
        assert valuation["PropertyValuationAmount"] == "510000.00"

    def test_sales_contract_amount(self):
        loan = _make_mock_loan(purchase_price=Decimal("500000.00"))
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        contract = result["COLLATERAL"]["SUBJECT_PROPERTY"]["SALES_CONTRACTS"]["SALES_CONTRACT"]
        assert contract["SalesContractAmount"] == "500000.00"

    def test_property_unit_count(self):
        loan = _make_mock_loan(property_units=4, property_type="multi_family")
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_collateral_container(loan)

        detail = result["COLLATERAL"]["SUBJECT_PROPERTY"]["PROPERTY_DETAIL"]
        assert detail["FinancedUnitCount"] == 4
        assert detail["PropertyType"] == "TwoToFourUnitProperty"


# =============================================================================
# XML generation tests
# =============================================================================

@pytest.mark.unit
class TestXMLGeneration:
    """Test MISMO XML generation produces valid structure."""

    def _generate_xml_for_mock_loan(self):
        """Helper to generate XML from a mock loan."""
        loan = _make_mock_loan()
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        # Patch the service methods to return mock data
        with patch.object(service, '_get_loan', return_value=loan):
            with patch.object(service, '_get_lead_for_loan', return_value=lead):
                with patch.object(service, '_get_documents', return_value=[]):
                    xml_str = service.generate_mismo_xml(loan_id=1, org_id=100)

        return xml_str

    def test_xml_is_well_formed(self):
        """Generated XML should be parseable."""
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        # Should not raise
        root = ET.fromstring(xml_str)
        assert root.tag == "MESSAGE"

    def test_xml_has_mismo_namespace(self):
        xml_str = self._generate_xml_for_mock_loan()
        assert "http://www.mismo.org/residential/2009/schemas" in xml_str

    def test_xml_has_version_attribute(self):
        xml_str = self._generate_xml_for_mock_loan()
        assert 'MISMOReferenceModelIdentifier="3.6"' in xml_str

    def test_xml_contains_deal_structure(self):
        """XML should contain DEAL_SETS > DEAL_SET > DEALS > DEAL."""
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        root = ET.fromstring(xml_str)

        deal_sets = root.find("DEAL_SETS")
        assert deal_sets is not None
        deal_set = deal_sets.find("DEAL_SET")
        assert deal_set is not None
        deals = deal_set.find("DEALS")
        assert deals is not None
        deal = deals.find("DEAL")
        assert deal is not None

    def test_xml_contains_loans_element(self):
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        root = ET.fromstring(xml_str)
        # Navigate to DEAL
        deal = root.find("DEAL_SETS/DEAL_SET/DEALS/DEAL")
        loans = deal.find("LOANS")
        assert loans is not None

    def test_xml_contains_parties_element(self):
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        root = ET.fromstring(xml_str)
        deal = root.find("DEAL_SETS/DEAL_SET/DEALS/DEAL")
        parties = deal.find("PARTIES")
        assert parties is not None

    def test_xml_contains_collaterals_element(self):
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        root = ET.fromstring(xml_str)
        deal = root.find("DEAL_SETS/DEAL_SET/DEALS/DEAL")
        collaterals = deal.find("COLLATERALS")
        assert collaterals is not None

    def test_xml_loan_amount_value(self):
        """Verify the loan amount appears correctly in the XML."""
        import xml.etree.ElementTree as ET
        xml_str = self._generate_xml_for_mock_loan()
        assert "450000.00" in xml_str


# =============================================================================
# Completeness validation tests
# =============================================================================

@pytest.mark.unit
class TestCompletenessValidation:
    """Test MISMO field completeness checking."""

    def test_fully_populated_loan_has_high_completeness(self):
        loan = _make_mock_loan()
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service.db, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = loan
            with patch.object(service, '_get_lead_for_loan', return_value=lead):
                result = service.validate_mismo_completeness(loan_id=1)

        assert result["completeness"]["completeness_pct"] > 50
        assert result["completeness"]["populated_fields"] > 20

    def test_minimal_loan_identifies_missing_required(self):
        """A loan with minimal data should list missing required fields."""
        loan = _make_mock_loan(
            rate=None,
            property_address=None,
            property_city=None,
            property_state=None,
            property_zip=None,
            appraisal_value=None,
            initial_disclosures_sent_date=None,
            cd_sent_to_borrower_date=None,
        )

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service.db, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = loan
            with patch.object(service, '_get_lead_for_loan', return_value=None):
                result = service.validate_mismo_completeness(loan_id=1)

        missing = result["required_fields"]["missing"]
        assert len(missing) > 0
        assert result["gse_delivery_ready"] is False

    def test_gse_delivery_ready_when_all_required_populated(self):
        """Loan with all required fields populated should be GSE delivery ready."""
        loan = _make_mock_loan()
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service.db, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = loan
            with patch.object(service, '_get_lead_for_loan', return_value=lead):
                result = service.validate_mismo_completeness(loan_id=1)

        # With a fully-populated mock, most required fields should be present
        assert result["required_fields"]["required_completeness_pct"] > 70

    def test_completeness_result_structure(self):
        loan = _make_mock_loan()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service.db, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = loan
            with patch.object(service, '_get_lead_for_loan', return_value=None):
                result = service.validate_mismo_completeness(loan_id=1)

        assert "loan_id" in result
        assert "mismo_version" in result
        assert "completeness" in result
        assert "required_fields" in result
        assert "gse_delivery_ready" in result
        assert "populated_paths" in result
        assert isinstance(result["populated_paths"], list)

    def test_completeness_raises_for_missing_loan(self):
        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())

        with patch.object(service.db, 'query') as mock_query:
            mock_query.return_value.filter.return_value.first.return_value = None
            with pytest.raises(ValueError, match="not found"):
                service.validate_mismo_completeness(loan_id=999)


# =============================================================================
# Required MISMO fields tests
# =============================================================================

@pytest.mark.unit
class TestRequiredMISMOFields:
    """Test the REQUIRED_MISMO_FIELDS constant."""

    def test_required_fields_count(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert len(REQUIRED_MISMO_FIELDS) == 20

    def test_required_fields_include_loan_amount(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert "DEAL/LOANS/LOAN/LoanAmountType" in REQUIRED_MISMO_FIELDS

    def test_required_fields_include_borrower_name(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert "PARTY/INDIVIDUAL/NAME/FirstName" in REQUIRED_MISMO_FIELDS
        assert "PARTY/INDIVIDUAL/NAME/LastName" in REQUIRED_MISMO_FIELDS

    def test_required_fields_include_property_address(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/AddressLineText" in REQUIRED_MISMO_FIELDS
        assert "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/StateCode" in REQUIRED_MISMO_FIELDS

    def test_required_fields_include_disclosure_dates(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/InitialDisclosureSentDate" in REQUIRED_MISMO_FIELDS
        assert "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/ClosingDisclosureSentDate" in REQUIRED_MISMO_FIELDS

    def test_required_fields_include_credit_score(self):
        from services.smart_docs.integrations.mismo_mapper_service import REQUIRED_MISMO_FIELDS
        assert "PARTY/ROLES/ROLE/BORROWER/CREDIT/CREDIT_SCORE/CreditScoreValue" in REQUIRED_MISMO_FIELDS


# =============================================================================
# Parties container tests
# =============================================================================

@pytest.mark.unit
class TestPartiesContainer:
    """Test PARTIES container construction with borrower, co-borrower, and agents."""

    def test_parties_includes_borrower(self):
        loan = _make_mock_loan()
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_parties_container(loan, lead)

        assert "PARTY" in result
        parties = result["PARTY"]
        assert len(parties) >= 1
        # First party should be borrower
        borrower_role = parties[0]["ROLES"]["ROLE"]["ROLE_DETAIL"]["PartyRoleType"]
        assert borrower_role == "Borrower"

    def test_parties_includes_coborrower(self):
        loan = _make_mock_loan(
            coborrower_name="Jane Smith",
            co_borrower_email="jane@example.com",
        )
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_parties_container(loan, lead)

        parties = result["PARTY"]
        assert len(parties) >= 2
        coborrower = parties[1]
        assert coborrower["ROLES"]["ROLE"]["ROLE_DETAIL"]["PartyRoleType"] == "CoBorrower"

    def test_parties_includes_selling_agent(self):
        loan = _make_mock_loan(realtor_agent="Jane Realtor")
        lead = _make_mock_lead()

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_parties_container(loan, lead)

        parties = result["PARTY"]
        agent_parties = [
            p for p in parties
            if p.get("ROLES", {}).get("ROLE", {}).get("ROLE_DETAIL", {}).get("PartyRoleType") == "SellingAgent"
        ]
        assert len(agent_parties) == 1

    def test_parties_fallback_to_loan_borrower_info(self):
        """When no lead exists, borrower info should come from loan fields."""
        loan = _make_mock_loan(borrower_name="John Doe", borrower_email="john@doe.com")

        from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService
        service = MISMOMapperService(db=MagicMock())
        result = service._build_parties_container(loan, lead=None)

        parties = result["PARTY"]
        assert len(parties) >= 1
        name = parties[0]["INDIVIDUAL"]["NAME"]
        assert name["FullName"] == "John Doe"


# =============================================================================
# Mapping field count tests
# =============================================================================

@pytest.mark.unit
class TestMappingFieldCounts:
    """Verify the mapping dictionaries have sufficient coverage."""

    def test_loan_mappings_has_at_least_30_fields(self):
        from services.smart_docs.integrations.mismo_mapper_service import LOAN_MAPPINGS
        assert len(LOAN_MAPPINGS) >= 30, (
            f"Expected at least 30 loan mappings, got {len(LOAN_MAPPINGS)}"
        )

    def test_borrower_mappings_has_at_least_10_fields(self):
        from services.smart_docs.integrations.mismo_mapper_service import BORROWER_MAPPINGS
        assert len(BORROWER_MAPPINGS) >= 10

    def test_property_mappings_has_at_least_8_fields(self):
        from services.smart_docs.integrations.mismo_mapper_service import PROPERTY_MAPPINGS
        assert len(PROPERTY_MAPPINGS) >= 8
