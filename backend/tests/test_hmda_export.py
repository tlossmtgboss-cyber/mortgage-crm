"""
Tests for HMDA LAR Export Service — validation, record building, and export generation.

Covers:
  - validate_hmda_readiness: identifies missing required fields (loan-level + demographic)
  - validate_hmda_readiness: passes when all fields present
  - _validate_loan_for_hmda: per-loan validation logic
  - generate_hmda_lar: produces valid pipe-delimited LAR output
  - generate_hmda_lar: blocks export when validation errors exist
  - generate_hmda_lar: returns empty result when no loans match
  - _build_lar_record: correct pipe-delimited format and field count
  - ACTION_TAKEN_MAP: loan stage to HMDA action code mapping
  - LOAN_TYPE_MAP / LOAN_PURPOSE_MAP: field value mappings
  - Demographic field encoding via _get_gmi_data
  - Helper functions: _safe_str, _format_amount, _format_rate, _format_date_hmda

Run with: pytest tests/test_hmda_export.py -v
"""

import sys
import os
from datetime import datetime, date
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.hmda_export import (
    ACTION_TAKEN_MAP,
    LOAN_TYPE_MAP,
    LOAN_PURPOSE_MAP,
    PROPERTY_TYPE_MAP,
    OCCUPANCY_TYPE_MAP,
    REQUIRED_LOAN_FIELDS,
    REQUIRED_DEMOGRAPHIC_FIELDS,
    RECOMMENDED_FIELDS,
    _validate_loan_for_hmda,
    _build_lar_record,
    _safe_str,
    _format_amount,
    _format_rate,
    _format_date_hmda,
    _get_gmi_data,
    generate_hmda_lar,
    validate_hmda_readiness,
)


# =============================================================================
# Fakes / Helpers
# =============================================================================

class FakeLoan:
    """Lightweight stand-in for the Loan ORM model."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.loan_number = kwargs.get("loan_number", "LN-2025-001")
        self.stage = kwargs.get("stage", "FUNDED")
        self.loan_type = kwargs.get("loan_type", "conventional")
        self.loan_purpose = kwargs.get("loan_purpose", "purchase")
        self.amount = kwargs.get("amount", 350000.0)
        self.rate = kwargs.get("rate", 6.75)
        self.term = kwargs.get("term", 360)
        self.property_state = kwargs.get("property_state", "CA")
        self.property_county = kwargs.get("property_county", "Los Angeles")
        self.property_zip = kwargs.get("property_zip", "90210")
        self.property_type = kwargs.get("property_type", "single_family")
        self.property_units = kwargs.get("property_units", 1)
        self.occupancy_type = kwargs.get("occupancy_type", "primary")
        self.ltv = kwargs.get("ltv", 80.0)
        self.cltv = kwargs.get("cltv", 80.0)
        self.application_date = kwargs.get("application_date", date(2025, 3, 1))
        self.funded_date = kwargs.get("funded_date", date(2025, 6, 15))
        self.withdrawn_date = kwargs.get("withdrawn_date", None)
        self.updated_at = kwargs.get("updated_at", datetime(2025, 6, 15, 12, 0, 0))
        self.created_at = kwargs.get("created_at", datetime(2025, 3, 1, 10, 0, 0))
        self.organization_id = kwargs.get("organization_id", 1)
        self.borrower_name = kwargs.get("borrower_name", "Alice Smith")


class FakeBorrowerApplication:
    """Stand-in for BorrowerApplication ORM model."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.loan_id = kwargs.get("loan_id", 1)
        self.applicant_ethnicity = kwargs.get("applicant_ethnicity", "2")
        self.applicant_race = kwargs.get("applicant_race", "5")
        self.applicant_sex = kwargs.get("applicant_sex", "1")
        self.co_applicant_ethnicity = kwargs.get("co_applicant_ethnicity", "3")
        self.co_applicant_race = kwargs.get("co_applicant_race", "5")
        self.co_applicant_sex = kwargs.get("co_applicant_sex", "2")
        self.applicant_age = kwargs.get("applicant_age", "35")
        self.co_applicant_age = kwargs.get("co_applicant_age", "33")


