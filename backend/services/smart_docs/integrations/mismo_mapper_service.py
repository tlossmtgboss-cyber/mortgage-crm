"""
MISMO (Mortgage Industry Standards Maintenance Organization) Data Mapping Service

Maps CRM loan, borrower, income, asset, property, and document data to
MISMO Reference Model 3.6 format for GSE delivery and regulatory exams.

Supports:
- Full MISMO 3.6 XML generation for loan delivery
- Mortgage Compliance Dataset (MCD) v2.0 reports for regulatory exams
- Completeness validation against required MISMO fields
- Individual container mapping (DEAL, PARTIES, COLLATERALS, LOANS, etc.)

MISMO Reference: https://www.mismo.org/standards-and-resources/mismo-reference-model

Usage:
    from services.smart_docs.integrations.mismo_mapper_service import MISMOMapperService

    service = MISMOMapperService(db)
    mismo_data = service.map_loan_to_mismo(loan_id=42, org_id=1)
    xml_str = service.generate_mismo_xml(loan_id=42, org_id=1)
    completeness = service.validate_mismo_completeness(loan_id=42)
"""

import logging
import defusedxml.ElementTree as ET
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from xml.dom import minidom

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

__all__ = ["MISMOMapperService"]


# =============================================================================
# MISMO FIELD MAPPINGS
# =============================================================================

# CRM Loan fields -> MISMO 3.6 data point paths
LOAN_MAPPINGS: Dict[str, str] = {
    # DEAL/LOANS/LOAN
    "amount": "DEAL/LOANS/LOAN/LoanAmountType",
    "rate": "DEAL/LOANS/LOAN/NoteRatePercent",
    "loan_type": "DEAL/LOANS/LOAN/MortgageType",
    "term": "DEAL/LOANS/LOAN/LoanMaturityPeriodCount",
    "loan_purpose": "DEAL/LOANS/LOAN/LoanPurposeType",
    "program": "DEAL/LOANS/LOAN/MortgageProgramType",
    "rate_type": "DEAL/LOANS/LOAN/AmortizationType",
    "loan_number": "DEAL/LOANS/LOAN/LoanIdentifier",
    "purchase_price": "DEAL/LOANS/LOAN/CONSTRUCTION/LandOriginalCostAmount",
    "down_payment": "DEAL/LOANS/LOAN/HOUSING_EXPENSES/HousingExpensePaymentAmount",
    "monthly_payment": "DEAL/LOANS/LOAN/PAYMENT/PaymentAmount",
    "points": "DEAL/LOANS/LOAN/LOAN_DETAIL/DiscountPointsTotalAmount",
    "origination_fee": "DEAL/LOANS/LOAN/FEES/FEE/FeeActualTotalAmount",
    "ltv": "DEAL/LOANS/LOAN/LOAN_TO_VALUE/LTVRatioPercent",
    "cltv": "DEAL/LOANS/LOAN/LOAN_TO_VALUE/CombinedLTVRatioPercent",
    "index_rate": "DEAL/LOANS/LOAN/ADJUSTMENT/IndexCurrentValuePercent",
    "margin": "DEAL/LOANS/LOAN/ADJUSTMENT/IndexMarginPercent",

    # DEAL/LOANS/LOAN/CLOSING_INFORMATION
    "closing_date": "DEAL/LOANS/LOAN/CLOSING_INFORMATION/ClosingDate",
    "funded_date": "DEAL/LOANS/LOAN/CLOSING_INFORMATION/DisbursementDate",
    "first_payment_date": "DEAL/LOANS/LOAN/CLOSING_INFORMATION/FirstPaymentDate",
    "scheduled_closing_date": "DEAL/LOANS/LOAN/CLOSING_INFORMATION/ScheduledClosingDate",

    # DEAL/LOANS/LOAN/QUALIFICATION
    "proposed_housing_expense": "DEAL/LOANS/LOAN/QUALIFICATION/EXPENSE/ExpenseMonthlyPaymentAmount",

    # DEAL/LOANS/LOAN/TERMS_OF_MORTGAGE
    "lock_date": "DEAL/LOANS/LOAN/TERMS_OF_MORTGAGE/RateLockDate",
    "lock_expiration_date": "DEAL/LOANS/LOAN/TERMS_OF_MORTGAGE/RateLockExpirationDate",

    # DEAL/LOANS/LOAN/HMDA_LOAN
    "file_state": "DEAL/LOANS/LOAN/HMDA_LOAN/HMDA_LOAN_DETAIL/StateCode",

    # DEAL/LOANS/LOAN/DISCLOSURE
    "initial_disclosures_sent_date": "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/InitialDisclosureSentDate",
    "initial_disclosures_signed_date": "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/InitialDisclosureReceivedDate",
    "cd_sent_to_borrower_date": "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/ClosingDisclosureSentDate",
    "cd_acknowledged_date": "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/ClosingDisclosureReceivedDate",

    # DEAL/LOANS/LOAN/UNDERWRITING
    "risk_score": "DEAL/LOANS/LOAN/UNDERWRITING/AutomatedUnderwritingRiskScore",
    "loan_approved_date": "DEAL/LOANS/LOAN/UNDERWRITING/ApprovalDate",

    # Insurance / Tax
    "property_tax": "DEAL/LOANS/LOAN/ESCROW/EscrowMonthlyPaymentTaxesAmount",
    "hazard_insurance": "DEAL/LOANS/LOAN/ESCROW/EscrowMonthlyPaymentInsuranceAmount",
    "mortgage_insurance": "DEAL/LOANS/LOAN/MI_DATA/MIMonthlyPaymentAmount",
    "hoa_amount": "DEAL/LOANS/LOAN/HOUSING_EXPENSES/HOADuesAmount",

    # Second lien
    "second_loan_amount": "DEAL/LOANS/LOAN/SUBORDINATE_FINANCING/SubordinateLienAmount",
    "second_loan_rate": "DEAL/LOANS/LOAN/SUBORDINATE_FINANCING/SubordinateNoteRatePercent",
    "second_loan_payment": "DEAL/LOANS/LOAN/SUBORDINATE_FINANCING/SubordinatePaymentAmount",
}

