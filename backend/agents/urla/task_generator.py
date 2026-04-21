"""
Perennia AI — URLA Task Auto-Generator
=======================================
Generates CRM tasks from a completed URLA voice agent session.

Task categories:
  - DOCUMENT_COLLECTION: Documents the LO needs to collect
  - VERIFICATION: Employment, asset, identity verification
  - FOLLOW_UP: Items flagged during the call
  - COMPLIANCE: Regulatory tasks (LE delivery, consent, etc.)
  - SCHEDULING: Calendar and communication tasks

Tasks are returned as structured objects ready to be pushed to the CRM
task API or inserted directly into the database.
"""
import logging
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import (
    AssetType,
    LiabilityType,
    LoanPurpose,
    LoanType,
    OtherIncomeType,
    PropertyOccupancy,
    URLAApplication,
    Borrower,
)

logger = logging.getLogger(__name__)


# =============================================================================
# TASK MODELS
# =============================================================================

class TaskPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskCategory(str, Enum):
    DOCUMENT_COLLECTION = "DOCUMENT_COLLECTION"
    VERIFICATION = "VERIFICATION"
    FOLLOW_UP = "FOLLOW_UP"
    COMPLIANCE = "COMPLIANCE"
    SCHEDULING = "SCHEDULING"


class URLATask(BaseModel):
    title: str
    description: str
    category: TaskCategory
    priority: TaskPriority
    due_in_business_days: int
    related_section: Optional[str] = None
    assigned_to_role: str = "loan_officer"  # or "processor", "closer"
    tags: List[str] = Field(default_factory=list)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _borrower_label(borrower: Borrower) -> str:
    """Short display name for a borrower, e.g. 'John Smith' or 'Co-borrower (borrower_2)'."""
    s1a = borrower.section_1a
    if s1a and s1a.first_name and s1a.last_name:
        return f"{s1a.first_name} {s1a.last_name}"
    return f"Co-borrower ({borrower.borrower_id})" if not borrower.is_primary else "Primary borrower"


def _has_self_employment(borrower: Borrower) -> bool:
    """True if the borrower reports self-employment in Section 1b or 1c."""
    if borrower.section_1b and borrower.section_1b.self_employed:
        return True
    if borrower.section_1c:
        for emp in borrower.section_1c.employments:
            if emp.self_employed:
                return True
    return False


def _has_w2_employment(borrower: Borrower) -> bool:
    """True if the borrower has W-2 (non-self-employed) employment."""
    if borrower.section_1b and not borrower.section_1b.does_not_apply and not borrower.section_1b.self_employed:
        return True
    if borrower.section_1c:
        for emp in borrower.section_1c.employments:
            if not emp.self_employed:
                return True
    return False


def _has_other_income(borrower: Borrower) -> bool:
    """True if the borrower reports other income sources in Section 1e."""
    if borrower.section_1e and not borrower.section_1e.does_not_apply and borrower.section_1e.sources:
        return True
    return False


def _has_alimony_child_support_income(borrower: Borrower) -> bool:
    """True if borrower receives alimony, child support, or separate maintenance income."""
    if not borrower.section_1e or not borrower.section_1e.sources:
        return False
    flagged = {OtherIncomeType.ALIMONY, OtherIncomeType.CHILD_SUPPORT, OtherIncomeType.SEPARATE_MAINTENANCE}
    return any(s.source_type in flagged for s in borrower.section_1e.sources)


def _has_alimony_child_support_liability(app: URLAApplication) -> bool:
    """True if Section 2d has alimony, child support, or separate maintenance obligations."""
    if not app.section_2 or not app.section_2.other_liabilities:
        return False
    flagged = {
        LiabilityType.ALIMONY,
        LiabilityType.CHILD_SUPPORT,
        LiabilityType.SEPARATE_MAINTENANCE,
    }
    # LiabilityType values are stored as strings due to use_enum_values=True
    flagged_values = {t.value if isinstance(t, LiabilityType) else t for t in flagged}
    return any(
        (ol.liability_type in flagged or ol.liability_type in flagged_values)
        for ol in app.section_2.other_liabilities
    )


def _is_renting(borrower: Borrower) -> bool:
    """True if borrower's current housing is 'RENT'."""
    if borrower.section_1a and borrower.section_1a.current_address:
        return borrower.section_1a.current_address.own_or_rent == "RENT"
    return False