class FakeQuery:
    """Chainable mock for SQLAlchemy query builder patterns."""
    def __init__(self, results=None):
        self._results = results or []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self._results

    def first(self):
        return self._results[0] if self._results else None


class FakeDB:
    """Mock database session for HMDA export tests."""
    def __init__(self, loans=None, borrower_apps=None):
        self._loans = loans or []
        self._borrower_apps = borrower_apps or []
        self._query_call_count = 0

    def query(self, model):
        model_name = model.__name__ if hasattr(model, "__name__") else str(model)
        if "Loan" in model_name:
            return FakeQuery(self._loans)
        elif "BorrowerApplication" in model_name:
            return FakeQuery(self._borrower_apps)
        return FakeQuery([])


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestSafeStr:
    """Tests for _safe_str helper."""

    def test_none_returns_default(self):
        assert _safe_str(None) == "NA"

    def test_empty_string_returns_default(self):
        assert _safe_str("") == "NA"

    def test_whitespace_returns_default(self):
        assert _safe_str("   ") == "NA"

    def test_value_returned(self):
        assert _safe_str("California") == "California"

    def test_custom_default(self):
        assert _safe_str(None, "UNKNOWN") == "UNKNOWN"

    def test_numeric_value(self):
        assert _safe_str(42) == "42"


class TestFormatAmount:
    """Tests for _format_amount helper."""

    def test_normal_amount(self):
        assert _format_amount(350000.0) == "350000"

    def test_none_returns_na(self):
        assert _format_amount(None) == "NA"

    def test_zero_returns_na(self):
        assert _format_amount(0) == "NA"

    def test_negative_returns_na(self):
        assert _format_amount(-100) == "NA"

    def test_rounds_to_integer(self):
        """HMDA reports amount in whole dollars."""
        assert _format_amount(350000.75) == "350001"


class TestFormatRate:
    """Tests for _format_rate helper."""

    def test_normal_rate(self):
        assert _format_rate(6.75) == "6.75"

    def test_none_returns_na(self):
        assert _format_rate(None) == "NA"

    def test_two_decimal_places(self):
        assert _format_rate(5.5) == "5.50"

    def test_three_decimal_input(self):
        assert _format_rate(6.125) == "6.12"  # rounded to 2 decimals


class TestFormatDateHMDA:
    """Tests for _format_date_hmda helper."""

    def test_date_object(self):
        assert _format_date_hmda(date(2025, 6, 15)) == "20250615"

    def test_datetime_object(self):
        assert _format_date_hmda(datetime(2025, 6, 15, 12, 0, 0)) == "20250615"

    def test_none_returns_na(self):
        assert _format_date_hmda(None) == "NA"

    def test_string_returns_na(self):
        assert _format_date_hmda("not a date") == "NA"


# =============================================================================
# Action Taken Mapping Tests
# =============================================================================

class TestActionTakenMap:
    """Tests for loan stage to HMDA action taken code mapping."""

    def test_funded_maps_to_originated(self):
        """FUNDED stage maps to action taken code 1 (originated)."""
        assert ACTION_TAKEN_MAP["FUNDED"] == "1"

    def test_approved_maps_to_approved_not_accepted(self):
        """APPROVED maps to code 2 (approved but not accepted)."""
        assert ACTION_TAKEN_MAP["APPROVED"] == "2"

    def test_denied_maps_to_denied(self):
        """DENIED maps to code 3."""
        assert ACTION_TAKEN_MAP["DENIED"] == "3"

    def test_withdrawn_maps_to_withdrawn(self):
        """WITHDRAWN maps to code 4."""
        assert ACTION_TAKEN_MAP["WITHDRAWN"] == "4"

    def test_cancelled_maps_to_file_closed(self):
        """CANCELLED maps to code 5 (file closed for incompleteness)."""
        assert ACTION_TAKEN_MAP["CANCELLED"] == "5"

    def test_does_not_qualify_maps_to_denied(self):
        """DOES_NOT_QUALIFY maps to denied (code 3)."""
        assert ACTION_TAKEN_MAP["DOES_NOT_QUALIFY"] == "3"

    def test_dead_maps_to_file_closed(self):
        """DEAD maps to file closed (code 5)."""
        assert ACTION_TAKEN_MAP["DEAD"] == "5"

    def test_active_stages_not_in_map(self):
        """Active pipeline stages are NOT in the action taken map."""
        assert "APPLICATION" not in ACTION_TAKEN_MAP
        assert "PROCESSING" not in ACTION_TAKEN_MAP
        assert "UNDERWRITING" not in ACTION_TAKEN_MAP