# CRM borrower/lead fields -> MISMO PARTY/BORROWER container
BORROWER_MAPPINGS: Dict[str, str] = {
    "first_name": "PARTY/INDIVIDUAL/NAME/FirstName",
    "last_name": "PARTY/INDIVIDUAL/NAME/LastName",
    "email": "PARTY/INDIVIDUAL/CONTACT_POINTS/CONTACT_POINT/ContactPointEmailValue",
    "phone": "PARTY/INDIVIDUAL/CONTACT_POINTS/CONTACT_POINT/ContactPointTelephoneValue",
    "credit_score": "PARTY/ROLES/ROLE/BORROWER/CREDIT/CREDIT_SCORE/CreditScoreValue",
    "annual_income": "PARTY/ROLES/ROLE/BORROWER/CURRENT_INCOME/CurrentIncomeMonthlyTotalAmount",
    "employment_status": "PARTY/ROLES/ROLE/BORROWER/EMPLOYERS/EMPLOYER/EmploymentStatusType",
    "employer_name": "PARTY/ROLES/ROLE/BORROWER/EMPLOYERS/EMPLOYER/EmployerName",
    "address": "PARTY/ADDRESSES/ADDRESS/AddressLineText",
    "city": "PARTY/ADDRESSES/ADDRESS/CityName",
    "state": "PARTY/ADDRESSES/ADDRESS/StateCode",
    "zip_code": "PARTY/ADDRESSES/ADDRESS/PostalCode",
    "first_time_buyer": "PARTY/ROLES/ROLE/BORROWER/BORROWER_DETAIL/FirstTimeHomebuyerIndicator",
    "debt_to_income": "PARTY/ROLES/ROLE/BORROWER/BORROWER_DETAIL/DebtToIncomeRatio",
    "occupancy_type": "PARTY/ROLES/ROLE/BORROWER/BORROWER_DETAIL/IntendedOccupancyType",
}

# CRM property fields -> MISMO COLLATERAL/SUBJECT_PROPERTY container
PROPERTY_MAPPINGS: Dict[str, str] = {
    "property_address": "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/AddressLineText",
    "property_city": "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/CityName",
    "property_state": "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/StateCode",
    "property_zip": "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/PostalCode",
    "property_county": "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/CountyName",
    "property_type": "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_DETAIL/PropertyType",
    "occupancy_type": "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_DETAIL/PropertyUsageType",
    "property_units": "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_DETAIL/FinancedUnitCount",
    "appraisal_value": "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_VALUATIONS/PROPERTY_VALUATION/PropertyValuationAmount",
    "purchase_price": "COLLATERAL/SUBJECT_PROPERTY/SALES_CONTRACTS/SALES_CONTRACT/SalesContractAmount",
}

# CRM loan_type values -> MISMO MortgageType enumerations
LOAN_TYPE_MISMO_MAP: Dict[str, str] = {
    "conventional": "Conventional",
    "fha": "FHA",
    "va": "VA",
    "usda": "FarmersHomeAdministration",
    "jumbo": "Conventional",  # Jumbo is a conventional variant
    "non_qm": "Other",
}

# CRM property_type values -> MISMO PropertyType enumerations
PROPERTY_TYPE_MISMO_MAP: Dict[str, str] = {
    "single_family": "Detached",
    "condo": "Condominium",
    "townhouse": "Attached",
    "multi_family": "TwoToFourUnitProperty",
    "manufactured": "ManufacturedHousing",
    "Single Family": "Detached",
    "Condo": "Condominium",
    "Townhouse": "Attached",
    "Multi Family": "TwoToFourUnitProperty",
    "Manufactured": "ManufacturedHousing",
}

# CRM occupancy_type values -> MISMO PropertyUsageType enumerations
OCCUPANCY_MISMO_MAP: Dict[str, str] = {
    "primary": "PrimaryResidence",
    "second_home": "SecondHome",
    "investment": "Investment",
    "Primary": "PrimaryResidence",
    "Second Home": "SecondHome",
    "Investment": "Investment",
}

# CRM loan_purpose values -> MISMO LoanPurposeType enumerations
PURPOSE_MISMO_MAP: Dict[str, str] = {
    "purchase": "Purchase",
    "Purchase": "Purchase",
    "refinance": "NoCashOutRefinance",
    "Refinance": "NoCashOutRefinance",
    "cash_out": "CashOutRefinance",
    "Cash Out": "CashOutRefinance",
    "construction": "ConstructionToPermanent",
}

# CRM income source types -> MISMO CurrentIncomeType enumerations
INCOME_TYPE_MISMO_MAP: Dict[str, str] = {
    "w2_employment": "Base",
    "self_employment": "SelfEmployment",
    "commission": "Commissions",
    "bonus": "Bonus",
    "overtime": "Overtime",
    "pension": "Pension",
    "social_security": "SocialSecurity",
    "disability": "Disability",
    "child_support": "ChildSupport",
    "alimony": "AlimonyMaintenance",
    "rental": "NetRentalIncome",
    "investment": "DividendsInterest",
    "part_time": "PartTimeNotSeasonalIncome",
    "military": "MilitaryBasePay",
    "other": "OtherIncome",
}

