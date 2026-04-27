"""
Perennia AI -- MISMO 3.4 XML Serializer
========================================
Serialize a URLAApplication to MISMO 3.4 (ULAD) XML for email attachment
or LOS import.  Uses only Python stdlib (xml.etree.ElementTree).

MISMO 3.4 Reference:
    Namespace:  http://www.mismo.org/residential/2009/schemas
    ULAD Ext:   http://www.datamodelextension.org/Schema/ULAD
    Version:    3.4.032420210307

Usage:
    from agents.urla.mismo_serializer import serialize_to_mismo34
    xml_str = serialize_to_mismo34(app, loan_officer=lo)
"""
from __future__ import annotations

import logging
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .bytepro_adapter import LoanOfficer
from .models import (
    URLAApplication,
    Borrower,
    Address,
    Asset,
    Liability,
    OtherLiability,
    PropertyOwned,
    Gift,
    OtherIncomeSource,
    Section1a_PersonalInformation,
    Section1b_CurrentEmployment,
    Section1d_PreviousEmployment,
    Section4a_LoanAndProperty,
    Section5a_DeclarationsPropertyMoney,
    Section5b_DeclarationsFinances,
    Section7_MilitaryService,
    Section8_Demographics,
    Section9_LoanOriginator,
)

logger = logging.getLogger("urla.mismo")

# ---------------------------------------------------------------------------
# XML Namespaces
# ---------------------------------------------------------------------------
MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
ULAD_NS = "http://www.datamodelextension.org/Schema/ULAD"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
MISMO_VERSION = "3.4.032420210307"


# ---------------------------------------------------------------------------
# Enum -> MISMO value maps
# ---------------------------------------------------------------------------
LOAN_PURPOSE_MAP: Dict[str, str] = {
    "PURCHASE": "Purchase",
    "REFINANCE": "Refinance",
    "CONSTRUCTION": "Construction",
    "OTHER": "Other",
}

OCCUPANCY_MAP: Dict[str, str] = {
    "PRIMARY_RESIDENCE": "PrimaryResidence",
    "SECOND_HOME": "SecondHome",
    "INVESTMENT": "Investment",
    "FHA_SECONDARY_RESIDENCE": "FHASecondaryResidence",
}

CITIZENSHIP_MAP: Dict[str, str] = {
    "US_CITIZEN": "USCitizen",
    "PERMANENT_RESIDENT_ALIEN": "PermanentResidentAlien",
    "NON_PERMANENT_RESIDENT_ALIEN": "NonPermanentResidentAlien",
}

MARITAL_MAP: Dict[str, str] = {
    "MARRIED": "Married",
    "SEPARATED": "Separated",
    "UNMARRIED": "Unmarried",
}

ASSET_TYPE_MAP: Dict[str, str] = {
    "CHECKING_ACCOUNT": "CheckingAccount",
    "SAVINGS_ACCOUNT": "SavingsAccount",
    "MONEY_MARKET": "MoneyMarketFund",
    "CERTIFICATE_OF_DEPOSIT": "CertificateOfDepositTimeDeposit",
    "MUTUAL_FUND": "MutualFund",
    "STOCKS": "Stock",
    "STOCK_OPTIONS": "StockOptions",
    "BONDS": "Bond",
    "RETIREMENT": "RetirementFund",
    "BRIDGE_LOAN_NOT_DEPOSITED": "BridgeLoanNotDeposited",
    "TRUST_ACCOUNT": "TrustAccount",
    "CASH_ON_HAND": "CashOnHand",
    "GIFT_OF_CASH_NOT_DEPOSITED": "GiftOfCash",
    "GIFT_OF_PROPERTY_EQUITY": "GiftOfPropertyEquity",
    "LOT_EQUITY": "LotEquity",
    "RELOCATION_FUNDS": "RelocationMoney",
    "SWEAT_EQUITY": "SweatEquity",
    "TRADE_EQUITY": "TradeEquity",
    "SALE_OF_NON_REAL_ESTATE_ASSET": "ProceedsFromSaleOfNonRealEstateAsset",
    "SECURED_BORROWED_FUNDS": "SecuredBorrowedFundsNotDeposited",
    "UNSECURED_BORROWED_FUNDS": "UnsecuredBorrowedFundsNotDeposited",
    "PROCEEDS_FROM_REAL_ESTATE": "ProceedsFromRealEstateProperty",
    "EARNEST_MONEY": "EarnestMoneyCashDepositTowardPurchase",
    "OTHER": "Other",
}

LIABILITY_TYPE_MAP: Dict[str, str] = {
    "REVOLVING": "Revolving",
    "INSTALLMENT": "Installment",
    "OPEN_30_DAY": "Open30DayChargeAccount",
    "LEASE": "LeasePayment",
    "HELOC": "HELOC",
    "MORTGAGE_LOAN": "MortgageLoan",
    "TAXES": "Taxes",
    "CHILD_SUPPORT": "ChildSupport",
    "ALIMONY": "Alimony",
    "SEPARATE_MAINTENANCE": "SeparateMaintenanceExpense",
    "JOB_RELATED_EXPENSE": "JobRelatedExpenses",
    "OTHER": "Other",
}

INCOME_TYPE_MAP: Dict[str, str] = {
    "ALIMONY": "AlimonyChildSupport",
    "CHILD_SUPPORT": "AlimonyChildSupport",
    "SEPARATE_MAINTENANCE": "SeparateMaintenanceIncome",
    "SOCIAL_SECURITY": "SocialSecurity",
    "DISABILITY": "Disability",
    "RETIREMENT_PENSION": "Pension",
    "VA_BENEFITS": "VABenefits",
    "UNEMPLOYMENT": "UnemploymentBenefits",
    "PUBLIC_ASSISTANCE": "PublicAssistance",
    "INVESTMENT_DIVIDENDS": "DividendsInterest",
    "RENTAL_INCOME": "RentalIncome",
    "BOARDER_INCOME": "BoarderIncome",
    "ROYALTY": "Royalties",
    "TRUST": "TrustIncome",
    "NOTES_RECEIVABLE": "NotesReceivable",
    "FOSTER_CARE": "FosterCare",
    "OTHER": "Other",
}