def _has_military_service(borrower: Borrower) -> bool:
    """True if borrower has any military service flags set."""
    s7 = borrower.section_7
    if not s7:
        return False
    return bool(
        s7.served_in_military
        or s7.currently_active_duty
        or s7.retired_discharged_separated
        or s7.non_activated_reserve_national_guard
        or s7.surviving_spouse
    )


def _has_gifts_or_grants(app: URLAApplication) -> bool:
    """True if Section 4d contains any gifts or grants."""
    if not app.section_4 or not app.section_4.section_4d:
        return False
    s4d = app.section_4.section_4d
    return not s4d.does_not_apply and len(s4d.gifts) > 0


def _loan_purpose(app: URLAApplication) -> Optional[str]:
    """Return the loan purpose string, or None."""
    if app.section_4 and app.section_4.section_4a and app.section_4.section_4a.loan_purpose:
        purpose = app.section_4.section_4a.loan_purpose
        return purpose.value if hasattr(purpose, "value") else str(purpose)
    return None


def _loan_type_is_va(app: URLAApplication) -> bool:
    """Check all borrowers for military service (VA eligibility indicator)."""
    return any(_has_military_service(b) for b in app.borrowers)


def _occupancy(app: URLAApplication) -> Optional[str]:
    """Return the occupancy string, or None."""
    if app.section_4 and app.section_4.section_4a and app.section_4.section_4a.occupancy:
        occ = app.section_4.section_4a.occupancy
        return occ.value if hasattr(occ, "value") else str(occ)
    return None


def _property_address_short(app: URLAApplication) -> str:
    """Short property description for task titles."""
    if app.section_4 and app.section_4.section_4a and app.section_4.section_4a.subject_property_address:
        addr = app.section_4.section_4a.subject_property_address
        return f"{addr.street}, {addr.city}, {addr.state}"
    return "subject property"


def _bank_account_assets(app: URLAApplication) -> list:
    """Return assets that are bank/depository accounts."""
    if not app.section_2 or not app.section_2.assets:
        return []
    bank_types = {
        AssetType.CHECKING_ACCOUNT, AssetType.SAVINGS_ACCOUNT,
        AssetType.MONEY_MARKET, AssetType.CERTIFICATE_OF_DEPOSIT,
    }
    bank_type_values = {t.value for t in bank_types}
    return [
        a for a in app.section_2.assets
        if a.asset_type in bank_types or a.asset_type in bank_type_values
    ]


def _all_employers(borrower: Borrower) -> list:
    """Collect all employer records for a borrower (current + additional)."""
    employers = []
    if borrower.section_1b and not borrower.section_1b.does_not_apply:
        employers.append(borrower.section_1b)
    if borrower.section_1c:
        employers.extend(borrower.section_1c.employments)
    return employers


# =============================================================================
# TASK GENERATORS BY CATEGORY
# =============================================================================

