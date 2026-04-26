"""Tests for URLA Pydantic models."""
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from agents.urla.models import (
    URLAApplication,
    Borrower,
    Section1a_PersonalInformation,
    Section1b_CurrentEmployment,
    Section2_AssetsAndLiabilities,
    Asset,
    AssetType,
    Section4_LoanAndProperty,
    Section4a_LoanAndProperty,
    Section5_Declarations,
    Section5a_DeclarationsPropertyMoney,
    Section5b_DeclarationsFinances,
    Section6_Acknowledgments,
    Section8_Demographics,
    Address,
    ResidenceHistory,
    LoanPurpose,
    PropertyOccupancy,
    CitizenshipStatus,
)


def _minimal_app() -> URLAApplication:
    return URLAApplication(
        loan_id="TEST-001",
        tenant_id="test",
        caller_phone="+18435551212",
        borrowers=[Borrower(borrower_id="borrower_1", is_primary=True)],
    )


def _complete_app() -> URLAApplication:
    """Build a minimally complete application that passes validate_complete()."""
    app = _minimal_app()
    b = app.borrowers[0]
    b.section_1a = Section1a_PersonalInformation(
        first_name="Jane",
        last_name="Doe",
        ssn="219-09-9999",
        date_of_birth=date(1990, 1, 15),
        citizenship=CitizenshipStatus.US_CITIZEN,
        current_address=ResidenceHistory(
            address=Address(street="123 Main St", city="Charleston", state="SC", zip_code="29401"),
            years_at_address=5,
            months_at_address=0,
        ),
    )
    b.section_1b = Section1b_CurrentEmployment(
        employer_name="Acme Corp",
        base_monthly=Decimal("5000"),
    )
    b.section_5 = Section5_Declarations(
        section_5a=Section5a_DeclarationsPropertyMoney(
            will_occupy_as_primary_residence=True,
            had_ownership_interest_last_3_years=False,
            family_business_relationship_with_seller=False,
            borrowing_money_for_transaction=False,
            applying_for_other_mortgage_before_closing=False,
            applying_for_new_credit_before_closing=False,
            property_subject_to_lien=False,
        ),
        section_5b=Section5b_DeclarationsFinances(
            outstanding_judgments=False,
            currently_delinquent_on_federal_debt=False,
            party_to_lawsuit=False,
            conveyed_title_in_lieu_of_foreclosure=False,
            pre_foreclosure_short_sale=False,
            foreclosed_last_7_years=False,
            declared_bankruptcy_last_7_years=False,
            co_signer_on_undisclosed_debt=False,
            delinquent_on_child_support_alimony=False,
        ),
    )
    b.section_8 = Section8_Demographics(
        demographics_notice_read_at=datetime.now(timezone.utc),
        was_demographic_info_provided_by_borrower=False,
    )
    app.section_2 = Section2_AssetsAndLiabilities(
        assets=[Asset(asset_type=AssetType.CHECKING_ACCOUNT, financial_institution="Bank", cash_or_market_value=Decimal("25000"))],
    )
    app.section_4 = Section4_LoanAndProperty(
        section_4a=Section4a_LoanAndProperty(
            loan_amount=Decimal("300000"),
            loan_purpose=LoanPurpose.PURCHASE,
            property_value=Decimal("400000"),
            occupancy=PropertyOccupancy.PRIMARY_RESIDENCE,
            subject_property_address=Address(street="456 Oak Ave", city="Charleston", state="SC", zip_code="29401"),
        ),
    )
    app.section_6 = Section6_Acknowledgments(
        verbal_consent_given=True,
        verbal_consent_timestamp=datetime.now(timezone.utc),
        privacy_notice_consent_given=True,
        privacy_notice_consent_timestamp=datetime.now(timezone.utc),
    )
    return app


class TestProgressSummary:
    def test_empty_app(self):
        app = _minimal_app()
        summary = app.progress_summary()
        assert summary["percent_complete"] == 0
        assert summary["is_finalized"] is False

    def test_partial_completion(self):
        app = _minimal_app()
        app.completed_sections = ["SECTION_1A", "SECTION_1B"]
        summary = app.progress_summary()
        assert 10 <= summary["percent_complete"] <= 15

    def test_trackable_sections_count(self):
        assert len(URLAApplication.TRACKABLE_SECTIONS) == 17


class TestValidateComplete:
    def test_complete_app_passes(self):
        app = _complete_app()
        errors = app.validate_complete()
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_name(self):
        app = _complete_app()
        app.borrowers[0].section_1a.first_name = None
        errors = app.validate_complete()
        assert any("name" in e.lower() for e in errors)

    def test_missing_ssn(self):
        app = _complete_app()
        app.borrowers[0].section_1a.ssn = None
        errors = app.validate_complete()
        assert any("ssn" in e.lower() for e in errors)

    def test_missing_consent(self):
        app = _complete_app()
        app.section_6.verbal_consent_given = False
        errors = app.validate_complete()
        assert any("consent" in e.lower() for e in errors)

    def test_missing_loan_amount(self):
        app = _complete_app()
        app.section_4.section_4a.loan_amount = None
        errors = app.validate_complete()
        assert any("loan amount" in e.lower() for e in errors)


class TestTRIDTriggers:
    def test_triggers_when_complete(self):
        app = _complete_app()
        assert app.check_trid_triggers() is True
        assert app.application_received_at is not None

    def test_does_not_retrigger(self):
        app = _complete_app()
        app.check_trid_triggers()
        first_time = app.application_received_at
        assert app.check_trid_triggers() is False
        assert app.application_received_at == first_time

    def test_does_not_trigger_without_income(self):
        app = _complete_app()
        app.borrowers[0].section_1b = None
        app.borrowers[0].section_1e = None
        assert app.check_trid_triggers() is False

    def test_does_not_trigger_without_property(self):
        app = _complete_app()
        app.section_4.section_4a.subject_property_address = None
        assert app.check_trid_triggers() is False


class TestSessionLockToken:
    def test_default_none(self):
        app = _minimal_app()
        assert app.session_lock_token is None

    def test_set_token(self):
        app = _minimal_app()
        app.session_lock_token = "abc123"
        assert app.session_lock_token == "abc123"


class TestPrivacyNoticeConsent:
    def test_default_false(self):
        ack = Section6_Acknowledgments()
        assert ack.privacy_notice_consent_given is False
        assert ack.privacy_notice_consent_timestamp is None


class TestDemographicsNoticeTimestamp:
    def test_default_none(self):
        demo = Section8_Demographics()
        assert demo.demographics_notice_read_at is None

    def test_set_timestamp(self):
        now = datetime.now(timezone.utc)
        demo = Section8_Demographics(demographics_notice_read_at=now)
        assert demo.demographics_notice_read_at == now
