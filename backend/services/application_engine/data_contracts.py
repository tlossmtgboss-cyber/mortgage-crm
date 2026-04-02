"""
Data Contracts for Application Engine

Standardized input/output formats for application audit modules.
All data flows through these contracts for consistency and auditability.

Flow: Call Transcript → AI Extraction → ExtractedData → Audit Modules → AuditResponse
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Union


# =============================================================================
# ENUMS
# =============================================================================

class AuditModuleType(str, Enum):
    """Types of audit modules in the Application Engine."""
    IDENTITY = "identity"
    ADDRESS = "address"
    EMPLOYMENT = "employment"
    INCOME = "income"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    REO = "reo"  # Real Estate Owned
    DECLARATIONS = "declarations"


class AuditStatus(str, Enum):
    """Status of an audit result."""
    COMPLETE = "complete"          # All required data collected
    INCOMPLETE = "incomplete"      # Missing required data
    NEEDS_REVIEW = "needs_review"  # Data conflicts or anomalies
    ERROR = "error"                # Processing error


class FieldStatus(str, Enum):
    """Status of an individual field."""
    VERIFIED = "verified"       # Confirmed by borrower
    EXTRACTED = "extracted"     # AI-extracted, not confirmed
    MISSING = "missing"         # Not provided
    CONFLICTING = "conflicting" # Multiple conflicting values
    INVALID = "invalid"         # Failed validation


class TaskPriority(str, Enum):
    """Priority levels for generated tasks."""
    CRITICAL = "critical"  # Blocking - must resolve before proceeding
    HIGH = "high"          # Important - should resolve soon
    MEDIUM = "medium"      # Normal priority
    LOW = "low"            # Nice to have


class TaskAssignee(str, Enum):
    """Task assignee types."""
    BORROWER = "borrower"     # Task for borrower portal
    PA = "pa"                 # Production Assistant
    LO = "lo"                 # Loan Officer
    PROCESSOR = "processor"
    UNDERWRITER = "underwriter"


class ConfidenceLevel(str, Enum):
    """AI extraction confidence level."""
    HIGH = "high"      # 90%+ confidence
    MEDIUM = "medium"  # 70-90% confidence
    LOW = "low"        # <70% confidence


# =============================================================================
# BASE EXTRACTED DATA
# =============================================================================

@dataclass
class ExtractedField:
    """A single extracted field with metadata."""
    field_name: str
    value: Any
    status: FieldStatus = FieldStatus.EXTRACTED
    confidence: float = 0.0  # 0-100
    source: str = ""  # "call_transcript", "document", "user_input"
    extracted_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verification_method: Optional[str] = None  # "voice_confirm", "document_match"
    conflicts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "status": self.status.value,
            "confidence": self.confidence,
            "source": self.source,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


# =============================================================================
# IDENTITY MODULE DATA
# =============================================================================

@dataclass
class IdentityData:
    """Identity information for a borrower."""
    borrower_type: str = "primary"  # "primary", "co_borrower"

    # Basic Identity
    first_name: Optional[ExtractedField] = None
    middle_name: Optional[ExtractedField] = None
    last_name: Optional[ExtractedField] = None
    suffix: Optional[ExtractedField] = None

    # Date of Birth
    date_of_birth: Optional[ExtractedField] = None

    # SSN
    ssn: Optional[ExtractedField] = None  # Stored as last 4 only
    ssn_full_collected: bool = False  # Flag if full SSN collected securely

    # Contact
    email: Optional[ExtractedField] = None
    phone_primary: Optional[ExtractedField] = None
    phone_secondary: Optional[ExtractedField] = None
    preferred_contact_method: Optional[str] = None

    # Citizenship
    citizenship_status: Optional[ExtractedField] = None  # US_CITIZEN, PERMANENT_RESIDENT, NON_PERMANENT
    visa_type: Optional[ExtractedField] = None
    visa_expiration: Optional[ExtractedField] = None

    # Marital Status
    marital_status: Optional[ExtractedField] = None  # SINGLE, MARRIED, SEPARATED, DIVORCED, WIDOWED

    # Demographics (HMDA)
    ethnicity: Optional[ExtractedField] = None
    race: Optional[ExtractedField] = None
    sex: Optional[ExtractedField] = None

    # Military
    military_status: Optional[ExtractedField] = None  # NONE, ACTIVE, VETERAN, RESERVE, SURVIVING_SPOUSE

    def get_completion_percentage(self) -> float:
        """Calculate completion percentage of required fields."""
        required = ["first_name", "last_name", "date_of_birth", "ssn",
                   "email", "phone_primary", "citizenship_status"]
        completed = sum(1 for f in required if getattr(self, f) and
                       getattr(self, f).status != FieldStatus.MISSING)
        return (completed / len(required)) * 100


@dataclass
class AddressData:
    """Address information."""
    address_type: str = "current"  # "current", "mailing", "previous"

    street_line_1: Optional[ExtractedField] = None
    street_line_2: Optional[ExtractedField] = None
    city: Optional[ExtractedField] = None
    state: Optional[ExtractedField] = None
    zip_code: Optional[ExtractedField] = None
    county: Optional[ExtractedField] = None
    country: Optional[ExtractedField] = None

    # Residency details
    ownership_status: Optional[ExtractedField] = None  # OWN, RENT, LIVING_RENT_FREE
    monthly_payment: Optional[ExtractedField] = None  # Rent or mortgage
    years_at_address: Optional[ExtractedField] = None
    months_at_address: Optional[ExtractedField] = None
    move_in_date: Optional[ExtractedField] = None


# =============================================================================
# EMPLOYMENT MODULE DATA
# =============================================================================

@dataclass
class EmploymentData:
    """Employment information for a single employer."""
    employment_type: str = "current"  # "current", "previous", "secondary"

    employer_name: Optional[ExtractedField] = None
    employer_address: Optional[ExtractedField] = None
    employer_phone: Optional[ExtractedField] = None

    position_title: Optional[ExtractedField] = None
    employment_status: Optional[ExtractedField] = None  # EMPLOYED, SELF_EMPLOYED, RETIRED, OTHER

    start_date: Optional[ExtractedField] = None
    end_date: Optional[ExtractedField] = None  # For previous employment
    years_employed: Optional[ExtractedField] = None
    months_employed: Optional[ExtractedField] = None

    # Self-employment details
    is_self_employed: bool = False
    business_name: Optional[ExtractedField] = None
    business_type: Optional[ExtractedField] = None  # SOLE_PROP, LLC, CORP, PARTNERSHIP
    ownership_percentage: Optional[ExtractedField] = None
    business_phone: Optional[ExtractedField] = None


# =============================================================================
# INCOME MODULE DATA
# =============================================================================

@dataclass
class IncomeSourceData:
    """Individual income source."""
    income_type: str = ""  # BASE, OVERTIME, BONUS, COMMISSION, SELF_EMPLOYMENT, RENTAL, etc.

    employer_or_source: Optional[ExtractedField] = None
    monthly_amount: Optional[ExtractedField] = None
    annual_amount: Optional[ExtractedField] = None

    frequency: Optional[str] = None  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY, ANNUAL

    # For variable income
    is_variable: bool = False
    years_history: Optional[int] = None
    trending: Optional[str] = None  # INCREASING, STABLE, DECLINING

    # Documentation status
    documentation_type: Optional[str] = None  # PAYSTUB, W2, TAX_RETURN, BANK_STATEMENT
    documents_collected: List[str] = field(default_factory=list)


@dataclass
class IncomeData:
    """Complete income profile for a borrower."""
    borrower_type: str = "primary"

    income_sources: List[IncomeSourceData] = field(default_factory=list)

    # Totals
    total_monthly_income: Optional[Decimal] = None
    total_annual_income: Optional[Decimal] = None

    # Documentation requirements identified
    required_documents: List[str] = field(default_factory=list)


# =============================================================================
# ASSETS MODULE DATA
# =============================================================================

@dataclass
class AssetData:
    """Individual asset account."""
    asset_type: str = ""  # CHECKING, SAVINGS, MONEY_MARKET, CD, STOCKS, RETIREMENT, OTHER

    institution_name: Optional[ExtractedField] = None
    account_number_last4: Optional[ExtractedField] = None

    current_balance: Optional[ExtractedField] = None

    # For retirement/stocks
    is_vested: Optional[bool] = None
    vested_amount: Optional[ExtractedField] = None

    # Gift funds
    is_gift: bool = False
    gift_donor_name: Optional[ExtractedField] = None
    gift_donor_relationship: Optional[ExtractedField] = None

    # Documentation
    months_statements_needed: int = 2


@dataclass
class AssetsData:
    """Complete assets profile."""
    borrower_type: str = "primary"

    assets: List[AssetData] = field(default_factory=list)

    # Totals
    total_liquid_assets: Optional[Decimal] = None
    total_retirement_assets: Optional[Decimal] = None
    total_gift_funds: Optional[Decimal] = None

    # Down payment source
    down_payment_source: Optional[str] = None
    down_payment_amount: Optional[Decimal] = None


# =============================================================================
# LIABILITIES MODULE DATA
# =============================================================================

@dataclass
class LiabilityData:
    """Individual liability/debt."""
    liability_type: str = ""  # MORTGAGE, INSTALLMENT, REVOLVING, STUDENT_LOAN, AUTO, OTHER

    creditor_name: Optional[ExtractedField] = None
    account_number_last4: Optional[ExtractedField] = None

    current_balance: Optional[ExtractedField] = None
    monthly_payment: Optional[ExtractedField] = None

    # Payoff details
    will_be_paid_off: bool = False
    paid_by_closing: bool = False
    months_remaining: Optional[int] = None

    # For mortgages
    property_address: Optional[str] = None
    is_subject_property: bool = False


@dataclass
class LiabilitiesData:
    """Complete liabilities profile."""
    borrower_type: str = "primary"

    liabilities: List[LiabilityData] = field(default_factory=list)

    # Totals
    total_monthly_payments: Optional[Decimal] = None
    total_balances: Optional[Decimal] = None

    # Payoff at closing
    payoffs_at_closing: List[str] = field(default_factory=list)
    total_payoff_amount: Optional[Decimal] = None


# =============================================================================
# REO (REAL ESTATE OWNED) MODULE DATA
# =============================================================================

@dataclass
class RealEstateData:
    """Individual real estate property owned."""
    property_address: Optional[ExtractedField] = None
    property_type: Optional[ExtractedField] = None  # SFR, CONDO, MULTI_UNIT, etc.

    current_value: Optional[ExtractedField] = None

    # Mortgage details
    has_mortgage: bool = True
    mortgage_balance: Optional[ExtractedField] = None
    mortgage_payment: Optional[ExtractedField] = None
    lender_name: Optional[ExtractedField] = None

    # Usage
    usage_type: Optional[ExtractedField] = None  # PRIMARY, INVESTMENT, SECOND_HOME

    # Rental income
    is_rental: bool = False
    monthly_rent: Optional[ExtractedField] = None

    # Disposition
    will_be_sold: bool = False
    will_be_retained: bool = True
    pending_sale: bool = False


@dataclass
class REOData:
    """Complete real estate owned profile."""
    borrower_type: str = "primary"

    properties: List[RealEstateData] = field(default_factory=list)

    # Summary
    total_property_value: Optional[Decimal] = None
    total_mortgage_balance: Optional[Decimal] = None
    total_monthly_payments: Optional[Decimal] = None
    total_rental_income: Optional[Decimal] = None


# =============================================================================
# DECLARATIONS MODULE DATA
# =============================================================================

@dataclass
class DeclarationData:
    """URLA declarations (yes/no questions)."""
    # Section J - About This Property and Your Money for This Loan
    will_occupy_as_primary: Optional[ExtractedField] = None
    has_ownership_interest_3yrs: Optional[ExtractedField] = None
    has_family_relationship_seller: Optional[ExtractedField] = None
    borrowing_money_for_transaction: Optional[ExtractedField] = None
    applying_for_other_mortgage: Optional[ExtractedField] = None
    applying_for_other_credit: Optional[ExtractedField] = None
    subject_to_lien: Optional[ExtractedField] = None

    # Section K - About Your Finances
    is_co_signer: Optional[ExtractedField] = None
    has_outstanding_judgments: Optional[ExtractedField] = None
    is_delinquent_federal_debt: Optional[ExtractedField] = None
    is_party_to_lawsuit: Optional[ExtractedField] = None
    has_conveyed_title_lieu: Optional[ExtractedField] = None
    has_preforeclosure_short_sale: Optional[ExtractedField] = None
    has_foreclosure: Optional[ExtractedField] = None
    has_bankruptcy: Optional[ExtractedField] = None
    bankruptcy_chapter: Optional[str] = None
    bankruptcy_discharge_date: Optional[date] = None

    # If any "yes" answers
    explanation_notes: Dict[str, str] = field(default_factory=dict)


# =============================================================================
# TASK GENERATION
# =============================================================================

@dataclass
class GeneratedTask:
    """Task generated by audit modules."""
    task_id: Optional[str] = None

    title: str = ""
    description: str = ""

    task_type: str = ""  # COLLECT_DOCUMENT, VERIFY_INFO, RESOLVE_CONFLICT, etc.
    assignee: TaskAssignee = TaskAssignee.PA
    priority: TaskPriority = TaskPriority.MEDIUM

    # Context
    module: AuditModuleType = AuditModuleType.IDENTITY
    field_name: Optional[str] = None
    borrower_type: str = "primary"

    # Document requirements
    required_document_type: Optional[str] = None
    document_checklist_item_id: Optional[int] = None

    # Due date calculation
    days_until_due: int = 3
    due_date: Optional[datetime] = None

    # Portal display
    borrower_portal_visible: bool = False
    borrower_instructions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "assignee": self.assignee.value,
            "priority": self.priority.value,
            "module": self.module.value,
            "field_name": self.field_name,
            "borrower_type": self.borrower_type,
            "required_document_type": self.required_document_type,
            "days_until_due": self.days_until_due,
            "borrower_portal_visible": self.borrower_portal_visible,
            "borrower_instructions": self.borrower_instructions,
        }


# =============================================================================
# AUDIT RESULTS
# =============================================================================

@dataclass
class AuditResult:
    """Result from a single audit module."""
    module: AuditModuleType
    status: AuditStatus

    # Completion metrics
    fields_total: int = 0
    fields_complete: int = 0
    fields_missing: int = 0
    fields_conflicting: int = 0
    completion_percentage: float = 0.0

    # The extracted data
    data: Any = None  # Module-specific data class

    # Generated tasks
    tasks: List[GeneratedTask] = field(default_factory=list)

    # Issues and notes
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Processing metadata
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processing_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module.value,
            "status": self.status.value,
            "fields_total": self.fields_total,
            "fields_complete": self.fields_complete,
            "fields_missing": self.fields_missing,
            "fields_conflicting": self.fields_conflicting,
            "completion_percentage": self.completion_percentage,
            "tasks_count": len(self.tasks),
            "issues": self.issues,
            "warnings": self.warnings,
            "processed_at": self.processed_at.isoformat(),
        }


# =============================================================================
# ORCHESTRATOR REQUEST/RESPONSE
# =============================================================================

@dataclass
class CallTranscriptData:
    """Data extracted from a call transcript by Call Intelligence."""
    call_id: str
    call_type: str = ""  # "initial_intake", "follow_up", "document_review"
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Extracted sections by module
    identity_extractions: Dict[str, Any] = field(default_factory=dict)
    address_extractions: Dict[str, Any] = field(default_factory=dict)
    employment_extractions: Dict[str, Any] = field(default_factory=dict)
    income_extractions: Dict[str, Any] = field(default_factory=dict)
    assets_extractions: Dict[str, Any] = field(default_factory=dict)
    liabilities_extractions: Dict[str, Any] = field(default_factory=dict)
    reo_extractions: Dict[str, Any] = field(default_factory=dict)
    declarations_extractions: Dict[str, Any] = field(default_factory=dict)

    # Confidence scores
    extraction_confidence: Dict[str, float] = field(default_factory=dict)

    # Raw transcript reference
    transcript_segments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ApplicationAuditRequest:
    """Request to audit application data."""
    loan_id: int
    organization_id: int

    # Call data to process
    call_data: Optional[CallTranscriptData] = None

    # Existing application data (from database)
    existing_data: Dict[str, Any] = field(default_factory=dict)

    # Options
    modules_to_run: List[AuditModuleType] = field(default_factory=lambda: list(AuditModuleType))
    generate_tasks: bool = True
    include_guideline_recommendations: bool = True

    # Context
    loan_type: Optional[str] = None  # CONVENTIONAL, FHA, VA, USDA
    property_type: Optional[str] = None


@dataclass
class ApplicationAuditResponse:
    """Response from application audit."""
    loan_id: int

    # Overall status
    overall_status: AuditStatus = AuditStatus.INCOMPLETE
    overall_completion: float = 0.0

    # Module results
    module_results: Dict[AuditModuleType, AuditResult] = field(default_factory=dict)

    # Aggregated tasks
    all_tasks: List[GeneratedTask] = field(default_factory=list)
    borrower_tasks: List[GeneratedTask] = field(default_factory=list)
    pa_tasks: List[GeneratedTask] = field(default_factory=list)

    # Document requirements from Guideline Intelligence
    document_recommendations: List[Dict[str, Any]] = field(default_factory=list)

    # Summary counts
    total_fields: int = 0
    complete_fields: int = 0
    missing_fields: int = 0
    conflicting_fields: int = 0

    # Processing metadata
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "overall_status": self.overall_status.value,
            "overall_completion": self.overall_completion,
            "module_results": {
                k.value: v.to_dict() for k, v in self.module_results.items()
            },
            "tasks_summary": {
                "total": len(self.all_tasks),
                "borrower": len(self.borrower_tasks),
                "pa": len(self.pa_tasks),
            },
            "field_summary": {
                "total": self.total_fields,
                "complete": self.complete_fields,
                "missing": self.missing_fields,
                "conflicting": self.conflicting_fields,
            },
            "document_recommendations": self.document_recommendations,
            "processed_at": self.processed_at.isoformat(),
            "total_duration_ms": self.total_duration_ms,
        }