def _generate_document_collection_tasks(app: URLAApplication) -> List[URLATask]:
    """Generate document collection tasks based on application data."""
    tasks: List[URLATask] = []

    # --- Photo ID (always) ---
    tasks.append(URLATask(
        title="Collect photo ID",
        description="Obtain a copy of a valid government-issued photo ID (driver's license or passport) for each borrower.",
        category=TaskCategory.DOCUMENT_COLLECTION,
        priority=TaskPriority.HIGH,
        due_in_business_days=5,
        related_section="Section 1a",
        tags=["identity", "required"],
    ))

    for borrower in app.borrowers:
        label = _borrower_label(borrower)

        # --- Pay stubs (if W-2 employed) ---
        if _has_w2_employment(borrower):
            tasks.append(URLATask(
                title=f"Collect pay stubs — {label}",
                description=f"Request most recent 30 days of pay stubs from {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=5,
                related_section="Section 1b",
                tags=["income", "employment"],
            ))

        # --- W-2s (if W-2 employed) ---
        if _has_w2_employment(borrower):
            tasks.append(URLATask(
                title=f"Collect W-2s (last 2 years) — {label}",
                description=f"Request W-2 forms for the last 2 tax years from {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=7,
                related_section="Section 1b",
                tags=["income", "employment", "tax"],
            ))

        # --- Tax returns (if self-employed or other income) ---
        if _has_self_employment(borrower) or _has_other_income(borrower):
            tasks.append(URLATask(
                title=f"Collect tax returns (last 2 years) — {label}",
                description=f"Request complete personal tax returns (all schedules) for the last 2 tax years from {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=7,
                related_section="Section 1b/1e",
                tags=["income", "tax"],
            ))

        # --- Self-employed: profit/loss and business returns ---
        if _has_self_employment(borrower):
            tasks.append(URLATask(
                title=f"Collect YTD profit & loss statement — {label}",
                description=f"Request a year-to-date profit and loss statement (prepared and signed) from {label}'s business.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=7,
                related_section="Section 1b",
                tags=["income", "self-employed"],
            ))
            tasks.append(URLATask(
                title=f"Collect business tax returns (last 2 years) — {label}",
                description=f"Request complete business tax returns for the last 2 tax years from {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=7,
                related_section="Section 1b",
                tags=["income", "self-employed", "tax"],
            ))

        # --- VA Certificate of Eligibility ---
        if _has_military_service(borrower):
            tasks.append(URLATask(
                title=f"Obtain VA Certificate of Eligibility — {label}",
                description=f"Request COE from VA or obtain via WebLGY for {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=5,
                related_section="Section 7",
                tags=["va", "military", "eligibility"],
            ))
            tasks.append(URLATask(
                title=f"Collect DD-214 — {label}",
                description=f"Request DD-214 (Certificate of Release or Discharge from Active Duty) from {label}.",
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=5,
                related_section="Section 7",
                tags=["va", "military"],
            ))

        # --- Divorce decree (if alimony/child support obligations) ---
        if _has_alimony_child_support_income(borrower) or _has_alimony_child_support_liability(app):
            tasks.append(URLATask(
                title=f"Collect divorce decree / separation agreement — {label}",
                description=(
                    f"Obtain the complete divorce decree or separation agreement for {label}. "
                    "Needed to verify alimony, child support, or separate maintenance obligations and income."
                ),
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.MEDIUM,
                due_in_business_days=7,
                related_section="Section 1e / Section 2d",
                tags=["legal", "alimony", "child-support"],
            ))

        # --- Landlord contact (if renting) ---
        if _is_renting(borrower) and borrower.is_primary:
            tasks.append(URLATask(
                title="Collect landlord contact information",
                description=(
                    f"Obtain landlord name, phone, and address for {label}'s current rental. "
                    "Needed for verification of rent history."
                ),
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.LOW,
                due_in_business_days=7,
                related_section="Section 1a",
                tags=["housing", "rental"],
            ))

    # --- Bank statements (for each depository asset) ---
    bank_accounts = _bank_account_assets(app)
    if bank_accounts:
        for i, asset in enumerate(bank_accounts, 1):
            institution = asset.financial_institution or f"Account #{i}"
            acct_suffix = f" (****{asset.account_number_last_4})" if asset.account_number_last_4 else ""
            tasks.append(URLATask(
                title=f"Collect bank statements — {institution}{acct_suffix}",
                description=(
                    f"Request the last 2 months of bank statements for {institution}{acct_suffix}. "
                    "All pages required, including any pages with no transactions."
                ),
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=5,
                related_section="Section 2a",
                tags=["assets", "bank-statements"],
            ))
    else:
        # Fallback: no specific accounts listed but we always need bank statements
        tasks.append(URLATask(
            title="Collect bank statements (last 2 months)",
            description="Request 2 months of statements for all checking and savings accounts. All pages required.",
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.HIGH,
            due_in_business_days=5,
            related_section="Section 2a",
            tags=["assets", "bank-statements"],
        ))

    # --- Gift letter ---
    if _has_gifts_or_grants(app):
        tasks.append(URLATask(
            title="Collect gift letter",
            description=(
                "Obtain a signed gift letter for each gift/grant listed in Section 4d. "
                "Letter must state: donor name, relationship, amount, property address, and that no repayment is expected."
            ),
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.HIGH,
            due_in_business_days=5,
            related_section="Section 4d",
            tags=["gift", "down-payment"],
        ))

    # --- Bankruptcy discharge ---
    for borrower in app.borrowers:
        label = _borrower_label(borrower)
        s5b = None
        if borrower.section_5 and borrower.section_5.section_5b:
            s5b = borrower.section_5.section_5b
        if s5b and s5b.declared_bankruptcy_last_7_years:
            bk_types = ", ".join(s5b.bankruptcy_types) if s5b.bankruptcy_types else "type unknown"
            tasks.append(URLATask(
                title=f"Collect bankruptcy discharge papers — {label}",
                description=(
                    f"Obtain bankruptcy discharge documentation for {label} ({bk_types}). "
                    "Include petition, schedules, and discharge order."
                ),
                category=TaskCategory.DOCUMENT_COLLECTION,
                priority=TaskPriority.HIGH,
                due_in_business_days=5,
                related_section="Section 5b",
                tags=["credit", "bankruptcy", "legal"],
            ))

    # --- Refinance-specific documents ---
    purpose = _loan_purpose(app)
    if purpose == LoanPurpose.REFINANCE.value:
        tasks.append(URLATask(
            title="Collect current mortgage statement",
            description="Request the most recent mortgage statement for the property being refinanced.",
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.HIGH,
            due_in_business_days=5,
            related_section="Section 4a",
            tags=["refinance", "mortgage"],
        ))
        tasks.append(URLATask(
            title="Request payoff statement",
            description="Order payoff statement from current servicer for the existing mortgage on the subject property.",
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.HIGH,
            due_in_business_days=5,
            assigned_to_role="processor",
            related_section="Section 4a",
            tags=["refinance", "payoff"],
        ))

    # --- Investment property: rental agreement + management contact ---
    if _occupancy(app) == PropertyOccupancy.INVESTMENT.value:
        tasks.append(URLATask(
            title="Collect rental agreement — investment property",
            description=(
                f"Obtain current lease/rental agreement for {_property_address_short(app)}. "
                "If property is vacant, document expected rental income with market rent analysis."
            ),
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.MEDIUM,
            due_in_business_days=7,
            related_section="Section 4c",
            tags=["investment", "rental"],
        ))
        tasks.append(URLATask(
            title="Collect property management contact",
            description=f"Obtain property management company contact for {_property_address_short(app)} if applicable.",
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.LOW,
            due_in_business_days=7,
            related_section="Section 4c",
            tags=["investment", "property-management"],
        ))

    # --- FHA: HUD addendum ---
    # Note: URLA models don't have an explicit loan_type field on Section 4a,
    # but FHA secondary residence occupancy is a strong FHA signal.
    if app.section_4 and app.section_4.section_4a and app.section_4.section_4a.fha_secondary_residence:
        tasks.append(URLATask(
            title="Prepare FHA/HUD addendum",
            description="Complete and execute the HUD/FHA addendum to the URLA as required for FHA-insured loans.",
            category=TaskCategory.DOCUMENT_COLLECTION,
            priority=TaskPriority.HIGH,
            due_in_business_days=5,
            related_section="Section 4a",
            tags=["fha", "compliance"],
        ))

    return tasks


