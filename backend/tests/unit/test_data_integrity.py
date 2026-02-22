"""
Data Integrity Unit Tests

Tests data model integrity directly without making HTTP requests:
- Loan financial fields use Numeric (not Float) for precision
- Lead stage validation against LeadStage enum
- Loan stage validation against LoanStage enum
- Email format patterns
- Enum value consistency

These tests verify the SQLAlchemy model definitions and validators
are correctly configured to protect data integrity.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone


# Mark all tests as unit tests
pytestmark = [pytest.mark.unit]


class TestLoanFinancialFieldsAreNumeric:
    """Verify that financial columns use Numeric(18,2) or Numeric(8,4), not Float."""

    def test_loan_amount_is_numeric(self):
        """Loan.amount should be Numeric(18,2) for precise currency storage."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        amount_col = Loan.__table__.columns["amount"]
        assert isinstance(amount_col.type, Numeric), (
            f"Loan.amount should be Numeric, got {type(amount_col.type).__name__}"
        )
        assert amount_col.type.precision == 18, (
            f"Loan.amount precision should be 18, got {amount_col.type.precision}"
        )
        assert amount_col.type.scale == 2, (
            f"Loan.amount scale should be 2, got {amount_col.type.scale}"
        )

    def test_loan_rate_is_numeric(self):
        """Loan.rate should be Numeric(8,4) for precise rate storage."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        rate_col = Loan.__table__.columns["rate"]
        assert isinstance(rate_col.type, Numeric), (
            f"Loan.rate should be Numeric, got {type(rate_col.type).__name__}"
        )
        assert rate_col.type.precision == 8
        assert rate_col.type.scale == 4

    def test_loan_purchase_price_is_numeric(self):
        """Loan.purchase_price should be Numeric(18,2)."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        col = Loan.__table__.columns["purchase_price"]
        assert isinstance(col.type, Numeric), (
            f"Loan.purchase_price should be Numeric, got {type(col.type).__name__}"
        )

    def test_loan_down_payment_is_numeric(self):
        """Loan.down_payment should be Numeric(18,2)."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        col = Loan.__table__.columns["down_payment"]
        assert isinstance(col.type, Numeric), (
            f"Loan.down_payment should be Numeric, got {type(col.type).__name__}"
        )

    def test_loan_monthly_payment_is_numeric(self):
        """Loan.monthly_payment should be Numeric(18,2)."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        col = Loan.__table__.columns["monthly_payment"]
        assert isinstance(col.type, Numeric), (
            f"Loan.monthly_payment should be Numeric, got {type(col.type).__name__}"
        )

    def test_lead_loan_amount_is_numeric(self):
        """Lead.loan_amount should be Numeric(18,2)."""
        from database.models.lead_loan import Lead
        from sqlalchemy import Numeric

        col = Lead.__table__.columns["loan_amount"]
        assert isinstance(col.type, Numeric), (
            f"Lead.loan_amount should be Numeric, got {type(col.type).__name__}"
        )

    def test_lead_preapproval_amount_is_numeric(self):
        """Lead.preapproval_amount should be Numeric(18,2)."""
        from database.models.lead_loan import Lead
        from sqlalchemy import Numeric

        col = Lead.__table__.columns["preapproval_amount"]
        assert isinstance(col.type, Numeric), (
            f"Lead.preapproval_amount should be Numeric, got {type(col.type).__name__}"
        )

    def test_loan_appraisal_value_is_numeric(self):
        """Loan.appraisal_value should be Numeric(18,2)."""
        from database.models.lead_loan import Loan
        from sqlalchemy import Numeric

        col = Loan.__table__.columns["appraisal_value"]
        assert isinstance(col.type, Numeric), (
            f"Loan.appraisal_value should be Numeric, got {type(col.type).__name__}"
        )


class TestLeadStageValidation:
    """Tests for Lead stage validation."""

    def test_lead_valid_stages_match_enum(self):
        """Lead._VALID_LEAD_STAGES should match all LeadStage enum values."""
        from database.models.lead_loan import Lead
        from database.enums import LeadStage

        enum_values = {s.value for s in LeadStage}
        assert Lead._VALID_LEAD_STAGES == enum_values, (
            f"Lead valid stages mismatch. "
            f"Missing from Lead: {enum_values - Lead._VALID_LEAD_STAGES}, "
            f"Extra in Lead: {Lead._VALID_LEAD_STAGES - enum_values}"
        )

    def test_lead_default_stage_is_new(self):
        """Lead.stage should default to 'New'."""
        from database.models.lead_loan import Lead

        stage_col = Lead.__table__.columns["stage"]
        default = stage_col.default
        if default is not None:
            assert default.arg == "New", (
                f"Lead default stage should be 'New', got '{default.arg}'"
            )

    def test_lead_stage_validator_accepts_valid_stage(self):
        """Lead.validate_stage should accept valid stage strings."""
        from database.models.lead_loan import Lead

        lead = Lead.__new__(Lead)
        # Simulate @validates call
        result = lead.validate_stage("stage", "New")
        assert result == "New"

    def test_lead_stage_validator_accepts_enum_value(self):
        """Lead.validate_stage should extract .value from enum members."""
        from database.models.lead_loan import Lead
        from database.enums import LeadStage

        lead = Lead.__new__(Lead)
        result = lead.validate_stage("stage", LeadStage.NEW)
        assert result == "New"

    def test_lead_stage_validator_accepts_none(self):
        """Lead.validate_stage should pass through None."""
        from database.models.lead_loan import Lead

        lead = Lead.__new__(Lead)
        result = lead.validate_stage("stage", None)
        assert result is None

    def test_lead_stage_validator_warns_on_unknown(self, caplog):
        """Lead.validate_stage should log warning but allow unknown stages."""
        import logging
        from database.models.lead_loan import Lead

        lead = Lead.__new__(Lead)
        # Unknown stage should be allowed (backward compat) but trigger a log warning
        with caplog.at_level(logging.WARNING):
            result = lead.validate_stage("stage", "TOTALLY_UNKNOWN_STAGE")
        # Result should pass through even for unknown stages
        assert result == "TOTALLY_UNKNOWN_STAGE"
        assert any("TOTALLY_UNKNOWN_STAGE" in r.message for r in caplog.records)