# CRM DocumentType -> MISMO DocumentType enumerations
DOC_TYPE_MISMO_MAP: Dict[str, str] = {
    "W2": "W2",
    "Paystub": "PayStub",
    "Tax Return (1040)": "FederalIncomeTaxReturn",
    "1099": "IRS1099",
    "Profit & Loss Statement": "ProfitAndLossStatement",
    "Bank Statement": "BankStatement",
    "Credit Report": "CreditReport",
    "Purchase Contract": "SalesContract",
    "Appraisal": "AppraisalReport",
    "Title Commitment": "TitleCommitment",
    "Homeowners Insurance": "HomeownersInsurancePolicy",
    "Loan Estimate": "LoanEstimate",
    "Closing Disclosure": "ClosingDisclosure",
    "Initial Disclosures": "InitialDisclosurePackage",
    "Driver's License": "GovernmentIssuedIdentification",
    "Gift Letter": "GiftLetter",
}

# Required fields for MISMO 3.6 GSE delivery
REQUIRED_MISMO_FIELDS: List[str] = [
    "DEAL/LOANS/LOAN/LoanAmountType",
    "DEAL/LOANS/LOAN/NoteRatePercent",
    "DEAL/LOANS/LOAN/MortgageType",
    "DEAL/LOANS/LOAN/LoanMaturityPeriodCount",
    "DEAL/LOANS/LOAN/LoanPurposeType",
    "DEAL/LOANS/LOAN/LoanIdentifier",
    "DEAL/LOANS/LOAN/CLOSING_INFORMATION/ClosingDate",
    "DEAL/LOANS/LOAN/LOAN_TO_VALUE/LTVRatioPercent",
    "PARTY/INDIVIDUAL/NAME/FirstName",
    "PARTY/INDIVIDUAL/NAME/LastName",
    "PARTY/ROLES/ROLE/BORROWER/CREDIT/CREDIT_SCORE/CreditScoreValue",
    "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/AddressLineText",
    "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/CityName",
    "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/StateCode",
    "COLLATERAL/SUBJECT_PROPERTY/ADDRESS/PostalCode",
    "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_DETAIL/PropertyType",
    "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_DETAIL/PropertyUsageType",
    "COLLATERAL/SUBJECT_PROPERTY/PROPERTY_VALUATIONS/PROPERTY_VALUATION/PropertyValuationAmount",
    "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/InitialDisclosureSentDate",
    "DEAL/LOANS/LOAN/DOCUMENT/DISCLOSURE/ClosingDisclosureSentDate",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _safe_str(value: Any) -> Optional[str]:
    """Convert a value to string, returning None for empty/None values."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _safe_decimal(value: Any) -> Optional[str]:
    """Convert a numeric value to a MISMO-compliant decimal string."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        return str(d.quantize(Decimal("0.01")))
    except Exception:
        return _safe_str(value)


def _safe_date(value: Any) -> Optional[str]:
    """Convert a date/datetime to MISMO date string (YYYY-MM-DD)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return _safe_str(value)


def _safe_bool(value: Any) -> Optional[str]:
    """Convert a boolean to MISMO boolean string (true/false)."""
    if value is None:
        return None
    return "true" if value else "false"


def _translate_enum(value: Any, mapping: Dict[str, str]) -> Optional[str]:
    """Translate a CRM enum value to its MISMO equivalent."""
    if value is None:
        return None
    s = str(value)
    return mapping.get(s, s)


# =============================================================================
# MISMO MAPPER SERVICE
# =============================================================================

class MISMOMapperService:
    """Maps CRM data to MISMO Reference Model 3.6 format.

    Provides individual container mapping methods plus full XML generation
    and completeness validation for GSE delivery and regulatory compliance.
    """

    MISMO_VERSION = "3.6"
    MISMO_NAMESPACE = "http://www.mismo.org/residential/2009/schemas"

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Internal data fetch helpers
    # -------------------------------------------------------------------------

    def _get_loan(self, loan_id: int, org_id: int) -> Optional[Dict[str, Any]]:
        """Fetch loan record with tenant isolation."""
        from database.models.lead_loan import Loan
        loan = (
            self.db.query(Loan)
            .filter(Loan.id == loan_id, Loan.organization_id == org_id)
            .first()
        )
        return loan

    def _get_lead_for_loan(self, loan) -> Optional[Any]:
        """Find the lead associated with this loan via loan_number."""
        if not loan or not loan.loan_number:
            return None
        from database.models.lead_loan import Lead
        return (
            self.db.query(Lead)
            .filter(
                Lead.loan_number == loan.loan_number,
                Lead.organization_id == loan.organization_id,
            )
            .first()
        )

    def _get_income_calculation(self, loan_id: int) -> Optional[Any]:
        """Get the latest approved/completed income calculation for a loan."""
        from database.models.income_calculation import IncomeCalculation
        return (
            self.db.query(IncomeCalculation)
            .filter(IncomeCalculation.loan_id == loan_id)
            .order_by(IncomeCalculation.created_at.desc())
            .first()
        )

    def _get_income_sources(self, calculation_id: int) -> List[Any]:
        """Get income sources for a calculation."""
        from database.models.income_calculation import IncomeSource
        return (
            self.db.query(IncomeSource)
            .filter(IncomeSource.calculation_id == calculation_id)
            .all()
        )

    def _get_documents(self, loan_id: int) -> List[Any]:
        """Get all documents for a loan."""
        from database.models.document import Document
        return (
            self.db.query(Document)
            .filter(Document.loan_id == loan_id, Document.status == "active")
            .all()
        )

    # -------------------------------------------------------------------------
    # Public mapping methods
    # -------------------------------------------------------------------------

    def map_loan_to_mismo(self, loan_id: int, org_id: int) -> Dict[str, Any]:
        """Map all loan fields to MISMO data points.

        Returns a nested dict mirroring the MISMO 3.6 container hierarchy:
        MESSAGE -> DEAL_SETS -> DEAL_SET -> DEALS -> DEAL -> {
            LOANS, PARTIES, COLLATERALS, LIABILITIES, SERVICES, RELATIONSHIPS
        }
        """
        loan = self._get_loan(loan_id, org_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found for org {org_id}")

        lead = self._get_lead_for_loan(loan)

        # Build top-level MISMO message
        mismo = {
            "MISMO_VERSION": self.MISMO_VERSION,
            "MESSAGE": {
                "ABOUT_VERSIONS": {
                    "DataVersionIdentifier": self.MISMO_VERSION,
                    "DataVersionName": "MISMO Reference Model",
                },
                "DEAL_SETS": {
                    "DEAL_SET": {
                        "DEALS": {
                            "DEAL": {
                                "LOANS": self._build_loan_container(loan),
                                "PARTIES": self._build_parties_container(loan, lead),
                                "COLLATERALS": self._build_collateral_container(loan),
                                "LIABILITIES": self._build_liabilities_container(loan),
                                "SERVICES": self._build_services_container(loan),
                            }
                        }
                    }
                },
            },
        }

        return mismo

    def map_borrower_to_mismo(self, borrower_id: int) -> Dict[str, Any]:
        """Map lead/borrower to MISMO BORROWER container.

        Includes Name, Contact, Residence, Employment, Declarations.
        """
        from database.models.lead_loan import Lead
        lead = self.db.query(Lead).filter(Lead.id == borrower_id).first()
        if not lead:
            raise ValueError(f"Borrower (Lead) {borrower_id} not found")

        return self._map_lead_to_party(lead, role="Borrower")

    def map_income_to_mismo(self, calculation_id: int) -> Dict[str, Any]:
        """Map income calculation to MISMO CURRENT_INCOME container.

        Income types: Base, Overtime, Bonus, Commission, SelfEmployment,
        Rental, Other. Includes qualifying income and trending data.
        """
        from database.models.income_calculation import IncomeCalculation
        calc = self.db.query(IncomeCalculation).filter_by(id=calculation_id).first()

        if not calc:
            raise ValueError(f"Income calculation {calculation_id} not found")

        sources = self._get_income_sources(calculation_id)

        income_items = []
        for src in sources:
            source_type = src.source_type
            if hasattr(source_type, "value"):
                source_type = source_type.value

            item = {
                "CURRENT_INCOME_ITEM": {
                    "CurrentIncomeMonthlyTotalAmount": _safe_decimal(src.total_monthly_income),
                    "IncomeType": _translate_enum(source_type, INCOME_TYPE_MISMO_MAP),
                    "EmploymentIncomeIndicator": _safe_bool(
                        source_type in ("w2_employment", "self_employment", "commission")
                    ),
                },
                "EMPLOYER": {
                    "EmployerName": _safe_str(src.employer_name),
                    "PositionTitle": _safe_str(src.position_title),
                    "EmploymentStartDate": _safe_date(src.employment_start_date),
                    "EmploymentYearsCount": _safe_decimal(src.employment_years),
                },
                "INCOME_BREAKDOWN": {
                    "BaseMonthlyIncomeAmount": _safe_decimal(src.base_monthly_income),
                    "OvertimeMonthlyIncomeAmount": _safe_decimal(src.overtime_monthly),
                    "BonusMonthlyIncomeAmount": _safe_decimal(src.bonus_monthly),
                    "CommissionMonthlyIncomeAmount": _safe_decimal(src.commission_monthly),
                    "OtherMonthlyIncomeAmount": _safe_decimal(src.other_monthly),
                },
                "TRENDING": {
                    "TrendingDirection": _safe_str(
                        src.trending_direction.value if src.trending_direction and hasattr(src.trending_direction, "value") else src.trending_direction
                    ),
                    "Year1Income": _safe_decimal(src.year1_income),
                    "Year2Income": _safe_decimal(src.year2_income),
                    "YearOverYearChangePct": _safe_decimal(src.year_over_year_change_pct),
                },
            }
            income_items.append(item)

        return {
            "CURRENT_INCOME": {
                "TotalQualifyingMonthlyIncome": _safe_decimal(calc.total_qualifying_monthly_income),
                "TotalQualifyingAnnualIncome": _safe_decimal(calc.total_qualifying_annual_income),
                "CalculationMethod": _safe_str(calc.calculation_method),
                "FrontEndDTIRatio": _safe_decimal(calc.dti_front_end),
                "BackEndDTIRatio": _safe_decimal(calc.dti_back_end),
                "INCOME_ITEMS": income_items,
            },
        }

    def map_assets_to_mismo(self, loan_id: int) -> Dict[str, Any]:
        """Map asset documents and data to MISMO ASSETS container.

        Pulls from documents table for bank statements and asset documents,
        and from lead financial fields.
        """
        from database.models.lead_loan import Loan
        loan = self.db.query(Loan).filter_by(id=loan_id).first()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        lead = self._get_lead_for_loan(loan)

        # Get asset-related documents
        from database.models.document import Document
        asset_docs = (
            self.db.query(Document)
            .filter(
                Document.loan_id == loan_id,
                Document.status == "active",
                Document.doc_category.in_(["Assets", "ASSETS"]),
            )
            .all()
        )

        asset_items = []
        for doc in asset_docs:
            doc_type = doc.doc_type
            if hasattr(doc_type, "value"):
                doc_type = doc_type.value

            asset_item = {
                "ASSET": {
                    "AssetType": self._map_doc_to_asset_type(doc_type),
                    "DocumentType": _translate_enum(doc_type, DOC_TYPE_MISMO_MAP),
                    "PeriodStartDate": _safe_date(doc.period_start_date),
                    "PeriodEndDate": _safe_date(doc.period_end_date),
                },
            }
            asset_items.append(asset_item)

        # Include down payment as a known asset
        if loan.down_payment:
            asset_items.append({
                "ASSET": {
                    "AssetType": "EarnestMoneyCashDepositTowardPurchase",
                    "AssetCashOrMarketValueAmount": _safe_decimal(loan.down_payment),
                },
            })

        return {
            "ASSETS": {
                "ASSET_ITEMS": asset_items,
                "TotalAssetCount": len(asset_items),
            },
        }

    def map_property_to_mismo(self, loan_id: int) -> Dict[str, Any]:
        """Map property data to MISMO COLLATERAL/SUBJECT_PROPERTY.

        Includes address, type, occupancy, appraised value, and sales
        contract information.
        """
        from database.models.lead_loan import Loan
        loan = self.db.query(Loan).filter_by(id=loan_id).first()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        return self._build_collateral_container(loan)

    def map_documents_to_mismo(self, loan_id: int) -> Dict[str, Any]:
        """Map Smart Docs documents to MISMO DOCUMENT container.

        Maps document types, statuses, and dates.
        """
        docs = self._get_documents(loan_id)

        document_items = []
        for doc in docs:
            doc_type = doc.doc_type
            if hasattr(doc_type, "value"):
                doc_type = doc_type.value

            doc_category = doc.doc_category
            if hasattr(doc_category, "value"):
                doc_category = doc_category.value

            item = {
                "DOCUMENT": {
                    "DocumentIdentifier": str(doc.id),
                    "DocumentType": _translate_enum(doc_type, DOC_TYPE_MISMO_MAP),
                    "DocumentCategoryType": _safe_str(doc_category),
                    "DocumentReceivedDate": _safe_date(doc.uploaded_at),
                    "DocumentStatusType": _map_doc_status_to_mismo(doc.status),
                    "DocumentFileName": _safe_str(doc.filename),
                    "DocumentSourceType": _safe_str(doc.source),
                },
            }
            document_items.append(item)

        return {
            "DOCUMENTS": {
                "DOCUMENT_ITEMS": document_items,
                "TotalDocumentCount": len(document_items),
            },
        }

    # -------------------------------------------------------------------------
    # XML generation
    # -------------------------------------------------------------------------

    def generate_mismo_xml(
        self,
        loan_id: int,
        org_id: int,
        version: str = "3.6",
    ) -> str:
        """Generate full MISMO 3.6 XML for loan delivery.

        Produces a well-formed XML document conforming to the MISMO
        Reference Model namespace and structure.

        Args:
            loan_id: Loan ID to export.
            org_id: Organization ID for tenant isolation.
            version: MISMO version (default "3.6").

        Returns:
            Pretty-printed XML string.
        """
        mismo_data = self.map_loan_to_mismo(loan_id, org_id)

        # Build XML tree
        root = ET.Element("MESSAGE")
        root.set("xmlns", self.MISMO_NAMESPACE)
        root.set("MISMOReferenceModelIdentifier", version)

        # ABOUT_VERSIONS
        about = ET.SubElement(root, "ABOUT_VERSIONS")
        about_ver = ET.SubElement(about, "ABOUT_VERSION")
        ET.SubElement(about_ver, "DataVersionIdentifier").text = version
        ET.SubElement(about_ver, "CreatedDatetime").text = datetime.now(timezone.utc).isoformat()

        # DEAL_SETS -> DEAL_SET -> DEALS -> DEAL
        deal_sets = ET.SubElement(root, "DEAL_SETS")
        deal_set = ET.SubElement(deal_sets, "DEAL_SET")
        deals = ET.SubElement(deal_set, "DEALS")
        deal = ET.SubElement(deals, "DEAL")

        deal_data = mismo_data["MESSAGE"]["DEAL_SETS"]["DEAL_SET"]["DEALS"]["DEAL"]

        # LOANS
        self._dict_to_xml(deal_data.get("LOANS", {}), deal, "LOANS")

        # PARTIES
        self._dict_to_xml(deal_data.get("PARTIES", {}), deal, "PARTIES")

        # COLLATERALS
        self._dict_to_xml(deal_data.get("COLLATERALS", {}), deal, "COLLATERALS")

        # LIABILITIES
        self._dict_to_xml(deal_data.get("LIABILITIES", {}), deal, "LIABILITIES")

        # SERVICES
        self._dict_to_xml(deal_data.get("SERVICES", {}), deal, "SERVICES")

        # Pretty print
        rough_string = ET.tostring(root, encoding="unicode", xml_declaration=False)
        dom = minidom.parseString(rough_string)
        xml_str = dom.toprettyxml(indent="  ", encoding=None)

        # Remove extra blank lines minidom sometimes adds
        lines = [line for line in xml_str.split("\n") if line.strip()]
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # MCD Report
    # -------------------------------------------------------------------------

    def generate_mcd_report(self, loan_id: int, org_id: int) -> Dict[str, Any]:
        """Generate Mortgage Compliance Dataset v2.0 report.

        Required for regulatory exams (new Dec 2025 standard). Includes
        HMDA data points, fair lending indicators, TRID timing, and
        fee tolerance analysis.

        Returns a dict with sections: loan_info, borrower_demographics,
        trid_compliance, fee_analysis, fair_lending, and regulatory_flags.
        """
        loan = self._get_loan(loan_id, org_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found for org {org_id}")

        lead = self._get_lead_for_loan(loan)

        # TRID timing
        le_days = None
        cd_days = None
        if loan.application_date and loan.initial_disclosures_sent_date:
            le_days = (loan.initial_disclosures_sent_date - loan.application_date).days
            if hasattr(le_days, "days"):
                le_days = le_days.days
        if loan.cd_sent_to_borrower_date and loan.funded_date:
            cd_days = (loan.funded_date - loan.cd_sent_to_borrower_date).days
            if hasattr(cd_days, "days"):
                cd_days = cd_days.days

        trid_issues = []
        if le_days is not None and le_days > 3:
            trid_issues.append({
                "type": "LE_TIMING_VIOLATION",
                "detail": f"LE sent {le_days} days after application (max 3 business days)",
                "severity": "high",
            })
        if cd_days is not None and cd_days < 3:
            trid_issues.append({
                "type": "CD_TIMING_VIOLATION",
                "detail": f"CD sent {cd_days} days before closing (min 3 business days)",
                "severity": "critical",
            })

        report = {
            "mcd_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "loan_info": {
                "loan_identifier": _safe_str(loan.loan_number),
                "loan_amount": _safe_decimal(loan.amount),
                "note_rate": _safe_decimal(loan.rate),
                "mortgage_type": _translate_enum(loan.loan_type, LOAN_TYPE_MISMO_MAP),
                "loan_purpose": _translate_enum(loan.loan_purpose, PURPOSE_MISMO_MAP),
                "property_type": _translate_enum(loan.property_type, PROPERTY_TYPE_MISMO_MAP),
                "occupancy_type": _translate_enum(loan.occupancy_type, OCCUPANCY_MISMO_MAP),
                "loan_term_months": loan.term,
                "ltv_ratio": _safe_decimal(loan.ltv),
                "cltv_ratio": _safe_decimal(loan.cltv),
                "property_state": _safe_str(loan.property_state),
                "property_county": _safe_str(loan.property_county),
            },
            "borrower_demographics": {
                "credit_score": lead.credit_score if lead else None,
                "dti_ratio": _safe_decimal(lead.debt_to_income) if lead else None,
                "first_time_buyer": lead.first_time_buyer if lead else None,
                "income_documented": _safe_decimal(lead.annual_income) if lead else None,
            },
            "trid_compliance": {
                "le_application_to_sent_days": le_days,
                "le_sent_date": _safe_date(loan.initial_disclosures_sent_date),
                "le_signed_date": _safe_date(loan.initial_disclosures_signed_date),
                "cd_sent_date": _safe_date(loan.cd_sent_to_borrower_date),
                "cd_acknowledged_date": _safe_date(loan.cd_acknowledged_date),
                "cd_to_closing_days": cd_days,
                "issues": trid_issues,
                "is_compliant": len(trid_issues) == 0,
            },
            "fee_analysis": {
                "origination_fee": _safe_decimal(loan.origination_fee),
                "points": _safe_decimal(loan.points),
                "estimated_prepaid_interest": _safe_decimal(loan.estimated_prepaid_interest),
            },
            "fair_lending": {
                "rate_spread_indicator": None,  # Calculated during HMDA submission
                "hoepa_status": "NotApplicable",
                "qm_status": "QualifiedMortgage" if loan.loan_type != "non_qm" else "NonQualifiedMortgage",
            },
            "regulatory_flags": trid_issues,
        }

        return report

    # -------------------------------------------------------------------------
    # Completeness validation
    # -------------------------------------------------------------------------

    def validate_mismo_completeness(self, loan_id: int) -> Dict[str, Any]:
        """Check which MISMO fields are populated vs. required.

        Returns completeness percentage, populated fields, and missing
        required fields. Uses REQUIRED_MISMO_FIELDS as the baseline.
        """
        # We need to find org_id from the loan
        from database.models.lead_loan import Loan
        loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        org_id = loan.organization_id
        lead = self._get_lead_for_loan(loan)

        populated = set()
        missing_required = []

        # Check loan-level mappings
        for crm_field, mismo_path in LOAN_MAPPINGS.items():
            val = getattr(loan, crm_field, None)
            if val is not None:
                populated.add(mismo_path)

        # Check borrower-level mappings
        if lead:
            for crm_field, mismo_path in BORROWER_MAPPINGS.items():
                val = getattr(lead, crm_field, None)
                if val is not None:
                    populated.add(mismo_path)

        # Check property-level mappings
        for crm_field, mismo_path in PROPERTY_MAPPINGS.items():
            val = getattr(loan, crm_field, None)
            if val is not None:
                populated.add(mismo_path)

        # Check required fields
        for req_path in REQUIRED_MISMO_FIELDS:
            if req_path not in populated:
                missing_required.append(req_path)

        total_mapped = len(LOAN_MAPPINGS) + len(BORROWER_MAPPINGS) + len(PROPERTY_MAPPINGS)
        populated_count = len(populated)
        completeness_pct = round((populated_count / total_mapped) * 100, 1) if total_mapped > 0 else 0

        required_populated = len(REQUIRED_MISMO_FIELDS) - len(missing_required)
        required_pct = round(
            (required_populated / len(REQUIRED_MISMO_FIELDS)) * 100, 1
        ) if REQUIRED_MISMO_FIELDS else 0

        return {
            "loan_id": loan_id,
            "mismo_version": self.MISMO_VERSION,
            "completeness": {
                "total_mapped_fields": total_mapped,
                "populated_fields": populated_count,
                "completeness_pct": completeness_pct,
            },
            "required_fields": {
                "total_required": len(REQUIRED_MISMO_FIELDS),
                "populated": required_populated,
                "missing": missing_required,
                "required_completeness_pct": required_pct,
            },
            "gse_delivery_ready": len(missing_required) == 0,
            "populated_paths": sorted(populated),
        }

    # -------------------------------------------------------------------------
    # Internal container builders
    # -------------------------------------------------------------------------

    def _build_loan_container(self, loan) -> Dict[str, Any]:
        """Build the MISMO LOANS container from a Loan object."""
        return {
            "LOAN": {
                "LoanIdentifier": _safe_str(loan.loan_number),
                "LoanAmountType": _safe_decimal(loan.amount),
                "NoteRatePercent": _safe_decimal(loan.rate),
                "MortgageType": _translate_enum(loan.loan_type, LOAN_TYPE_MISMO_MAP),
                "LoanMaturityPeriodCount": loan.term,
                "LoanPurposeType": _translate_enum(loan.loan_purpose, PURPOSE_MISMO_MAP),
                "MortgageProgramType": _safe_str(loan.program),
                "AmortizationType": _safe_str(loan.rate_type),
                "LOAN_DETAIL": {
                    "DiscountPointsTotalAmount": _safe_decimal(loan.points),
                    "OriginationFeeAmount": _safe_decimal(loan.origination_fee),
                },
                "LOAN_TO_VALUE": {
                    "LTVRatioPercent": _safe_decimal(loan.ltv),
                    "CombinedLTVRatioPercent": _safe_decimal(loan.cltv),
                },
                "CLOSING_INFORMATION": {
                    "ClosingDate": _safe_date(loan.closing_date),
                    "DisbursementDate": _safe_date(loan.funded_date),
                    "ScheduledClosingDate": _safe_date(loan.scheduled_closing_date),
                    "FirstPaymentDate": _safe_date(loan.first_payment_date),
                },
                "TERMS_OF_MORTGAGE": {
                    "RateLockDate": _safe_date(loan.lock_date),
                    "RateLockExpirationDate": _safe_date(loan.lock_expiration_date),
                },
                "PAYMENT": {
                    "PaymentAmount": _safe_decimal(loan.monthly_payment),
                },
                "ESCROW": {
                    "EscrowMonthlyPaymentTaxesAmount": _safe_decimal(loan.property_tax),
                    "EscrowMonthlyPaymentInsuranceAmount": _safe_decimal(loan.hazard_insurance),
                },
                "MI_DATA": {
                    "MIMonthlyPaymentAmount": _safe_decimal(loan.mortgage_insurance),
                },
                "HOUSING_EXPENSES": {
                    "HOADuesAmount": _safe_decimal(loan.hoa_amount),
                },
                "ADJUSTMENT": {
                    "IndexCurrentValuePercent": _safe_decimal(loan.index_rate),
                    "IndexMarginPercent": _safe_decimal(loan.margin),
                },
                "UNDERWRITING": {
                    "AutomatedUnderwritingRiskScore": loan.risk_score,
                    "ApprovalDate": _safe_date(loan.loan_approved_date),
                },
                "DISCLOSURE": {
                    "InitialDisclosureSentDate": _safe_date(loan.initial_disclosures_sent_date),
                    "InitialDisclosureReceivedDate": _safe_date(loan.initial_disclosures_signed_date),
                    "ClosingDisclosureSentDate": _safe_date(loan.cd_sent_to_borrower_date),
                    "ClosingDisclosureReceivedDate": _safe_date(loan.cd_acknowledged_date),
                },
                "SUBORDINATE_FINANCING": {
                    "SubordinateLienAmount": _safe_decimal(loan.second_loan_amount),
                    "SubordinateNoteRatePercent": _safe_decimal(loan.second_loan_rate),
                    "SubordinatePaymentAmount": _safe_decimal(loan.second_loan_payment),
                },
            },
        }

    def _build_parties_container(self, loan, lead) -> Dict[str, Any]:
        """Build the MISMO PARTIES container with borrower and co-borrower."""
        parties = {"PARTY": []}

        # Primary borrower
        if lead:
            parties["PARTY"].append(self._map_lead_to_party(lead, role="Borrower"))
        else:
            # Fall back to loan-level borrower info
            parties["PARTY"].append({
                "INDIVIDUAL": {
                    "NAME": {
                        "FullName": _safe_str(loan.borrower_name),
                    },
                    "CONTACT_POINTS": {
                        "CONTACT_POINT": {
                            "ContactPointEmailValue": _safe_str(loan.borrower_email),
                            "ContactPointTelephoneValue": _safe_str(loan.borrower_phone),
                        },
                    },
                },
                "ROLES": {
                    "ROLE": {
                        "ROLE_DETAIL": {
                            "PartyRoleType": "Borrower",
                        },
                    },
                },
            })

        # Co-borrower
        coborrower_name = loan.coborrower_name
        if coborrower_name:
            parties["PARTY"].append({
                "INDIVIDUAL": {
                    "NAME": {
                        "FullName": _safe_str(coborrower_name),
                    },
                    "CONTACT_POINTS": {
                        "CONTACT_POINT": {
                            "ContactPointEmailValue": _safe_str(loan.co_borrower_email),
                        },
                    },
                },
                "ROLES": {
                    "ROLE": {
                        "ROLE_DETAIL": {
                            "PartyRoleType": "CoBorrower",
                        },
                    },
                },
            })

        # Seller (realtor)
        if loan.realtor_agent:
            parties["PARTY"].append({
                "INDIVIDUAL": {
                    "NAME": {
                        "FullName": _safe_str(loan.realtor_agent),
                    },
                },
                "ROLES": {
                    "ROLE": {
                        "ROLE_DETAIL": {
                            "PartyRoleType": "SellingAgent",
                        },
                    },
                },
            })

        return parties

    def _build_collateral_container(self, loan) -> Dict[str, Any]:
        """Build the MISMO COLLATERALS container."""
        return {
            "COLLATERAL": {
                "SUBJECT_PROPERTY": {
                    "ADDRESS": {
                        "AddressLineText": _safe_str(loan.property_address),
                        "CityName": _safe_str(loan.property_city),
                        "StateCode": _safe_str(loan.property_state),
                        "PostalCode": _safe_str(loan.property_zip),
                        "CountyName": _safe_str(loan.property_county),
                    },
                    "PROPERTY_DETAIL": {
                        "PropertyType": _translate_enum(
                            loan.property_type, PROPERTY_TYPE_MISMO_MAP
                        ),
                        "PropertyUsageType": _translate_enum(
                            loan.occupancy_type, OCCUPANCY_MISMO_MAP
                        ),
                        "FinancedUnitCount": loan.property_units,
                    },
                    "PROPERTY_VALUATIONS": {
                        "PROPERTY_VALUATION": {
                            "PropertyValuationAmount": _safe_decimal(loan.appraisal_value),
                            "AppraisalOrderedDate": _safe_date(loan.appraisal_ordered_date),
                            "AppraisalCompletedDate": _safe_date(loan.appraisal_completed_date),
                            "AppraisalReceivedDate": _safe_date(loan.appraisal_received_date),
                        },
                    },
                    "SALES_CONTRACTS": {
                        "SALES_CONTRACT": {
                            "SalesContractAmount": _safe_decimal(loan.purchase_price),
                        },
                    },
                },
            },
        }

    def _build_liabilities_container(self, loan) -> Dict[str, Any]:
        """Build MISMO LIABILITIES container from housing expense data."""
        return {
            "LIABILITY": {
                "HOUSING_EXPENSES": {
                    "PresentHousingExpense": _safe_decimal(loan.present_housing_expense),
                    "ProposedHousingExpense": _safe_decimal(loan.proposed_housing_expense),
                    "PresentMonthlyPayment": _safe_decimal(loan.present_monthly_payment),
                    "ProposedMonthlyPayment": _safe_decimal(loan.proposed_monthly_payment),
                },
            },
        }

    def _build_services_container(self, loan) -> Dict[str, Any]:
        """Build MISMO SERVICES container for third-party services."""
        services = {"SERVICE": []}

        if loan.title_company:
            services["SERVICE"].append({
                "SERVICE_DETAIL": {
                    "ServiceType": "TitleInsurance",
                    "ServiceProviderName": _safe_str(loan.title_company),
                    "ServiceOrderedDate": _safe_date(loan.title_ordered_date),
                    "ServiceReceivedDate": _safe_date(loan.title_received_date),
                },
            })

        if loan.lender:
            services["SERVICE"].append({
                "SERVICE_DETAIL": {
                    "ServiceType": "Lender",
                    "ServiceProviderName": _safe_str(loan.lender),
                },
            })

        return services

    def _map_lead_to_party(self, lead, role: str = "Borrower") -> Dict[str, Any]:
        """Map a Lead record to a MISMO PARTY dict."""
        return {
            "INDIVIDUAL": {
                "NAME": {
                    "FirstName": _safe_str(lead.first_name),
                    "LastName": _safe_str(lead.last_name),
                    "FullName": _safe_str(lead.name),
                },
                "CONTACT_POINTS": {
                    "CONTACT_POINT": {
                        "ContactPointEmailValue": _safe_str(lead.email),
                        "ContactPointTelephoneValue": _safe_str(lead.phone),
                        "ContactPointPreference": _safe_str(lead.preferred_communication),
                    },
                },
            },
            "ADDRESSES": {
                "ADDRESS": {
                    "AddressLineText": _safe_str(lead.address),
                    "CityName": _safe_str(lead.city),
                    "StateCode": _safe_str(lead.state),
                    "PostalCode": _safe_str(lead.zip_code),
                },
            },
            "ROLES": {
                "ROLE": {
                    "ROLE_DETAIL": {
                        "PartyRoleType": role,
                    },
                    "BORROWER": {
                        "BORROWER_DETAIL": {
                            "FirstTimeHomebuyerIndicator": _safe_bool(lead.first_time_buyer),
                            "DebtToIncomeRatio": _safe_decimal(lead.debt_to_income),
                            "IntendedOccupancyType": _translate_enum(
                                lead.occupancy_type, OCCUPANCY_MISMO_MAP
                            ),
                        },
                        "CREDIT": {
                            "CREDIT_SCORE": {
                                "CreditScoreValue": lead.credit_score,
                            },
                        },
                        "CURRENT_INCOME": {
                            "CurrentIncomeMonthlyTotalAmount": _safe_decimal(
                                Decimal(str(lead.annual_income)) / 12
                                if lead.annual_income else None
                            ),
                        },
                        "EMPLOYERS": {
                            "EMPLOYER": {
                                "EmployerName": _safe_str(lead.employer_name),
                                "EmploymentStatusType": _safe_str(lead.employment_status),
                            },
                        },
                    },
                },
            },
        }

    def _map_doc_to_asset_type(self, doc_type: str) -> str:
        """Map a document type string to a MISMO asset type."""
        asset_map = {
            "Bank Statement": "CheckingAccount",
            "Retirement Account Statement": "RetirementFund",
            "Investment Statement": "StockBond",
            "Gift Letter": "GiftOfCash",
        }
        return asset_map.get(doc_type, "OtherLiquidAsset")

    # -------------------------------------------------------------------------
    # XML helper
    # -------------------------------------------------------------------------

    def _dict_to_xml(
        self,
        data: Any,
        parent: ET.Element,
        tag_name: str,
    ) -> None:
        """Recursively convert a dict to XML sub-elements under parent."""
        if data is None:
            return

        elem = ET.SubElement(parent, tag_name)

        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    continue
                if isinstance(value, dict):
                    self._dict_to_xml(value, elem, key)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            self._dict_to_xml(item, elem, key)
                        elif item is not None:
                            sub = ET.SubElement(elem, key)
                            sub.text = str(item)
                else:
                    sub = ET.SubElement(elem, key)
                    sub.text = str(value)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Use tag_name + "_ITEM" for list items
                    self._dict_to_xml(item, elem, f"{tag_name}_ITEM")
                elif item is not None:
                    sub = ET.SubElement(elem, "ITEM")
                    sub.text = str(item)
        else:
            elem.text = str(data)


# =============================================================================
# Module-level helpers
# =============================================================================

def _map_doc_status_to_mismo(status: Optional[str]) -> str:
    """Map CRM document status to MISMO DocumentStatusType."""
    status_map = {
        "active": "Received",
        "archived": "Archived",
        "deleted": "Voided",
        "pending": "Pending",
    }
    return status_map.get(status, "Other") if status else "Other"


def get_mismo_mapper_service(db: Session) -> MISMOMapperService:
    """Factory function to create a MISMOMapperService instance."""
    return MISMOMapperService(db)