GIFT_TYPE_MAP: Dict[str, str] = {
    "CASH_GIFT": "CashGift",
    "GIFT_OF_EQUITY": "GiftOfEquity",
    "GRANT": "Grant",
}

GIFT_SOURCE_MAP: Dict[str, str] = {
    "RELATIVE": "Relative",
    "UNMARRIED_PARTNER": "UnmarriedPartner",
    "FEDERAL_AGENCY": "FederalAgency",
    "STATE_AGENCY": "StateAgency",
    "LOCAL_AGENCY": "LocalAgency",
    "EMPLOYER": "Employer",
    "RELIGIOUS_NONPROFIT": "ReligiousNonProfit",
    "COMMUNITY_NONPROFIT": "CommunityNonProfit",
    "LENDER": "Lender",
    "OTHER": "Other",
}

ETHNICITY_MAP: Dict[str, str] = {
    "HISPANIC_OR_LATINO": "HispanicOrLatino",
    "NOT_HISPANIC_OR_LATINO": "NotHispanicOrLatino",
    "NOT_PROVIDED": "InformationNotProvidedByApplicantInMailInternetOrTelephoneApplication",
}

RACE_MAP: Dict[str, str] = {
    "AMERICAN_INDIAN_OR_ALASKA_NATIVE": "AmericanIndianOrAlaskaNative",
    "ASIAN": "Asian",
    "BLACK_OR_AFRICAN_AMERICAN": "BlackOrAfricanAmerican",
    "NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER": "NativeHawaiianOrOtherPacificIslander",
    "WHITE": "White",
    "NOT_PROVIDED": "InformationNotProvidedByApplicantInMailInternetOrTelephoneApplication",
}

SEX_MAP: Dict[str, str] = {
    "FEMALE": "Female",
    "MALE": "Male",
    "NOT_PROVIDED": "InformationNotProvidedByApplicantInMailInternetOrTelephoneApplication",
}

PROPERTY_STATUS_MAP: Dict[str, str] = {
    "SOLD": "Sold",
    "PENDING_SALE": "PendingSale",
    "RETAINED": "Retained",
}