class TestLoanStageValidation:
    """Tests for Loan stage validation."""

    def test_loan_valid_stages_match_enum(self):
        """Loan._VALID_LOAN_STAGES should match all LoanStage enum values."""
        from database.models.lead_loan import Loan
        from database.enums import LoanStage

        enum_values = {s.value for s in LoanStage}
        assert Loan._VALID_LOAN_STAGES == enum_values, (
            f"Loan valid stages mismatch. "
            f"Missing: {enum_values - Loan._VALID_LOAN_STAGES}, "
            f"Extra: {Loan._VALID_LOAN_STAGES - enum_values}"
        )

    def test_loan_default_stage_is_disclosed(self):
        """Loan.stage should default to 'DISCLOSED'."""
        from database.models.lead_loan import Loan

        stage_col = Loan.__table__.columns["stage"]
        default = stage_col.default
        if default is not None:
            assert default.arg == "DISCLOSED", (
                f"Loan default stage should be 'DISCLOSED', got '{default.arg}'"
            )

    def test_loan_stage_validator_uppercases(self):
        """Loan.validate_stage should uppercase the value."""
        from database.models.lead_loan import Loan

        loan = Loan.__new__(Loan)
        result = loan.validate_stage("stage", "processing")
        assert result == "PROCESSING", (
            f"Loan stage should be uppercased, got '{result}'"
        )

    def test_loan_stage_validator_accepts_enum(self):
        """Loan.validate_stage should extract .value from LoanStage enum."""
        from database.models.lead_loan import Loan
        from database.enums import LoanStage

        loan = Loan.__new__(Loan)
        result = loan.validate_stage("stage", LoanStage.FUNDED)
        assert result == "FUNDED"

    def test_loan_stage_validator_accepts_none(self):
        """Loan.validate_stage should pass through None."""
        from database.models.lead_loan import Loan

        loan = Loan.__new__(Loan)
        result = loan.validate_stage("stage", None)
        assert result is None

    def test_all_loan_stages_are_uppercase(self):
        """All LoanStage enum values should be uppercase."""
        from database.enums import LoanStage

        for stage in LoanStage:
            assert stage.value == stage.value.upper(), (
                f"LoanStage.{stage.name} value '{stage.value}' should be uppercase"
            )


class TestEmailFormatValidation:
    """Tests for email format patterns in the models."""

    def test_lead_email_column_exists(self):
        """Lead model should have an email column."""
        from database.models.lead_loan import Lead

        assert "email" in Lead.__table__.columns, "Lead should have email column"

    def test_loan_borrower_email_column_exists(self):
        """Loan model should have a borrower_email column."""
        from database.models.lead_loan import Loan

        assert "borrower_email" in Loan.__table__.columns, (
            "Loan should have borrower_email column"
        )

    def test_lead_email_is_indexed(self):
        """Lead.email should be indexed for fast lookups."""
        from database.models.lead_loan import Lead

        email_col = Lead.__table__.columns["email"]
        assert email_col.index is True, "Lead.email should be indexed"


class TestEnumConsistency:
    """Tests for enum value consistency between code and database."""

    def test_lead_stage_enum_has_standard_values(self):
        """LeadStage enum should include critical lifecycle stages."""
        from database.enums import LeadStage

        critical_stages = ["New", "Application", "Pre-Approved", "Closed", "Withdrawn"]
        enum_values = {s.value for s in LeadStage}

        for stage in critical_stages:
            assert stage in enum_values, (
                f"Critical stage '{stage}' missing from LeadStage enum"
            )

    def test_loan_stage_enum_has_pipeline_stages(self):
        """LoanStage enum should include full pipeline stages."""
        from database.enums import LoanStage

        pipeline_stages = [
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "APPROVED", "CLEAR_TO_CLOSE",
            "DOCS_OUT", "FUNDED", "CANCELLED", "DENIED",
        ]
        enum_values = {s.value for s in LoanStage}

        for stage in pipeline_stages:
            assert stage in enum_values, (
                f"Pipeline stage '{stage}' missing from LoanStage enum"
            )

    def test_terminal_stages_are_valid_loan_stages(self):
        """Terminal stages constant should only contain valid LoanStage values."""
        from database.enums import LoanStage

        # From CLAUDE.md constants
        terminal_stages = ("FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY")
        valid_stages = {s.value for s in LoanStage}

        for stage in terminal_stages:
            assert stage in valid_stages, (
                f"Terminal stage '{stage}' is not a valid LoanStage"
            )
