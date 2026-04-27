"""
URLA -> POS Hydration Service
=============================
Maps URLAApplication (Redis / voice agent) data into the POS PostgreSQL tables
(pos_applications, pos_application_sections, pos_application_pii) so that
borrower-collected data appears in the self-service portal and CRM.

Called after the URLA voice agent finalizes and pushes to BytePro.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from database.models.pos import (
    POSApplication,
    POSApplicationSection,
    POSSectionKey,
    POSStatus,
    calculate_completion_pct,
)
from services.pos.application_service import (
    ApplicationService,
    AuditContext,
)

logger = logging.getLogger("pos.urla_hydration")


# ---------------------------------------------------------------------------
# Section mappers — one per POS section key
# ---------------------------------------------------------------------------

def _map_personal(urla: dict, primary: dict | None) -> dict[str, Any]:
    """Map URLA Section 1a -> POS 'personal' section."""
    if not primary:
        return {}
    s1a = primary.get("section_1a") or {}
    data: dict[str, Any] = {}

    if s1a.get("first_name"):
        data["first_name"] = s1a["first_name"]
    if s1a.get("middle_name"):
        data["middle_name"] = s1a["middle_name"]
    if s1a.get("last_name"):
        data["last_name"] = s1a["last_name"]
    if s1a.get("suffix"):
        data["suffix"] = s1a["suffix"]
    if s1a.get("alternate_names"):
        data["alternate_names"] = s1a["alternate_names"]

    if s1a.get("email"):
        data["email"] = s1a["email"]
    if s1a.get("home_phone"):
        data["home_phone"] = s1a["home_phone"]
    if s1a.get("cell_phone"):
        data["cell_phone"] = s1a["cell_phone"]
    if s1a.get("work_phone"):
        data["work_phone"] = s1a["work_phone"]

    if s1a.get("citizenship"):
        data["citizenship"] = s1a["citizenship"]
    if s1a.get("marital_status"):
        data["marital_status"] = s1a["marital_status"]

    if s1a.get("dependents_count") is not None:
        data["dependents_count"] = s1a["dependents_count"]
    if s1a.get("dependents_ages"):
        data["dependents_ages"] = s1a["dependents_ages"]

    if s1a.get("mailing_address_same_as_current") is not None:
        data["mailing_address_same_as_current"] = s1a["mailing_address_same_as_current"]
    if s1a.get("mailing_address"):
        data["mailing_address"] = s1a["mailing_address"]

    # Military service (Section 7) maps here as well — it's personal info
    s7 = primary.get("section_7") or {}
    if s7:
        mil: dict[str, Any] = {}
        for key in (
            "served_in_military", "currently_active_duty",
            "retired_discharged_separated", "non_activated_reserve_national_guard",
            "surviving_spouse", "expiration_of_active_duty",
        ):
            if s7.get(key) is not None:
                mil[key] = s7[key]
        if mil:
            data["military_service"] = mil

    return data


def _map_residence(primary: dict | None) -> dict[str, Any]:
    """Map URLA Section 1a residence history -> POS 'residence' section."""
    if not primary:
        return {}
    s1a = primary.get("section_1a") or {}
    data: dict[str, Any] = {}

    if s1a.get("current_address"):
        data["current_address"] = s1a["current_address"]
    if s1a.get("prior_addresses"):
        data["prior_addresses"] = s1a["prior_addresses"]

    return data


def _map_employment(primary: dict | None) -> dict[str, Any]:
    """Map URLA Sections 1b/1c/1d/1e -> POS 'employment' section."""
    if not primary:
        return {}
    data: dict[str, Any] = {}

    # Current employment (1b)
    s1b = primary.get("section_1b") or {}
    if s1b:
        current: dict[str, Any] = {}
        for key in (
            "does_not_apply", "employer_name", "employer_address", "employer_phone",
            "position_title", "start_date", "years_in_profession",
            "self_employed", "self_employment_ownership_share_ge_25",
            "self_employment_monthly_income_loss",
            "base_monthly", "overtime_monthly", "bonus_monthly",
            "commission_monthly", "military_entitlements_monthly", "other_monthly",
            "employed_by_family_or_party_to_transaction",
        ):
            if s1b.get(key) is not None:
                current[key] = s1b[key]
        if current:
            data["current_employment"] = current

    # Additional employment (1c)
    s1c = primary.get("section_1c") or {}
    employments = s1c.get("employments") or []
    if employments:
        data["additional_employments"] = employments

    # Previous employment (1d)
    s1d = primary.get("section_1d") or {}
    if s1d and not s1d.get("does_not_apply"):
        prev: dict[str, Any] = {}
        for key in (
            "employer_name", "employer_address", "position_title",
            "start_date", "end_date", "self_employed",
            "previous_gross_monthly_income",
        ):
            if s1d.get(key) is not None:
                prev[key] = s1d[key]
        if prev:
            data["previous_employment"] = prev

    # Other income (1e)
    s1e = primary.get("section_1e") or {}
    if s1e and not s1e.get("does_not_apply"):
        sources = s1e.get("sources") or []
        if sources:
            data["other_income_sources"] = sources

    return data


def _map_assets(urla: dict) -> dict[str, Any]:
    """Map URLA Section 2 (assets + other credits) -> POS 'assets' section."""
    s2 = urla.get("section_2") or {}
    data: dict[str, Any] = {}

    assets = s2.get("assets") or []
    if assets:
        data["assets"] = assets

    other_credits = s2.get("other_credits") or []
    if other_credits:
        data["other_credits"] = other_credits

    return data


def _map_liabilities(urla: dict) -> dict[str, Any]:
    """Map URLA Section 2 (liabilities + other liabilities) -> POS 'liabilities' section."""
    s2 = urla.get("section_2") or {}
    data: dict[str, Any] = {}

    liabilities = s2.get("liabilities") or []
    if liabilities:
        data["liabilities"] = liabilities

    other_liabilities = s2.get("other_liabilities") or []
    if other_liabilities:
        data["other_liabilities"] = other_liabilities

    return data


def _map_reo(urla: dict) -> dict[str, Any]:
    """Map URLA Section 3 -> POS 'reo' section."""
    s3 = urla.get("section_3") or {}
    data: dict[str, Any] = {}

    if s3.get("does_not_apply"):
        data["does_not_apply"] = True
        return data

    properties = s3.get("properties") or []
    if properties:
        data["properties"] = properties

    return data


def _map_loan(urla: dict) -> dict[str, Any]:
    """Map URLA Section 4 -> POS 'loan' section."""
    s4 = urla.get("section_4") or {}
    data: dict[str, Any] = {}

    # 4a — Loan and property info
    s4a = s4.get("section_4a") or {}
    for key in (
        "loan_amount", "loan_purpose", "loan_purpose_other_description",
        "subject_property_address", "number_of_units", "property_value",
        "occupancy", "fha_secondary_residence", "mixed_use_property",
        "manufactured_home",
    ):
        if s4a.get(key) is not None:
            data[key] = s4a[key]

    # 4b — Other new mortgages
    s4b = s4.get("section_4b") or {}
    if s4b and not s4b.get("does_not_apply"):
        other_mortgage: dict[str, Any] = {}
        for key in (
            "creditor_name", "lien_type", "monthly_payment",
            "loan_amount", "credit_limit",
        ):
            if s4b.get(key) is not None:
                other_mortgage[key] = s4b[key]
        if other_mortgage:
            data["other_new_mortgage"] = other_mortgage

    # 4c — Rental income on subject
    s4c = s4.get("section_4c") or {}
    if s4c and not s4c.get("does_not_apply"):
        rental: dict[str, Any] = {}
        for key in ("expected_monthly_rental_income", "expected_net_monthly_rental_income"):
            if s4c.get(key) is not None:
                rental[key] = s4c[key]
        if rental:
            data["rental_income"] = rental

    # 4d — Gifts or grants
    s4d = s4.get("section_4d") or {}
    if s4d and not s4d.get("does_not_apply"):
        gifts = s4d.get("gifts") or []
        if gifts:
            data["gifts"] = gifts

    return data


def _map_declarations(primary: dict | None) -> dict[str, Any]:
    """Map URLA Section 5 -> POS 'declarations' section."""
    if not primary:
        return {}
    s5 = primary.get("section_5") or {}
    data: dict[str, Any] = {}

    # 5a — Property and money declarations
    s5a = s5.get("section_5a") or {}
    for key in (
        "will_occupy_as_primary_residence", "had_ownership_interest_last_3_years",
        "property_type_last_3_years", "how_held_title_last_3_years",
        "family_business_relationship_with_seller", "borrowing_money_for_transaction",
        "borrowed_amount", "applying_for_other_mortgage_before_closing",
        "applying_for_new_credit_before_closing", "property_subject_to_lien",
    ):
        if s5a.get(key) is not None:
            data[key] = s5a[key]

    # 5b — Financial declarations
    s5b = s5.get("section_5b") or {}
    for key in (
        "co_signer_on_undisclosed_debt", "outstanding_judgments",
        "currently_delinquent_on_federal_debt", "party_to_lawsuit",
        "conveyed_title_in_lieu_of_foreclosure_last_7_years",
        "short_sale_or_pre_foreclosure_last_7_years",
        "foreclosed_last_7_years", "declared_bankruptcy_last_7_years",
        "bankruptcy_types",
    ):
        if s5b.get(key) is not None:
            data[key] = s5b[key]

    return data


def _map_review(urla: dict, primary: dict | None) -> dict[str, Any]:
    """Map URLA Section 6 (consent) + Section 8 (demographics) -> POS 'review' section."""
    data: dict[str, Any] = {}

    # Section 6 — Acknowledgments
    s6 = urla.get("section_6") or {}
    consent: dict[str, Any] = {}
    for key in (
        "verbal_consent_given", "verbal_consent_timestamp",
        "verbal_consent_recording_url",
        "privacy_notice_consent_given", "privacy_notice_consent_timestamp",
    ):
        if s6.get(key) is not None:
            consent[key] = s6[key]
    if consent:
        data["acknowledgments"] = consent

    # Section 8 — Demographics (HMDA)
    if primary:
        s8 = primary.get("section_8") or {}
        demographics: dict[str, Any] = {}
        for key in (
            "demographics_notice_read_at",
            "ethnicity", "ethnicity_hispanic_subcategory", "ethnicity_other_origin",
            "race", "race_asian_subcategory", "race_nhopi_subcategory", "race_other_origin",
            "sex", "was_demographic_info_provided_by_borrower",
            "was_collected_via_visual_observation_or_surname", "application_channel",
        ):
            if s8.get(key) is not None:
                demographics[key] = s8[key]
        if demographics:
            data["demographics"] = demographics

    # Voice agent metadata
    data["source"] = "voice_agent"
    data["voice_finalized_at"] = urla.get("finalized_at")
    data["bytepro_loan_number"] = urla.get("bytepro_loan_number")
    data["urla_loan_id"] = urla.get("loan_id")

    return data


# ---------------------------------------------------------------------------
# Section completion detection
# ---------------------------------------------------------------------------

# Map URLA completed_sections entries to POS section keys
_URLA_TO_POS_COMPLETION: dict[str, str] = {
    "SECTION_1A": POSSectionKey.PERSONAL,
    "SECTION_1B": POSSectionKey.EMPLOYMENT,
    "SECTION_1C": POSSectionKey.EMPLOYMENT,
    "SECTION_1D": POSSectionKey.EMPLOYMENT,
    "SECTION_1E": POSSectionKey.EMPLOYMENT,
    "SECTION_2": POSSectionKey.ASSETS,  # Also maps to liabilities
    "SECTION_3": POSSectionKey.REO,
    "SECTION_4A": POSSectionKey.LOAN,
    "SECTION_4B": POSSectionKey.LOAN,
    "SECTION_4C": POSSectionKey.LOAN,
    "SECTION_4D": POSSectionKey.LOAN,
    "SECTION_5A": POSSectionKey.DECLARATIONS,
    "SECTION_5B": POSSectionKey.DECLARATIONS,
    "SECTION_7": POSSectionKey.PERSONAL,
    "SECTION_8": POSSectionKey.REVIEW,
    "SECTION_6": POSSectionKey.REVIEW,
}

# These URLA sections also mark liabilities complete (Section 2 covers both)
_URLA_LIABILITIES_TRIGGERS = {"SECTION_2"}

# Residence is complete when Section 1a has current_address
# (no dedicated URLA section for residence alone)


def _resolve_completed_pos_sections(
    urla_completed: list[str],
    urla_data: dict,
) -> set[str]:
    """Determine which POS sections should be marked complete."""
    completed: set[str] = set()

    for urla_section in urla_completed:
        pos_key = _URLA_TO_POS_COMPLETION.get(urla_section)
        if pos_key:
            completed.add(pos_key)
        if urla_section in _URLA_LIABILITIES_TRIGGERS:
            completed.add(POSSectionKey.LIABILITIES)

    # Residence: mark complete if current_address is populated and SECTION_1A done
    if "SECTION_1A" in urla_completed:
        primary = _get_primary_borrower(urla_data)
        s1a = (primary or {}).get("section_1a") or {}
        if s1a.get("current_address"):
            completed.add(POSSectionKey.RESIDENCE)

    return completed


def _get_primary_borrower(urla_data: dict) -> dict | None:
    """Extract the primary borrower dict from serialized URLAApplication."""
    borrowers = urla_data.get("borrowers") or []
    for b in borrowers:
        if b.get("is_primary"):
            return b
    return borrowers[0] if borrowers else None


def _get_co_borrower(urla_data: dict) -> dict | None:
    """Extract the first co-borrower dict (if any)."""
    borrowers = urla_data.get("borrowers") or []
    for b in borrowers:
        if not b.get("is_primary"):
            return b
    return None


# ---------------------------------------------------------------------------
# Main hydration service
# ---------------------------------------------------------------------------


class URLAHydrationService:
    """Maps URLA voice agent data to POS PostgreSQL tables."""

    def __init__(self) -> None:
        self._app_service = ApplicationService()

    def hydrate_from_urla(
        self,
        session: Session,
        urla_data: dict[str, Any],
        organization_id: int,
        workspace_id: int,
        contact_id: int,
        loan_id: int | None = None,
        urla_loan_id: str | None = None,
    ) -> POSApplication:
        """
        Create or update a POSApplication from URLA voice data.

        - Creates POSApplication if none exists for this contact+loan
        - Upserts all sections with mapped data
        - Writes PII (SSN, DOB) to pos_application_pii with encryption
        - Marks sections as complete based on URLA completed_sections
        - Returns the POSApplication

        Args:
            session: SQLAlchemy sync session
            urla_data: URLAApplication.model_dump() dict
            organization_id: CRM organization ID
            workspace_id: CRM workspace ID
            contact_id: Lead/Contact ID in the CRM
            loan_id: Optional CRM loan ID to link
            urla_loan_id: Optional URLA loan identifier for source_channel tagging
        """
        ctx = AuditContext(
            actor_type="system",
            actor_id=None,
            ip_address=None,
            user_agent="urla-voice-agent/hydration",
        )

        # Build source_channel with urla_loan_id for idempotency checks
        source_channel = f"voice:{urla_loan_id}" if urla_loan_id else "voice_agent"

        # 1. Get or create the POS application
        app = self._app_service.get_or_create_for_loan(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            contact_id=contact_id,
            loan_id=loan_id,
            source_channel=source_channel,
            ctx=ctx,
        )

        primary = _get_primary_borrower(urla_data)
        co_borrower = _get_co_borrower(urla_data)
        completed_urla_sections = urla_data.get("completed_sections") or []
        completed_pos_sections = _resolve_completed_pos_sections(
            completed_urla_sections, urla_data,
        )

        # 2. Map and upsert each section
        section_mappers: list[tuple[str, dict[str, Any]]] = [
            (POSSectionKey.PERSONAL, _map_personal(urla_data, primary)),
            (POSSectionKey.RESIDENCE, _map_residence(primary)),
            (POSSectionKey.EMPLOYMENT, _map_employment(primary)),
            (POSSectionKey.ASSETS, _map_assets(urla_data)),
            (POSSectionKey.LIABILITIES, _map_liabilities(urla_data)),
            (POSSectionKey.REO, _map_reo(urla_data)),
            (POSSectionKey.LOAN, _map_loan(urla_data)),
            (POSSectionKey.DECLARATIONS, _map_declarations(primary)),
            (POSSectionKey.REVIEW, _map_review(urla_data, primary)),
        ]

        for section_key, data in section_mappers:
            if not data:
                continue
            is_complete = section_key in completed_pos_sections
            self._app_service.upsert_section(
                session,
                application=app,
                section_key=section_key,
                data=data,
                mark_complete=is_complete,
                ctx=ctx,
            )

        # 3. Write PII (SSN, DOB) to the encrypted PII table
        pii_kwargs: dict[str, Any] = {}

        if primary:
            s1a = primary.get("section_1a") or {}
            if s1a.get("ssn"):
                pii_kwargs["ssn"] = s1a["ssn"]
            if s1a.get("date_of_birth"):
                pii_kwargs["dob"] = s1a["date_of_birth"]

        if co_borrower:
            co_s1a = co_borrower.get("section_1a") or {}
            if co_s1a.get("ssn"):
                pii_kwargs["co_ssn"] = co_s1a["ssn"]
            if co_s1a.get("date_of_birth"):
                pii_kwargs["co_dob"] = co_s1a["date_of_birth"]

        if pii_kwargs:
            self._app_service.upsert_pii(
                session,
                application=app,
                **pii_kwargs,
            )

        # 4. Update application status metadata
        if urla_data.get("is_finalized"):
            # Voice application is complete — set status to submitted
            app.status = POSStatus.SUBMITTED
            app.submitted_at = datetime.now(timezone.utc)
            app.completion_pct = 100
            app.current_step = POSSectionKey.REVIEW
        else:
            # Partial hydration — recalculate completion
            complete_count = sum(1 for s in app.sections if s.is_complete)
            app.completion_pct = calculate_completion_pct(complete_count)

        session.flush()

        logger.info(
            "POS hydrated from URLA voice data",
            extra={
                "pos_application_id": str(app.id),
                "urla_loan_id": urla_data.get("loan_id"),
                "contact_id": contact_id,
                "loan_id": loan_id,
                "sections_hydrated": len([d for _, d in section_mappers if d]),
                "pii_fields": len(pii_kwargs),
                "is_finalized": urla_data.get("is_finalized", False),
            },
        )

        return app
