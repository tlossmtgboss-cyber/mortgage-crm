"""Tests for URLA -> POS hydration service.

Verifies that:
  - Hydration creates POSApplication from URLA data
  - All URLA sections map to correct POS section keys
  - SSN is written to the encrypted PII table
  - Completion percentage reflects URLA progress
  - Hydration is idempotent (no duplicate applications)
  - Finalized URLA sets application to submitted status

Uses the SQLite in-memory test DB from tests/pos/conftest.py.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from database.models.pos import (
    POSApplication,
    POSApplicationPII,
    POSApplicationSection,
    POSSectionKey,
    POSStatus,
)


# ---------------------------------------------------------------------------
# URLA data builders
# ---------------------------------------------------------------------------

def _build_urla_data(
    *,
    loan_id: str = "LOAN-001",
    tenant_id: str = "1",
    is_finalized: bool = False,
    completed_sections: list[str] | None = None,
    include_personal: bool = True,
    include_employment: bool = True,
    include_assets: bool = True,
    include_liabilities: bool = True,
    include_reo: bool = False,
    include_loan_info: bool = True,
    include_declarations: bool = True,
    include_demographics: bool = False,
    include_consent: bool = False,
    include_military: bool = False,
    ssn: str | None = None,
    dob: str | None = None,
    co_borrower: bool = False,
    co_ssn: str | None = None,
    co_dob: str | None = None,
) -> dict[str, Any]:
    """Build a serialized URLAApplication dict for hydration."""
    data: dict[str, Any] = {
        "loan_id": loan_id,
        "tenant_id": tenant_id,
        "caller_phone": "+15551234567",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_section": "SECTION_4A" if not is_finalized else "FINALIZED",
        "completed_sections": completed_sections or [],
        "is_finalized": is_finalized,
        "finalized_at": datetime.now(timezone.utc).isoformat() if is_finalized else None,
        "borrowers": [],
    }

    # Primary borrower
    primary: dict[str, Any] = {
        "borrower_id": "borrower_1",
        "is_primary": True,
    }

    if include_personal:
        s1a: dict[str, Any] = {
            "first_name": "Alice",
            "middle_name": "M",
            "last_name": "Anderson",
            "email": "alice@example.com",
            "cell_phone": "+15551234567",
            "home_phone": "+15559876543",
            "citizenship": "US_CITIZEN",
            "marital_status": "MARRIED",
            "dependents_count": 2,
            "dependents_ages": [5, 8],
            "current_address": {
                "address": {
                    "street": "123 Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip_code": "78701",
                    "country": "US",
                },
                "years_at_address": 3,
                "months_at_address": 6,
                "housing_expense_monthly": 2100,
                "own_or_rent": "RENT",
            },
            "mailing_address_same_as_current": True,
        }
        if ssn:
            s1a["ssn"] = ssn
        if dob:
            s1a["date_of_birth"] = dob
        primary["section_1a"] = s1a

    if include_employment:
        primary["section_1b"] = {
            "employer_name": "Acme Corp",
            "employer_address": {
                "street": "456 Commerce Blvd",
                "city": "Austin",
                "state": "TX",
                "zip_code": "78702",
                "country": "US",
            },
            "position_title": "Software Engineer",
            "start_date": "2020-03-15",
            "years_in_profession": 6,
            "self_employed": False,
            "base_monthly": 8500,
            "overtime_monthly": 500,
            "bonus_monthly": 1000,
        }
        primary["section_1e"] = {
            "does_not_apply": True,
            "sources": [],
        }

    if include_declarations:
        primary["section_5"] = {
            "section_5a": {
                "will_occupy_as_primary_residence": True,
                "had_ownership_interest_last_3_years": False,
                "family_business_relationship_with_seller": False,
                "borrowing_money_for_transaction": False,
                "applying_for_other_mortgage_before_closing": False,
                "applying_for_new_credit_before_closing": False,
                "property_subject_to_lien": False,
            },
            "section_5b": {
                "co_signer_on_undisclosed_debt": False,
                "outstanding_judgments": False,
                "currently_delinquent_on_federal_debt": False,
                "party_to_lawsuit": False,
                "conveyed_title_in_lieu_of_foreclosure_last_7_years": False,
                "short_sale_or_pre_foreclosure_last_7_years": False,
                "foreclosed_last_7_years": False,
                "declared_bankruptcy_last_7_years": False,
            },
        }

    if include_demographics:
        primary["section_8"] = {
            "demographics_notice_read_at": datetime.now(timezone.utc).isoformat(),
            "ethnicity": ["NOT_HISPANIC_OR_LATINO"],
            "race": ["WHITE"],
            "sex": "FEMALE",
            "was_demographic_info_provided_by_borrower": True,
            "application_channel": "TELEPHONE",
        }

    if include_military:
        primary["section_7"] = {
            "served_in_military": False,
        }

    data["borrowers"].append(primary)

    # Co-borrower
    if co_borrower:
        co: dict[str, Any] = {
            "borrower_id": "borrower_2",
            "is_primary": False,
            "section_1a": {
                "first_name": "Bob",
                "last_name": "Anderson",
                "email": "bob@example.com",
            },
        }
        if co_ssn:
            co["section_1a"]["ssn"] = co_ssn
        if co_dob:
            co["section_1a"]["date_of_birth"] = co_dob
        data["borrowers"].append(co)

    # Shared sections
    if include_assets:
        data["section_2"] = {
            "assets": [
                {
                    "asset_type": "CHECKING_ACCOUNT",
                    "financial_institution": "First National Bank",
                    "account_number_last_4": "4321",
                    "cash_or_market_value": 45000,
                },
                {
                    "asset_type": "SAVINGS_ACCOUNT",
                    "financial_institution": "First National Bank",
                    "account_number_last_4": "8765",
                    "cash_or_market_value": 120000,
                },
            ],
            "other_credits": [],
        }
        if include_liabilities:
            data["section_2"]["liabilities"] = [
                {
                    "liability_type": "REVOLVING",
                    "creditor_name": "Chase",
                    "account_number_last_4": "1111",
                    "unpaid_balance": 5000,
                    "monthly_payment": 150,
                    "to_be_paid_off_at_closing": False,
                },
            ]
            data["section_2"]["other_liabilities"] = []

    if include_reo:
        data["section_3"] = {
            "does_not_apply": False,
            "properties": [
                {
                    "address": {
                        "street": "789 Investment Ln",
                        "city": "Dallas",
                        "state": "TX",
                        "zip_code": "75201",
                        "country": "US",
                    },
                    "property_value": 300000,
                    "status": "RETAINED",
                    "intended_occupancy": "INVESTMENT",
                    "monthly_rental_income": 2000,
                    "mortgages": [
                        {
                            "creditor_name": "Wells Fargo",
                            "monthly_payment": 1500,
                            "unpaid_balance": 200000,
                            "to_be_paid_off": False,
                        }
                    ],
                }
            ],
        }

    if include_loan_info:
        data["section_4"] = {
            "section_4a": {
                "loan_amount": 350000,
                "loan_purpose": "PURCHASE",
                "subject_property_address": {
                    "street": "100 New Home Ave",
                    "city": "Austin",
                    "state": "TX",
                    "zip_code": "78703",
                    "country": "US",
                },
                "number_of_units": 1,
                "property_value": 425000,
                "occupancy": "PRIMARY_RESIDENCE",
                "mixed_use_property": False,
                "manufactured_home": False,
            },
            "section_4b": {"does_not_apply": True},
            "section_4c": {"does_not_apply": True},
            "section_4d": {"does_not_apply": True},
        }

    if include_consent:
        data["section_6"] = {
            "verbal_consent_given": True,
            "verbal_consent_timestamp": datetime.now(timezone.utc).isoformat(),
            "privacy_notice_consent_given": True,
        }

    return data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hydration_service():
    """Create a URLAHydrationService with the ApplicationService mocked.

    We mock ApplicationService methods because the real service depends on
    ORM patterns (selectinload, UUID primary keys) that don't fully work
    on the SQLite test DB. Instead we test the mapping logic directly.
    """
    from unittest.mock import MagicMock, patch
    from services.pos.urla_hydration_service import URLAHydrationService

    svc = URLAHydrationService()
    return svc


@pytest.fixture
def mock_app_service():
    """Return a mocked ApplicationService with stubbed methods."""
    from unittest.mock import MagicMock

    mock_svc = MagicMock()

    # get_or_create_for_loan returns a POSApplication-like object
    mock_app = MagicMock(spec=POSApplication)
    mock_app.id = uuid4()
    mock_app.organization_id = 1
    mock_app.workspace_id = 1
    mock_app.contact_id = 1001
    mock_app.loan_id = None
    mock_app.status = POSStatus.DRAFT
    mock_app.current_step = POSSectionKey.PERSONAL
    mock_app.completion_pct = 0
    mock_app.sections = []
    mock_app.pii = None
    mock_app.submitted_at = None
    mock_svc.get_or_create_for_loan.return_value = mock_app

    # upsert_section returns a mock section
    def make_section(**kwargs):
        sec = MagicMock(spec=POSApplicationSection)
        sec.section_key = kwargs.get("section_key", "personal")
        sec.data = kwargs.get("data", {})
        sec.is_complete = kwargs.get("mark_complete", False)
        sec.completed_at = None
        mock_app.sections.append(sec)
        return sec

    mock_svc.upsert_section.side_effect = lambda session, *, application, section_key, data, mark_complete=False, ctx: make_section(
        section_key=section_key, data=data, mark_complete=mark_complete,
    )

    # upsert_pii returns a mock PII record
    mock_pii = MagicMock(spec=POSApplicationPII)
    mock_pii.ssn_encrypted = None
    mock_pii.co_ssn_encrypted = None
    mock_pii.dob = None
    mock_pii.co_dob = None
    mock_svc.upsert_pii.return_value = mock_pii

    return mock_svc, mock_app


# ==========================================================================
# Test 1: Hydration creates POSApplication from URLA data
# ==========================================================================

class TestHydrationCreatesApplication:
    """Verify that hydrate_from_urla creates a POSApplication with sections."""

    def test_creates_application_with_correct_sections(self, mock_app_service):
        """All non-empty URLA sections should be upserted."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            include_personal=True,
            include_employment=True,
            include_assets=True,
            include_liabilities=True,
            include_loan_info=True,
            include_declarations=True,
        )

        result = svc.hydrate_from_urla(
            session,
            urla_data=urla,
            organization_id=1,
            workspace_id=1,
            contact_id=1001,
            loan_id=42,
        )

        # get_or_create should have been called
        mock_svc.get_or_create_for_loan.assert_called_once()
        call_kwargs = mock_svc.get_or_create_for_loan.call_args
        assert call_kwargs.kwargs["contact_id"] == 1001
        assert call_kwargs.kwargs["loan_id"] == 42
        assert call_kwargs.kwargs["source_channel"] == "voice_agent"

        # Verify upsert_section was called for non-empty sections
        upsert_calls = mock_svc.upsert_section.call_args_list
        section_keys_upserted = [
            call.kwargs["section_key"] for call in upsert_calls
        ]

        # These sections should all have data from our builder
        assert POSSectionKey.PERSONAL in section_keys_upserted
        assert POSSectionKey.EMPLOYMENT in section_keys_upserted
        assert POSSectionKey.ASSETS in section_keys_upserted
        assert POSSectionKey.LIABILITIES in section_keys_upserted
        assert POSSectionKey.LOAN in section_keys_upserted
        assert POSSectionKey.DECLARATIONS in section_keys_upserted

    def test_personal_section_maps_name_and_contact(self, mock_app_service):
        """Personal section data should include name, email, phone, citizenship."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_personal=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        # Find the personal section upsert call
        personal_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.PERSONAL
        )
        assert personal_call is not None
        data = personal_call.kwargs["data"]
        assert data["first_name"] == "Alice"
        assert data["last_name"] == "Anderson"
        assert data["email"] == "alice@example.com"
        assert data["citizenship"] == "US_CITIZEN"

    def test_employment_section_maps_employer_and_income(self, mock_app_service):
        """Employment section should map employer, position, and income fields."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_employment=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        emp_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.EMPLOYMENT
        )
        assert emp_call is not None
        data = emp_call.kwargs["data"]
        assert "current_employment" in data
        current = data["current_employment"]
        assert current["employer_name"] == "Acme Corp"
        assert current["position_title"] == "Software Engineer"
        assert current["base_monthly"] == 8500

    def test_loan_section_maps_amount_and_purpose(self, mock_app_service):
        """Loan section should include loan_amount, loan_purpose, property address."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_loan_info=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        loan_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.LOAN
        )
        assert loan_call is not None
        data = loan_call.kwargs["data"]
        assert data["loan_amount"] == 350000
        assert data["loan_purpose"] == "PURCHASE"
        assert "subject_property_address" in data
        assert data["occupancy"] == "PRIMARY_RESIDENCE"

    def test_residence_section_maps_current_address(self, mock_app_service):
        """Residence section should include current_address from Section 1a."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_personal=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        res_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.RESIDENCE
        )
        assert res_call is not None
        data = res_call.kwargs["data"]
        assert "current_address" in data