def _generate_verification_tasks(app: URLAApplication) -> List[URLATask]:
    """Generate verification tasks for employment, deposits, property."""
    tasks: List[URLATask] = []

    # --- Credit report pull (always) ---
    tasks.append(URLATask(
        title="Pull credit report",
        description="Order tri-merge credit report for all borrowers. Review tradelines, scores, and public records.",
        category=TaskCategory.VERIFICATION,
        priority=TaskPriority.HIGH,
        due_in_business_days=1,
        related_section="Section 2c",
        assigned_to_role="processor",
        tags=["credit", "required"],
    ))

    # --- VOE for each employer ---
    for borrower in app.borrowers:
        label = _borrower_label(borrower)
        for emp in _all_employers(borrower):
            if emp.does_not_apply:
                continue
            employer_name = emp.employer_name or "employer"
            tasks.append(URLATask(
                title=f"VOE — {employer_name} ({label})",
                description=(
                    f"Order Verification of Employment for {label} at {employer_name}. "
                    "Verify dates of employment, position, and income."
                ),
                category=TaskCategory.VERIFICATION,
                priority=TaskPriority.MEDIUM,
                due_in_business_days=7,
                related_section="Section 1b",
                assigned_to_role="processor",
                tags=["employment", "verification"],
            ))

    # --- VOD for each bank account ---
    bank_accounts = _bank_account_assets(app)
    for asset in bank_accounts:
        institution = asset.financial_institution or "financial institution"
        acct_suffix = f" (****{asset.account_number_last_4})" if asset.account_number_last_4 else ""
        tasks.append(URLATask(
            title=f"VOD — {institution}{acct_suffix}",
            description=(
                f"Order Verification of Deposit for {institution}{acct_suffix}. "
                "Verify account ownership, current balance, and average balance."
            ),
            category=TaskCategory.VERIFICATION,
            priority=TaskPriority.MEDIUM,
            due_in_business_days=7,
            related_section="Section 2a",
            assigned_to_role="processor",
            tags=["assets", "verification"],
        ))

    # --- Title search ---
    prop_addr = _property_address_short(app)
    tasks.append(URLATask(
        title=f"Order title search — {prop_addr}",
        description=f"Order title search and commitment for {prop_addr}. Review for liens, easements, and encumbrances.",
        category=TaskCategory.VERIFICATION,
        priority=TaskPriority.HIGH,
        due_in_business_days=7,
        related_section="Section 4a",
        assigned_to_role="processor",
        tags=["title", "property"],
    ))

    # --- Appraisal order ---
    tasks.append(URLATask(
        title=f"Order appraisal — {prop_addr}",
        description=f"Order property appraisal for {prop_addr}. Coordinate access with borrower/agent.",
        category=TaskCategory.VERIFICATION,
        priority=TaskPriority.HIGH,
        due_in_business_days=7,
        related_section="Section 4a",
        assigned_to_role="processor",
        tags=["appraisal", "property"],
    ))

    return tasks


