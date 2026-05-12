"""
MISMO 3.4 XML Generator Service
Generates industry-standard MISMO 3.4 XML from application data for LOS integration
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import uuid

logger = logging.getLogger(__name__)

# MISMO 3.4 Namespace
MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
XLINK_NS = "http://www.w3.org/1999/xlink"


class MISMOGenerator:
    """
    MISMO 3.4 XML Generator for Uniform Residential Loan Application (URLA)

    Converts internal application data to MISMO 3.4 compliant XML format
    for integration with Loan Origination Systems (LOS).
    """

    # Loan purpose mapping
    LOAN_PURPOSE_MAP = {
        "purchase": "Purchase",
        "refinance": "NoCashOutRefinance",
        "cash_out_refinance": "CashOutRefinance",
        "construction": "ConstructionToPermanent",
    }

    # Property type mapping
    PROPERTY_TYPE_MAP = {
        "single_family": "Attached",
        "condo": "Condominium",
        "townhouse": "Attached",
        "multi_family": "Attached",
        "manufactured": "ManufacturedHousing",
    }

    # Occupancy mapping
    OCCUPANCY_MAP = {
        "primary": "PrimaryResidence",
        "secondary": "SecondHome",
        "investment": "Investor",
    }

    # Employment type mapping
    EMPLOYMENT_TYPE_MAP = {
        "w2": "Employed",
        "self_employed": "SelfEmployed",
        "1099": "Contract",
        "retired": "Retired",
        "other": "Other",
    }

    # Marital status mapping
    MARITAL_STATUS_MAP = {
        "single": "Unmarried",
        "married": "Married",
        "divorced": "Unmarried",
        "separated": "Separated",
        "widowed": "Unmarried",
    }

    # Citizenship mapping
    CITIZENSHIP_MAP = {
        "us_citizen": "USCitizen",
        "permanent_resident": "PermanentResidentAlien",
        "non_permanent_resident": "NonPermanentResidentAlien",
    }

    def __init__(self):
        self.message_id = str(uuid.uuid4())
        self.timestamp = datetime.now(timezone.utc).isoformat() + "Z"

    def generate(self, application_data: Dict[str, Any]) -> str:
        """
        Generate MISMO 3.4 XML from application data

        Args:
            application_data: Dictionary containing all application fields

        Returns:
            Pretty-printed MISMO 3.4 XML string
        """
        # Create root element with namespaces
        root = Element("MESSAGE")
        root.set("xmlns", MISMO_NS)
        root.set("xmlns:xlink", XLINK_NS)
        root.set("MISMOReferenceModelIdentifier", "3.4.0")

        # Add message header
        self._add_about_versions(root)

        # Add deal sets container
        deal_sets = SubElement(root, "DEAL_SETS")
        deal_set = SubElement(deal_sets, "DEAL_SET")
        deals = SubElement(deal_set, "DEALS")
        deal = SubElement(deals, "DEAL")

        # Add main sections
        self._add_parties(deal, application_data)
        self._add_collaterals(deal, application_data)
        self._add_loans(deal, application_data)
        self._add_services(deal, application_data)

        # Convert to pretty-printed string
        xml_string = tostring(root, encoding="unicode")
        dom = minidom.parseString(xml_string)
        return dom.toprettyxml(indent="  ")

    def _add_about_versions(self, root: Element):
        """Add MISMO version information"""
        about = SubElement(root, "ABOUT_VERSIONS")
        about_version = SubElement(about, "ABOUT_VERSION")

        SubElement(about_version, "AboutVersionIdentifier").text = self.message_id
        SubElement(about_version, "CreatedDatetime").text = self.timestamp

        data_version = SubElement(about_version, "DataVersionIdentifier")
        data_version.text = "3.4.0"

    def _add_parties(self, deal: Element, data: Dict):
        """Add parties section (borrowers, employers, etc.)"""
        parties = SubElement(deal, "PARTIES")

        # Add primary borrower
        self._add_borrower_party(parties, data, is_coborrower=False)

        # Add co-borrower if present
        if data.get("has_coborrower") or data.get("co_first_name"):
            self._add_borrower_party(parties, data, is_coborrower=True)

        # Add employer
        if data.get("employerName"):
            self._add_employer_party(parties, data)

    def _add_borrower_party(self, parties: Element, data: Dict, is_coborrower: bool = False):
        """Add a borrower party"""
        prefix = "co_" if is_coborrower else ""
        party = SubElement(parties, "PARTY")
        party.set("SequenceNumber", "2" if is_coborrower else "1")

        # Individual
        individual = SubElement(party, "INDIVIDUAL")
        name = SubElement(individual, "NAME")

        first_name = data.get(f"{prefix}first_name") or data.get(f"{prefix}firstName") or ""
        last_name = data.get(f"{prefix}last_name") or data.get(f"{prefix}lastName") or ""
        middle_name = data.get(f"{prefix}middle_name") or data.get(f"{prefix}middleName") or ""

        SubElement(name, "FirstName").text = first_name
        SubElement(name, "LastName").text = last_name
        if middle_name:
            SubElement(name, "MiddleName").text = middle_name

        # Contact points
        contact_points = SubElement(individual, "CONTACT_POINTS")

        # Email
        email = data.get(f"{prefix}email") or ""
        if email:
            contact = SubElement(contact_points, "CONTACT_POINT")
            contact_detail = SubElement(contact, "CONTACT_POINT_EMAIL")
            SubElement(contact_detail, "ContactPointEmailValue").text = email

        # Phone
        phone = data.get(f"{prefix}phone") or ""
        if phone:
            contact = SubElement(contact_points, "CONTACT_POINT")
            contact_detail = SubElement(contact, "CONTACT_POINT_TELEPHONE")
            SubElement(contact_detail, "ContactPointTelephoneValue").text = phone

        # Roles
        roles = SubElement(party, "ROLES")
        role = SubElement(roles, "ROLE")

        # Borrower details
        borrower = SubElement(role, "BORROWER")
        borrower_detail = SubElement(borrower, "BORROWER_DETAIL")

        # Marital status
        marital = data.get("maritalStatus") or data.get("marital_status") or ""
        if marital:
            marital_status = self.MARITAL_STATUS_MAP.get(marital.lower(), "Unknown")
            SubElement(borrower_detail, "MaritalStatusType").text = marital_status

        # Dependents
        dependents = data.get("dependentsCount") or data.get("dependents_count") or 0
        SubElement(borrower_detail, "DependentCount").text = str(dependents)

        # Declaration
        declaration = SubElement(borrower, "DECLARATION")
        self._add_declarations(declaration, data)

        # Government monitoring
        gov = SubElement(borrower, "GOVERNMENT_MONITORING")
        gov_detail = SubElement(gov, "GOVERNMENT_MONITORING_DETAIL")

        citizenship = data.get("citizenshipStatus") or data.get("citizenship_status") or ""
        if citizenship:
            citizen_type = self.CITIZENSHIP_MAP.get(citizenship.lower(), "Unknown")
            SubElement(gov_detail, "CitizenshipResidencyType").text = citizen_type

        # Employment
        if not is_coborrower and data.get("employerName"):
            self._add_employment(role, data)

    def _add_declarations(self, declaration: Element, data: Dict):
        """Add borrower declarations"""
        detail = SubElement(declaration, "DECLARATION_DETAIL")

        # Bankruptcy
        has_bankruptcy = data.get("hasBankruptcy") or data.get("has_bankruptcy")
        SubElement(detail, "BankruptcyIndicator").text = "true" if has_bankruptcy else "false"

        # Foreclosure
        has_foreclosure = data.get("hasForeclosure") or data.get("has_foreclosure")
        SubElement(detail, "PropertyForeclosedPastSevenYearsIndicator").text = "true" if has_foreclosure else "false"

        # Lawsuit
        has_lawsuit = data.get("hasLawsuit") or data.get("has_lawsuit")
        SubElement(detail, "PartyToLawsuitIndicator").text = "true" if has_lawsuit else "false"

        # Occupy property
        will_occupy = data.get("willOccupyProperty") or data.get("will_occupy_property")
        SubElement(detail, "IntentToOccupyType").text = "Yes" if will_occupy else "No"

        # Delinquent debt
        has_delinquent = data.get("hasDelinquentDebt") or data.get("has_delinquent_debt")
        SubElement(detail, "OutstandingJudgementsIndicator").text = "true" if has_delinquent else "false"

    def _add_employment(self, role: Element, data: Dict):
        """Add employment information"""
        employer = SubElement(role, "EMPLOYER")

        # Employment detail
        emp_detail = SubElement(employer, "EMPLOYMENT")
        detail = SubElement(emp_detail, "EMPLOYMENT_DETAIL")

        emp_type = data.get("employmentType") or data.get("employment_type") or ""
        if emp_type:
            employment_type = self.EMPLOYMENT_TYPE_MAP.get(emp_type.lower(), "Other")
            SubElement(detail, "EmploymentClassificationType").text = employment_type

        position = data.get("jobTitle") or data.get("job_title") or ""
        if position:
            SubElement(detail, "EmploymentPositionDescription").text = position

        years = data.get("yearsEmployed") or data.get("years_employed") or 0
        months = data.get("monthsEmployed") or data.get("months_employed") or 0
        total_months = int(years) * 12 + int(months)
        SubElement(detail, "EmploymentMonthsOnJobCount").text = str(total_months)

        # Legal entity (employer name)
        legal = SubElement(employer, "LEGAL_ENTITY")
        legal_detail = SubElement(legal, "LEGAL_ENTITY_DETAIL")
        SubElement(legal_detail, "FullName").text = data.get("employerName") or ""

        # Address
        if data.get("employerAddress"):
            contacts = SubElement(legal, "CONTACTS")
            contact = SubElement(contacts, "CONTACT")
            address = SubElement(contact, "ADDRESS")
            SubElement(address, "AddressLineText").text = data.get("employerAddress") or ""
            SubElement(address, "CityName").text = data.get("employerCity") or ""
            SubElement(address, "StateCode").text = data.get("employerState") or ""

    def _add_employer_party(self, parties: Element, data: Dict):
        """Add employer as a separate party"""
        party = SubElement(parties, "PARTY")
        party.set("SequenceNumber", "3")

        legal = SubElement(party, "LEGAL_ENTITY")
        detail = SubElement(legal, "LEGAL_ENTITY_DETAIL")
        SubElement(detail, "FullName").text = data.get("employerName") or ""

        # Contact info
        if data.get("employerPhone"):
            contacts = SubElement(legal, "CONTACTS")
            contact = SubElement(contacts, "CONTACT")
            contact_points = SubElement(contact, "CONTACT_POINTS")
            cp = SubElement(contact_points, "CONTACT_POINT")
            phone = SubElement(cp, "CONTACT_POINT_TELEPHONE")
            SubElement(phone, "ContactPointTelephoneValue").text = data.get("employerPhone") or ""

    def _add_collaterals(self, deal: Element, data: Dict):
        """Add collateral (property) information"""
        collaterals = SubElement(deal, "COLLATERALS")
        collateral = SubElement(collaterals, "COLLATERAL")

        # Subject property
        subject = SubElement(collateral, "SUBJECT_PROPERTY")

        # Address
        address = SubElement(subject, "ADDRESS")
        SubElement(address, "AddressLineText").text = data.get("propertyAddress") or ""
        SubElement(address, "CityName").text = data.get("city") or ""
        SubElement(address, "StateCode").text = data.get("state") or ""
        SubElement(address, "PostalCode").text = data.get("zip") or ""
        SubElement(address, "CountyName").text = data.get("county") or ""

        # Property detail
        prop_detail = SubElement(subject, "PROPERTY_DETAIL")

        prop_type = data.get("propertyType") or data.get("property_type") or ""
        if prop_type:
            property_type = self.PROPERTY_TYPE_MAP.get(prop_type.lower(), "Unknown")
            SubElement(prop_detail, "PropertyEstateType").text = property_type

        # Property valuations
        valuations = SubElement(subject, "PROPERTY_VALUATIONS")
        valuation = SubElement(valuations, "PROPERTY_VALUATION")
        val_detail = SubElement(valuation, "PROPERTY_VALUATION_DETAIL")

        purchase_price = data.get("purchasePrice") or data.get("purchase_price") or 0
        SubElement(val_detail, "PropertyValuationAmount").text = str(purchase_price)

    def _add_loans(self, deal: Element, data: Dict):
        """Add loan information"""
        loans = SubElement(deal, "LOANS")
        loan = SubElement(loans, "LOAN")

        # Loan detail
        loan_detail = SubElement(loan, "LOAN_DETAIL")

        purpose = data.get("loanPurpose") or data.get("loan_purpose") or ""
        if purpose:
            loan_purpose = self.LOAN_PURPOSE_MAP.get(purpose.lower(), "Unknown")
            SubElement(loan_detail, "LoanPurposeType").text = loan_purpose

        # Calculate loan amount from purchase price and down payment
        purchase_price = float(data.get("purchasePrice") or data.get("purchase_price") or 0)
        down_payment = float(data.get("downPayment") or data.get("down_payment") or 0)
        down_type = data.get("downPaymentType") or data.get("down_payment_type") or "percentage"

        if down_type == "percentage":
            down_amount = purchase_price * (down_payment / 100)
        else:
            down_amount = down_payment

        loan_amount = purchase_price - down_amount
        SubElement(loan_detail, "BorrowerRequestedLoanAmount").text = str(int(loan_amount))

        # Terms
        terms = SubElement(loan, "TERMS_OF_LOAN")
        SubElement(terms, "BaseLoanAmount").text = str(int(loan_amount))

        # Occupancy
        occupancy = data.get("occupancy") or ""
        if occupancy:
            occ_type = self.OCCUPANCY_MAP.get(occupancy.lower(), "Unknown")
            SubElement(loan_detail, "PropertyUsageType").text = occ_type

        # Housing expense
        housing = SubElement(loan, "HOUSING_EXPENSES")
        expense = SubElement(housing, "HOUSING_EXPENSE")
        exp_detail = SubElement(expense, "HOUSING_EXPENSE_DETAIL")

        rent = data.get("monthlyRentMortgage") or data.get("monthly_rent_mortgage") or 0
        SubElement(exp_detail, "HousingExpensePaymentAmount").text = str(rent)
        SubElement(exp_detail, "HousingExpenseType").text = "Rent"

        # Current income
        self._add_income(loan, data)

        # Assets
        self._add_assets(loan, data)

        # Liabilities
        self._add_liabilities(loan, data)

    def _add_income(self, loan: Element, data: Dict):
        """Add income information"""
        current_income = SubElement(loan, "CURRENT_INCOME")

        annual = float(data.get("annualIncome") or data.get("annual_income") or 0)
        monthly_base = annual / 12

        # Base income
        income = SubElement(current_income, "CURRENT_INCOME_ITEM")
        detail = SubElement(income, "CURRENT_INCOME_ITEM_DETAIL")
        SubElement(detail, "CurrentIncomeMonthlyTotalAmount").text = str(int(monthly_base))
        SubElement(detail, "IncomeType").text = "Base"

        # Bonus
        bonus = float(data.get("monthlyBonus") or data.get("monthly_bonus") or 0)
        if bonus > 0:
            income = SubElement(current_income, "CURRENT_INCOME_ITEM")
            detail = SubElement(income, "CURRENT_INCOME_ITEM_DETAIL")
            SubElement(detail, "CurrentIncomeMonthlyTotalAmount").text = str(int(bonus))
            SubElement(detail, "IncomeType").text = "Bonus"

        # Commission
        commission = float(data.get("monthlyCommission") or data.get("monthly_commission") or 0)
        if commission > 0:
            income = SubElement(current_income, "CURRENT_INCOME_ITEM")
            detail = SubElement(income, "CURRENT_INCOME_ITEM_DETAIL")
            SubElement(detail, "CurrentIncomeMonthlyTotalAmount").text = str(int(commission))
            SubElement(detail, "IncomeType").text = "Commission"

        # Other income
        other = float(data.get("otherIncome") or data.get("other_income") or 0)
        if other > 0:
            income = SubElement(current_income, "CURRENT_INCOME_ITEM")
            detail = SubElement(income, "CURRENT_INCOME_ITEM_DETAIL")
            SubElement(detail, "CurrentIncomeMonthlyTotalAmount").text = str(int(other))
            SubElement(detail, "IncomeType").text = "Other"

            source = data.get("otherIncomeSource") or data.get("other_income_source") or ""
            if source:
                SubElement(detail, "IncomeTypeOtherDescription").text = source

    def _add_assets(self, loan: Element, data: Dict):
        """Add asset information"""
        assets = SubElement(loan, "ASSETS")

        asset_fields = [
            ("checkingBalance", "checking_balance", "CheckingAccount"),
            ("savingsBalance", "savings_balance", "SavingsAccount"),
            ("investmentValue", "investment_value", "StockOptions"),
            ("retirementValue", "retirement_value", "RetirementFund"),
            ("otherAssets", "other_assets", "Other"),
            ("giftFunds", "gift_funds", "GiftOfEquity"),
        ]

        for camel, snake, asset_type in asset_fields:
            value = float(data.get(camel) or data.get(snake) or 0)
            if value > 0:
                asset = SubElement(assets, "ASSET")
                detail = SubElement(asset, "ASSET_DETAIL")
                SubElement(detail, "AssetCashOrMarketValueAmount").text = str(int(value))
                SubElement(detail, "AssetType").text = asset_type

    def _add_liabilities(self, loan: Element, data: Dict):
        """Add liability information"""
        liabilities = SubElement(loan, "LIABILITIES")

        liability_fields = [
            ("carPayment", "car_payment", "Installment", "AutoLoan"),
            ("studentLoans", "student_loans", "Installment", "StudentLoan"),
            ("creditCardPayments", "credit_card_payments", "Revolving", "CreditCard"),
            ("childSupport", "child_support", "Other", "ChildSupport"),
            ("otherDebts", "other_debts", "Other", "OtherDebt"),
        ]

        for camel, snake, liability_type, account_type in liability_fields:
            value = float(data.get(camel) or data.get(snake) or 0)
            if value > 0:
                liability = SubElement(liabilities, "LIABILITY")
                detail = SubElement(liability, "LIABILITY_DETAIL")
                SubElement(detail, "LiabilityMonthlyPaymentAmount").text = str(int(value))
                SubElement(detail, "LiabilityType").text = liability_type
                SubElement(detail, "LiabilityAccountType").text = account_type

    def _add_services(self, deal: Element, data: Dict):
        """Add services section (loan product info)"""
        services = SubElement(deal, "SERVICES")
        service = SubElement(services, "SERVICE")
        loan_srv = SubElement(service, "LOAN")
        product = SubElement(loan_srv, "LOAN_PRODUCT")
        product_detail = SubElement(product, "LOAN_PRODUCT_DETAIL")

        # Default to conventional 30-year fixed
        SubElement(product_detail, "LoanProductType").text = "Conventional"
        SubElement(product_detail, "LoanTermMonthsCount").text = "360"  # 30 years

    def generate_filename(self, application_id: str) -> str:
        """Generate a standardized filename for the MISMO XML"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"MISMO34_{application_id}_{timestamp}.xml"


# Singleton instance
mismo_generator = MISMOGenerator()


def generate_mismo_xml(application_data: Dict[str, Any]) -> str:
    """
    Convenience function to generate MISMO XML

    Args:
        application_data: Dictionary containing application fields

    Returns:
        MISMO 3.4 compliant XML string
    """
    generator = MISMOGenerator()
    return generator.generate(application_data)