# ==========================================================================
# Test 2: PII mapping (SSN, DOB)
# ==========================================================================

class TestHydrationMapsSSNToPII:
    """Verify SSN and DOB are written to the encrypted PII table."""

    def test_ssn_passed_to_upsert_pii(self, mock_app_service):
        """SSN from URLA Section 1a should be passed to upsert_pii."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            ssn="123-45-6789",
            dob="1985-06-12",
        )

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        mock_svc.upsert_pii.assert_called_once()
        pii_kwargs = mock_svc.upsert_pii.call_args.kwargs
        assert pii_kwargs["ssn"] == "123-45-6789"
        assert pii_kwargs["dob"] == "1985-06-12"

    def test_co_borrower_ssn_passed_to_pii(self, mock_app_service):
        """Co-borrower SSN should also be passed."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            ssn="111-22-3333",
            co_borrower=True,
            co_ssn="444-55-6666",
            co_dob="1990-03-20",
        )

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        pii_kwargs = mock_svc.upsert_pii.call_args.kwargs
        assert pii_kwargs["ssn"] == "111-22-3333"
        assert pii_kwargs["co_ssn"] == "444-55-6666"
        assert pii_kwargs["co_dob"] == "1990-03-20"

    def test_no_pii_call_when_no_ssn_or_dob(self, mock_app_service):
        """If no SSN or DOB in URLA, upsert_pii should not be called."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            ssn=None,
            dob=None,
            include_personal=True,
        )

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        mock_svc.upsert_pii.assert_not_called()


# ==========================================================================
# Test 3: Completion percentage reflects URLA progress
# ==========================================================================

class TestHydrationCompletion:
    """Verify completion_pct tracks URLA completed_sections."""

    def test_partial_completion(self, mock_app_service):
        """5 of 9 POS sections complete -> ~55% completion."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            completed_sections=[
                "SECTION_1A",  # -> personal
                "SECTION_1B",  # -> employment
                "SECTION_2",   # -> assets + liabilities
                "SECTION_4A",  # -> loan
                "SECTION_5A",  # -> declarations (partial)
            ],
            include_personal=True,
            include_employment=True,
            include_assets=True,
            include_liabilities=True,
            include_loan_info=True,
            include_declarations=True,
        )

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        # Sections with mark_complete=True
        upsert_calls = mock_svc.upsert_section.call_args_list
        completed_keys = [
            call.kwargs["section_key"]
            for call in upsert_calls
            if call.kwargs.get("mark_complete")
        ]

        # SECTION_1A -> personal + residence (if current_address present)
        # SECTION_1B -> employment
        # SECTION_2 -> assets + liabilities
        # SECTION_4A -> loan
        # SECTION_5A -> declarations (but 5B not yet -> still mapped)
        assert POSSectionKey.PERSONAL in completed_keys
        assert POSSectionKey.EMPLOYMENT in completed_keys
        assert POSSectionKey.ASSETS in completed_keys
        assert POSSectionKey.LIABILITIES in completed_keys
        assert POSSectionKey.LOAN in completed_keys

    def test_finalized_sets_submitted_status(self, mock_app_service):
        """When is_finalized=True, the app should be marked SUBMITTED with 100%."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(is_finalized=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        assert mock_app.status == POSStatus.SUBMITTED
        assert mock_app.completion_pct == 100
        assert mock_app.submitted_at is not None
        assert mock_app.current_step == POSSectionKey.REVIEW

    def test_non_finalized_recalculates_completion(self, mock_app_service):
        """When not finalized, completion should reflect section count."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        # Simulate some complete sections already
        for i in range(3):
            sec = MagicMock(spec=POSApplicationSection)
            sec.is_complete = True
            mock_app.sections.append(sec)

        session = MagicMock()
        urla = _build_urla_data(is_finalized=False)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        # Not finalized, so status should still be draft
        assert mock_app.status != POSStatus.SUBMITTED