def _generate_compliance_tasks(app: URLAApplication) -> List[URLATask]:
    """Generate regulatory compliance tasks."""
    tasks: List[URLATask] = []

    # --- Loan Estimate delivery (TRID 3-business-day rule) ---
    tasks.append(URLATask(
        title="Deliver Loan Estimate",
        description=(
            "Prepare and deliver the Loan Estimate (LE) to the borrower. "
            "TRID requires delivery within 3 business days of receiving the application. "
            f"Application received trigger: {'SET' if app.application_received_at else 'NOT YET SET — monitor for 6-piece completion'}."
        ),
        category=TaskCategory.COMPLIANCE,
        priority=TaskPriority.CRITICAL,
        due_in_business_days=3,
        related_section="TRID / Reg Z",
        tags=["trid", "loan-estimate", "critical-deadline"],
    ))

    # --- ECOA adverse action notice readiness ---
    tasks.append(URLATask(
        title="Send ECOA notice of action taken",
        description=(
            "Ensure Equal Credit Opportunity Act (Reg B) notice is prepared. "
            "If the application is denied or withdrawn, the adverse action notice must be "
            "delivered within 30 days. Queue template for processing."
        ),
        category=TaskCategory.COMPLIANCE,
        priority=TaskPriority.MEDIUM,
        due_in_business_days=5,
        related_section="Reg B / ECOA",
        tags=["ecoa", "compliance"],
    ))

    # --- Verbal consent archival ---
    recording_url = None
    if app.section_6 and app.section_6.verbal_consent_recording_url:
        recording_url = app.section_6.verbal_consent_recording_url
    tasks.append(URLATask(
        title="Archive verbal consent recording",
        description=(
            f"Link the verbal consent recording to the loan file. "
            f"Recording URL: {recording_url or 'NOT CAPTURED — escalate immediately'}. "
            "Ensure recording is stored per retention policy (minimum 3 years)."
        ),
        category=TaskCategory.COMPLIANCE,
        priority=TaskPriority.HIGH,
        due_in_business_days=1,
        related_section="Section 6",
        tags=["consent", "recording", "retention"],
    ))

    # --- HMDA data review ---
    hmda_complete = all(
        b.section_8 is not None for b in app.borrowers
    )
    tasks.append(URLATask(
        title="HMDA data completeness review",
        description=(
            f"Review demographic data (Section 8) for HMDA reporting completeness. "
            f"All borrowers provided demographics: {'Yes' if hmda_complete else 'No — follow up on missing responses'}. "
            "If information was not provided, document that the question was asked and the borrower declined."
        ),
        category=TaskCategory.COMPLIANCE,
        priority=TaskPriority.MEDIUM,
        due_in_business_days=3,
        related_section="Section 8 / HMDA",
        tags=["hmda", "demographics"],
    ))

    return tasks


