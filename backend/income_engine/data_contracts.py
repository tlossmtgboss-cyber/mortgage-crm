"""
Data Contracts for Income Intelligence Engine

Standardized input/output formats for income calculation.
All data flows through these contracts for consistency and auditability.

Flow: Raw Documents → AI Extraction → DocumentFacts → Engines → CalculationResponse
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any


# =============================================================================
# ENUMS
# =============================================================================

class IncomeStreamType(str, Enum):
    """Types of income streams processed by engines."""
    W2_BASE = "W2_BASE"
    W2_OVERTIME = "W2_OVERTIME"
    W2_BONUS = "W2_BONUS"
    W2_COMMISSION = "W2_COMMISSION"
    SCHEDULE_C = "SCHEDULE_C"
    SCHEDULE_E_RENTAL = "SCHEDULE_E_RENTAL"
    K1_PARTNERSHIP = "K1_PARTNERSHIP"
    K1_SCORP = "K1_SCORP"
    K1_CCORP = "K1_CCORP"
    BANK_STATEMENT = "BANK_STATEMENT"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    PENSION = "PENSION"
    ALIMONY = "ALIMONY"
    CHILD_SUPPORT = "CHILD_SUPPORT"
    OTHER = "OTHER"


class FlagSeverity(str, Enum):
    """Severity levels for calculation flags."""
    INFO = "INFO"           # Informational only
    WARNING = "WARNING"     # Potential issue, requires review
    ERROR = "ERROR"         # Calculation issue, needs resolution
    BLOCKING = "BLOCKING"   # Cannot proceed without resolution


class TrendDirection(str, Enum):
    """Income trending direction."""
    INCREASING = "INCREASING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"


# =============================================================================
# BASE DOCUMENT FACTS (Common fields)
# =============================================================================

@dataclass
class DocumentFacts:
    """Base class for all document fact extractions."""
    document_id: str
    document_type: str
    extraction_date: datetime
    confidence_score: float  # 0-100
    source_file_name: Optional[str] = None
    extraction_warnings: List[str] = field(default_factory=list)


# =============================================================================
# W-2 FACTS
# =============================================================================

@dataclass
class W2Facts(DocumentFacts):
    """Facts extracted from W-2 forms."""
    tax_year: int = 0
    employer_name: str = ""
    employer_ein: Optional[str] = None
    employer_address: Optional[str] = None

    # Box values
    box1_wages: Decimal = Decimal("0")           # Wages, tips, other compensation
    box2_federal_tax: Decimal = Decimal("0")     # Federal income tax withheld
    box3_social_security_wages: Decimal = Decimal("0")
    box4_social_security_tax: Decimal = Decimal("0")
    box5_medicare_wages: Decimal = Decimal("0")
    box6_medicare_tax: Decimal = Decimal("0")

    # Additional boxes
    box12_codes: Dict[str, Decimal] = field(default_factory=dict)  # e.g., {"D": 5000, "DD": 1200}
    box14_other: Dict[str, Decimal] = field(default_factory=dict)

    # Employee info
    employee_name: Optional[str] = None
    employee_ssn_last4: Optional[str] = None

    def __post_init__(self):
        self.document_type = "W2"


# =============================================================================
# PAYSTUB FACTS
# =============================================================================

@dataclass
class PaystubFacts(DocumentFacts):
    """Facts extracted from paystubs."""
    pay_date: Optional[date] = None
    pay_period_start: Optional[date] = None
    pay_period_end: Optional[date] = None
    pay_frequency: str = ""  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY

    employer_name: str = ""
    employer_ein: Optional[str] = None

    # Current period earnings
    gross_pay: Decimal = Decimal("0")
    net_pay: Decimal = Decimal("0")
    regular_hours: Optional[Decimal] = None
    overtime_hours: Optional[Decimal] = None
    hourly_rate: Optional[Decimal] = None
    regular_earnings: Decimal = Decimal("0")
    overtime_earnings: Decimal = Decimal("0")
    bonus_earnings: Decimal = Decimal("0")
    commission_earnings: Decimal = Decimal("0")
    tips: Decimal = Decimal("0")
    other_earnings: Decimal = Decimal("0")

    # YTD totals
    ytd_gross: Decimal = Decimal("0")
    ytd_regular: Decimal = Decimal("0")
    ytd_overtime: Decimal = Decimal("0")
    ytd_bonus: Decimal = Decimal("0")
    ytd_commission: Decimal = Decimal("0")

    # Deductions
    federal_tax_withheld: Decimal = Decimal("0")
    state_tax_withheld: Decimal = Decimal("0")
    social_security: Decimal = Decimal("0")
    medicare: Decimal = Decimal("0")
    retirement_401k: Decimal = Decimal("0")

    # Employee info
    employee_name: Optional[str] = None
    hire_date: Optional[date] = None

    def __post_init__(self):
        self.document_type = "PAYSTUB"


# =============================================================================
# SCHEDULE C FACTS (Self-Employment)
# =============================================================================

@dataclass
class ScheduleCFacts(DocumentFacts):
    """Facts extracted from Schedule C (Profit or Loss from Business)."""
    tax_year: int = 0
    business_name: Optional[str] = None
    business_code: Optional[str] = None  # Principal business code

    # Part I - Income
    line1_gross_receipts: Decimal = Decimal("0")
    line2_returns_allowances: Decimal = Decimal("0")
    line4_cost_of_goods_sold: Decimal = Decimal("0")
    line5_gross_profit: Decimal = Decimal("0")
    line6_other_income: Decimal = Decimal("0")
    line7_gross_income: Decimal = Decimal("0")

    # Part II - Expenses (key items for add-backs)
    line9_car_truck_expenses: Decimal = Decimal("0")
    line13_depreciation: Decimal = Decimal("0")
    line14_employee_benefit: Decimal = Decimal("0")
    line15_insurance: Decimal = Decimal("0")
    line16a_mortgage_interest: Decimal = Decimal("0")
    line18_office_expense: Decimal = Decimal("0")
    line20a_vehicle_rent_lease: Decimal = Decimal("0")
    line22_supplies: Decimal = Decimal("0")
    line24a_travel: Decimal = Decimal("0")
    line24b_meals: Decimal = Decimal("0")  # 50% deductible
    line25_utilities: Decimal = Decimal("0")
    line27a_other_expenses: Decimal = Decimal("0")
    line28_total_expenses: Decimal = Decimal("0")

    # Part III - COGS (if applicable)
    line33_cogs_inventory_start: Decimal = Decimal("0")
    line34_cogs_purchases: Decimal = Decimal("0")
    line35_cogs_cost_of_labor: Decimal = Decimal("0")
    line37_cogs_inventory_end: Decimal = Decimal("0")
    line42_cogs_total: Decimal = Decimal("0")

    # Part IV - Vehicle (for mileage add-back)
    line44a_vehicle_placed_in_service: Optional[date] = None
    line44b_vehicle_miles_business: Optional[int] = None
    line44c_vehicle_miles_commute: Optional[int] = None
    line44d_vehicle_miles_other: Optional[int] = None

    # Net profit/loss
    line31_net_profit_loss: Decimal = Decimal("0")

    # Form 8829 - Business Use of Home
    form_8829_deduction: Decimal = Decimal("0")
    form_8829_depreciation_portion: Decimal = Decimal("0")

    def __post_init__(self):
        self.document_type = "SCHEDULE_C"


# =============================================================================
# SCHEDULE E FACTS (Rental Income)
# =============================================================================

@dataclass
class RentalProperty:
    """Individual rental property from Schedule E."""
    property_address: str
    property_type: str  # SFR, CONDO, MULTI_2_4, etc.

    # Income
    rents_received: Decimal = Decimal("0")

    # Expenses
    advertising: Decimal = Decimal("0")
    auto_travel: Decimal = Decimal("0")
    cleaning_maintenance: Decimal = Decimal("0")
    commissions: Decimal = Decimal("0")
    insurance: Decimal = Decimal("0")
    legal_professional: Decimal = Decimal("0")
    management_fees: Decimal = Decimal("0")
    mortgage_interest: Decimal = Decimal("0")
    other_interest: Decimal = Decimal("0")
    repairs: Decimal = Decimal("0")
    supplies: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    utilities: Decimal = Decimal("0")
    depreciation: Decimal = Decimal("0")
    other_expenses: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")

    # Net income/loss
    net_income_loss: Decimal = Decimal("0")

    # Days rented/personal use
    days_rented: Optional[int] = None
    days_personal_use: Optional[int] = None

    # QBI deduction
    qbi_deduction: Decimal = Decimal("0")


@dataclass
class ScheduleEFacts(DocumentFacts):
    """Facts extracted from Schedule E (Supplemental Income and Loss)."""
    tax_year: int = 0

    # Part I - Rental properties (up to 3 per Schedule E page)
    properties: List[RentalProperty] = field(default_factory=list)

    # Totals from Part I
    total_rents_received: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    total_depreciation: Decimal = Decimal("0")
    total_net_income_loss: Decimal = Decimal("0")

    def __post_init__(self):
        self.document_type = "SCHEDULE_E"


# =============================================================================
# K-1 FACTS (Partnership, S-Corp, C-Corp)
# =============================================================================

@dataclass
class K1Facts(DocumentFacts):
    """Facts extracted from K-1 forms (1065, 1120S, 1120)."""
    tax_year: int = 0
    k1_type: str = ""  # "PARTNERSHIP", "SCORP", "CCORP"

    # Entity information
    entity_name: str = ""
    entity_ein: Optional[str] = None
    entity_address: Optional[str] = None

    # Partner/Shareholder information
    partner_name: Optional[str] = None
    partner_ssn_last4: Optional[str] = None
    ownership_percentage: Decimal = Decimal("0")  # 0-100

    # Partnership/S-Corp K-1 (Form 1065/1120S) key boxes
    box1_ordinary_income: Decimal = Decimal("0")
    box2_net_rental_income: Decimal = Decimal("0")
    box3_other_net_rental_income: Decimal = Decimal("0")
    box4_guaranteed_payments: Decimal = Decimal("0")
    box5_interest_income: Decimal = Decimal("0")
    box6_dividends: Decimal = Decimal("0")
    box7_royalties: Decimal = Decimal("0")
    box8_net_short_term_cap_gain: Decimal = Decimal("0")
    box9_net_long_term_cap_gain: Decimal = Decimal("0")
    box10_net_section_1231_gain: Decimal = Decimal("0")
    box11_other_income: Decimal = Decimal("0")

    # Section 179 deduction
    box12_section_179: Decimal = Decimal("0")

    # Other deductions
    box13_other_deductions: Decimal = Decimal("0")

    # Self-employment earnings (Partnership only)
    box14_self_employment: Decimal = Decimal("0")

    # Distributions (for liquidity analysis)
    distributions_cash: Decimal = Decimal("0")
    distributions_property: Decimal = Decimal("0")

    # Depreciation (for add-back)
    depreciation: Decimal = Decimal("0")
    amortization: Decimal = Decimal("0")
    depletion: Decimal = Decimal("0")

    # C-Corp specific (Form 1120)
    w2_from_corp: Decimal = Decimal("0")  # W-2 wages from the corporation

    def __post_init__(self):
        self.document_type = f"K1_{self.k1_type}"


# =============================================================================
# BANK STATEMENT FACTS
# =============================================================================

@dataclass
class BankStatementMonth:
    """Single month of bank statement data."""
    month: int  # 1-12
    year: int
    beginning_balance: Decimal = Decimal("0")
    ending_balance: Decimal = Decimal("0")
    total_deposits: Decimal = Decimal("0")
    total_withdrawals: Decimal = Decimal("0")

    # Deposit breakdown
    deposit_count: int = 0
    largest_deposit: Decimal = Decimal("0")
    deposits_detail: List[Dict[str, Any]] = field(default_factory=list)

    # Identified adjustments
    non_recurring_deposits: Decimal = Decimal("0")  # Loans, transfers, one-time items
    nsf_fees: Decimal = Decimal("0")
    overdraft_occurrences: int = 0


@dataclass
class BankStatementFacts(DocumentFacts):
    """Facts extracted from bank statements (12 or 24 months)."""
    account_holder_name: str = ""
    account_number_last4: str = ""
    account_type: str = ""  # CHECKING, SAVINGS, BUSINESS_CHECKING
    bank_name: str = ""

    # Statement period
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    months_of_data: int = 0

    # Monthly data
    monthly_data: List[BankStatementMonth] = field(default_factory=list)

    # Aggregated totals
    total_deposits: Decimal = Decimal("0")
    total_withdrawals: Decimal = Decimal("0")
    average_monthly_deposits: Decimal = Decimal("0")
    average_ending_balance: Decimal = Decimal("0")

    # Non-QM specific
    expense_factor: Decimal = Decimal("0.50")  # Default 50% expense factor

    def __post_init__(self):
        self.document_type = "BANK_STATEMENT"


# =============================================================================
# CALCULATION REQUEST/RESPONSE
# =============================================================================

@dataclass
class CalculationRequest:
    """Request to calculate income for a loan."""
    loan_id: int
    borrower_id: int  # 1 = primary, 2 = co-borrower

    # Document facts to process
    w2_facts: List[W2Facts] = field(default_factory=list)
    paystub_facts: List[PaystubFacts] = field(default_factory=list)
    schedule_c_facts: List[ScheduleCFacts] = field(default_factory=list)
    schedule_e_facts: List[ScheduleEFacts] = field(default_factory=list)
    k1_facts: List[K1Facts] = field(default_factory=list)
    bank_statement_facts: List[BankStatementFacts] = field(default_factory=list)

    # Calculation context
    investor_code: Optional[str] = None  # FNMA, FHLMC, FHA, VA
    program_code: Optional[str] = None
    use_24_month_average: bool = False  # Override to require 24-month for declining

    # Options
    generate_worksheets: bool = True
    include_audit_trail: bool = True


@dataclass
class IncomeStreamResult:
    """Result for a single income stream."""
    stream_type: IncomeStreamType
    stream_name: str  # e.g., "ABC Company W-2" or "123 Main St Rental"
    monthly_income: Decimal
    annual_income: Decimal

    # Calculation audit trail
    calculation_inputs: Dict[str, Any] = field(default_factory=dict)
    calculation_steps: List[Dict[str, Any]] = field(default_factory=list)
    add_backs: Dict[str, Decimal] = field(default_factory=dict)
    subtractions: Dict[str, Decimal] = field(default_factory=dict)

    # Source tracking
    document_ids: List[str] = field(default_factory=list)
    tax_years: List[int] = field(default_factory=list)

    # Trending
    trending_direction: Optional[TrendDirection] = None
    trending_percentage: Optional[Decimal] = None
    year1_income: Optional[Decimal] = None
    year2_income: Optional[Decimal] = None
    uses_lower_year: bool = False


@dataclass
class CalculationFlag:
    """Flag raised during calculation."""
    rule_id: str
    severity: FlagSeverity
    message: str
    required_action: Optional[str] = None
    affected_stream: Optional[str] = None
    affected_document_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_create_condition: bool = False


@dataclass
class CalculationResponse:
    """Response from income calculation."""
    loan_id: int
    borrower_id: int

    # Summary
    total_monthly_income: Decimal
    total_annual_income: Decimal
    is_approvable: bool

    # Income streams
    income_streams: List[IncomeStreamResult] = field(default_factory=list)

    # Flags
    flags: List[CalculationFlag] = field(default_factory=list)
    blocking_flags_count: int = 0
    error_flags_count: int = 0
    warning_flags_count: int = 0
    info_flags_count: int = 0

    # Metadata
    ruleset_version: str = "2025.1"
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    calculation_duration_ms: int = 0

    # Generated worksheets
    worksheet_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "loan_id": self.loan_id,
            "borrower_id": self.borrower_id,
            "total_monthly_income": float(self.total_monthly_income),
            "total_annual_income": float(self.total_annual_income),
            "is_approvable": self.is_approvable,
            "income_streams": [
                {
                    "stream_type": s.stream_type.value,
                    "stream_name": s.stream_name,
                    "monthly_income": float(s.monthly_income),
                    "annual_income": float(s.annual_income),
                    "trending_direction": s.trending_direction.value if s.trending_direction else None,
                    "trending_percentage": float(s.trending_percentage) if s.trending_percentage else None,
                }
                for s in self.income_streams
            ],
            "flags": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity.value,
                    "message": f.message,
                    "required_action": f.required_action,
                }
                for f in self.flags
            ],
            "flags_summary": {
                "blocking": self.blocking_flags_count,
                "errors": self.error_flags_count,
                "warnings": self.warning_flags_count,
                "info": self.info_flags_count,
            },
            "ruleset_version": self.ruleset_version,
            "calculated_at": self.calculated_at.isoformat(),
        }