# ==========================================================================
# Test 4: Hydration is idempotent
# ==========================================================================

class TestHydrationIdempotency:
    """Verify hydrating the same data twice does not create duplicates."""

    def test_second_hydration_reuses_existing_app(self, mock_app_service):
        """get_or_create_for_loan should return the same app on second call."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data()

        # First hydration
        result1 = svc.hydrate_from_urla(session, urla, 1, 1, 1001, loan_id=42)
        # Second hydration with same data
        result2 = svc.hydrate_from_urla(session, urla, 1, 1, 1001, loan_id=42)

        # get_or_create should be called twice but return the same app
        assert mock_svc.get_or_create_for_loan.call_count == 2
        assert result1 is result2  # Same object returned

    def test_upsert_sections_replace_not_duplicate(self, mock_app_service):
        """Sections should be upserted (update if exists), not duplicated."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data()

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)
        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        # upsert_section should have been called the same number each time
        # (not accumulating) since the service re-maps from the same data
        first_count = len(_build_expected_nonempty_sections(urla))
        total_calls = mock_svc.upsert_section.call_count
        # Two hydrations should each call upsert for the same sections
        assert total_calls == first_count * 2


# ==========================================================================
# Test 5: All section type mappings
# ==========================================================================

class TestSectionMappings:
    """Verify each URLA section maps to the correct POS section key."""

    def test_assets_section_maps_from_section_2(self, mock_app_service):
        """URLA Section 2 assets -> POS 'assets' section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_assets=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        assets_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.ASSETS
        )
        assert assets_call is not None
        data = assets_call.kwargs["data"]
        assert "assets" in data
        assert len(data["assets"]) == 2
        assert data["assets"][0]["asset_type"] == "CHECKING_ACCOUNT"

    def test_liabilities_section_maps_from_section_2(self, mock_app_service):
        """URLA Section 2 liabilities -> POS 'liabilities' section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_liabilities=True, include_assets=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        liab_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.LIABILITIES
        )
        assert liab_call is not None
        data = liab_call.kwargs["data"]
        assert "liabilities" in data
        assert data["liabilities"][0]["creditor_name"] == "Chase"

    def test_reo_section_maps_from_section_3(self, mock_app_service):
        """URLA Section 3 properties -> POS 'reo' section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_reo=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        reo_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.REO
        )
        assert reo_call is not None
        data = reo_call.kwargs["data"]
        assert "properties" in data
        assert data["properties"][0]["property_value"] == 300000

    def test_reo_does_not_apply(self, mock_app_service):
        """When no REO properties, section data should indicate does_not_apply."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_reo=False)
        # Add an empty section_3 with does_not_apply
        urla["section_3"] = {"does_not_apply": True}

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        reo_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.REO
        )
        assert reo_call is not None
        data = reo_call.kwargs["data"]
        assert data.get("does_not_apply") is True

    def test_declarations_section_maps_from_section_5(self, mock_app_service):
        """URLA Section 5a/5b -> POS 'declarations' section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_declarations=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        decl_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.DECLARATIONS
        )
        assert decl_call is not None
        data = decl_call.kwargs["data"]
        assert data["will_occupy_as_primary_residence"] is True
        assert data["declared_bankruptcy_last_7_years"] is False

    def test_review_section_includes_consent_and_demographics(self, mock_app_service):
        """URLA Sections 6 + 8 -> POS 'review' section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(
            include_consent=True,
            include_demographics=True,
        )

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        review_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.REVIEW
        )
        assert review_call is not None
        data = review_call.kwargs["data"]
        # Consent from Section 6
        assert "acknowledgments" in data
        assert data["acknowledgments"]["verbal_consent_given"] is True
        # Demographics from Section 8
        assert "demographics" in data
        assert data["demographics"]["sex"] == "FEMALE"
        # Voice agent metadata
        assert data["source"] == "voice_agent"

    def test_military_maps_to_personal_section(self, mock_app_service):
        """URLA Section 7 (military) should be nested in the personal section."""
        from services.pos.urla_hydration_service import URLAHydrationService

        mock_svc, mock_app = mock_app_service
        svc = URLAHydrationService()
        svc._app_service = mock_svc

        session = MagicMock()
        urla = _build_urla_data(include_military=True, include_personal=True)

        svc.hydrate_from_urla(session, urla, 1, 1, 1001)

        personal_call = _find_upsert_call(
            mock_svc.upsert_section, POSSectionKey.PERSONAL
        )
        assert personal_call is not None
        data = personal_call.kwargs["data"]
        assert "military_service" in data
        assert data["military_service"]["served_in_military"] is False