def _generate_declaration_follow_up_tasks(app: URLAApplication) -> List[URLATask]:
    """Generate follow-up tasks based on yes answers in Section 5 declarations."""
    tasks: List[URLATask] = []

    for borrower in app.borrowers:
        label = _borrower_label(borrower)
        s5 = borrower.section_5
        if not s5:
            continue

        # --- Section 5a flags ---
        s5a = s5.section_5a
        if s5a:
            if s5a.borrowing_money_for_transaction:
                tasks.append(URLATask(
                    title=f"Investigate borrowed funds source — {label}",
                    description=(
                        f"{label} indicated they are borrowing money for this transaction. "
                        f"Borrowed amount: {s5a.borrowed_amount or 'not specified'}. "
                        "Determine source, terms, and impact on qualifying ratios. Document fully."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5a",
                    tags=["declarations", "borrowed-funds"],
                ))

            if s5a.property_subject_to_lien:
                tasks.append(URLATask(
                    title=f"Obtain lien details on subject property — {label}",
                    description=(
                        f"{label} indicated the property is subject to a lien. "
                        "Obtain lien documentation, determine lien type, amount, and priority. "
                        "Verify whether it will be paid off at closing."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5a",
                    tags=["declarations", "lien"],
                ))

            if s5a.family_business_relationship_with_seller:
                tasks.append(URLATask(
                    title=f"Document seller relationship — {label}",
                    description=(
                        f"{label} indicated a family or business relationship with the seller. "
                        "Document nature of relationship and disclose on the file. "
                        "Review for potential non-arm's-length transaction requirements."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.MEDIUM,
                    due_in_business_days=3,
                    related_section="Section 5a",
                    tags=["declarations", "identity-of-interest"],
                ))

            if s5a.applying_for_other_mortgage_before_closing:
                tasks.append(URLATask(
                    title=f"Review concurrent mortgage application — {label}",
                    description=(
                        f"{label} indicated they are applying for another mortgage before closing. "
                        "Obtain details on the other loan: lender, property, amount. "
                        "Assess impact on DTI and document."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5a",
                    tags=["declarations", "concurrent-loan"],
                ))

            if s5a.applying_for_new_credit_before_closing:
                tasks.append(URLATask(
                    title=f"Review new credit application — {label}",
                    description=(
                        f"{label} indicated they are applying for new credit before closing. "
                        "Counsel borrower on impact to credit score and qualifying ratios. "
                        "Document acknowledgment."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.MEDIUM,
                    due_in_business_days=3,
                    related_section="Section 5a",
                    tags=["declarations", "new-credit"],
                ))

        # --- Section 5b flags ---
        s5b = s5.section_5b
        if s5b:
            if s5b.outstanding_judgments:
                tasks.append(URLATask(
                    title=f"Obtain judgment documentation — {label}",
                    description=(
                        f"{label} disclosed outstanding judgments. "
                        "Obtain judgment documentation: court, amount, date, payment plan. "
                        "Determine if it must be satisfied prior to closing."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "judgments", "legal"],
                ))

            if s5b.currently_delinquent_on_federal_debt:
                tasks.append(URLATask(
                    title=f"Assess federal debt delinquency — {label}",
                    description=(
                        f"{label} disclosed delinquency on federal debt (student loans, taxes, SBA, etc.). "
                        "Determine the nature and status of the delinquency. "
                        "This may impact eligibility for FHA/VA/USDA programs. "
                        "Obtain payment history and any repayment agreement."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.CRITICAL,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "federal-debt", "eligibility"],
                ))

            if s5b.party_to_lawsuit:
                tasks.append(URLATask(
                    title=f"Review pending lawsuit — {label}",
                    description=(
                        f"{label} disclosed being a party to a lawsuit. "
                        "Obtain details: nature of suit, potential liability, status. "
                        "Assess impact on borrower's financial position."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "lawsuit", "legal"],
                ))

            if s5b.co_signer_on_undisclosed_debt:
                tasks.append(URLATask(
                    title=f"Investigate undisclosed co-signed debt — {label}",
                    description=(
                        f"{label} disclosed co-signing on undisclosed debt. "
                        "Obtain details on the co-signed obligation: creditor, balance, payment. "
                        "Include in DTI calculation."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "co-signer"],
                ))

            # --- Prior foreclosure / short sale / deed-in-lieu ---
            if s5b.foreclosed_last_7_years:
                tasks.append(URLATask(
                    title=f"Gather foreclosure documentation — {label}",
                    description=(
                        f"{label} disclosed a foreclosure within the last 7 years. "
                        "Obtain foreclosure date, lender, and property details. "
                        "Verify waiting period eligibility for current loan program."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "foreclosure", "credit-event"],
                ))

            if s5b.short_sale_or_pre_foreclosure_last_7_years:
                tasks.append(URLATask(
                    title=f"Gather short sale / pre-foreclosure documentation — {label}",
                    description=(
                        f"{label} disclosed a short sale or pre-foreclosure within the last 7 years. "
                        "Obtain closing statement or settlement documentation. "
                        "Verify waiting period eligibility for current loan program."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "short-sale", "credit-event"],
                ))

            if s5b.conveyed_title_in_lieu_of_foreclosure_last_7_years:
                tasks.append(URLATask(
                    title=f"Gather deed-in-lieu documentation — {label}",
                    description=(
                        f"{label} disclosed conveying title in lieu of foreclosure within the last 7 years. "
                        "Obtain deed-in-lieu agreement and settlement documentation. "
                        "Verify waiting period eligibility for current loan program."
                    ),
                    category=TaskCategory.FOLLOW_UP,
                    priority=TaskPriority.HIGH,
                    due_in_business_days=3,
                    related_section="Section 5b",
                    tags=["declarations", "deed-in-lieu", "credit-event"],
                ))

    return tasks


def _generate_scheduling_tasks(app: URLAApplication) -> List[URLATask]:
    """Generate scheduling and communication tasks."""
    tasks: List[URLATask] = []

    # --- LO kickoff call ---
    if not app.lo_kickoff_booking:
        primary = app.primary_borrower()
        borrower_name = _borrower_label(primary) if primary else "borrower"
        tasks.append(URLATask(
            title=f"Schedule LO kickoff call — {borrower_name}",
            description=(
                f"Schedule an introductory call with {borrower_name} to review the application, "
                "set expectations on the process and timeline, and address any immediate questions. "
                "Use Smart Calendar to book."
            ),
            category=TaskCategory.SCHEDULING,
            priority=TaskPriority.HIGH,
            due_in_business_days=1,
            related_section="Post-application",
            tags=["kickoff", "calendar"],
        ))

    # --- Processor assignment ---
    tasks.append(URLATask(
        title="Assign loan processor",
        description=(
            f"Assign a processor to loan {app.loan_id}. "
            "Review application complexity and processor workload for optimal assignment."
        ),
        category=TaskCategory.SCHEDULING,
        priority=TaskPriority.HIGH,
        due_in_business_days=1,
        related_section="Post-application",
        assigned_to_role="loan_officer",
        tags=["processor", "assignment"],
    ))

    return tasks


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def generate_urla_tasks(app: URLAApplication) -> List[URLATask]:
    """
    Generate all CRM tasks from a completed URLA voice agent session.

    Analyzes the application data across all sections and creates the same
    follow-up tasks a human supervisor would generate after reviewing a
    new loan application.

    Args:
        app: A completed (or substantially complete) URLAApplication.

    Returns:
        A list of URLATask objects, sorted by priority then due date.
    """
    tasks: List[URLATask] = []

    tasks.extend(_generate_document_collection_tasks(app))
    tasks.extend(_generate_verification_tasks(app))
    tasks.extend(_generate_compliance_tasks(app))
    tasks.extend(_generate_declaration_follow_up_tasks(app))
    tasks.extend(_generate_scheduling_tasks(app))

    # Sort: CRITICAL first, then HIGH, MEDIUM, LOW; within same priority, earlier due date first
    priority_order = {
        TaskPriority.CRITICAL: 0,
        TaskPriority.HIGH: 1,
        TaskPriority.MEDIUM: 2,
        TaskPriority.LOW: 3,
    }
    tasks.sort(key=lambda t: (priority_order.get(t.priority, 99), t.due_in_business_days))

    logger.info(
        "Generated %d URLA tasks for loan %s: %d doc_collection, %d verification, "
        "%d compliance, %d follow_up, %d scheduling",
        len(tasks),
        app.loan_id,
        sum(1 for t in tasks if t.category == TaskCategory.DOCUMENT_COLLECTION),
        sum(1 for t in tasks if t.category == TaskCategory.VERIFICATION),
        sum(1 for t in tasks if t.category == TaskCategory.COMPLIANCE),
        sum(1 for t in tasks if t.category == TaskCategory.FOLLOW_UP),
        sum(1 for t in tasks if t.category == TaskCategory.SCHEDULING),
    )

    return tasks