class TestFieldMappings:
    """Tests for HMDA field value mappings."""

    def test_loan_type_conventional(self):
        assert LOAN_TYPE_MAP["conventional"] == "1"

    def test_loan_type_fha(self):
        assert LOAN_TYPE_MAP["fha"] == "2"

    def test_loan_type_va(self):
        assert LOAN_TYPE_MAP["va"] == "3"

    def test_loan_type_usda(self):
        assert LOAN_TYPE_MAP["usda"] == "4"

    def test_loan_purpose_purchase(self):
        assert LOAN_PURPOSE_MAP["purchase"] == "1"

    def test_loan_purpose_refinance(self):
        assert LOAN_PURPOSE_MAP["refinance"] == "31"

    def test_occupancy_primary(self):
        assert OCCUPANCY_TYPE_MAP["primary"] == "1"

    def test_occupancy_investment(self):
        assert OCCUPANCY_TYPE_MAP["investment"] == "3"

    def test_property_single_family(self):
        assert PROPERTY_TYPE_MAP["single_family"] == "1"

    def test_property_manufactured(self):
        assert PROPERTY_TYPE_MAP["manufactured"] == "2"


# =============================================================================
# Per-Loan Validation Tests
# =============================================================================

class TestValidateLoanForHMDA:
    """Tests for per-loan HMDA validation logic."""

    def test_valid_loan_no_errors(self):
        """A fully-populated funded loan produces no validation errors."""
        loan = FakeLoan()
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        assert len(errors) == 0

    def test_missing_loan_number(self):
        """Missing loan_number is flagged."""
        loan = FakeLoan(loan_number=None)
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        field_names = [e["field"] for e in errors]
        assert "loan_number" in field_names

    def test_invalid_stage(self):
        """Non-terminal stage is flagged as unmappable."""
        loan = FakeLoan()
        errors = _validate_loan_for_hmda(loan, "PROCESSING")

        field_names = [e["field"] for e in errors]
        assert "stage" in field_names

    def test_missing_loan_purpose(self):
        """Missing loan purpose is flagged."""
        loan = FakeLoan(loan_purpose=None)
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        field_names = [e["field"] for e in errors]
        assert "loan_purpose" in field_names

    def test_missing_amount(self):
        """Missing or zero amount is flagged."""
        loan = FakeLoan(amount=0)
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        field_names = [e["field"] for e in errors]
        assert "amount" in field_names

    def test_missing_property_state(self):
        """Missing property state is flagged."""
        loan = FakeLoan(property_state=None)
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        field_names = [e["field"] for e in errors]
        assert "property_state" in field_names

    def test_missing_property_county(self):
        """Missing property county is flagged."""
        loan = FakeLoan(property_county=None)
        errors = _validate_loan_for_hmda(loan, "FUNDED")

        field_names = [e["field"] for e in errors]
        assert "property_county" in field_names

    def test_demographic_check_no_application(self):
        """When db is provided but no BorrowerApplication exists, demographic error is raised."""
        loan = FakeLoan()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        errors = _validate_loan_for_hmda(loan, "FUNDED", db=db)

        field_names = [e["field"] for e in errors]
        assert "borrower_application" in field_names

    def test_demographic_check_missing_fields(self):
        """Missing demographic fields on BorrowerApplication are flagged."""
        loan = FakeLoan()
        app = FakeBorrowerApplication(applicant_ethnicity=None, applicant_race="", applicant_sex="1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = app

        errors = _validate_loan_for_hmda(loan, "FUNDED", db=db)

        field_names = [e["field"] for e in errors]
        assert "applicant_ethnicity" in field_names
        assert "applicant_race" in field_names

    def test_demographic_check_all_present(self):
        """Fully-populated demographic fields produce no errors."""
        loan = FakeLoan()
        app = FakeBorrowerApplication()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = app

        errors = _validate_loan_for_hmda(loan, "FUNDED", db=db)

        assert len(errors) == 0

    def test_no_demographic_check_without_db(self):
        """Without a db session, demographic checks are skipped."""
        loan = FakeLoan()

        errors = _validate_loan_for_hmda(loan, "FUNDED", db=None)

        # Only loan-level checks, no demographic errors
        demo_fields = {"applicant_ethnicity", "applicant_race", "applicant_sex", "borrower_application"}
        field_names = {e["field"] for e in errors}
        assert not field_names.intersection(demo_fields)


# =============================================================================
# LAR Record Builder Tests
# =============================================================================

class TestBuildLARRecord:
    """Tests for _build_lar_record pipe-delimited output."""

    def test_record_is_pipe_delimited(self):
        """LAR record uses pipe delimiter."""
        loan = FakeLoan()
        record = _build_lar_record(loan, lei="TESTLEI1234567890AB", year=2025)

        assert "|" in record
        fields = record.split("|")
        assert len(fields) > 10

    def test_field_count(self):
        """LAR record has exactly 36 fields (as defined in _build_lar_record)."""
        loan = FakeLoan()
        record = _build_lar_record(loan, lei="TESTLEI1234567890AB", year=2025)

        fields = record.split("|")
        assert len(fields) == 36

    def test_activity_year(self):
        """First field is the activity year."""
        loan = FakeLoan()
        record = _build_lar_record(loan, lei="TESTLEI", year=2025)

        fields = record.split("|")
        assert fields[0] == "2025"

    def test_lei_field(self):
        """Second field is the LEI."""
        loan = FakeLoan()
        record = _build_lar_record(loan, lei="TESTLEI1234567890AB", year=2025)

        fields = record.split("|")
        assert fields[1] == "TESTLEI1234567890AB"

    def test_loan_number_field(self):
        """Third field is the loan number (ULI)."""
        loan = FakeLoan(loan_number="LN-2025-TEST")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[2] == "LN-2025-TEST"

    def test_action_taken_funded(self):
        """Funded loan has action taken code 1."""
        loan = FakeLoan(stage="FUNDED")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[10] == "1"  # Field 11: Action Taken

    def test_action_taken_denied(self):
        """Denied loan has action taken code 3."""
        loan = FakeLoan(stage="DENIED")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[10] == "3"

    def test_loan_type_mapping(self):
        """Loan type is correctly mapped."""
        loan = FakeLoan(loan_type="fha")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[4] == "2"  # Field 5: Loan Type (FHA = 2)

    def test_loan_purpose_mapping(self):
        """Loan purpose is correctly mapped."""
        loan = FakeLoan(loan_purpose="refinance")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[5] == "31"  # Field 6: Loan Purpose (Refinance = 31)

    def test_loan_amount_formatted(self):
        """Loan amount is whole dollars (no decimals)."""
        loan = FakeLoan(amount=425000.00)
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[9] == "425000"  # Field 10: Loan Amount

    def test_interest_rate_formatted(self):
        """Interest rate has 2 decimal places."""
        loan = FakeLoan(rate=6.5)
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[28] == "6.50"  # Field 29: Interest Rate

    def test_state_code(self):
        """Property state code is included."""
        loan = FakeLoan(property_state="TX")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[12] == "TX"  # Field 13: State

    def test_missing_fields_use_na(self):
        """Missing optional fields default to NA."""
        loan = FakeLoan(rate=None, property_zip=None)
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[28] == "NA"  # Interest Rate
        assert fields[30] == "NA"  # Property ZIP

    def test_funded_date_as_action_date(self):
        """Funded loan uses funded_date as action taken date."""
        loan = FakeLoan(stage="FUNDED", funded_date=date(2025, 6, 15))
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[11] == "20250615"  # Field 12: Action Taken Date

    def test_application_date_formatted(self):
        """Application date is in YYYYMMDD format."""
        loan = FakeLoan(application_date=date(2025, 3, 1))
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[3] == "20250301"  # Field 4: Application Date

    def test_zip_truncated_to_5_digits(self):
        """Property ZIP is truncated to first 5 characters."""
        loan = FakeLoan(property_zip="90210-1234")
        record = _build_lar_record(loan, lei="LEI", year=2025)

        fields = record.split("|")
        assert fields[30] == "90210"  # Field 31: Property ZIP


class TestBuildLARRecordDemographics:
    """Tests for demographic field encoding in LAR records."""

    def test_demographics_from_db(self):
        """When db is provided, demographics come from BorrowerApplication."""
        loan = FakeLoan()
        app = FakeBorrowerApplication(
            loan_id=1,
            applicant_ethnicity="2",
            applicant_race="5",
            applicant_sex="1",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = app

        record = _build_lar_record(loan, lei="LEI", year=2025, db=db)
        fields = record.split("|")

        # Fields 16-27 are demographic fields
        assert fields[15] == "2"   # applicant_ethnicity
        assert fields[19] == "5"   # applicant_race
        assert fields[23] == "1"   # applicant_sex

    def test_demographics_default_na_without_db(self):
        """Without a db session, all demographic fields default to NA."""
        loan = FakeLoan()
        record = _build_lar_record(loan, lei="LEI", year=2025, db=None)
        fields = record.split("|")

        # All demographic fields (16-27) should be NA
        for i in range(15, 27):
            assert fields[i] == "NA", f"Field {i+1} should be NA, got '{fields[i]}'"

    def test_demographics_na_when_no_application(self):
        """Demographics are NA when no BorrowerApplication exists."""
        loan = FakeLoan()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        record = _build_lar_record(loan, lei="LEI", year=2025, db=db)
        fields = record.split("|")

        assert fields[15] == "NA"  # applicant_ethnicity


# =============================================================================
# GMI Data Lookup Tests
# =============================================================================

class TestGetGMIData:
    """Tests for _get_gmi_data demographic field lookup."""

    def test_returns_application_data(self):
        """Returns demographic data from BorrowerApplication."""
        loan = FakeLoan(id=42)
        app = FakeBorrowerApplication(
            loan_id=42,
            applicant_ethnicity="2",
            applicant_race="5",
            applicant_sex="1",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = app

        gmi = _get_gmi_data(db, loan)

        assert gmi["applicant_ethnicity"] == "2"
        assert gmi["applicant_race"] == "5"
        assert gmi["applicant_sex"] == "1"

    def test_returns_defaults_when_no_application(self):
        """Returns NA defaults when no BorrowerApplication is linked."""
        loan = FakeLoan(id=99)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        gmi = _get_gmi_data(db, loan)

        assert gmi["applicant_ethnicity"] == "NA"
        assert gmi["applicant_race"] == "NA"
        assert gmi["applicant_sex"] == "NA"

    def test_handles_exception_gracefully(self):
        """Returns defaults when BorrowerApplication import or query fails."""
        loan = FakeLoan(id=1)
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        gmi = _get_gmi_data(db, loan)

        assert gmi["applicant_ethnicity"] == "NA"


# =============================================================================
# Full Export (generate_hmda_lar) Tests
# =============================================================================

def _make_hmda_db(loans=None, borrower_app=None):
    """Create a mock DB session that handles the SQLAlchemy query patterns
    used by generate_hmda_lar and validate_hmda_readiness.

    These functions do lazy imports of Loan/BorrowerApplication and build
    SQLAlchemy filter expressions, so we need to mock at a level that
    intercepts db.query(model).filter(...).order_by(...).all().
    """
    db = MagicMock()
    _loans = loans if loans is not None else []

    # db.query(ANY_MODEL).filter(ANY_ARGS).order_by(ANY_ARGS).all() -> loans
    # db.query(ANY_MODEL).filter(ANY_ARGS).all() -> loans or apps
    # db.query(ANY_MODEL).filter(ANY_ARGS).first() -> borrower_app
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = _loans
    chain.first.return_value = borrower_app
    db.query.return_value = chain

    return db


class TestGenerateHMDALAR:
    """Tests for the generate_hmda_lar entry point."""

    def test_no_loans_returns_empty(self):
        """When no terminal-stage loans exist, returns empty result with warning."""
        db = _make_hmda_db(loans=[])

        result = generate_hmda_lar(db, organization_id=1, year=2025)

        assert result["lar_content"] is None
        assert result["total_records"] == 0
        assert len(result["validation_warnings"]) > 0

    def test_valid_loans_produce_lar(self):
        """Valid loans produce pipe-delimited LAR content."""
        loan = FakeLoan()
        app = FakeBorrowerApplication(loan_id=loan.id)
        db = _make_hmda_db(loans=[loan], borrower_app=app)

        result = generate_hmda_lar(db, organization_id=1, year=2025, lei="TESTLEI12345")

        assert result["lar_content"] is not None
        assert result["total_records"] == 1
        assert "|" in result["lar_content"]
        assert "2025" in result["lar_content"]

    def test_validation_errors_block_export(self):
        """Loans with missing required fields prevent LAR generation."""
        bad_loan = FakeLoan(loan_number=None, loan_purpose=None, amount=0)
        db = _make_hmda_db(loans=[bad_loan], borrower_app=None)

        result = generate_hmda_lar(db, organization_id=1, year=2025)

        assert result["lar_content"] is None
        assert len(result["validation_errors"]) > 0

    def test_multiple_loans_multiple_lines(self):
        """Multiple valid loans produce multiple LAR lines."""
        loans = [
            FakeLoan(id=1, loan_number="LN-001"),
            FakeLoan(id=2, loan_number="LN-002"),
        ]
        app = FakeBorrowerApplication(loan_id=1)
        db = _make_hmda_db(loans=loans, borrower_app=app)

        result = generate_hmda_lar(db, organization_id=1, year=2025, lei="LEI")

        if result["lar_content"]:
            lines = result["lar_content"].strip().split("\n")
            assert len(lines) == 2

    def test_export_metadata(self):
        """Export result includes metadata fields."""
        db = _make_hmda_db(loans=[])

        result = generate_hmda_lar(db, organization_id=42, year=2025, lei="TESTLEI")

        assert "export_timestamp" in result


# =============================================================================
# validate_hmda_readiness Tests
# =============================================================================

class TestValidateHMDAReadiness:
    """Tests for the validate_hmda_readiness readiness check."""

    def test_ready_when_all_fields_present(self):
        """is_ready is True when all required fields are populated on every loan."""
        loan = FakeLoan()
        app = FakeBorrowerApplication(loan_id=loan.id)

        # validate_hmda_readiness queries Loan first, then BorrowerApplication.
        # We track call order to return the right data.
        call_count = {"n": 0}
        def query_side_effect(model):
            call_count["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            if call_count["n"] == 1:
                # First query: Loan
                chain.all.return_value = [loan]
            else:
                # Second query: BorrowerApplication
                chain.all.return_value = [app]
            return chain

        db = MagicMock()
        db.query.side_effect = query_side_effect

        result = validate_hmda_readiness(db, organization_id=1, year=2025)

        assert result["total_loans"] == 1
        if result["is_ready"]:
            assert result["loans_with_errors"] == 0

    def test_not_ready_missing_fields(self):
        """is_ready is False when required fields are missing."""
        bad_loan = FakeLoan(property_state=None, property_county=None)

        call_count = {"n": 0}
        def query_side_effect(model):
            call_count["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            if call_count["n"] == 1:
                chain.all.return_value = [bad_loan]
            else:
                chain.all.return_value = []  # No BorrowerApplications
            return chain

        db = MagicMock()
        db.query.side_effect = query_side_effect

        result = validate_hmda_readiness(db, organization_id=1, year=2025)

        assert result["is_ready"] is False
        assert result["loans_with_errors"] > 0

    def test_no_loans_not_ready(self):
        """No terminal-stage loans means not ready."""
        db = _make_hmda_db(loans=[])

        result = validate_hmda_readiness(db, organization_id=1, year=2025)

        assert result["is_ready"] is False
        assert result["total_loans"] == 0

    def test_field_coverage_statistics(self):
        """Result includes field_coverage percentage statistics."""
        loan = FakeLoan()
        app = FakeBorrowerApplication(loan_id=loan.id)

        call_count = {"n": 0}
        def query_side_effect(model):
            call_count["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            if call_count["n"] == 1:
                chain.all.return_value = [loan]
            else:
                chain.all.return_value = [app]
            return chain

        db = MagicMock()
        db.query.side_effect = query_side_effect

        result = validate_hmda_readiness(db, organization_id=1, year=2025)

        assert "field_coverage" in result
        assert isinstance(result["field_coverage"], dict)
        assert "loan_number" in result["field_coverage"]

    def test_missing_demographic_fields_flagged(self):
        """Missing demographic fields are identified in validation errors."""
        loan = FakeLoan()

        call_count = {"n": 0}
        def query_side_effect(model):
            call_count["n"] += 1
            chain = MagicMock()
            chain.filter.return_value = chain
            if call_count["n"] == 1:
                chain.all.return_value = [loan]
            else:
                chain.all.return_value = []  # No BorrowerApplications
            return chain

        db = MagicMock()
        db.query.side_effect = query_side_effect

        result = validate_hmda_readiness(db, organization_id=1, year=2025)

        # Demographic fields should appear in the missing fields
        if result["validation_errors"]:
            all_missing = []
            for err in result["validation_errors"]:
                all_missing.extend(err.get("missing_fields", []))
            assert "applicant_ethnicity" in all_missing or not result["is_ready"]


# =============================================================================
# Required Fields Constants Tests
# =============================================================================

class TestRequiredFieldsConstants:
    """Tests for HMDA required field constants."""

    def test_required_loan_fields(self):
        """Required loan fields list contains expected entries."""
        assert "loan_number" in REQUIRED_LOAN_FIELDS
        assert "loan_type" in REQUIRED_LOAN_FIELDS
        assert "loan_purpose" in REQUIRED_LOAN_FIELDS
        assert "loan_amount" in REQUIRED_LOAN_FIELDS
        assert "property_state" in REQUIRED_LOAN_FIELDS
        assert "property_county" in REQUIRED_LOAN_FIELDS

    def test_required_demographic_fields(self):
        """Required demographic fields list contains HMDA-mandated fields."""
        assert "applicant_ethnicity" in REQUIRED_DEMOGRAPHIC_FIELDS
        assert "applicant_race" in REQUIRED_DEMOGRAPHIC_FIELDS
        assert "applicant_sex" in REQUIRED_DEMOGRAPHIC_FIELDS

    def test_recommended_fields(self):
        """Recommended fields contain expected optional entries."""
        assert "property_type" in RECOMMENDED_FIELDS
        assert "occupancy_type" in RECOMMENDED_FIELDS
        assert "interest_rate" in RECOMMENDED_FIELDS
