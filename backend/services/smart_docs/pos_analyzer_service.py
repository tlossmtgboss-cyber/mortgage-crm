"""
Smart Document Collection - POS Application Analyzer

Analyzes Point of Sale (POS) loan application data to automatically determine
which documents are required based on:
- Loan type (Conventional, FHA, VA, USDA, Jumbo, Non-QM)
- Occupancy type (Primary, Second Home, Investment)
- Income type (W2, Self-Employed, Retired, Military)
- Special circumstances (gift funds, bankruptcy, foreign national, etc.)
- Borrower and co-borrower requirements separately
- State-specific requirements

This is the core intelligence that powers the automatic needs-list generation.
It replaces manual checklist creation with rule-based analysis of application
data, call intelligence, and borrower profile characteristics.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import text

from models.smart_docs_models import (
    DocType, RequestPriority, AppliesTo, RequestStatus,
    DocumentRequest,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RequiredDocument:
    """A document requirement identified from POS analysis."""
    doc_type: str  # DocType value
    title: str
    description: str
    instructions: str
    category: str  # identity, income, assets, property, credit, special
    priority: str  # CRITICAL, HIGH, NORMAL, LOW
    applies_to: str  # BORROWER, CO_BORROWER, BOTH
    required_count: int
    freshness_days: Optional[int]
    auto_renew: bool
    payroll_frequency: Optional[str]
    reason: str  # Why this document is needed


@dataclass
class POSAnalysisResult:
    """Result of POS application analysis."""
    loan_id: int
    requirements: List[RequiredDocument]
    total_documents_needed: int
    categories: Dict[str, int]  # count by category
    analysis_notes: List[str]  # Notes about the analysis
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# CONSTANTS - Loan Type Keywords
# =============================================================================

# Loan types that map to specific programs. The DB stores loan_type as a plain
# string, so we match case-insensitively against known patterns.
_FHA_PATTERNS = {"fha"}
_VA_PATTERNS = {"va"}
_USDA_PATTERNS = {"usda", "rural", "rd"}
_JUMBO_PATTERNS = {"jumbo", "non-conforming", "nonconforming"}
_NON_QM_PATTERNS = {"non-qm", "nonqm", "non_qm", "bank statement", "dscr", "asset depletion"}
_CONVENTIONAL_PATTERNS = {"conventional", "conv", "fnma", "fhlmc", "fannie", "freddie"}

# Occupancy keywords
_INVESTMENT_PATTERNS = {"investment", "non-owner", "rental", "noo"}
_SECOND_HOME_PATTERNS = {"second home", "second_home", "vacation"}

# Property type keywords
_CONDO_PATTERNS = {"condo", "condominium"}
_MULTI_FAMILY_PATTERNS = {"multi", "2-4 unit", "duplex", "triplex", "fourplex", "2 unit", "3 unit", "4 unit"}
_MANUFACTURED_PATTERNS = {"manufactured", "mobile", "modular"}

# Income classification thresholds
_COMMISSION_BONUS_THRESHOLD = 0.25  # 25% of income from variable sources triggers tax return requirement

# Jumbo threshold (for auto-detection when loan_type is blank)
_CONFORMING_LIMIT_2025 = 806_500
_HIGH_COST_LIMIT_2025 = 1_209_750

# States with notable additional requirements
_STATES_REQUIRING_EXTRA_DISCLOSURES = {
    "TX": "Texas requires 12-day cooling-off period for home equity loans",
    "CA": "California requires MLDS (Mortgage Loan Disclosure Statement)",
    "NY": "New York requires subprime lending disclosures above rate threshold",
    "GA": "Georgia Fair Lending Act applies to high-cost home loans",
    "NJ": "New Jersey licensed lender act imposes additional disclosure obligations",
    "IL": "Illinois Responsible Lending Act has anti-predatory lending rules",
    "MA": "Massachusetts prohibits prepayment penalties on primary residence loans",
}


# =============================================================================
# SERVICE
# =============================================================================

class POSAnalyzerService:
    """
    Analyzes POS loan application data to determine required documents.

    Considers:
    - Loan type (Conventional, FHA, VA, USDA, Jumbo, Non-QM)
    - Occupancy type (Primary, Second Home, Investment)
    - Income type (W2, Self-Employed, Retired, Military)
    - Special circumstances (gift funds, bankruptcy, foreign national, etc.)
    - Borrower and co-borrower separately
    - State-specific requirements
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def analyze_loan_application(
        self,
        loan_id: int,
        application_data: Optional[Dict] = None,
    ) -> POSAnalysisResult:
        """
        Analyze a loan application and return all required documents.

        If application_data is not provided, fetches it from the loans table.
        Returns a comprehensive list of required documents organized by category.
        """
        try:
            if application_data is None:
                loan_data = self._get_loan_data(loan_id)
                if loan_data is None:
                    return POSAnalysisResult(
                        loan_id=loan_id,
                        requirements=[],
                        total_documents_needed=0,
                        categories={},
                        analysis_notes=[],
                        success=False,
                        error=f"Loan {loan_id} not found",
                    )
            else:
                loan_data = application_data
                loan_data.setdefault("loan_id", loan_id)

            # Normalize fields for consistent downstream processing
            loan_data = self._normalize_loan_data(loan_data)

            notes: List[str] = []
            requirements: List[RequiredDocument] = []

            # Gather requirements from each category
            identity_reqs = self._get_identity_requirements(loan_data)
            requirements.extend(identity_reqs)
            if identity_reqs:
                notes.append(f"Identity: {len(identity_reqs)} documents required")

            income_reqs = self._get_income_requirements(loan_data)
            requirements.extend(income_reqs)
            if income_reqs:
                notes.append(f"Income: {len(income_reqs)} documents required ({loan_data.get('income_classification', 'standard')})")

            asset_reqs = self._get_asset_requirements(loan_data)
            requirements.extend(asset_reqs)
            if asset_reqs:
                notes.append(f"Assets: {len(asset_reqs)} documents required")

            property_reqs = self._get_property_requirements(loan_data)
            requirements.extend(property_reqs)
            if property_reqs:
                notes.append(f"Property: {len(property_reqs)} documents required")

            credit_reqs = self._get_credit_requirements(loan_data)
            requirements.extend(credit_reqs)
            if credit_reqs:
                notes.append(f"Credit: {len(credit_reqs)} documents required")

            special_reqs = self._get_special_requirements(loan_data)
            requirements.extend(special_reqs)
            if special_reqs:
                notes.append(f"Special/Program: {len(special_reqs)} documents required")

            # Deduplicate: if the same doc_type + applies_to appears multiple times,
            # keep the one with the highest priority
            requirements = self._deduplicate_requirements(requirements)

            # Build category counts
            categories: Dict[str, int] = {}
            for req in requirements:
                categories[req.category] = categories.get(req.category, 0) + 1

            # Add analysis summary notes
            program = loan_data.get("program_type", "CONVENTIONAL")
            notes.insert(0, f"Program: {program}, Occupancy: {loan_data.get('occupancy_normalized', 'PRIMARY')}")
            if loan_data.get("has_coborrower"):
                notes.append("Co-borrower present - duplicate identity/income docs required")
            if loan_data.get("property_state"):
                state = loan_data["property_state"].upper()
                if state in _STATES_REQUIRING_EXTRA_DISCLOSURES:
                    notes.append(f"State note: {_STATES_REQUIRING_EXTRA_DISCLOSURES[state]}")

            logger.info(
                f"POS analysis for loan {loan_id}: {len(requirements)} documents required "
                f"across {len(categories)} categories"
            )

            return POSAnalysisResult(
                loan_id=loan_id,
                requirements=requirements,
                total_documents_needed=len(requirements),
                categories=categories,
                analysis_notes=notes,
                success=True,
            )

        except Exception as e:
            logger.exception(f"POS analysis failed for loan {loan_id}")
            return POSAnalysisResult(
                loan_id=loan_id,
                requirements=[],
                total_documents_needed=0,
                categories={},
                analysis_notes=[],
                success=False,
                error=str(e),
            )

    def analyze_from_call_intelligence(
        self,
        loan_id: int,
        call_notes: List[Dict],
    ) -> List[RequiredDocument]:
        """
        Parse call notes/transcripts for document-related mentions and return
        additional requirements that automated POS analysis might miss.

        Each call_notes entry should have at least a 'content' or 'transcript' key.
        Optional keys: 'date', 'agent', 'summary'.

        Recognized patterns:
        - Job change / new employment -> updated employment verification docs
        - Rental properties -> lease agreements, Schedule E
        - Divorce -> divorce decree
        - Gift funds mentioned -> gift letter
        - Large deposits -> LOE for large deposits
        - Bankruptcy mentioned -> bankruptcy discharge
        - Self-employed / business owner -> business tax returns, P&L
        - Child support / alimony -> court order documentation
        - Foreign income -> translated tax documents
        """
        additional_reqs: List[RequiredDocument] = []
        seen_types: Set[str] = set()

        # Compile all note text into a single searchable corpus
        combined_text = ""
        for note in call_notes:
            text_content = note.get("content") or note.get("transcript") or note.get("summary") or ""
            combined_text += " " + text_content
        combined_text = combined_text.lower()

        if not combined_text.strip():
            return additional_reqs

        # Pattern matching rules
        _call_patterns: List[Tuple[str, RequiredDocument]] = [
            # Job change
            (
                r"(job change|new job|changed employer|started.+new position|switched companies|new employment)",
                RequiredDocument(
                    doc_type=DocType.PAYSTUB.value,
                    title="Updated Pay Stubs (New Employer)",
                    description="Pay stubs from new employer covering most recent 30-day period",
                    instructions=(
                        "Since you recently changed jobs, please provide pay stubs from "
                        "your new employer covering at least 30 days of employment. Include "
                        "the full pay period detail showing year-to-date earnings."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=2,
                    freshness_days=30,
                    auto_renew=True,
                    payroll_frequency=None,
                    reason="Borrower mentioned recent job change during call",
                ),
            ),
            # Offer letter for new job
            (
                r"(offer letter|employment offer|start date|new position)",
                RequiredDocument(
                    doc_type=DocType.OTHER.value,
                    title="Employment Offer Letter",
                    description="Written offer letter from new employer",
                    instructions=(
                        "Please provide a signed offer letter or employment contract "
                        "showing your position, start date, and compensation details."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower discussed new position or employment offer",
                ),
            ),
            # Rental properties
            (
                r"(rental propert|rental income|landlord|tenant|rent.+collect|investment propert)",
                RequiredDocument(
                    doc_type=DocType.LEASE_AGREEMENT.value,
                    title="Rental Lease Agreements",
                    description="Current signed lease agreements for all rental properties",
                    instructions=(
                        "Please provide fully executed lease agreements for each rental "
                        "property you own, showing tenant names, monthly rent amount, and "
                        "lease term. If month-to-month, provide the original lease plus "
                        "proof of current rent payments (bank statements showing deposits)."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned rental properties during call",
                ),
            ),
            # Divorce
            (
                r"(divorce|divorced|ex.?spouse|separation agreement|marital settlement|alimony|spousal support)",
                RequiredDocument(
                    doc_type=DocType.OTHER.value,
                    title="Divorce Decree / Separation Agreement",
                    description="Final divorce decree and property settlement agreement",
                    instructions=(
                        "Please provide the complete final divorce decree, including all "
                        "pages of the property settlement agreement. If the divorce is "
                        "pending, provide the signed separation agreement and any court "
                        "orders regarding property division, alimony, or child support."
                    ),
                    category="credit",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned divorce or marital settlement",
                ),
            ),
            # Gift funds
            (
                r"(gift.+fund|gift.+money|family.+help.+down|parent.+giving|relative.+contributing)",
                RequiredDocument(
                    doc_type=DocType.GIFT_LETTER.value,
                    title="Gift Letter and Donor Documentation",
                    description="Signed gift letter with proof of donor's ability to gift",
                    instructions=(
                        "Please provide: (1) A signed gift letter stating the donor's name, "
                        "relationship, gift amount, property address, and confirmation that "
                        "no repayment is required. (2) Donor's bank statement showing "
                        "sufficient funds to provide the gift. (3) Evidence of the gift "
                        "transfer (wire confirmation or deposit receipt)."
                    ),
                    category="assets",
                    priority=RequestPriority.CRITICAL.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned gift funds for down payment",
                ),
            ),
            # Large deposits
            (
                r"(large deposit|big deposit|unusual deposit|deposit.+explain|where.+money came from)",
                RequiredDocument(
                    doc_type=DocType.LOE.value,
                    title="Letter of Explanation - Large Deposit",
                    description="Written explanation for large or unusual deposits",
                    instructions=(
                        "Please provide a signed letter explaining the source of any "
                        "deposits exceeding 50%% of your qualifying monthly income. "
                        "Include documentation supporting the explanation (e.g., sale "
                        "receipt, gift letter, insurance settlement, tax refund notice)."
                    ),
                    category="assets",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower discussed large or unusual deposits",
                ),
            ),
            # Bankruptcy
            (
                r"(bankrupt|chapter 7|chapter 13|filed.+bankruptcy|discharged)",
                RequiredDocument(
                    doc_type=DocType.BANKRUPTCY_DISCHARGE.value,
                    title="Bankruptcy Discharge Papers",
                    description="Complete bankruptcy discharge documentation",
                    instructions=(
                        "Please provide the full bankruptcy discharge order from the "
                        "court, including the petition filing date, case number, chapter "
                        "filed under, and discharge date. If Chapter 13, also provide the "
                        "payment plan and trustee letter confirming satisfactory payments."
                    ),
                    category="credit",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned bankruptcy history during call",
                ),
            ),
            # Self-employed / business owner
            (
                r"(self.?employed|own.+business|business owner|freelanc|independ.+contract|1099.+worker|sole proprietor|llc|s.?corp)",
                RequiredDocument(
                    doc_type=DocType.PROFIT_LOSS.value,
                    title="Year-to-Date Profit & Loss Statement",
                    description="Current year P&L statement for business",
                    instructions=(
                        "Please provide a year-to-date profit and loss statement for "
                        "your business, signed and dated. If you have an accountant, "
                        "a CPA-prepared statement is preferred but not required."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=90,
                    auto_renew=True,
                    payroll_frequency=None,
                    reason="Borrower indicated self-employment or business ownership",
                ),
            ),
            # Child support
            (
                r"(child support|custody.+order|family court.+order|child.+maintenance)",
                RequiredDocument(
                    doc_type=DocType.OTHER.value,
                    title="Child Support Court Order",
                    description="Court order documenting child support obligation or receipt",
                    instructions=(
                        "Please provide the court order or divorce decree section that "
                        "specifies the child support amount, payment schedule, and "
                        "duration. If you receive child support as income, also provide "
                        "proof of receipt for the most recent 6 months (bank statements "
                        "or payment receipts)."
                    ),
                    category="credit",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned child support obligations",
                ),
            ),
            # Social Security / Disability income
            (
                r"(social security|disability.+income|ssi|ssdi|disability.+benefit|ss.+benefit)",
                RequiredDocument(
                    doc_type=DocType.OTHER.value,
                    title="Social Security / Disability Award Letter",
                    description="Current benefit award letter from SSA",
                    instructions=(
                        "Please provide your most recent Social Security or disability "
                        "benefit award letter (SSA-1099 or benefit verification letter). "
                        "The letter must show your current monthly benefit amount and be "
                        "dated within the current or prior calendar year."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned Social Security or disability income",
                ),
            ),
            # Retirement / pension income
            (
                r"(pension|retired|retirement.+income|401k.+distribution|ira.+distribution|annuity.+income)",
                RequiredDocument(
                    doc_type=DocType.OTHER.value,
                    title="Pension / Retirement Income Documentation",
                    description="Proof of pension or retirement income distributions",
                    instructions=(
                        "Please provide documentation of your retirement income: "
                        "(1) Pension award letter or 1099-R showing annual distributions, "
                        "(2) Most recent account statement showing balance and distribution "
                        "schedule, (3) If income is from asset depletion, provide all "
                        "retirement account statements."
                    ),
                    category="income",
                    priority=RequestPriority.HIGH.value,
                    applies_to=AppliesTo.BORROWER.value,
                    required_count=1,
                    freshness_days=None,
                    auto_renew=False,
                    payroll_frequency=None,
                    reason="Borrower mentioned pension or retirement income",
                ),
            ),
        ]

        for pattern, req_doc in _call_patterns:
            if re.search(pattern, combined_text) and req_doc.doc_type not in seen_types:
                # For patterns that might produce the same doc_type (e.g., OTHER),
                # we track by doc_type + title to allow multiple OTHER entries
                dedup_key = f"{req_doc.doc_type}:{req_doc.title}"
                if dedup_key not in seen_types:
                    seen_types.add(dedup_key)
                    additional_reqs.append(req_doc)

        logger.info(
            f"Call intelligence analysis for loan {loan_id}: "
            f"{len(additional_reqs)} additional requirements identified from "
            f"{len(call_notes)} call notes"
        )

        return additional_reqs

    def compare_with_existing(
        self,
        loan_id: int,
        requirements: List[RequiredDocument],
    ) -> Dict[str, Any]:
        """
        Compare identified requirements against existing smart_document_requests.

        Returns:
            {
                "new": [...],              # Requirements not yet requested
                "already_requested": [...], # Requirements that have an open/pending request
                "completed": [...],         # Requirements already fulfilled
            }
        """
        # Fetch existing requests for this loan
        existing_rows = self.db.execute(
            text("""
                SELECT doc_type, title, status, applies_to
                FROM smart_document_requests
                WHERE loan_id = :loan_id AND is_active = true
            """),
            {"loan_id": loan_id},
        ).fetchall()

        # Build lookup: (doc_type, applies_to) -> status
        existing_map: Dict[Tuple[str, str], str] = {}
        for row in existing_rows:
            key = (row[0], row[3])  # doc_type, applies_to
            existing_map[key] = row[2]  # status

        new_reqs: List[RequiredDocument] = []
        already_requested: List[RequiredDocument] = []
        completed: List[RequiredDocument] = []

        for req in requirements:
            key = (req.doc_type, req.applies_to)
            if key not in existing_map:
                new_reqs.append(req)
            elif existing_map[key] in ("ACCEPTED",):
                completed.append(req)
            else:
                # OPEN, PENDING_REVIEW, REJECTED, WAIVED
                already_requested.append(req)

        return {
            "new": new_reqs,
            "already_requested": already_requested,
            "completed": completed,
            "summary": {
                "new_count": len(new_reqs),
                "already_requested_count": len(already_requested),
                "completed_count": len(completed),
            },
        }

    # =========================================================================
    # DATA FETCHING
    # =========================================================================

    def _get_loan_data(self, loan_id: int) -> Optional[Dict]:
        """
        Fetch loan data from the loans table, plus supplementary data from
        the leads table if a matching loan_number exists.
        """
        row = self.db.execute(
            text("""
                SELECT
                    l.id, l.loan_number, l.loan_type, l.program,
                    l.occupancy_type, l.property_type, l.property_state,
                    l.borrower_name, l.coborrower_name, l.borrower_email,
                    l.co_borrower_email,
                    l.amount, l.purchase_price, l.down_payment,
                    l.ltv, l.cltv,
                    l.loan_purpose,
                    l.property_units,
                    l.hoa_amount,
                    l.user_metadata,
                    l.stage
                FROM loans l
                WHERE l.id = :loan_id
            """),
            {"loan_id": loan_id},
        ).fetchone()

        if row is None:
            return None

        loan_data = {
            "loan_id": row[0],
            "loan_number": row[1],
            "loan_type": row[2],
            "program": row[3],
            "occupancy_type": row[4],
            "property_type": row[5],
            "property_state": row[6],
            "borrower_name": row[7],
            "coborrower_name": row[8],
            "borrower_email": row[9],
            "co_borrower_email": row[10],
            "loan_amount": float(row[11] or 0),
            "purchase_price": float(row[12] or 0),
            "down_payment": float(row[13] or 0),
            "ltv": float(row[14] or 0),
            "cltv": float(row[15] or 0),
            "loan_purpose": row[16],
            "property_units": row[17],
            "hoa_amount": float(row[18] or 0),
            "user_metadata": row[19] or {},
            "stage": row[20],
        }

        # Supplement from leads table (employment, credit score, self-employment, notes)
        lead_row = self.db.execute(
            text("""
                SELECT
                    ld.employment_status, ld.credit_score, ld.notes,
                    ld.first_time_buyer, ld.annual_income, ld.loan_purpose as lead_loan_purpose
                FROM leads ld
                WHERE ld.loan_number = :loan_number
                LIMIT 1
            """),
            {"loan_number": loan_data["loan_number"]},
        ).fetchone()

        if lead_row:
            loan_data["employment_status"] = lead_row[0]
            loan_data["credit_score"] = lead_row[1]
            loan_data["notes"] = lead_row[2]
            loan_data["first_time_buyer"] = lead_row[3]
            loan_data["annual_income"] = float(lead_row[4] or 0)
            # Use lead loan purpose as fallback
            if not loan_data.get("loan_purpose"):
                loan_data["loan_purpose"] = lead_row[5]
        else:
            loan_data.setdefault("employment_status", None)
            loan_data.setdefault("credit_score", None)
            loan_data.setdefault("notes", None)
            loan_data.setdefault("first_time_buyer", False)
            loan_data.setdefault("annual_income", 0)

        return loan_data

    # =========================================================================
    # NORMALIZATION
    # =========================================================================

    def _normalize_loan_data(self, data: Dict) -> Dict:
        """
        Normalize raw loan data into consistent classification fields used by
        the requirement generators.

        Sets derived fields:
        - program_type: CONVENTIONAL, FHA, VA, USDA, JUMBO, NON_QM
        - occupancy_normalized: PRIMARY, SECOND_HOME, INVESTMENT
        - property_normalized: SINGLE_FAMILY, CONDO, MULTI_FAMILY, MANUFACTURED, OTHER
        - income_classification: W2, SELF_EMPLOYED, RETIRED, MILITARY
        - has_coborrower: bool
        - has_gift_funds: bool
        - has_bankruptcy: bool
        - is_self_employed: bool
        - is_purchase: bool
        - is_refinance: bool
        """
        # --- Program type ---
        loan_type_raw = (data.get("loan_type") or data.get("program") or "").lower().strip()
        program_raw = (data.get("program") or "").lower().strip()
        combined_type = f"{loan_type_raw} {program_raw}"

        if any(p in combined_type for p in _VA_PATTERNS):
            data["program_type"] = "VA"
        elif any(p in combined_type for p in _FHA_PATTERNS):
            data["program_type"] = "FHA"
        elif any(p in combined_type for p in _USDA_PATTERNS):
            data["program_type"] = "USDA"
        elif any(p in combined_type for p in _NON_QM_PATTERNS):
            data["program_type"] = "NON_QM"
        elif any(p in combined_type for p in _JUMBO_PATTERNS):
            data["program_type"] = "JUMBO"
        else:
            # Auto-detect jumbo based on loan amount
            loan_amount = data.get("loan_amount", 0) or 0
            if loan_amount > _CONFORMING_LIMIT_2025:
                data["program_type"] = "JUMBO"
            else:
                data["program_type"] = "CONVENTIONAL"

        # --- Occupancy ---
        occ_raw = (data.get("occupancy_type") or "").lower().strip()
        if any(p in occ_raw for p in _INVESTMENT_PATTERNS):
            data["occupancy_normalized"] = "INVESTMENT"
        elif any(p in occ_raw for p in _SECOND_HOME_PATTERNS):
            data["occupancy_normalized"] = "SECOND_HOME"
        else:
            data["occupancy_normalized"] = "PRIMARY"

        # --- Property type ---
        prop_raw = (data.get("property_type") or "").lower().strip()
        if any(p in prop_raw for p in _CONDO_PATTERNS):
            data["property_normalized"] = "CONDO"
        elif any(p in prop_raw for p in _MULTI_FAMILY_PATTERNS):
            data["property_normalized"] = "MULTI_FAMILY"
        elif any(p in prop_raw for p in _MANUFACTURED_PATTERNS):
            data["property_normalized"] = "MANUFACTURED"
        elif prop_raw:
            data["property_normalized"] = "SINGLE_FAMILY"
        else:
            data["property_normalized"] = "SINGLE_FAMILY"

        # --- Income classification ---
        emp_raw = (data.get("employment_status") or "").lower().strip()
        notes_raw = (data.get("notes") or "").lower()

        if any(kw in emp_raw for kw in ("self", "business owner", "1099", "freelanc", "independ")):
            data["income_classification"] = "SELF_EMPLOYED"
            data["is_self_employed"] = True
        elif any(kw in emp_raw for kw in ("retired", "pension", "social security")):
            data["income_classification"] = "RETIRED"
            data["is_self_employed"] = False
        elif any(kw in emp_raw for kw in ("military", "active duty", "veteran")):
            data["income_classification"] = "MILITARY"
            data["is_self_employed"] = False
        elif "self" in notes_raw and "employed" in notes_raw:
            data["income_classification"] = "SELF_EMPLOYED"
            data["is_self_employed"] = True
        else:
            data["income_classification"] = "W2"
            data["is_self_employed"] = data.get("is_self_employed", False)

        # --- Booleans ---
        data["has_coborrower"] = bool(data.get("coborrower_name"))
        data["has_gift_funds"] = data.get("has_gift_funds", False)
        data["has_bankruptcy"] = data.get("has_bankruptcy", False)

        # Detect gift funds and bankruptcy from notes
        if not data["has_gift_funds"] and notes_raw:
            if any(kw in notes_raw for kw in ("gift fund", "gift letter", "gift from", "family gift")):
                data["has_gift_funds"] = True
        if not data["has_bankruptcy"] and notes_raw:
            if any(kw in notes_raw for kw in ("bankrupt", "chapter 7", "chapter 13", "bk discharge")):
                data["has_bankruptcy"] = True

        # Detect from user_metadata if available
        metadata = data.get("user_metadata") or {}
        if isinstance(metadata, dict):
            if metadata.get("has_gift_funds"):
                data["has_gift_funds"] = True
            if metadata.get("has_bankruptcy"):
                data["has_bankruptcy"] = True
            if metadata.get("is_self_employed"):
                data["is_self_employed"] = True
                data["income_classification"] = "SELF_EMPLOYED"

        # --- Loan purpose ---
        purpose_raw = (data.get("loan_purpose") or "").lower()
        data["is_purchase"] = any(kw in purpose_raw for kw in ("purchase", "buy"))
        data["is_refinance"] = any(kw in purpose_raw for kw in ("refinance", "refi", "cash out", "cashout", "rate term"))

        return data

    # =========================================================================
    # REQUIREMENT GENERATORS
    # =========================================================================

    def _get_identity_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Identity verification documents.
        Always required for borrower. If co-borrower, required for them too.
        VA loans require Certificate of Eligibility and DD-214.
        """
        reqs: List[RequiredDocument] = []

        # Primary borrower - Driver's License / Government ID
        reqs.append(RequiredDocument(
            doc_type=DocType.DRIVERS_LICENSE.value,
            title="Government-Issued Photo ID",
            description="Valid, unexpired driver's license or passport for the primary borrower",
            instructions=(
                "Please upload a clear, color copy of your valid government-issued "
                "photo ID (driver's license or passport). The ID must be unexpired. "
                "Ensure all four corners are visible and text is legible."
            ),
            category="identity",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason="Government ID is required for all mortgage applications per TRID/ECOA",
        ))

        # Co-borrower ID
        if loan_data.get("has_coborrower"):
            reqs.append(RequiredDocument(
                doc_type=DocType.DRIVERS_LICENSE.value,
                title="Co-Borrower Government-Issued Photo ID",
                description="Valid, unexpired driver's license or passport for the co-borrower",
                instructions=(
                    "Please upload a clear, color copy of the co-borrower's valid "
                    "government-issued photo ID (driver's license or passport). The ID "
                    "must be unexpired. Ensure all four corners are visible."
                ),
                category="identity",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.CO_BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason="Co-borrower government ID required for joint mortgage applications",
            ))

        # VA-specific identity documents
        program = loan_data.get("program_type", "")
        if program == "VA":
            reqs.append(RequiredDocument(
                doc_type=DocType.VA_COE.value,
                title="VA Certificate of Eligibility (COE)",
                description="Certificate of Eligibility from the Department of Veterans Affairs",
                instructions=(
                    "Please provide your VA Certificate of Eligibility (COE). You can "
                    "obtain this from eBenefits (https://www.ebenefits.va.gov), through "
                    "your lender, or by mailing VA Form 26-1880. If you have a prior VA "
                    "loan, we may need to request a restoration of entitlement."
                ),
                category="identity",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason="VA COE is required to verify VA loan entitlement and funding fee exemption status",
            ))

            reqs.append(RequiredDocument(
                doc_type=DocType.DD214.value,
                title="DD-214 (Certificate of Release or Discharge)",
                description="DD-214 showing character of service for veterans",
                instructions=(
                    "Please provide your DD-214 (Certificate of Release or Discharge "
                    "from Active Duty). If you are currently active duty, provide your "
                    "most recent Leave and Earnings Statement (LES) instead. A Statement "
                    "of Service signed by your commanding officer is also acceptable for "
                    "active duty service members."
                ),
                category="identity",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason="DD-214 verifies military service dates and character of discharge for VA eligibility",
            ))

        return reqs

    def _get_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Income documentation requirements based on employment type.

        W2 employees: Paystubs + W2s, plus tax returns if >25% variable income
        Self-employed: Tax returns (personal + business), P&L, balance sheet
        Retired: Pension/SS documentation, tax returns
        Military: LES, DD-214
        All: paystubs get auto_renew=True with payroll_frequency
        """
        reqs: List[RequiredDocument] = []
        classification = loan_data.get("income_classification", "W2")

        if classification == "W2":
            reqs.extend(self._get_w2_income_requirements(loan_data))
        elif classification == "SELF_EMPLOYED":
            reqs.extend(self._get_self_employed_income_requirements(loan_data))
        elif classification == "RETIRED":
            reqs.extend(self._get_retired_income_requirements(loan_data))
        elif classification == "MILITARY":
            reqs.extend(self._get_military_income_requirements(loan_data))

        # Co-borrower income docs (assume W2 unless specified otherwise)
        if loan_data.get("has_coborrower"):
            reqs.extend(self._get_coborrower_income_requirements(loan_data))

        return reqs

    def _get_w2_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """Standard W2 employee income requirements."""
        reqs: List[RequiredDocument] = []

        # Pay stubs - most recent 30 days
        reqs.append(RequiredDocument(
            doc_type=DocType.PAYSTUB.value,
            title="Recent Pay Stubs (30 Days)",
            description=(
                "Most recent 30 days of consecutive pay stubs showing year-to-date "
                "earnings, deductions, and employer information"
            ),
            instructions=(
                "Please upload your most recent pay stubs covering a full 30-day "
                "period. Each pay stub should show: (1) Your name and employer name, "
                "(2) Pay period dates, (3) Gross earnings, (4) Year-to-date totals, "
                "(5) All deductions. If paid weekly, provide 5 stubs. If bi-weekly, "
                "provide 3 stubs. If semi-monthly or monthly, provide 2 stubs."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=2,
            freshness_days=30,
            auto_renew=True,
            payroll_frequency=None,  # Set after we learn the borrower's pay schedule
            reason="30-day paystub history required per Fannie Mae B3-3.1 for W2 income verification",
        ))

        # W-2 forms - last 2 years
        reqs.append(RequiredDocument(
            doc_type=DocType.W2.value,
            title="W-2 Forms (2 Years)",
            description="W-2 wage and tax statements for the most recent 2 tax years",
            instructions=(
                "Please upload W-2 forms from all employers for the past 2 complete "
                "tax years. If you had multiple employers in either year, include W-2s "
                "from each employer. Ensure the Social Security number and employer "
                "identification number (EIN) are clearly visible."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=2,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason="W-2 forms for 2 years required per Fannie Mae B3-3.1 to verify employment history and earnings stability",
        ))

        # Tax returns if commission/bonus income exceeds 25%
        # We add this as NORMAL priority since we may not know the exact
        # breakdown until we see the paystubs; the LO can upgrade priority.
        notes_raw = (loan_data.get("notes") or "").lower()
        emp_raw = (loan_data.get("employment_status") or "").lower()
        has_variable_income = any(
            kw in notes_raw or kw in emp_raw
            for kw in ("commission", "bonus", "overtime", "variable", "fluctuat")
        )

        if has_variable_income:
            reqs.append(RequiredDocument(
                doc_type=DocType.TAX_RETURN.value,
                title="Personal Tax Returns (2 Years) - Variable Income",
                description=(
                    "Complete federal tax returns for the past 2 years, including all "
                    "schedules, due to commission/bonus/overtime income"
                ),
                instructions=(
                    "Because your income includes variable components (commission, "
                    "bonus, or overtime), we need your complete federal tax returns for "
                    "the past 2 years. Please include all pages and schedules, "
                    "especially Schedule C if applicable. Signed copies (Form 8879 "
                    "e-file authorization or wet-signed 1040) are preferred."
                ),
                category="income",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Tax returns required when >25% of qualifying income is from "
                    "variable sources (commission/bonus/overtime) per FNMA B3-3.1-09"
                ),
            ))

        return reqs

    def _get_self_employed_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """Self-employed borrower income requirements."""
        reqs: List[RequiredDocument] = []

        # Personal tax returns - 2 years
        reqs.append(RequiredDocument(
            doc_type=DocType.TAX_RETURN.value,
            title="Personal Tax Returns (2 Years)",
            description=(
                "Complete federal personal tax returns (Form 1040) for the past "
                "2 tax years, including all schedules and attachments"
            ),
            instructions=(
                "Please upload complete federal personal tax returns (Form 1040) for "
                "the past 2 years. Include ALL pages and schedules, especially: "
                "Schedule C (sole proprietorship), Schedule E (rental/partnership), "
                "Schedule K-1 (partnership/S-Corp). Include the e-file confirmation "
                "(Form 8879) or signed 1040. If you filed an extension, include "
                "Form 4868."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=2,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "2-year personal tax returns required for self-employed borrowers "
                "per FNMA B3-3.2 to calculate qualifying income via Form 1084"
            ),
        ))

        # Business tax returns - 2 years
        reqs.append(RequiredDocument(
            doc_type=DocType.BUSINESS_TAX_RETURN.value,
            title="Business Tax Returns (2 Years)",
            description=(
                "Complete business tax returns for the past 2 tax years "
                "(Form 1120, 1120S, 1065, or Schedule C as applicable)"
            ),
            instructions=(
                "Please upload complete business tax returns for the past 2 years. "
                "Depending on your business structure, this may be: (1) Schedule C "
                "if sole proprietor (included with 1040), (2) Form 1065 for "
                "partnerships, (3) Form 1120S for S-Corporations, or (4) Form 1120 "
                "for C-Corporations. Include all schedules, K-1 forms, and "
                "depreciation schedules."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=2,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Business tax returns required for self-employed income calculation "
                "using Fannie Mae Form 1084/1088 analysis"
            ),
        ))

        # Year-to-date P&L
        reqs.append(RequiredDocument(
            doc_type=DocType.PROFIT_LOSS.value,
            title="Year-to-Date Profit & Loss Statement",
            description=(
                "Current year-to-date profit and loss statement for the business, "
                "signed and dated by the borrower"
            ),
            instructions=(
                "Please provide a year-to-date profit and loss (P&L) statement for "
                "your business. The P&L must: (1) Cover January 1 through the most "
                "recent month-end, (2) Show gross revenue, expenses by category, and "
                "net profit, (3) Be signed and dated by you (the borrower). A "
                "CPA-prepared P&L is preferred but borrower-prepared is acceptable. "
                "If your business has been operating for less than 2 years, note the "
                "business start date."
            ),
            category="income",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=90,
            auto_renew=True,
            payroll_frequency=None,
            reason=(
                "YTD P&L verifies current-year business performance and is required "
                "if more than 3 months have elapsed since the end of the last tax year "
                "(FNMA B3-3.2-01)"
            ),
        ))

        # Balance sheet
        reqs.append(RequiredDocument(
            doc_type=DocType.BALANCE_SHEET.value,
            title="Business Balance Sheet",
            description="Current business balance sheet showing assets and liabilities",
            instructions=(
                "Please provide a current balance sheet for your business showing "
                "assets, liabilities, and owner's equity. This helps verify business "
                "liquidity and that no unusual withdrawals have occurred."
            ),
            category="income",
            priority=RequestPriority.NORMAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=90,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Balance sheet required for businesses with >25% ownership to verify "
                "liquidity and capital adequacy"
            ),
        ))

        return reqs

    def _get_retired_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """Retired borrower income requirements."""
        reqs: List[RequiredDocument] = []

        # Pension / Social Security award letter
        reqs.append(RequiredDocument(
            doc_type=DocType.OTHER.value,
            title="Pension / Social Security Award Letter",
            description=(
                "Current award letter or benefit verification letter showing "
                "monthly benefit amount"
            ),
            instructions=(
                "Please provide your most recent benefit award or verification "
                "letter from each source of retirement income. Acceptable documents "
                "include: (1) Social Security Administration benefit verification "
                "letter (SSA-1099 or TPQY response), (2) Pension benefit statement "
                "from employer/fund administrator, (3) Annuity contract showing "
                "guaranteed monthly payment. The document must show the current "
                "monthly or annual benefit amount."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Retirement benefit verification required to establish stable, "
                "continuing income per FNMA B3-3.1-09"
            ),
        ))

        # Tax returns - most recent 1 year (2 if asset-depletion income)
        reqs.append(RequiredDocument(
            doc_type=DocType.TAX_RETURN.value,
            title="Personal Tax Returns (Most Recent Year)",
            description=(
                "Most recent year's federal tax return to verify retirement income "
                "reporting and identify additional income sources"
            ),
            instructions=(
                "Please provide your most recent complete federal tax return "
                "(Form 1040) including all schedules. This verifies that your "
                "retirement income is reported consistently with your award letter."
            ),
            category="income",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Tax return verifies retirement income consistency and identifies "
                "any additional income sources (rental, investment, etc.)"
            ),
        ))

        # Retirement account statements (for asset-depletion qualification)
        reqs.append(RequiredDocument(
            doc_type=DocType.INVESTMENT_STATEMENT.value,
            title="Retirement Account Statements",
            description=(
                "Most recent quarterly or monthly statements for all retirement "
                "accounts (401k, IRA, pension fund)"
            ),
            instructions=(
                "Please provide the most recent statements for all retirement and "
                "investment accounts. Include: 401(k), Traditional IRA, Roth IRA, "
                "pension accounts, annuities, and brokerage accounts. Each statement "
                "should show the account balance and recent transactions."
            ),
            category="income",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=90,
            auto_renew=True,
            payroll_frequency=None,
            reason=(
                "Retirement account statements may be needed for asset-depletion "
                "income calculation or to verify distribution sustainability"
            ),
        ))

        return reqs

    def _get_military_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """Active duty military income requirements."""
        reqs: List[RequiredDocument] = []

        # Leave and Earnings Statement (LES)
        reqs.append(RequiredDocument(
            doc_type=DocType.PAYSTUB.value,
            title="Leave and Earnings Statement (LES)",
            description="Most recent Leave and Earnings Statement showing all military pay and allowances",
            instructions=(
                "Please provide your most recent Leave and Earnings Statement (LES). "
                "The LES should show: (1) Base pay, (2) BAH (Basic Allowance for "
                "Housing), (3) BAS (Basic Allowance for Subsistence), (4) Any special "
                "pay or incentive pay, (5) COLA if stationed overseas. You can "
                "download your LES from myPay (https://mypay.dfas.mil)."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=30,
            auto_renew=True,
            payroll_frequency="MONTHLY",
            reason=(
                "LES is the military equivalent of pay stubs and documents base pay "
                "plus allowances (BAH/BAS) used for qualifying income"
            ),
        ))

        # W-2 forms
        reqs.append(RequiredDocument(
            doc_type=DocType.W2.value,
            title="W-2 Forms (2 Years)",
            description="W-2 forms from DFAS for the past 2 tax years",
            instructions=(
                "Please provide W-2 forms for the past 2 years. Military W-2s "
                "are issued by DFAS. If you had any off-duty employment, include "
                "those W-2s as well."
            ),
            category="income",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=2,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason="W-2 history verifies consistent military income over 2-year period",
        ))

        return reqs

    def _get_coborrower_income_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """Income requirements for the co-borrower (assumed W2 unless noted)."""
        reqs: List[RequiredDocument] = []

        # Co-borrower paystubs
        reqs.append(RequiredDocument(
            doc_type=DocType.PAYSTUB.value,
            title="Co-Borrower Pay Stubs (30 Days)",
            description="Co-borrower's most recent 30 days of consecutive pay stubs",
            instructions=(
                "Please upload the co-borrower's most recent pay stubs covering a "
                "full 30-day period. Each pay stub should show employer name, pay "
                "period dates, gross earnings, and year-to-date totals."
            ),
            category="income",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.CO_BORROWER.value,
            required_count=2,
            freshness_days=30,
            auto_renew=True,
            payroll_frequency=None,
            reason="Co-borrower income verification required when qualifying with combined income",
        ))

        # Co-borrower W-2s
        reqs.append(RequiredDocument(
            doc_type=DocType.W2.value,
            title="Co-Borrower W-2 Forms (2 Years)",
            description="Co-borrower's W-2 forms for the past 2 tax years",
            instructions=(
                "Please upload the co-borrower's W-2 forms from all employers for "
                "the past 2 complete tax years."
            ),
            category="income",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.CO_BORROWER.value,
            required_count=2,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason="Co-borrower W-2 history required for employment and income stability verification",
        ))

        return reqs

    def _get_asset_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Asset documentation requirements.

        Always: Bank statements (60-day / 2 months).
        Conditional: Investment statements, gift letter, co-borrower assets.
        Jumbo: Extended asset documentation (12 months).
        """
        reqs: List[RequiredDocument] = []
        program = loan_data.get("program_type", "CONVENTIONAL")

        # Bank statements - 2 most recent months (all accounts)
        bank_stmt_count = 2
        bank_stmt_freshness = 60
        bank_stmt_instructions = (
            "Please provide the 2 most recent monthly bank statements for ALL "
            "checking, savings, and money market accounts. Each statement must "
            "show: (1) Account holder name, (2) Account number, (3) Statement "
            "period, (4) All transactions, (5) Ending balance. Include ALL pages "
            "of each statement, even blank pages. Online printouts must show the "
            "institution name and account number."
        )

        # Jumbo loans require 12 months of asset documentation
        if program == "JUMBO":
            bank_stmt_count = 12
            bank_stmt_freshness = 90
            bank_stmt_instructions = (
                "Jumbo loan programs require 12 months of bank statements for all "
                "accounts being used for qualification. Please provide complete "
                "statements (all pages) for each month. Statements must show account "
                "holder name, account number, and all transactions."
            )

        reqs.append(RequiredDocument(
            doc_type=DocType.BANK_STATEMENT.value,
            title=f"Bank Statements ({bank_stmt_count} Months)",
            description=(
                f"Most recent {bank_stmt_count} months of statements for all checking, "
                f"savings, and money market accounts"
            ),
            instructions=bank_stmt_instructions,
            category="assets",
            priority=RequestPriority.CRITICAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=bank_stmt_count,
            freshness_days=bank_stmt_freshness,
            auto_renew=True,
            payroll_frequency=None,
            reason=(
                f"Bank statements ({bank_stmt_count} months) required to verify "
                f"assets for down payment, closing costs, and reserves "
                f"{'(extended documentation for jumbo program)' if program == 'JUMBO' else '(per FNMA B3-4.2)'}"
            ),
        ))

        # Investment / retirement account statements
        # Required when borrower has significant non-liquid assets or reserves needed
        reqs.append(RequiredDocument(
            doc_type=DocType.INVESTMENT_STATEMENT.value,
            title="Investment / Retirement Account Statements",
            description=(
                "Most recent quarterly or monthly statements for investment, "
                "retirement (401k/IRA), and brokerage accounts"
            ),
            instructions=(
                "If you have investment or retirement accounts that will be used for "
                "reserves or down payment, please provide the most recent statement "
                "for each account. Include: 401(k), IRA, brokerage, mutual fund, and "
                "stock accounts. Each statement should show account balance, account "
                "holder name, and account number."
            ),
            category="assets",
            priority=RequestPriority.NORMAL.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=90,
            auto_renew=True,
            payroll_frequency=None,
            reason=(
                "Investment statements verify reserves and may contribute to "
                "qualifying assets per FNMA B3-4.3"
            ),
        ))

        # Gift letter
        if loan_data.get("has_gift_funds"):
            reqs.append(RequiredDocument(
                doc_type=DocType.GIFT_LETTER.value,
                title="Gift Letter and Donor Documentation",
                description=(
                    "Signed gift letter from donor with proof of donor's ability "
                    "to provide the gift and transfer documentation"
                ),
                instructions=(
                    "Please provide the following gift documentation: "
                    "(1) A signed gift letter on the template provided, stating: "
                    "donor name, donor relationship to borrower, dollar amount of "
                    "gift, property address, and a statement that no repayment is "
                    "expected. (2) Donor's bank statement showing sufficient funds "
                    "to provide the gift (must be dated before the transfer). "
                    "(3) Proof of transfer: wire confirmation, cashier's check copy, "
                    "or deposit receipt showing the funds in borrower's account. "
                    "Note: FHA/VA/USDA have specific donor eligibility rules."
                ),
                category="assets",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Gift funds require documentation of source, transfer, and "
                    "non-repayment per FNMA B3-4.3-04 and program-specific rules"
                ),
            ))

        # Co-borrower bank statements
        if loan_data.get("has_coborrower"):
            reqs.append(RequiredDocument(
                doc_type=DocType.BANK_STATEMENT.value,
                title="Co-Borrower Bank Statements (2 Months)",
                description=(
                    "Co-borrower's most recent 2 months of bank statements for "
                    "all accounts"
                ),
                instructions=(
                    "Please provide the co-borrower's 2 most recent monthly bank "
                    "statements for all checking, savings, and money market accounts. "
                    "Include all pages of each statement."
                ),
                category="assets",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.CO_BORROWER.value,
                required_count=2,
                freshness_days=60,
                auto_renew=True,
                payroll_frequency=None,
                reason=(
                    "Co-borrower asset verification required when qualifying with "
                    "combined assets or when co-borrower contributes to down payment"
                ),
            ))

        return reqs

    def _get_property_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Property-related document requirements.

        Purchase: Contract, appraisal, title, insurance.
        Refinance: Appraisal, title, insurance, mortgage statement.
        Condo: Condo questionnaire / HOA docs.
        """
        reqs: List[RequiredDocument] = []
        is_purchase = loan_data.get("is_purchase", True)
        property_type = loan_data.get("property_normalized", "SINGLE_FAMILY")

        # Purchase contract (purchase transactions only)
        if is_purchase:
            reqs.append(RequiredDocument(
                doc_type=DocType.PURCHASE_CONTRACT.value,
                title="Fully Executed Purchase Contract",
                description=(
                    "Complete, signed purchase agreement including all addenda, "
                    "amendments, and counter-offers"
                ),
                instructions=(
                    "Please upload the fully executed (all parties signed) purchase "
                    "contract for the subject property. Include: (1) All pages of the "
                    "purchase agreement, (2) All addenda and amendments, (3) Any "
                    "counter-offers, (4) Seller's disclosure statement if available. "
                    "The contract should show the purchase price, earnest money "
                    "deposit, closing date, and all contingencies."
                ),
                category="property",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Purchase contract is required to establish the sales price, "
                    "property address, closing date, and transaction terms"
                ),
            ))

        # Appraisal (ordered by lender, but tracked here)
        reqs.append(RequiredDocument(
            doc_type=DocType.APPRAISAL.value,
            title="Property Appraisal Report",
            description="Full appraisal report for the subject property",
            instructions=(
                "The appraisal will be ordered by the lender through an approved "
                "Appraisal Management Company (AMC). No action is needed from you "
                "unless the appraiser contacts you to schedule property access. "
                "This item will be updated automatically when the appraisal is received."
            ),
            category="property",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Appraisal required to establish market value for LTV calculation "
                "and property eligibility"
            ),
        ))

        # Title report / commitment
        reqs.append(RequiredDocument(
            doc_type=DocType.TITLE_REPORT.value,
            title="Preliminary Title Report / Title Commitment",
            description="Title search showing ownership history, liens, and encumbrances",
            instructions=(
                "The title report will be ordered through the title company. No "
                "action is typically needed from you. If there are title issues "
                "(liens, judgments, boundary disputes), you may be asked to provide "
                "additional documentation to clear title."
            ),
            category="property",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason="Title report required to verify clear title and identify any encumbrances",
        ))

        # Homeowners insurance
        reqs.append(RequiredDocument(
            doc_type=DocType.HOMEOWNERS_INSURANCE.value,
            title="Homeowners Insurance Policy / Binder",
            description=(
                "Evidence of homeowners insurance coverage with the lender listed "
                "as mortgagee"
            ),
            instructions=(
                "Please obtain a homeowners insurance policy for the subject property "
                "and provide the insurance binder or declarations page. The policy "
                "must: (1) List the lender as mortgagee, (2) Show coverage amount at "
                "least equal to the loan amount or replacement cost, (3) Show the "
                "property address, (4) Show the effective date (must be on or before "
                "closing). Contact your insurance agent and provide them the lender's "
                "mortgagee clause."
            ),
            category="property",
            priority=RequestPriority.HIGH.value,
            applies_to=AppliesTo.BORROWER.value,
            required_count=1,
            freshness_days=None,
            auto_renew=False,
            payroll_frequency=None,
            reason=(
                "Homeowners insurance with mortgagee clause is required prior to "
                "closing per lender requirements and investor guidelines"
            ),
        ))

        # Condo-specific: HOA questionnaire / condo docs
        if property_type == "CONDO":
            reqs.append(RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="Condominium Questionnaire / HOA Documents",
                description=(
                    "Completed condo questionnaire and HOA documents including "
                    "budget, reserves, and insurance"
                ),
                instructions=(
                    "The lender will send a condo questionnaire to the HOA management "
                    "company. The following may be needed from you: (1) HOA contact "
                    "information and management company details, (2) Most recent HOA "
                    "budget and reserve study, (3) HOA master insurance policy "
                    "declarations page, (4) CC&Rs (Covenants, Conditions & "
                    "Restrictions). Fannie Mae/Freddie Mac have specific project "
                    "eligibility requirements for condos."
                ),
                category="property",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Condo projects must meet agency warrantability requirements "
                    "(FNMA B4-2.1) including reserve adequacy and insurance coverage"
                ),
            ))

        # Multi-family: rental income documentation
        if property_type == "MULTI_FAMILY":
            reqs.append(RequiredDocument(
                doc_type=DocType.LEASE_AGREEMENT.value,
                title="Lease Agreements for Rental Units",
                description="Current signed leases for all non-owner-occupied units",
                instructions=(
                    "For each rental unit in the property, please provide the current "
                    "signed lease agreement showing: tenant name, monthly rent amount, "
                    "lease start/end dates. If any units are vacant, note which units "
                    "and provide a market rent analysis or comparable rent survey."
                ),
                category="property",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Lease agreements required for multi-family properties to verify "
                    "rental income used in qualifying per FNMA B3-3.1-08"
                ),
            ))

        return reqs

    def _get_credit_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Credit-related document requirements.

        Bankruptcy history: Discharge papers
        Credit issues in notes: Letter of Explanation
        """
        reqs: List[RequiredDocument] = []
        notes_raw = (loan_data.get("notes") or "").lower()

        # Bankruptcy discharge papers
        if loan_data.get("has_bankruptcy"):
            reqs.append(RequiredDocument(
                doc_type=DocType.BANKRUPTCY_DISCHARGE.value,
                title="Bankruptcy Discharge Papers",
                description=(
                    "Complete bankruptcy discharge order including petition, "
                    "schedules, and discharge date"
                ),
                instructions=(
                    "Please provide the complete bankruptcy documentation including: "
                    "(1) Bankruptcy petition (showing filing date and chapter), "
                    "(2) Schedule of debts, (3) Discharge order from the court, "
                    "(4) If Chapter 13: payment plan, trustee letter confirming "
                    "satisfactory payment history, and proof of all payments made. "
                    "Note: Waiting period requirements vary by loan program: "
                    "Conventional (Ch 7: 4 years, Ch 13: 2 years from discharge), "
                    "FHA (Ch 7: 2 years, Ch 13: 1 year with trustee approval), "
                    "VA (Ch 7: 2 years, Ch 13: 1 year)."
                ),
                category="credit",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Bankruptcy documentation required to verify discharge date and "
                    "calculate waiting period eligibility"
                ),
            ))

        # Letter of Explanation for credit issues
        credit_issue_keywords = [
            "late payment", "collection", "judgment", "charge off",
            "short sale", "foreclosure", "deed in lieu", "credit issue",
            "credit problem", "credit dispute", "medical bill", "tax lien",
            "student loan default", "repossession",
        ]
        has_credit_issues = any(kw in notes_raw for kw in credit_issue_keywords)

        if has_credit_issues:
            reqs.append(RequiredDocument(
                doc_type=DocType.LOE.value,
                title="Letter of Explanation - Credit Issues",
                description=(
                    "Written explanation for credit report derogatory items "
                    "(late payments, collections, judgments, etc.)"
                ),
                instructions=(
                    "Please provide a signed and dated letter explaining any "
                    "negative items on your credit report. For each item, address: "
                    "(1) What happened and why, (2) When it occurred, (3) The current "
                    "status (paid, settled, in dispute), (4) What steps you have taken "
                    "to prevent recurrence. Be specific with dates and amounts. "
                    "Supporting documentation (payment receipts, settlement letters) "
                    "is helpful but not required."
                ),
                category="credit",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Credit explanation letters are required by underwriting for any "
                    "derogatory credit items identified on the credit report"
                ),
            ))

        # Housing payment history for borrowers with no mortgage tradeline
        first_time = loan_data.get("first_time_buyer", False)
        if first_time:
            reqs.append(RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="Rental Payment History / VOR",
                description=(
                    "Verification of rent payments for the past 12 months "
                    "(cancelled checks, bank statements, or landlord letter)"
                ),
                instructions=(
                    "As a first-time homebuyer, please provide proof of your rental "
                    "payment history for the past 12 months. Acceptable documentation "
                    "includes: (1) Cancelled rent checks or bank statements showing "
                    "monthly rent payments, (2) Written verification from your "
                    "landlord (VOR) on letterhead, or (3) Third-party rent payment "
                    "verification service report."
                ),
                category="credit",
                priority=RequestPriority.NORMAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Housing payment history demonstrates payment reliability when "
                    "no mortgage tradeline exists on credit report"
                ),
            ))

        return reqs

    def _get_special_requirements(self, loan_data: Dict) -> List[RequiredDocument]:
        """
        Program-specific and special circumstance document requirements.

        FHA: FHA case number certification
        VA: (Handled in identity - COE, DD214)
        USDA: Eligibility verification
        Jumbo: Additional asset documentation (handled in assets)
        Investment property: Lease agreements
        Non-QM: Bank statements for income qualification
        """
        reqs: List[RequiredDocument] = []
        program = loan_data.get("program_type", "CONVENTIONAL")
        occupancy = loan_data.get("occupancy_normalized", "PRIMARY")
        notes_raw = (loan_data.get("notes") or "").lower()

        # FHA-specific
        if program == "FHA":
            reqs.append(RequiredDocument(
                doc_type=DocType.FHA_CERT.value,
                title="FHA Case Number Assignment",
                description=(
                    "FHA case number certification confirming the borrower's "
                    "eligibility for FHA financing"
                ),
                instructions=(
                    "The FHA case number will be assigned by the lender through "
                    "FHA Connection. This is tracked for compliance purposes. If you "
                    "have had a prior FHA loan, please notify your loan officer so "
                    "we can verify UFMIP refund eligibility and prior case status."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason="FHA case number required for FHA-insured mortgage processing",
            ))

            # FHA requires full 2-year employment history documentation
            reqs.append(RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="FHA Employment History Verification",
                description=(
                    "Documentation verifying 2-year employment history including "
                    "any gaps in employment"
                ),
                instructions=(
                    "FHA requires a documented 2-year employment history. If you "
                    "have any gaps in employment exceeding 30 days during the past "
                    "2 years, please provide a signed letter explaining the gap, "
                    "including dates and reason. If you changed employers, provide "
                    "documentation from each employer."
                ),
                category="special",
                priority=RequestPriority.NORMAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "FHA Handbook 4000.1 requires documented 2-year employment "
                    "history with explanations for any gaps"
                ),
            ))

        # USDA-specific
        if program == "USDA":
            reqs.append(RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="USDA Property Eligibility Verification",
                description=(
                    "Verification that the property is in a USDA-eligible rural area "
                    "and household income meets USDA limits"
                ),
                instructions=(
                    "The lender will verify property eligibility through the USDA "
                    "eligibility map. You may be asked to provide: (1) Documentation "
                    "of all household income (including non-borrower household "
                    "members over 18), (2) Verification that the property address is "
                    "in an eligible rural area. Note: USDA counts ALL household "
                    "income, not just borrower income, for eligibility."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "USDA Rural Development loans require property eligibility and "
                    "household income verification per RD Handbook HB-1-3555"
                ),
            ))

            # USDA requires household income documentation (all adults)
            reqs.append(RequiredDocument(
                doc_type=DocType.OTHER.value,
                title="Household Income Documentation",
                description=(
                    "Income documentation for all adult household members, "
                    "including non-borrower residents"
                ),
                instructions=(
                    "USDA requires documentation of income for ALL adult household "
                    "members (age 18+), even those not on the loan. For each adult "
                    "in the household, provide: (1) Most recent pay stub or income "
                    "documentation, (2) Most recent tax return, (3) If no income, "
                    "a signed statement confirming no income. This is used to verify "
                    "household income does not exceed USDA limits for your area."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BOTH.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "USDA household income limit verification requires all adult "
                    "household member income documentation"
                ),
            ))

        # Non-QM specific (bank statement programs)
        if program == "NON_QM":
            reqs.append(RequiredDocument(
                doc_type=DocType.BANK_STATEMENT.value,
                title="Bank Statements for Income Qualification (12-24 Months)",
                description=(
                    "12-24 months of personal or business bank statements for "
                    "Non-QM income qualification"
                ),
                instructions=(
                    "Non-QM bank statement programs use bank deposits to qualify "
                    "income instead of tax returns. Please provide: (1) 12 or 24 "
                    "consecutive months of bank statements (program dependent), "
                    "(2) All pages of each statement, (3) Use the account that "
                    "receives your primary business or personal income deposits. "
                    "If using business bank statements, also provide a business "
                    "license or CPA letter confirming business ownership."
                ),
                category="special",
                priority=RequestPriority.CRITICAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=12,
                freshness_days=90,
                auto_renew=True,
                payroll_frequency=None,
                reason=(
                    "Non-QM bank statement programs use deposit history as primary "
                    "income documentation in lieu of tax returns"
                ),
            ))

        # Investment property
        if occupancy == "INVESTMENT":
            reqs.append(RequiredDocument(
                doc_type=DocType.LEASE_AGREEMENT.value,
                title="Current Lease Agreements",
                description=(
                    "Signed lease agreements for the subject investment property "
                    "(if currently rented or if rental income will be used)"
                ),
                instructions=(
                    "If the investment property is currently rented or will be "
                    "rented, please provide: (1) Current signed lease agreement, "
                    "(2) If no lease exists, a market rent analysis or comparable "
                    "rent survey from a property manager or appraiser. The lease "
                    "should show tenant names, monthly rent, and lease term."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Lease agreements verify rental income for investment property "
                    "qualification and PITIA offset calculation"
                ),
            ))

            # Tax returns with Schedule E for existing rental properties
            reqs.append(RequiredDocument(
                doc_type=DocType.TAX_RETURN.value,
                title="Tax Returns with Schedule E (Rental Income)",
                description=(
                    "Personal tax returns including Schedule E showing rental income "
                    "and expenses from all investment properties"
                ),
                instructions=(
                    "Please provide your most recent 2 years of federal tax returns "
                    "including Schedule E (Supplemental Income and Loss). This "
                    "documents the net rental income from all investment properties "
                    "you own. Include all pages and attachments."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=2,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Schedule E from tax returns required to net rental income from "
                    "existing investment properties per FNMA B3-3.1-08"
                ),
            ))

            # Reserve requirements for investment property
            reqs.append(RequiredDocument(
                doc_type=DocType.BANK_STATEMENT.value,
                title="Reserve Verification (Investment Property)",
                description=(
                    "Bank/investment statements showing sufficient reserves "
                    "(typically 6 months PITIA for each financed property)"
                ),
                instructions=(
                    "Investment property loans require verified reserves. Please "
                    "provide current statements for accounts showing sufficient "
                    "liquid reserves. Typical requirement: 6 months of PITIA "
                    "(Principal, Interest, Taxes, Insurance, HOA) for the subject "
                    "property, plus 2 months for each additional financed property."
                ),
                category="special",
                priority=RequestPriority.HIGH.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=60,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Reserve verification required for investment property per "
                    "FNMA B3-4.1 (6 months PITIA minimum)"
                ),
            ))

        # Rental income from notes (existing properties, not just subject property)
        has_rental = any(
            kw in notes_raw
            for kw in ("rental income", "rental property", "landlord", "schedule e")
        )
        if has_rental and occupancy != "INVESTMENT":
            # Avoid duplicate if already added via investment path
            reqs.append(RequiredDocument(
                doc_type=DocType.LEASE_AGREEMENT.value,
                title="Lease Agreements for Existing Rental Properties",
                description="Current lease agreements for any properties borrower rents out",
                instructions=(
                    "Please provide signed lease agreements for all properties you "
                    "own and rent out. Include current leases for each property. If "
                    "you have a property management company, a management agreement "
                    "and rent roll is also helpful."
                ),
                category="special",
                priority=RequestPriority.NORMAL.value,
                applies_to=AppliesTo.BORROWER.value,
                required_count=1,
                freshness_days=None,
                auto_renew=False,
                payroll_frequency=None,
                reason=(
                    "Lease agreements needed to verify rental income from existing "
                    "properties listed in the application"
                ),
            ))

        return reqs

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    def _deduplicate_requirements(
        self,
        requirements: List[RequiredDocument],
    ) -> List[RequiredDocument]:
        """
        Remove duplicate requirements. When the same (doc_type, applies_to)
        appears multiple times, keep the one with the highest priority.
        For OTHER doc type, deduplicate by (doc_type, applies_to, title)
        since OTHER is used for multiple distinct document types.
        """
        priority_order = {
            RequestPriority.CRITICAL.value: 4,
            RequestPriority.HIGH.value: 3,
            RequestPriority.NORMAL.value: 2,
            RequestPriority.LOW.value: 1,
        }

        seen: Dict[str, RequiredDocument] = {}

        for req in requirements:
            # For OTHER type, use title as part of the dedup key
            if req.doc_type == DocType.OTHER.value:
                key = f"{req.doc_type}:{req.applies_to}:{req.title}"
            else:
                key = f"{req.doc_type}:{req.applies_to}"

            if key not in seen:
                seen[key] = req
            else:
                existing = seen[key]
                existing_priority = priority_order.get(existing.priority, 0)
                new_priority = priority_order.get(req.priority, 0)
                if new_priority > existing_priority:
                    seen[key] = req
                elif new_priority == existing_priority:
                    # Keep the one with more required_count
                    if req.required_count > existing.required_count:
                        seen[key] = req

        return list(seen.values())


# =============================================================================
# SINGLETON FACTORY
# =============================================================================

def get_pos_analyzer_service(db: Session) -> POSAnalyzerService:
    """Factory function to create a POSAnalyzerService instance."""
    return POSAnalyzerService(db)