APPLICATION_CHANNEL_MAP: Dict[str, str] = {
    "FACE_TO_FACE": "FaceToFace",
    "MAIL": "Mail",
    "TELEPHONE": "Telephone",
    "INTERNET": "Internet",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sub(parent: ET.Element, tag: str) -> ET.Element:
    """Create and return a direct child element."""
    return ET.SubElement(parent, tag)


def _text(parent: ET.Element, tag: str, value) -> Optional[ET.Element]:
    """Create a child element with text content if value is not None."""
    if value is None:
        return None
    el = ET.SubElement(parent, tag)
    if isinstance(value, bool):
        el.text = "true" if value else "false"
    elif isinstance(value, (Decimal, float)):
        # Financial amounts: render as integer if whole, else 2 decimals
        d = Decimal(str(value))
        if d == d.to_integral_value():
            el.text = str(int(d))
        else:
            el.text = str(d.quantize(Decimal("0.01")))
    elif isinstance(value, date):
        el.text = value.isoformat()
    elif isinstance(value, datetime):
        el.text = value.isoformat()
    else:
        el.text = str(value)
    return el


def _bool_indicator(val: Optional[bool]) -> Optional[str]:
    """Convert Optional[bool] to MISMO indicator string."""
    if val is None:
        return None
    return "true" if val else "false"


def _sequence_number() -> str:
    """Return a short unique label for SequenceNumber attributes."""
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Address builder
# ---------------------------------------------------------------------------
def _build_address(parent: ET.Element, addr: Address) -> ET.Element:
    """Append an ADDRESS element."""
    address_el = _sub(parent, "ADDRESS")
    line = addr.street
    if addr.unit:
        line += f" {addr.unit}"
    _text(address_el, "AddressLineText", line)
    _text(address_el, "CityName", addr.city)
    _text(address_el, "StateCode", addr.state)
    _text(address_el, "PostalCode", addr.zip_code)
    _text(address_el, "CountryCode", addr.country)
    return address_el


# ---------------------------------------------------------------------------
# ASSETS section
# ---------------------------------------------------------------------------
def _build_assets(deal: ET.Element, app: URLAApplication) -> None:
    """Build ASSETS container from Section 2 assets."""
    if not app.section_2 or not app.section_2.assets:
        return

    assets_el = _sub(deal, "ASSETS")
    for asset in app.section_2.assets:
        asset_el = _sub(assets_el, "ASSET")
        detail = _sub(asset_el, "ASSET_DETAIL")
        _text(detail, "AssetAccountIdentifier", asset.account_number_last_4)
        _text(detail, "AssetCashOrMarketValueAmount", asset.cash_or_market_value)
        _text(detail, "AssetType", ASSET_TYPE_MAP.get(asset.asset_type, asset.asset_type))

        if asset.financial_institution:
            holder = _sub(asset_el, "ASSET_HOLDER")
            name_el = _sub(holder, "NAME")
            _text(name_el, "FullName", asset.financial_institution)


# ---------------------------------------------------------------------------
# COLLATERALS section (subject property from 4a)
# ---------------------------------------------------------------------------
def _build_collaterals(deal: ET.Element, app: URLAApplication) -> None:
    """Build COLLATERALS from Section 4a subject property."""
    s4a = app.section_4.section_4a if app.section_4 else None
    if not s4a or not s4a.subject_property_address:
        return

    collaterals_el = _sub(deal, "COLLATERALS")
    collateral_el = _sub(collaterals_el, "COLLATERAL")
    subject = _sub(collateral_el, "SUBJECT_PROPERTY")
    _build_address(subject, s4a.subject_property_address)

    prop_detail = _sub(subject, "PROPERTY_DETAIL")
    _text(prop_detail, "PropertyEstimatedValueAmount", s4a.property_value)
    if s4a.occupancy:
        _text(prop_detail, "PropertyUsageType", OCCUPANCY_MAP.get(s4a.occupancy, s4a.occupancy))
    if s4a.number_of_units:
        _text(prop_detail, "FinancedUnitCount", s4a.number_of_units)
    if s4a.mixed_use_property is not None:
        _text(prop_detail, "PropertyMixedUsageIndicator", s4a.mixed_use_property)


# ---------------------------------------------------------------------------
# LIABILITIES section
# ---------------------------------------------------------------------------
def _build_liabilities(deal: ET.Element, app: URLAApplication) -> None:
    """Build LIABILITIES from Section 2 liabilities + other liabilities."""
    if not app.section_2:
        return
    all_liabs = app.section_2.liabilities
    other_liabs = app.section_2.other_liabilities
    if not all_liabs and not other_liabs:
        return

    liabilities_el = _sub(deal, "LIABILITIES")

    for liab in all_liabs:
        _build_one_liability(liabilities_el, liab)

    for other in other_liabs:
        _build_other_liability(liabilities_el, other)


def _build_one_liability(parent: ET.Element, liab: Liability) -> None:
    """Build a single LIABILITY element."""
    liability_el = _sub(parent, "LIABILITY")
    detail = _sub(liability_el, "LIABILITY_DETAIL")
    _text(detail, "LiabilityAccountIdentifier", liab.account_number_last_4)
    _text(detail, "LiabilityMonthlyPaymentAmount", liab.monthly_payment)
    _text(detail, "LiabilityType", LIABILITY_TYPE_MAP.get(liab.liability_type, liab.liability_type))
    _text(detail, "LiabilityUnpaidBalanceAmount", liab.unpaid_balance)
    if liab.months_remaining is not None:
        _text(detail, "LiabilityPaymentRemainingCount", liab.months_remaining)
    if liab.to_be_paid_off_at_closing:
        _text(detail, "LiabilityPayoffStatusIndicator", True)

    if liab.creditor_name:
        holder = _sub(liability_el, "LIABILITY_HOLDER")
        name_el = _sub(holder, "NAME")
        _text(name_el, "FullName", liab.creditor_name)


def _build_other_liability(parent: ET.Element, liab: OtherLiability) -> None:
    """Build a LIABILITY element from an OtherLiability (alimony, child support, etc.)."""
    liability_el = _sub(parent, "LIABILITY")
    detail = _sub(liability_el, "LIABILITY_DETAIL")
    _text(detail, "LiabilityMonthlyPaymentAmount", liab.monthly_payment)
    _text(detail, "LiabilityType", LIABILITY_TYPE_MAP.get(liab.liability_type, liab.liability_type))
    if liab.description:
        _text(detail, "LiabilityTypeOtherDescription", liab.description)


# ---------------------------------------------------------------------------
# LOANS section
# ---------------------------------------------------------------------------
def _build_loans(deal: ET.Element, app: URLAApplication) -> str:
    """Build LOANS/LOAN and return the loan SequenceNumber for RELATIONSHIPS."""
    loans_el = _sub(deal, "LOANS")
    loan_el = _sub(loans_el, "LOAN")
    loan_seq = _sequence_number()
    loan_el.set("SequenceNumber", loan_seq)

    s4a = app.section_4.section_4a if app.section_4 else None

    # LOAN_DETAIL
    loan_detail = _sub(loan_el, "LOAN_DETAIL")
    if app.application_received_at:
        _text(loan_detail, "ApplicationReceivedDate", app.application_received_at.date())
    elif app.created_at:
        _text(loan_detail, "ApplicationReceivedDate", app.created_at.date())
    if s4a and s4a.loan_purpose:
        _text(loan_detail, "LoanPurposeType", LOAN_PURPOSE_MAP.get(s4a.loan_purpose, s4a.loan_purpose))

    # TERMS_OF_LOAN
    terms = _sub(loan_el, "TERMS_OF_LOAN")
    if s4a:
        _text(terms, "BaseLoanAmount", s4a.loan_amount)
        if s4a.loan_purpose:
            _text(terms, "LoanPurposeType", LOAN_PURPOSE_MAP.get(s4a.loan_purpose, s4a.loan_purpose))

    # HOUSING_EXPENSES (from current address housing expense)
    _build_housing_expenses(loan_el, app)

    # CONSTRUCTION (Section 4b -- other new mortgages on subject property)
    _build_other_new_mortgage(loan_el, app)

    # GOVERNMENT_MONITORING (HMDA / Section 8 from primary borrower)
    _build_government_monitoring(loan_el, app)

    # GIFTS (Section 4d)
    _build_gifts(loan_el, app)

    return loan_seq


def _build_housing_expenses(loan_el: ET.Element, app: URLAApplication) -> None:
    """Add HOUSING_EXPENSES from borrower current address housing expense."""
    primary = app.primary_borrower()
    if not primary or not primary.section_1a or not primary.section_1a.current_address:
        return
    current = primary.section_1a.current_address
    if current.housing_expense_monthly is None:
        return

    expenses_el = _sub(loan_el, "HOUSING_EXPENSES")
    expense = _sub(expenses_el, "HOUSING_EXPENSE")
    _text(expense, "HousingExpensePaymentAmount", current.housing_expense_monthly)

    own_or_rent = current.own_or_rent
    if own_or_rent == "RENT":
        _text(expense, "HousingExpenseType", "Rent")
    elif own_or_rent == "OWN":
        _text(expense, "HousingExpenseType", "FirstMortgagePrincipalAndInterest")
    else:
        _text(expense, "HousingExpenseType", "Rent")


def _build_other_new_mortgage(loan_el: ET.Element, app: URLAApplication) -> None:
    """Section 4b: other new mortgage loans on subject property."""
    s4b = app.section_4.section_4b if app.section_4 else None
    if not s4b or s4b.does_not_apply:
        return

    addl = _sub(loan_el, "ADDITIONAL_LOANS")
    addl_loan = _sub(addl, "ADDITIONAL_LOAN")
    _text(addl_loan, "AdditionalLoanAmount", s4b.loan_amount)
    _text(addl_loan, "AdditionalLoanMonthlyPaymentAmount", s4b.monthly_payment)
    if s4b.creditor_name:
        _text(addl_loan, "AdditionalLoanCreditorName", s4b.creditor_name)
    if s4b.lien_type:
        _text(addl_loan, "AdditionalLoanLienPriorityType", s4b.lien_type.title())
    if s4b.credit_limit:
        _text(addl_loan, "AdditionalLoanCreditLimitAmount", s4b.credit_limit)


def _build_government_monitoring(loan_el: ET.Element, app: URLAApplication) -> None:
    """Build GOVERNMENT_MONITORING from primary borrower Section 8 (HMDA)."""
    primary = app.primary_borrower()
    if not primary or not primary.section_8:
        return
    s8 = primary.section_8

    gm = _sub(loan_el, "GOVERNMENT_MONITORING")
    gm_detail = _sub(gm, "GOVERNMENT_MONITORING_DETAIL")

    if s8.application_channel:
        _text(gm_detail, "HMDAPreapprovalType", APPLICATION_CHANNEL_MAP.get(
            s8.application_channel, s8.application_channel
        ))

    # Build per-borrower extension for all borrowers
    for borrower in app.borrowers:
        if not borrower.section_8:
            continue
        _build_hmda_borrower(gm, borrower)


def _build_hmda_borrower(gm: ET.Element, borrower: Borrower) -> None:
    """Build HMDA ethnicity/race/sex for a single borrower under GOVERNMENT_MONITORING."""
    s8 = borrower.section_8
    if not s8:
        return

    ext = _sub(gm, "GOVERNMENT_MONITORING_DETAIL_EXTENSION")

    # Ethnicities
    if s8.ethnicity:
        for eth in s8.ethnicity:
            _text(ext, "HMDAEthnicityType", ETHNICITY_MAP.get(eth, eth))

    # Races
    if s8.race:
        for r in s8.race:
            _text(ext, "HMDARaceType", RACE_MAP.get(r, r))

    # Sex
    if s8.sex:
        _text(ext, "HMDAGenderType", SEX_MAP.get(s8.sex, s8.sex))

    # Collection method
    if s8.was_collected_via_visual_observation_or_surname is not None:
        _text(ext, "HMDAEthnicityCollectedBasedOnVisualObservationOrSurnameIndicator",
              s8.was_collected_via_visual_observation_or_surname)
        _text(ext, "HMDARaceCollectedBasedOnVisualObservationOrSurnameIndicator",
              s8.was_collected_via_visual_observation_or_surname)
        _text(ext, "HMDAGenderCollectedBasedOnVisualObservationOrSurnameIndicator",
              s8.was_collected_via_visual_observation_or_surname)


def _build_gifts(loan_el: ET.Element, app: URLAApplication) -> None:
    """Section 4d: gifts and grants."""
    s4d = app.section_4.section_4d if app.section_4 else None
    if not s4d or s4d.does_not_apply or not s4d.gifts:
        return

    gifts_el = _sub(loan_el, "GIFTS")
    for gift in s4d.gifts:
        gift_el = _sub(gifts_el, "GIFT")
        _text(gift_el, "GiftOrGrantAmount", gift.cash_or_market_value)
        _text(gift_el, "GiftOrGrantType", GIFT_TYPE_MAP.get(gift.asset_type, gift.asset_type))
        _text(gift_el, "GiftOrGrantSourceType", GIFT_SOURCE_MAP.get(gift.source, gift.source))
        _text(gift_el, "FundsDepositedIndicator", gift.deposited)


# ---------------------------------------------------------------------------
# PARTIES section
# ---------------------------------------------------------------------------
def _build_parties(
    deal: ET.Element, app: URLAApplication, loan_officer: Optional[LoanOfficer]
) -> List[Tuple[str, str]]:
    """Build all PARTY elements. Returns list of (borrower_id, party_seq) for RELATIONSHIPS."""
    parties_el = _sub(deal, "PARTIES")
    borrower_party_seqs: List[Tuple[str, str]] = []

    # Borrower parties
    for borrower in app.borrowers:
        seq = _build_borrower_party(parties_el, borrower)
        borrower_party_seqs.append((borrower.borrower_id, seq))

    # Loan Originator party (from Section 9 or LoanOfficer param)
    _build_lo_party(parties_el, app, loan_officer)

    return borrower_party_seqs


def _build_borrower_party(parties_el: ET.Element, borrower: Borrower) -> str:
    """Build a PARTY element for a single borrower. Returns the SequenceNumber."""
    party_el = _sub(parties_el, "PARTY")
    party_seq = _sequence_number()
    party_el.set("SequenceNumber", party_seq)

    # INDIVIDUAL -> NAME + CONTACT_POINTS
    _build_individual(party_el, borrower)

    # ROLES -> ROLE -> BORROWER
    roles_el = _sub(party_el, "ROLES")
    role_el = _sub(roles_el, "ROLE")
    role_detail = _sub(role_el, "ROLE_DETAIL")
    _text(role_detail, "PartyRoleType", "Borrower")

    borrower_el = _sub(role_el, "BORROWER")

    # BORROWER_DETAIL
    _build_borrower_detail(borrower_el, borrower)

    # CURRENT_INCOME (from Section 1b employment income)
    _build_current_income(borrower_el, borrower)

    # EMPLOYERS (Section 1b + 1c + 1d)
    _build_employers(borrower_el, borrower)

    # RESIDENCES (current + prior addresses from Section 1a)
    _build_residences(borrower_el, borrower)

    # DECLARATION (Section 5)
    _build_borrower_declaration(borrower_el, borrower)

    return party_seq


def _build_individual(party_el: ET.Element, borrower: Borrower) -> None:
    """Build INDIVIDUAL with NAME and CONTACT_POINTS."""
    s1a = borrower.section_1a
    if not s1a:
        return

    individual = _sub(party_el, "INDIVIDUAL")

    # CONTACT_POINTS
    contacts = _sub(individual, "CONTACT_POINTS")

    if s1a.email:
        cp = _sub(contacts, "CONTACT_POINT")
        email_el = _sub(cp, "CONTACT_POINT_EMAIL")
        _text(email_el, "ContactPointEmailValue", s1a.email)

    phones = [
        ("Home", s1a.home_phone),
        ("Mobile", s1a.cell_phone),
        ("Work", s1a.work_phone),
    ]
    for phone_type, phone_val in phones:
        if phone_val:
            cp = _sub(contacts, "CONTACT_POINT")
            tel = _sub(cp, "CONTACT_POINT_TELEPHONE")
            _text(tel, "ContactPointTelephoneValue", phone_val)

    # NAME
    name_el = _sub(individual, "NAME")
    _text(name_el, "FirstName", s1a.first_name)
    _text(name_el, "MiddleName", s1a.middle_name)
    _text(name_el, "LastName", s1a.last_name)
    _text(name_el, "SuffixName", s1a.suffix)

    # Alternate names
    if s1a.alternate_names:
        aliases = _sub(individual, "ALIASES")
        for alias in s1a.alternate_names:
            alias_el = _sub(aliases, "ALIAS")
            alias_name = _sub(alias_el, "NAME")
            _text(alias_name, "FullName", alias)


def _build_borrower_detail(borrower_el: ET.Element, borrower: Borrower) -> None:
    """Build BORROWER_DETAIL with birth date, SSN, marital, citizenship, military, dependents."""
    s1a = borrower.section_1a
    s7 = borrower.section_7

    detail = _sub(borrower_el, "BORROWER_DETAIL")

    if s1a:
        _text(detail, "BorrowerBirthDate", s1a.date_of_birth)
        _text(detail, "BorrowerSSN", s1a.ssn)

        if s1a.citizenship:
            _text(detail, "CitizenshipResidencyType",
                  CITIZENSHIP_MAP.get(s1a.citizenship, s1a.citizenship))

        if s1a.marital_status:
            _text(detail, "MaritalStatusType",
                  MARITAL_MAP.get(s1a.marital_status, s1a.marital_status))

        if s1a.dependents_count is not None:
            _text(detail, "DependentCount", s1a.dependents_count)
        if s1a.dependents_ages:
            _text(detail, "DependentAgesDescription",
                  ", ".join(str(a) for a in s1a.dependents_ages))

    # Military service (Section 7)
    if s7:
        _text(detail, "SelfDeclaredMilitaryServiceIndicator",
              s7.served_in_military)
        if s7.served_in_military:
            if s7.currently_active_duty:
                _text(detail, "MilitaryStatusType", "ActiveDuty")
            elif s7.retired_discharged_separated:
                _text(detail, "MilitaryStatusType", "RetiredDischarged")
            elif s7.non_activated_reserve_national_guard:
                _text(detail, "MilitaryStatusType", "ReserveNationalGuardNeverActivated")
            elif s7.surviving_spouse:
                _text(detail, "MilitaryStatusType", "SurvivingSpouse")
            if s7.expiration_of_active_duty:
                _text(detail, "MilitaryServiceExpectedCompletionDate",
                      s7.expiration_of_active_duty)


def _build_current_income(borrower_el: ET.Element, borrower: Borrower) -> None:
    """Build CURRENT_INCOME from Section 1b employment income + Section 1e other income."""
    items: List[Tuple[str, Decimal]] = []

    # Employment income breakdown (Section 1b)
    s1b = borrower.section_1b
    if s1b and not s1b.does_not_apply:
        income_fields = [
            ("Base", s1b.base_monthly),
            ("Overtime", s1b.overtime_monthly),
            ("Bonus", s1b.bonus_monthly),
            ("Commissions", s1b.commission_monthly),
            ("MilitaryEntitlements", s1b.military_entitlements_monthly),
            ("Other", s1b.other_monthly),
        ]
        for income_type, amount in income_fields:
            if amount is not None and amount > 0:
                items.append((income_type, amount))

    # Self-employment income
    if s1b and s1b.self_employed and s1b.self_employment_monthly_income_loss is not None:
        items.append(("SelfEmploymentIncome", s1b.self_employment_monthly_income_loss))

    # Additional employment (Section 1c)
    s1c = borrower.section_1c
    if s1c:
        for addl_emp in s1c.employments:
            if addl_emp.base_monthly and addl_emp.base_monthly > 0:
                items.append(("Base", addl_emp.base_monthly))
            if addl_emp.overtime_monthly and addl_emp.overtime_monthly > 0:
                items.append(("Overtime", addl_emp.overtime_monthly))
            if addl_emp.bonus_monthly and addl_emp.bonus_monthly > 0:
                items.append(("Bonus", addl_emp.bonus_monthly))
            if addl_emp.commission_monthly and addl_emp.commission_monthly > 0:
                items.append(("Commissions", addl_emp.commission_monthly))

    # Other income (Section 1e)
    s1e = borrower.section_1e
    if s1e and not s1e.does_not_apply:
        for src in s1e.sources:
            mapped = INCOME_TYPE_MAP.get(src.source_type, "Other")
            items.append((mapped, src.monthly_amount))

    if not items:
        return

    income_el = _sub(borrower_el, "CURRENT_INCOME")
    items_el = _sub(income_el, "CURRENT_INCOME_ITEMS")
    for income_type, amount in items:
        item = _sub(items_el, "CURRENT_INCOME_ITEM")
        item_detail = _sub(item, "CURRENT_INCOME_ITEM_DETAIL")
        _text(item_detail, "CurrentIncomeMonthlyTotalAmount", amount)
        _text(item_detail, "IncomeType", income_type)


def _build_employers(borrower_el: ET.Element, borrower: Borrower) -> None:
    """Build EMPLOYERS from Section 1b (current) + 1c (additional) + 1d (previous)."""
    employers_list: List[Tuple[Section1b_CurrentEmployment, bool]] = []  # (employment, is_current)
    prev_list: List[Section1d_PreviousEmployment] = []

    s1b = borrower.section_1b
    if s1b and not s1b.does_not_apply and s1b.employer_name:
        employers_list.append((s1b, True))

    s1c = borrower.section_1c
    if s1c:
        for addl in s1c.employments:
            if addl.employer_name and not addl.does_not_apply:
                employers_list.append((addl, True))

    s1d = borrower.section_1d
    if s1d and not s1d.does_not_apply and s1d.employer_name:
        prev_list.append(s1d)

    if not employers_list and not prev_list:
        return

    employers_el = _sub(borrower_el, "EMPLOYERS")

    for emp, is_current in employers_list:
        employer_el = _sub(employers_el, "EMPLOYER")
        detail = _sub(employer_el, "EMPLOYER_DETAIL")
        _text(detail, "EmployerName", emp.employer_name)
        _text(detail, "EmploymentPositionDescription", emp.position_title)
        _text(detail, "EmploymentStartDate", emp.start_date)
        _text(detail, "EmploymentStatusType", "Current")
        if emp.self_employed:
            _text(detail, "SelfEmployedIndicator", True)
        if emp.years_in_profession is not None:
            _text(detail, "EmploymentTimeInLineOfWorkMonthsCount",
                  emp.years_in_profession * 12)
        if emp.employed_by_family_or_party_to_transaction is not None:
            _text(detail, "SpecialBorrowerEmployerRelationshipIndicator",
                  emp.employed_by_family_or_party_to_transaction)
        if emp.employer_phone:
            _text(detail, "EmploymentBorrowerSelfEmployedIndicator", emp.self_employed)

        if emp.employer_address:
            _build_address(employer_el, emp.employer_address)

    for prev in prev_list:
        employer_el = _sub(employers_el, "EMPLOYER")
        detail = _sub(employer_el, "EMPLOYER_DETAIL")
        _text(detail, "EmployerName", prev.employer_name)
        _text(detail, "EmploymentPositionDescription", prev.position_title)
        _text(detail, "EmploymentStartDate", prev.start_date)
        _text(detail, "EmploymentEndDate", prev.end_date)
        _text(detail, "EmploymentStatusType", "Previous")
        if prev.self_employed:
            _text(detail, "SelfEmployedIndicator", True)

        if prev.employer_address:
            _build_address(employer_el, prev.employer_address)


def _build_residences(borrower_el: ET.Element, borrower: Borrower) -> None:
    """Build RESIDENCES from Section 1a current + prior addresses."""
    s1a = borrower.section_1a
    if not s1a:
        return

    residences: List[Tuple] = []  # (ResidenceHistory, type_str)

    if s1a.current_address:
        residences.append((s1a.current_address, "Current"))
    if s1a.prior_addresses:
        for prior in s1a.prior_addresses:
            residences.append((prior, "Prior"))

    if not residences:
        return

    residences_el = _sub(borrower_el, "RESIDENCES")
    for res_hist, res_type in residences:
        res_el = _sub(residences_el, "RESIDENCE")
        _build_address(res_el, res_hist.address)

        detail = _sub(res_el, "RESIDENCE_DETAIL")
        total_months = (res_hist.years_at_address * 12) + res_hist.months_at_address
        _text(detail, "BorrowerResidencyDurationMonthsCount", total_months)
        _text(detail, "BorrowerResidencyType", res_type)
        if res_hist.own_or_rent:
            basis_map = {"OWN": "Own", "RENT": "Rent", "NO_PRIMARY_HOUSING_EXPENSE": "LivingRentFree"}
            _text(detail, "BorrowerResidencyBasisType",
                  basis_map.get(res_hist.own_or_rent, res_hist.own_or_rent))


def _build_borrower_declaration(borrower_el: ET.Element, borrower: Borrower) -> None:
    """Build DECLARATION from Section 5 for a borrower."""
    s5 = borrower.section_5
    if not s5:
        return

    decl = _sub(borrower_el, "DECLARATION")
    detail = _sub(decl, "DECLARATION_DETAIL")

    # Section 5a: Property and Money
    s5a = s5.section_5a
    if s5a:
        if s5a.will_occupy_as_primary_residence is not None:
            _text(detail, "IntentToOccupyType",
                  "Yes" if s5a.will_occupy_as_primary_residence else "No")
        if s5a.had_ownership_interest_last_3_years is not None:
            _text(detail, "HomeownerPastThreeYearsType",
                  "Yes" if s5a.had_ownership_interest_last_3_years else "No")
        if s5a.property_type_last_3_years:
            prop_type_map = {
                "PRIMARY": "PrimaryResidence",
                "SECOND_HOME": "SecondHome",
                "INVESTMENT": "Investment",
            }
            _text(detail, "PriorPropertyUsageType",
                  prop_type_map.get(s5a.property_type_last_3_years, s5a.property_type_last_3_years))
        if s5a.how_held_title_last_3_years:
            title_map = {
                "SOLE": "Solely",
                "JOINT_WITH_SPOUSE": "JointlyWithSpouse",
                "JOINT_WITH_OTHER": "JointlyWithOther",
            }
            _text(detail, "PriorPropertyTitleType",
                  title_map.get(s5a.how_held_title_last_3_years, s5a.how_held_title_last_3_years))

        _text(detail, "SpecialBorrowerSellerRelationshipIndicator",
              s5a.family_business_relationship_with_seller)
        _text(detail, "UndisclosedBorrowedFundsIndicator",
              s5a.borrowing_money_for_transaction)
        _text(detail, "UndisclosedBorrowedFundsAmount", s5a.borrowed_amount)
        _text(detail, "UndisclosedMortgageApplicationIndicator",
              s5a.applying_for_other_mortgage_before_closing)
        _text(detail, "UndisclosedCreditApplicationIndicator",
              s5a.applying_for_new_credit_before_closing)
        _text(detail, "PropertyProposedCleanEnergyLienIndicator",
              s5a.property_subject_to_lien)

    # Section 5b: Finances
    s5b = s5.section_5b
    if s5b:
        _text(detail, "UndisclosedComakerOfNoteIndicator",
              s5b.co_signer_on_undisclosed_debt)
        _text(detail, "OutstandingJudgmentsIndicator",
              s5b.outstanding_judgments)
        _text(detail, "PresentlyDelinquentIndicator",
              s5b.currently_delinquent_on_federal_debt)
        _text(detail, "PartyToLawsuitIndicator",
              s5b.party_to_lawsuit)
        _text(detail, "PriorPropertyDeedInLieuConveyedIndicator",
              s5b.conveyed_title_in_lieu_of_foreclosure_last_7_years)
        _text(detail, "PriorPropertyShortSaleCompletedIndicator",
              s5b.short_sale_or_pre_foreclosure_last_7_years)
        _text(detail, "PriorPropertyForeclosureCompletedIndicator",
              s5b.foreclosed_last_7_years)
        _text(detail, "BankruptcyIndicator",
              s5b.declared_bankruptcy_last_7_years)
        if s5b.declared_bankruptcy_last_7_years and s5b.bankruptcy_types:
            bk_type_map = {
                "CHAPTER_7": "Chapter7",
                "CHAPTER_11": "Chapter11",
                "CHAPTER_12": "Chapter12",
                "CHAPTER_13": "Chapter13",
            }
            for bk_type in s5b.bankruptcy_types:
                _text(detail, "BankruptcyChapterType",
                      bk_type_map.get(bk_type, bk_type))


# ---------------------------------------------------------------------------
# Loan Originator PARTY (Section 9)
# ---------------------------------------------------------------------------
def _build_lo_party(
    parties_el: ET.Element,
    app: URLAApplication,
    loan_officer: Optional[LoanOfficer],
) -> None:
    """Build the Loan Originator PARTY from Section 9 data or LoanOfficer param."""
    s9 = app.section_9
    lo = loan_officer

    # Need at least one data source
    if not s9 and not lo:
        return

    party_el = _sub(parties_el, "PARTY")

    # INDIVIDUAL -> NAME
    individual = _sub(party_el, "INDIVIDUAL")

    # Contact points for LO
    lo_email = (s9.loan_originator_email if s9 else None) or (lo.email if lo else None)
    lo_phone = (s9.loan_originator_phone if s9 else None) or (lo.phone if lo else None)
    if lo_email or lo_phone:
        contacts = _sub(individual, "CONTACT_POINTS")
        if lo_email:
            cp = _sub(contacts, "CONTACT_POINT")
            email_el = _sub(cp, "CONTACT_POINT_EMAIL")
            _text(email_el, "ContactPointEmailValue", lo_email)
        if lo_phone:
            cp = _sub(contacts, "CONTACT_POINT")
            tel = _sub(cp, "CONTACT_POINT_TELEPHONE")
            _text(tel, "ContactPointTelephoneValue", lo_phone)

    name_el = _sub(individual, "NAME")
    lo_name = (s9.loan_originator_name if s9 else None) or (lo.name if lo else None)
    if lo_name:
        parts = lo_name.split(None, 1)
        _text(name_el, "FirstName", parts[0] if parts else lo_name)
        if len(parts) > 1:
            _text(name_el, "LastName", parts[1])
    elif lo:
        # LoanOfficer stores name as a single field; split into first/last
        parts = lo.name.split(None, 1)
        _text(name_el, "FirstName", parts[0])
        if len(parts) > 1:
            _text(name_el, "LastName", parts[1])

    # ROLES -> ROLE -> LOAN_ORIGINATOR
    roles_el = _sub(party_el, "ROLES")
    role_el = _sub(roles_el, "ROLE")
    role_detail = _sub(role_el, "ROLE_DETAIL")
    _text(role_detail, "PartyRoleType", "NotePayTo")

    lo_el = _sub(role_el, "LOAN_ORIGINATOR")
    lo_detail = _sub(lo_el, "LOAN_ORIGINATOR_DETAIL")

    nmlsr_id = (s9.loan_originator_nmlsr_id if s9 else None) or (lo.nmlsr_id if lo else None)
    _text(lo_detail, "NMLSIdentifier", nmlsr_id)

    state_license = s9.loan_originator_state_license_id if s9 else None
    _text(lo_detail, "StateLicenseIdentifier", state_license)

    # Organization info
    org_name = (s9.loan_originator_organization_name if s9 else None) or (lo.organization_name if lo else None)
    org_nmlsr = (s9.loan_originator_organization_nmlsr_id if s9 else None) or (lo.organization_nmlsr_id if lo else None)
    if org_name or org_nmlsr:
        org_detail = _sub(lo_detail, "LOAN_ORIGINATION_COMPANY")
        _text(org_detail, "LoanOriginationCompanyName", org_name)
        _text(org_detail, "LoanOriginationCompanyNMLSIdentifier", org_nmlsr)

    if s9 and s9.loan_originator_organization_address:
        _build_address(lo_el, s9.loan_originator_organization_address)

    # TAXPAYER_IDENTIFIERS
    if nmlsr_id:
        tax_ids = _sub(party_el, "TAXPAYER_IDENTIFIERS")
        tax_id = _sub(tax_ids, "TAXPAYER_IDENTIFIER")
        _text(tax_id, "TaxpayerIdentifierType", "NMLSIdentifier")
        _text(tax_id, "TaxpayerIdentifierValue", nmlsr_id)


# ---------------------------------------------------------------------------
# Real Estate Owned (Section 3) -- goes under each borrower or as OWNED_PROPERTIES
# ---------------------------------------------------------------------------
def _build_real_estate_owned(deal: ET.Element, app: URLAApplication) -> None:
    """Build owned property entries from Section 3."""
    s3 = app.section_3
    if not s3 or s3.does_not_apply or not s3.properties:
        return

    # MISMO places REO under OWNED_PROPERTIES within the LOAN or as separate COLLATERALS.
    # For ULAD compliance we add them under a LOANS/LOAN/OWNED_PROPERTIES container.
    # Since the loan is already built, we append to the existing LOAN element.
    loan_el = deal.find(".//LOAN")
    if loan_el is None:
        return

    owned_props = _sub(loan_el, "OWNED_PROPERTIES")
    for prop in s3.properties:
        owned_prop = _sub(owned_props, "OWNED_PROPERTY")
        _build_address(owned_prop, prop.address)

        detail = _sub(owned_prop, "OWNED_PROPERTY_DETAIL")
        _text(detail, "OwnedPropertyMarketValueAmount", prop.property_value)
        _text(detail, "OwnedPropertyDispositionStatusType",
              PROPERTY_STATUS_MAP.get(prop.status, prop.status))
        _text(detail, "OwnedPropertyMaintenanceExpenseAmount",
              prop.monthly_insurance_taxes_assoc_dues)
        _text(detail, "OwnedPropertyRentalIncomeGrossAmount",
              prop.monthly_rental_income)
        _text(detail, "OwnedPropertyRentalIncomeNetAmount",
              prop.net_monthly_rental_income)
        if prop.intended_occupancy:
            _text(detail, "OwnedPropertyOccupancyType",
                  OCCUPANCY_MAP.get(prop.intended_occupancy, prop.intended_occupancy))

        # Mortgages on this property
        if prop.mortgages:
            mortgages_el = _sub(owned_prop, "OWNED_PROPERTY_MORTGAGES")
            for mtg in prop.mortgages:
                mtg_el = _sub(mortgages_el, "OWNED_PROPERTY_MORTGAGE")
                _text(mtg_el, "OwnedPropertyMortgageCreditorName", mtg.creditor_name)
                _text(mtg_el, "OwnedPropertyMortgageMonthlyPaymentAmount", mtg.monthly_payment)
                _text(mtg_el, "OwnedPropertyMortgageUnpaidBalanceAmount", mtg.unpaid_balance)
                _text(mtg_el, "OwnedPropertyMortgageToBePaidOffIndicator", mtg.to_be_paid_off)
                if mtg.credit_limit:
                    _text(mtg_el, "OwnedPropertyMortgageCreditLimitAmount", mtg.credit_limit)


# ---------------------------------------------------------------------------
# RELATIONSHIPS section
# ---------------------------------------------------------------------------
def _build_relationships(
    deal: ET.Element, borrower_seqs: List[Tuple[str, str]], loan_seq: str
) -> None:
    """Build RELATIONSHIPS linking borrower PARTYs to the LOAN."""
    if not borrower_seqs:
        return

    rels_el = _sub(deal, "RELATIONSHIPS")
    for idx, (borrower_id, party_seq) in enumerate(borrower_seqs):
        rel = _sub(rels_el, "RELATIONSHIP")
        rel.set("SequenceNumber", str(idx + 1))
        _text(rel, "ArcRoleType", "urn:fdc:mismo.org:2009:residential/PARTY_IsVerifiedBy_ROLE")
        _text(rel, "From_SequenceNumber", party_seq)
        _text(rel, "To_SequenceNumber", loan_seq)


# ---------------------------------------------------------------------------
# About Versions
# ---------------------------------------------------------------------------
def _build_about_versions(message: ET.Element) -> None:
    """Build ABOUT_VERSIONS header."""
    versions = _sub(message, "ABOUT_VERSIONS")
    version = _sub(versions, "ABOUT_VERSION")
    _text(version, "DataVersionIdentifier", "201003")
    _text(version, "DataVersionName", "Uniform Residential Loan Application")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def serialize_to_mismo34(
    app: URLAApplication,
    loan_officer: Optional[LoanOfficer] = None,
) -> str:
    """
    Serialize a URLAApplication to MISMO 3.4 XML string.

    Returns the complete XML document as a UTF-8 string with XML declaration.

    Args:
        app: The populated URLAApplication model.
        loan_officer: Optional LoanOfficer dataclass; supplements Section 9 data.

    Returns:
        A UTF-8 XML string conforming to MISMO 3.4 ULAD structure.
    """
    # Build the tree with plain (non-namespaced) tag names so that
    # ET.find(".//PARTY") works without namespace prefixes.  The xmlns
    # declarations are injected into the serialized string afterwards.
    message = ET.Element("MESSAGE", {"MISMOVersionID": MISMO_VERSION})

    # ABOUT_VERSIONS
    _build_about_versions(message)

    # DEAL_SETS / DEAL_SET / DEALS / DEAL
    deal_sets = _sub(message, "DEAL_SETS")
    deal_set = _sub(deal_sets, "DEAL_SET")
    deals = _sub(deal_set, "DEALS")
    deal = _sub(deals, "DEAL")

    # Build each major section within DEAL
    _build_assets(deal, app)
    _build_collaterals(deal, app)
    _build_liabilities(deal, app)
    loan_seq = _build_loans(deal, app)
    _build_real_estate_owned(deal, app)
    borrower_seqs = _build_parties(deal, app, loan_officer)
    _build_relationships(deal, borrower_seqs, loan_seq)

    # Serialize to string
    tree = ET.ElementTree(message)
    ET.indent(tree, space="  ")

    xml_body = ET.tostring(message, encoding="unicode", xml_declaration=False)

    # Inject MISMO namespace declarations on the root <MESSAGE> element.
    xml_body = xml_body.replace(
        "<MESSAGE ",
        '<MESSAGE xmlns="{}" xmlns:xsi="{}" xmlns:ULAD="{}" '.format(
            MISMO_NS, XSI_NS, ULAD_NS
        ),
        1,
    )

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body
    return xml_str


def serialize_to_mismo34_bytes(
    app: URLAApplication,
    loan_officer: Optional[LoanOfficer] = None,
) -> bytes:
    """
    Convenience wrapper: returns UTF-8 encoded bytes suitable for writing
    to a file or attaching to an email.
    """
    return serialize_to_mismo34(app, loan_officer).encode("utf-8")