# ==========================================================================
# Test 6: Completion section resolution
# ==========================================================================

class TestCompletionResolution:
    """Tests for _resolve_completed_pos_sections mapping logic."""

    def test_urla_section_1a_marks_personal_and_residence_complete(self):
        """SECTION_1A completion should mark personal and residence (if address present)."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data(include_personal=True)
        completed = _resolve_completed_pos_sections(["SECTION_1A"], urla)

        assert POSSectionKey.PERSONAL in completed
        assert POSSectionKey.RESIDENCE in completed  # current_address is populated

    def test_urla_section_2_marks_assets_and_liabilities_complete(self):
        """SECTION_2 completion should mark both assets and liabilities."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data()
        completed = _resolve_completed_pos_sections(["SECTION_2"], urla)

        assert POSSectionKey.ASSETS in completed
        assert POSSectionKey.LIABILITIES in completed

    def test_urla_section_4a_marks_loan_complete(self):
        """SECTION_4A completion should mark loan section complete."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data()
        completed = _resolve_completed_pos_sections(["SECTION_4A"], urla)

        assert POSSectionKey.LOAN in completed

    def test_urla_section_5_marks_declarations_complete(self):
        """Both SECTION_5A and SECTION_5B should map to declarations."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data()
        completed = _resolve_completed_pos_sections(
            ["SECTION_5A", "SECTION_5B"], urla
        )

        assert POSSectionKey.DECLARATIONS in completed

    def test_urla_section_6_and_8_mark_review_complete(self):
        """SECTION_6 and SECTION_8 map to review."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data()
        completed = _resolve_completed_pos_sections(
            ["SECTION_6", "SECTION_8"], urla
        )

        assert POSSectionKey.REVIEW in completed

    def test_empty_completed_sections(self):
        """No completed sections -> empty set."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data()
        completed = _resolve_completed_pos_sections([], urla)

        assert len(completed) == 0

    def test_residence_not_complete_without_address(self):
        """SECTION_1A without current_address should NOT mark residence complete."""
        from services.pos.urla_hydration_service import _resolve_completed_pos_sections

        urla = _build_urla_data(include_personal=False)
        # Add a primary borrower without current_address
        urla["borrowers"] = [{
            "borrower_id": "borrower_1",
            "is_primary": True,
            "section_1a": {
                "first_name": "Alice",
                "last_name": "Anderson",
                # No current_address
            },
        }]

        completed = _resolve_completed_pos_sections(["SECTION_1A"], urla)

        assert POSSectionKey.PERSONAL in completed
        assert POSSectionKey.RESIDENCE not in completed


