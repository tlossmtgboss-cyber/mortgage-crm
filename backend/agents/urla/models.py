"""
Perennia AI — URLA 1003 Pydantic Models
=======================================
Structured data models for the 2021 redesigned Uniform Residential Loan
Application (Fannie Mae Form 1003 / Freddie Mac Form 65).

Sections 1–9. Field names mirror the ULAD dataset so the mapping to BytePro
LOS is effectively 1:1 on finalize.

Design principles:
- Every field is Optional at the top level so the agent can persist partial
  progress across multiple calls. Validation happens at finalize time via
  `URLAApplication.validate_complete()`.
- Enums align to ULAD controlled vocabularies.
- Currency stored as Decimal, serialized as float for JSON/Redis.
- Dates stored as datetime.date, serialized ISO 8601.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import ClassVar, List, Optional, Dict, Any

from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict


# =============================================================================
# ENUMS
# =============================================================================

class CitizenshipStatus(str, Enum):
    US_CITIZEN = "US_CITIZEN"
    PERMANENT_RESIDENT_ALIEN = "PERMANENT_RESIDENT_ALIEN"
    NON_PERMANENT_RESIDENT_ALIEN = "NON_PERMANENT_RESIDENT_ALIEN"


class MaritalStatus(str, Enum):
    MARRIED = "MARRIED"
    SEPARATED = "SEPARATED"
    UNMARRIED = "UNMARRIED"  # Single, Divorced, Widowed


class IncomeFrequency(str, Enum):
    ANNUAL = "ANNUAL"
    MONTHLY = "MONTHLY"
    BIWEEKLY = "BIWEEKLY"
    WEEKLY = "WEEKLY"
    HOURLY = "HOURLY"


class OtherIncomeType(str, Enum):
    ALIMONY = "ALIMONY"
    CHILD_SUPPORT = "CHILD_SUPPORT"
    SEPARATE_MAINTENANCE = "SEPARATE_MAINTENANCE"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    DISABILITY = "DISABILITY"
    RETIREMENT_PENSION = "RETIREMENT_PENSION"
    VA_BENEFITS = "VA_BENEFITS"
    UNEMPLOYMENT = "UNEMPLOYMENT"
    PUBLIC_ASSISTANCE = "PUBLIC_ASSISTANCE"
    INVESTMENT_DIVIDENDS = "INVESTMENT_DIVIDENDS"
    RENTAL_INCOME = "RENTAL_INCOME"
    BOARDER_INCOME = "BOARDER_INCOME"
    ROYALTY = "ROYALTY"
    TRUST = "TRUST"
    NOTES_RECEIVABLE = "NOTES_RECEIVABLE"
    FOSTER_CARE = "FOSTER_CARE"
    OTHER = "OTHER"


class AssetType(str, Enum):
    CHECKING_ACCOUNT = "CHECKING_ACCOUNT"
    SAVINGS_ACCOUNT = "SAVINGS_ACCOUNT"
    MONEY_MARKET = "MONEY_MARKET"
    CERTIFICATE_OF_DEPOSIT = "CERTIFICATE_OF_DEPOSIT"
    MUTUAL_FUND = "MUTUAL_FUND"
    STOCKS = "STOCKS"
    STOCK_OPTIONS = "STOCK_OPTIONS"
    BONDS = "BONDS"
    RETIREMENT = "RETIREMENT"
    BRIDGE_LOAN_NOT_DEPOSITED = "BRIDGE_LOAN_NOT_DEPOSITED"
    TRUST_ACCOUNT = "TRUST_ACCOUNT"
    CASH_ON_HAND = "CASH_ON_HAND"
    GIFT_OF_CASH_NOT_DEPOSITED = "GIFT_OF_CASH_NOT_DEPOSITED"
    GIFT_OF_PROPERTY_EQUITY = "GIFT_OF_PROPERTY_EQUITY"
    LOT_EQUITY = "LOT_EQUITY"
    RELOCATION_FUNDS = "RELOCATION_FUNDS"
    SWEAT_EQUITY = "SWEAT_EQUITY"
    TRADE_EQUITY = "TRADE_EQUITY"
    SALE_OF_NON_REAL_ESTATE_ASSET = "SALE_OF_NON_REAL_ESTATE_ASSET"
    SECURED_BORROWED_FUNDS = "SECURED_BORROWED_FUNDS"
    UNSECURED_BORROWED_FUNDS = "UNSECURED_BORROWED_FUNDS"
    PROCEEDS_FROM_REAL_ESTATE = "PROCEEDS_FROM_REAL_ESTATE"
    EARNEST_MONEY = "EARNEST_MONEY"
    OTHER = "OTHER"


class LiabilityType(str, Enum):
    REVOLVING = "REVOLVING"
    INSTALLMENT = "INSTALLMENT"
    OPEN_30_DAY = "OPEN_30_DAY"
    LEASE = "LEASE"
    HELOC = "HELOC"
    MORTGAGE_LOAN = "MORTGAGE_LOAN"
    TAXES = "TAXES"
    CHILD_SUPPORT = "CHILD_SUPPORT"
    ALIMONY = "ALIMONY"
    SEPARATE_MAINTENANCE = "SEPARATE_MAINTENANCE"
    JOB_RELATED_EXPENSE = "JOB_RELATED_EXPENSE"
    OTHER = "OTHER"


class PropertyOccupancy(str, Enum):
    PRIMARY_RESIDENCE = "PRIMARY_RESIDENCE"
    SECOND_HOME = "SECOND_HOME"
    INVESTMENT = "INVESTMENT"
    FHA_SECONDARY_RESIDENCE = "FHA_SECONDARY_RESIDENCE"


class PropertyStatus(str, Enum):
    SOLD = "SOLD"
    PENDING_SALE = "PENDING_SALE"
    RETAINED = "RETAINED"


class LoanPurpose(str, Enum):
    PURCHASE = "PURCHASE"
    REFINANCE = "REFINANCE"
    CONSTRUCTION = "CONSTRUCTION"
    OTHER = "OTHER"


class LoanType(str, Enum):
    CONVENTIONAL = "CONVENTIONAL"
    FHA = "FHA"
    VA = "VA"
    USDA = "USDA"
    OTHER = "OTHER"


class PropertyType(str, Enum):
    SINGLE_FAMILY = "SINGLE_FAMILY"
    TWO_UNIT = "TWO_UNIT"
    THREE_UNIT = "THREE_UNIT"
    FOUR_UNIT = "FOUR_UNIT"
    CONDOMINIUM = "CONDOMINIUM"
    COOPERATIVE = "COOPERATIVE"
    MANUFACTURED_HOME = "MANUFACTURED_HOME"
    PUD = "PUD"


class GiftType(str, Enum):
    CASH_GIFT = "CASH_GIFT"
    GIFT_OF_EQUITY = "GIFT_OF_EQUITY"
    GRANT = "GRANT"


class GiftSource(str, Enum):
    RELATIVE = "RELATIVE"
    UNMARRIED_PARTNER = "UNMARRIED_PARTNER"
    FEDERAL_AGENCY = "FEDERAL_AGENCY"
    STATE_AGENCY = "STATE_AGENCY"
    LOCAL_AGENCY = "LOCAL_AGENCY"
    EMPLOYER = "EMPLOYER"
    RELIGIOUS_NONPROFIT = "RELIGIOUS_NONPROFIT"
    COMMUNITY_NONPROFIT = "COMMUNITY_NONPROFIT"
    LENDER = "LENDER"
    OTHER = "OTHER"


class EthnicityCategory(str, Enum):
    HISPANIC_OR_LATINO = "HISPANIC_OR_LATINO"
    NOT_HISPANIC_OR_LATINO = "NOT_HISPANIC_OR_LATINO"
    NOT_PROVIDED = "NOT_PROVIDED"


class RaceCategory(str, Enum):
    AMERICAN_INDIAN_OR_ALASKA_NATIVE = "AMERICAN_INDIAN_OR_ALASKA_NATIVE"
    ASIAN = "ASIAN"
    BLACK_OR_AFRICAN_AMERICAN = "BLACK_OR_AFRICAN_AMERICAN"
    NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER = "NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER"
    WHITE = "WHITE"
    NOT_PROVIDED = "NOT_PROVIDED"


class SexCategory(str, Enum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    NOT_PROVIDED = "NOT_PROVIDED"


class ApplicationChannel(str, Enum):
    FACE_TO_FACE = "FACE_TO_FACE"
    MAIL = "MAIL"
    TELEPHONE = "TELEPHONE"
    INTERNET = "INTERNET"


# =============================================================================
# BASE — shared config for JSON-safe Redis persistence
# =============================================================================

class URLABase(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )


# =============================================================================
# SHARED SUB-MODELS
# =============================================================================

class Address(URLABase):
    street: str
    unit: Optional[str] = None
    city: str
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str
    country: str = "US"

    @field_validator("state")
    @classmethod
    def uppercase_state(cls, v: str) -> str:
        return v.upper()


class ResidenceHistory(URLABase):
    address: Address
    years_at_address: int = Field(..., ge=0)
    months_at_address: int = Field(..., ge=0, le=11)
    housing_expense_monthly: Optional[Decimal] = None  # rent or PITI
    own_or_rent: Optional[str] = Field(None, pattern="^(OWN|RENT|NO_PRIMARY_HOUSING_EXPENSE)$")


# =============================================================================
# SECTION 1 — BORROWER INFORMATION
# =============================================================================

class Section1a_PersonalInformation(URLABase):
    """Section 1a: Personal Information."""
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    suffix: Optional[str] = None
    alternate_names: Optional[List[str]] = None

    ssn: Optional[str] = Field(None, pattern=r"^\d{3}-?\d{2}-?\d{4}$")
    date_of_birth: Optional[date] = None

    citizenship: Optional[CitizenshipStatus] = None
    marital_status: Optional[MaritalStatus] = None

    dependents_count: Optional[int] = Field(None, ge=0)
    dependents_ages: Optional[List[int]] = None

    home_phone: Optional[str] = None
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    email: Optional[EmailStr] = None

    # Residence history — requires minimum 2 years coverage
    current_address: Optional[ResidenceHistory] = None
    prior_addresses: Optional[List[ResidenceHistory]] = None

    mailing_address_same_as_current: Optional[bool] = True
    mailing_address: Optional[Address] = None


class Section1b_CurrentEmployment(URLABase):
    """Section 1b: Current Employment/Self-Employment and Income."""
    does_not_apply: Optional[bool] = False  # e.g., retired, unemployed

    employer_name: Optional[str] = None
    employer_address: Optional[Address] = None
    employer_phone: Optional[str] = None

    position_title: Optional[str] = None
    start_date: Optional[date] = None
    years_in_profession: Optional[int] = Field(None, ge=0)

    self_employed: Optional[bool] = False
    self_employment_ownership_share_ge_25: Optional[bool] = None
    self_employment_monthly_income_loss: Optional[Decimal] = None

    # Gross monthly income breakdown
    base_monthly: Optional[Decimal] = None
    overtime_monthly: Optional[Decimal] = None
    bonus_monthly: Optional[Decimal] = None
    commission_monthly: Optional[Decimal] = None
    military_entitlements_monthly: Optional[Decimal] = None
    other_monthly: Optional[Decimal] = None

    employed_by_family_or_party_to_transaction: Optional[bool] = None


class Section1c_AdditionalEmployment(URLABase):
    """Section 1c: Additional Employment/Self-Employment. List — 0..N."""
    employments: List[Section1b_CurrentEmployment] = Field(default_factory=list)


class Section1d_PreviousEmployment(URLABase):
    """Section 1d: Previous Employment (only if less than 2 years at current job)."""
    does_not_apply: Optional[bool] = False
    employer_name: Optional[str] = None
    employer_address: Optional[Address] = None
    position_title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    self_employed: Optional[bool] = False
    previous_gross_monthly_income: Optional[Decimal] = None


class OtherIncomeSource(URLABase):
    source_type: OtherIncomeType
    monthly_amount: Decimal
    description: Optional[str] = None


class Section1e_OtherIncome(URLABase):
    """Section 1e: Income from Other Sources. List — 0..N."""
    does_not_apply: Optional[bool] = False
    sources: List[OtherIncomeSource] = Field(default_factory=list)


# =============================================================================
# SECTION 2 — FINANCIAL INFORMATION: ASSETS AND LIABILITIES
# =============================================================================

class Asset(URLABase):
    asset_type: AssetType
    financial_institution: Optional[str] = None
    account_number_last_4: Optional[str] = Field(None, max_length=4)
    cash_or_market_value: Decimal


class OtherCredit(URLABase):
    """Section 2b: Other assets/credits like earnest money, employer assistance, trade equity."""
    credit_type: str
    amount: Decimal
    description: Optional[str] = None


class Liability(URLABase):
    liability_type: LiabilityType
    creditor_name: Optional[str] = None
    account_number_last_4: Optional[str] = Field(None, max_length=4)
    unpaid_balance: Decimal
    monthly_payment: Decimal
    months_remaining: Optional[int] = None
    to_be_paid_off_at_closing: bool = False


class OtherLiability(URLABase):
    """Section 2d: Alimony, child support, job-related expenses, etc."""
    liability_type: LiabilityType
    monthly_payment: Decimal
    description: Optional[str] = None


class Section2_AssetsAndLiabilities(URLABase):
    assets: List[Asset] = Field(default_factory=list)             # 2a
    other_credits: List[OtherCredit] = Field(default_factory=list) # 2b
    liabilities: List[Liability] = Field(default_factory=list)     # 2c
    other_liabilities: List[OtherLiability] = Field(default_factory=list)  # 2d


# =============================================================================
# SECTION 3 — REAL ESTATE OWNED
# =============================================================================

class REOMortgage(URLABase):
    creditor_name: Optional[str] = None
    account_number_last_4: Optional[str] = Field(None, max_length=4)
    monthly_payment: Decimal
    unpaid_balance: Decimal
    to_be_paid_off: bool = False
    loan_type: Optional[LoanType] = None
    credit_limit: Optional[Decimal] = None  # for HELOCs


class PropertyOwned(URLABase):
    address: Address
    property_value: Decimal
    status: PropertyStatus
    intended_occupancy: PropertyOccupancy
    monthly_insurance_taxes_assoc_dues: Optional[Decimal] = None  # excluding principal + interest
    monthly_rental_income: Optional[Decimal] = None
    net_monthly_rental_income: Optional[Decimal] = None
    mortgages: List[REOMortgage] = Field(default_factory=list)


class Section3_RealEstate(URLABase):
    does_not_apply: Optional[bool] = False
    properties: List[PropertyOwned] = Field(default_factory=list)


# =============================================================================
# SECTION 4 — LOAN AND PROPERTY INFORMATION
# =============================================================================

class Section4a_LoanAndProperty(URLABase):
    loan_amount: Optional[Decimal] = None
    loan_purpose: Optional[LoanPurpose] = None
    loan_purpose_other_description: Optional[str] = None

    subject_property_address: Optional[Address] = None
    number_of_units: Optional[int] = Field(None, ge=1, le=4)
    property_value: Optional[Decimal] = None
    occupancy: Optional[PropertyOccupancy] = None

    fha_secondary_residence: Optional[bool] = False
    mixed_use_property: Optional[bool] = False
    manufactured_home: Optional[bool] = False


class Section4b_OtherNewMortgages(URLABase):
    """Other new mortgage loans on the subject property (e.g., piggyback 2nd)."""
    does_not_apply: Optional[bool] = True
    creditor_name: Optional[str] = None
    lien_type: Optional[str] = Field(None, pattern="^(FIRST|SUBORDINATE)$")
    monthly_payment: Optional[Decimal] = None
    loan_amount: Optional[Decimal] = None
    credit_limit: Optional[Decimal] = None


class Section4c_RentalIncomeOnSubject(URLABase):
    """Rental income on the property being purchased (investment / 2-4 unit)."""
    does_not_apply: Optional[bool] = True
    expected_monthly_rental_income: Optional[Decimal] = None
    expected_net_monthly_rental_income: Optional[Decimal] = None


class Gift(URLABase):
    asset_type: GiftType
    deposited: bool
    source: GiftSource
    cash_or_market_value: Decimal


class Section4d_GiftsOrGrants(URLABase):
    does_not_apply: Optional[bool] = True
    gifts: List[Gift] = Field(default_factory=list)


class Section4_LoanAndProperty(URLABase):
    section_4a: Optional[Section4a_LoanAndProperty] = None
    section_4b: Optional[Section4b_OtherNewMortgages] = None
    section_4c: Optional[Section4c_RentalIncomeOnSubject] = None
    section_4d: Optional[Section4d_GiftsOrGrants] = None


# =============================================================================
# SECTION 5 — DECLARATIONS
# =============================================================================

class Section5a_DeclarationsPropertyMoney(URLABase):
    """5a: About this Property and Your Money for this Loan."""
    will_occupy_as_primary_residence: Optional[bool] = None
    had_ownership_interest_last_3_years: Optional[bool] = None
    property_type_last_3_years: Optional[str] = None  # PRIMARY / SECOND_HOME / INVESTMENT
    how_held_title_last_3_years: Optional[str] = None  # SOLE / JOINT_WITH_SPOUSE / JOINT_WITH_OTHER

    family_business_relationship_with_seller: Optional[bool] = None
    borrowing_money_for_transaction: Optional[bool] = None
    borrowed_amount: Optional[Decimal] = None

    applying_for_other_mortgage_before_closing: Optional[bool] = None
    applying_for_new_credit_before_closing: Optional[bool] = None
    property_subject_to_lien: Optional[bool] = None


class Section5b_DeclarationsFinances(URLABase):
    """5b: About Your Finances."""
    co_signer_on_undisclosed_debt: Optional[bool] = None
    outstanding_judgments: Optional[bool] = None
    currently_delinquent_on_federal_debt: Optional[bool] = None
    party_to_lawsuit: Optional[bool] = None
    conveyed_title_in_lieu_of_foreclosure_last_7_years: Optional[bool] = None
    short_sale_or_pre_foreclosure_last_7_years: Optional[bool] = None
    foreclosed_last_7_years: Optional[bool] = None
    declared_bankruptcy_last_7_years: Optional[bool] = None
    bankruptcy_types: Optional[List[str]] = None  # CHAPTER_7, CHAPTER_11, CHAPTER_12, CHAPTER_13


class Section5_Declarations(URLABase):
    section_5a: Optional[Section5a_DeclarationsPropertyMoney] = None
    section_5b: Optional[Section5b_DeclarationsFinances] = None


# =============================================================================
# SECTION 6 — ACKNOWLEDGMENTS AND AGREEMENTS
# =============================================================================

class Section6_Acknowledgments(URLABase):
    """Verbal acknowledgment captured; formal e-sign happens post-call."""
    verbal_consent_given: bool = False
    verbal_consent_timestamp: Optional[datetime] = None
    verbal_consent_recording_url: Optional[str] = None
    # GLBA Privacy Notice — separate from application consent
    privacy_notice_consent_given: bool = False
    privacy_notice_consent_timestamp: Optional[datetime] = None


# =============================================================================
# SECTION 7 — MILITARY SERVICE
# =============================================================================

class Section7_MilitaryService(URLABase):
    served_in_military: Optional[bool] = None
    currently_active_duty: Optional[bool] = None
    retired_discharged_separated: Optional[bool] = None
    non_activated_reserve_national_guard: Optional[bool] = None
    surviving_spouse: Optional[bool] = None
    expiration_of_active_duty: Optional[date] = None


# =============================================================================
# SECTION 8 — DEMOGRAPHIC INFORMATION (HMDA) — VOLUNTARY
# =============================================================================

class Section8_Demographics(URLABase):
    """Collected per Regulation B / HMDA. Providing is voluntary.

    IMPORTANT COMPLIANCE NOTE:
    The agent MUST read the government monitoring notice before asking these
    questions. See prompts.DEMOGRAPHICS_NOTICE.
    """
    # ECOA audit trail — timestamp proving notice was read before questions
    demographics_notice_read_at: Optional[datetime] = None
    ethnicity: Optional[List[EthnicityCategory]] = None
    ethnicity_hispanic_subcategory: Optional[List[str]] = None  # Mexican, PR, Cuban, Other
    ethnicity_other_origin: Optional[str] = None

    race: Optional[List[RaceCategory]] = None
    race_asian_subcategory: Optional[List[str]] = None
    race_nhopi_subcategory: Optional[List[str]] = None
    race_other_origin: Optional[str] = None

    sex: Optional[SexCategory] = None

    # How information was collected for government monitoring
    was_demographic_info_provided_by_borrower: Optional[bool] = None
    was_collected_via_visual_observation_or_surname: Optional[bool] = None
    application_channel: ApplicationChannel = ApplicationChannel.TELEPHONE


# =============================================================================
# SECTION 9 — LOAN ORIGINATOR INFORMATION (auto-populated from LO assignment)
# =============================================================================

class Section9_LoanOriginator(URLABase):
    loan_originator_organization_name: Optional[str] = None
    loan_originator_organization_nmlsr_id: Optional[str] = None
    loan_originator_organization_state_license_id: Optional[str] = None
    loan_originator_organization_address: Optional[Address] = None

    loan_originator_name: Optional[str] = None
    loan_originator_nmlsr_id: Optional[str] = None
    loan_originator_state_license_id: Optional[str] = None
    loan_originator_email: Optional[str] = None
    loan_originator_phone: Optional[str] = None

    application_signed_date: Optional[date] = None


# =============================================================================
# CALL TRANSCRIPT, CALL NOTES, SCHEDULED HANDOFF
# =============================================================================

class CallTranscriptEntry(URLABase):
    """One turn of spoken conversation captured during the URLA intake."""
    speaker: str  # "agent" or "borrower"
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CallNotes(URLABase):
    """
    LLM-generated briefing for the loan officer, produced at finalize time
    from the URLAApplication + conversation transcript.
    """
    executive_summary: str
    borrower_profile: str
    loan_snapshot: str
    red_flags: List[str] = Field(default_factory=list)
    stated_concerns: List[str] = Field(default_factory=list)
    recommended_talking_points: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScheduledHandoff(URLABase):
    """
    The AI's scheduled briefing call with the loan officer.

    Created at finalize time via Microsoft Graph. The event itself lives on
    the LO's calendar; this record stores the pointers we need to reference
    it later (cancellation, reschedule, outbound-dialer job scheduling).
    """
    lo_email: str
    lo_name: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int = 15
    graph_event_id: Optional[str] = None
    graph_ical_uid: Optional[str] = None
    web_link: Optional[str] = None
    subject: Optional[str] = None


# =============================================================================
# BORROWER & FULL APPLICATION
# =============================================================================

class Borrower(URLABase):
    """One borrower — fully captures Sections 1, 5, 7, 8 for that person."""
    borrower_id: str  # "borrower_1", "borrower_2", etc.
    is_primary: bool = True

    section_1a: Optional[Section1a_PersonalInformation] = None
    section_1b: Optional[Section1b_CurrentEmployment] = None
    section_1c: Optional[Section1c_AdditionalEmployment] = None
    section_1d: Optional[Section1d_PreviousEmployment] = None
    section_1e: Optional[Section1e_OtherIncome] = None

    section_5: Optional[Section5_Declarations] = None
    section_7: Optional[Section7_MilitaryService] = None
    section_8: Optional[Section8_Demographics] = None


class LOKickoffBooking(URLABase):
    """Post-finalize: LO kickoff call booked via the CRM Smart Calendar."""
    event_id: str
    confirmation_number: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    scheduled_timezone: Optional[str] = None
    loan_officer_name: str
    booked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class URLAApplication(URLABase):
    """
    Top-level URLA 1003 application record.

    Shared sections (2, 3, 4, 6, 9) apply to all borrowers on the loan.
    Per-borrower sections (1, 5, 7, 8) are nested under each Borrower.
    """
    # Identity
    loan_id: str
    tenant_id: str  # Perennia multi-tenant scoping
    caller_phone: str  # E.164 format, used for session resumption
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Session lock — prevents concurrent callers from colliding on the same loan
    session_lock_token: Optional[str] = None

    # Progress tracking
    current_section: str = "START"
    completed_sections: List[str] = Field(default_factory=list)
    is_finalized: bool = False
    finalized_at: Optional[datetime] = None

    # TRID trigger: application is "received" when all 6 triggers are captured
    # (name, SSN, income, property address, loan amount, property value)
    application_received_at: Optional[datetime] = None

    # BytePro submission tracking (post-finalize)
    bytepro_loan_number: Optional[str] = None
    bytepro_submitted_at: Optional[datetime] = None

    # Credit authorization — verbal consent does NOT satisfy FCRA 15 U.S.C. 1681b(a)(2).
    # Separate e-signed authorization required before any credit pull.
    credit_authorization_pending: bool = True
    credit_authorization_sent_at: Optional[datetime] = None
    credit_authorization_signed_at: Optional[datetime] = None

    # LO kickoff call booked via Smart Calendar (post-finalize)
    lo_kickoff_booking: Optional[LOKickoffBooking] = None

    # Borrowers (1 primary required, co-borrowers optional)
    borrowers: List[Borrower] = Field(default_factory=list)

    # Shared sections
    section_2: Optional[Section2_AssetsAndLiabilities] = None
    section_3: Optional[Section3_RealEstate] = None
    section_4: Optional[Section4_LoanAndProperty] = None
    section_6: Optional[Section6_Acknowledgments] = None
    section_9: Optional[Section9_LoanOriginator] = None

    # Handoff artifacts — populated at finalize time
    transcript: List[CallTranscriptEntry] = Field(default_factory=list)
    call_notes: Optional[CallNotes] = None
    scheduled_handoff: Optional[ScheduledHandoff] = None
    handoff_email_message_id: Optional[str] = None  # MS Graph message ID once sent

    # ---- Helpers ----

    def primary_borrower(self) -> Optional[Borrower]:
        return next((b for b in self.borrowers if b.is_primary), None)

    def get_borrower(self, borrower_id: str) -> Optional[Borrower]:
        return next((b for b in self.borrowers if b.borrower_id == borrower_id), None)

    def check_trid_triggers(self) -> bool:
        """Check if all 6 TRID triggers are captured. Returns True if newly triggered."""
        if self.application_received_at:
            return False  # Already triggered
        primary = self.primary_borrower()
        if not primary or not primary.section_1a:
            return False
        s1a = primary.section_1a
        has_name = bool(s1a.first_name and s1a.last_name)
        has_ssn = bool(s1a.ssn)
        has_income = bool(
            (primary.section_1b and primary.section_1b.base_monthly)
            or (primary.section_1e and primary.section_1e.sources)
        )
        s4a = self.section_4.section_4a if self.section_4 else None
        has_property = bool(s4a and s4a.subject_property_address)
        has_loan_amount = bool(s4a and s4a.loan_amount)
        has_property_value = bool(s4a and s4a.property_value)
        if all([has_name, has_ssn, has_income, has_property, has_loan_amount, has_property_value]):
            self.application_received_at = datetime.now(timezone.utc)
            return True
        return False

    TRACKABLE_SECTIONS: ClassVar[List[str]] = [
        "SECTION_1A", "SECTION_1B", "SECTION_1C", "SECTION_1D", "SECTION_1E",
        "SECTION_2", "SECTION_3",
        "SECTION_4A", "SECTION_4B", "SECTION_4C", "SECTION_4D",
        "SECTION_5A", "SECTION_5B",
        "SECTION_7", "SECTION_8",
        "COBORROWER_CHECK", "SECTION_6",
    ]

    def progress_summary(self) -> Dict[str, Any]:
        """Human-readable progress snapshot for voice read-backs and get_urla_status."""
        primary = self.primary_borrower()
        total_sections = len(self.TRACKABLE_SECTIONS)
        completed = len(self.completed_sections)
        return {
            "loan_id": self.loan_id,
            "percent_complete": int((completed / total_sections) * 100),
            "current_section": self.current_section,
            "completed_sections": self.completed_sections,
            "borrower_name": (
                f"{primary.section_1a.first_name or ''} {primary.section_1a.last_name or ''}".strip()
                if primary and primary.section_1a else None
            ),
            "has_co_borrower": len(self.borrowers) > 1,
            "is_finalized": self.is_finalized,
        }

    def validate_complete(self) -> List[str]:
        """
        Returns a list of validation errors. Empty list = ready to finalize.
        Used by finalize_urla tool before pushing to BytePro.
        """
        errors: List[str] = []

        primary = self.primary_borrower()
        if not primary:
            errors.append("No primary borrower on file.")
            return errors

        # Section 1a essentials
        s1a = primary.section_1a
        if not s1a:
            errors.append("Section 1a (personal info) is missing.")
        else:
            if not s1a.first_name or not s1a.last_name:
                errors.append("Primary borrower legal name is incomplete.")
            if not s1a.ssn:
                errors.append("Primary borrower SSN is missing.")
            if not s1a.date_of_birth:
                errors.append("Primary borrower date of birth is missing.")
            if not s1a.current_address:
                errors.append("Current residence address is missing.")
            if not s1a.citizenship:
                errors.append("Citizenship status is missing.")

        # Section 1b — employment OR 1e — other income required
        if not primary.section_1b and not (primary.section_1e and primary.section_1e.sources):
            errors.append("No income source on file (employment or other income).")

        # Section 2 essentials
        if not self.section_2 or not self.section_2.assets:
            errors.append("No assets listed in Section 2.")

        # Section 4a essentials
        s4a = self.section_4.section_4a if self.section_4 else None
        if not s4a:
            errors.append("Section 4a (loan and property) is missing.")
        else:
            if not s4a.loan_amount:
                errors.append("Loan amount is missing.")
            if not s4a.loan_purpose:
                errors.append("Loan purpose is missing.")
            if not s4a.subject_property_address:
                errors.append("Subject property address is missing.")
            if not s4a.occupancy:
                errors.append("Property occupancy is missing.")

        # Section 5 — declarations required
        if not primary.section_5 or not primary.section_5.section_5a or not primary.section_5.section_5b:
            errors.append("Declarations (Section 5) are incomplete.")

        # Section 6 — verbal consent required
        if not self.section_6 or not self.section_6.verbal_consent_given:
            errors.append("Verbal consent (Section 6 acknowledgment) was not recorded.")

        # Section 8 — voluntary, but a response (including "not provided") is required
        if not primary.section_8:
            errors.append("Demographic information collection (Section 8) was skipped.")

        # Validate co-borrowers
        for borrower in self.borrowers:
            if borrower.is_primary:
                continue  # Already validated above
            bid = borrower.borrower_id
            b_s1a = borrower.section_1a
            if not b_s1a:
                errors.append(f"Co-borrower {bid}: Section 1a (personal info) is missing.")
            else:
                if not b_s1a.first_name or not b_s1a.last_name:
                    errors.append(f"Co-borrower {bid}: Legal name is incomplete.")
                if not b_s1a.ssn:
                    errors.append(f"Co-borrower {bid}: SSN is missing.")
                if not b_s1a.date_of_birth:
                    errors.append(f"Co-borrower {bid}: Date of birth is missing.")
            if not borrower.section_5 or not borrower.section_5.section_5a or not borrower.section_5.section_5b:
                errors.append(f"Co-borrower {bid}: Declarations (Section 5) are incomplete.")
            if not borrower.section_8:
                errors.append(f"Co-borrower {bid}: Demographics (Section 8) was skipped.")

        return errors

    def to_ulad_dict(self) -> Dict[str, Any]:
        """
        Serialize to a ULAD-shaped dict for BytePro ingestion.
        The BytePro adapter converts this to MISMO ULAD XML.
        """
        return self.model_dump(mode="json", exclude_none=True)