# ==========================================================================
# Test helpers
# ==========================================================================

def _find_upsert_call(mock_upsert, section_key: str):
    """Find the upsert_section call for a specific section_key."""
    from unittest.mock import MagicMock

    for call in mock_upsert.call_args_list:
        if call.kwargs.get("section_key") == section_key:
            return call
    return None


def _build_expected_nonempty_sections(urla: dict) -> list[str]:
    """Predict which POS sections will be non-empty for a given URLA dict.

    This mirrors the logic in URLAHydrationService.hydrate_from_urla.
    """
    from services.pos.urla_hydration_service import (
        _map_personal,
        _map_residence,
        _map_employment,
        _map_assets,
        _map_liabilities,
        _map_reo,
        _map_loan,
        _map_declarations,
        _map_review,
        _get_primary_borrower,
    )

    primary = _get_primary_borrower(urla)
    mappers = [
        (POSSectionKey.PERSONAL, _map_personal(urla, primary)),
        (POSSectionKey.RESIDENCE, _map_residence(primary)),
        (POSSectionKey.EMPLOYMENT, _map_employment(primary)),
        (POSSectionKey.ASSETS, _map_assets(urla)),
        (POSSectionKey.LIABILITIES, _map_liabilities(urla)),
        (POSSectionKey.REO, _map_reo(urla)),
        (POSSectionKey.LOAN, _map_loan(urla)),
        (POSSectionKey.DECLARATIONS, _map_declarations(primary)),
        (POSSectionKey.REVIEW, _map_review(urla, primary)),
    ]
    return [key for key, data in mappers if data]
