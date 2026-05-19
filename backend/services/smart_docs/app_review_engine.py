"""
Application Review Engine - ACO Core Intelligence

The brain of the Application Completion Orchestrator. When a loan application
is submitted, this engine:

1. Reads the submitted application (loan + borrower data from the DB)
2. Compares against required 1003 fields, loan program rules, borrower
   scenario rules, and plausibility checks
3. Classifies all missing/weak areas into four buckets:
       FIELD        - a specific data field is blank or incomplete
       CLARIFICATION - data exists but is ambiguous or inconsistent
       DOCUMENT     - a supporting document is required but not on file
       EXCEPTION    - data looks implausible and needs human explanation
4. Returns a structured list of findings for the orchestration layer

Usage:
    from services.smart_docs.app_review_engine import ApplicationReviewEngine

    engine = ApplicationReviewEngine(db, org_id="42")
    result = await engine.review_application(loan_id="123")

Integration points:
    - database.models.lead_loan.Loan  (application data)
    - documents table                 (uploaded doc inventory)
    - compliance_alerts table         (existing condition flags)
"""

import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# FINDING TYPE ENUMS (string constants — avoids import overhead)
# =============================================================================

class FindingType:
    FIELD = "FIELD"
    CLARIFICATION = "CLARIFICATION"
    DOCUMENT = "DOCUMENT"
    EXCEPTION = "EXCEPTION"


class Severity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FieldRequirement:
    ALWAYS = "always"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"


# =============================================================================
# FIELD REQUIREMENTS REGISTRY
#
# Each entry maps a logical field to its column(s) on the loans table, a
# human-readable display name, and a borrower-friendly SMS-style question.
# Sections mirror the Uniform Residential Loan Application (URLA / 1003).
# =============================================================================

FIELD_REGISTRY: List[Dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # SECTION 1 — Borrower Identity  (8 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "borrower_name",
        "display_name": "Borrower Full Name",
        "borrower_question": "What is your full legal name as it appears on your ID?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 10,
    },
    {
        "field_path": "borrower_email",
        "display_name": "Borrower Email Address",
        "borrower_question": "What email address should we use for loan correspondence?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 8,
    },
    {
        "field_path": "borrower_phone",
        "display_name": "Borrower Phone Number",
        "borrower_question": "What is the best phone number to reach you?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 8,
    },
    {
        "field_path": "_ssn_indicator",
        "display_name": "Social Security Number",
        "borrower_question": "We will need your Social Security Number for the credit check. Is that something you can provide now?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 10,
        "virtual": True,
        "note": "SSN is collected via POS or encrypted field — flagged when credit has not been pulled",
    },
    {
        "field_path": "_dob_indicator",
        "display_name": "Date of Birth",
        "borrower_question": "What is your date of birth?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 8,
        "virtual": True,
        "note": "DOB collected via POS — flagged when borrower profile incomplete",
    },
    {
        "field_path": "_marital_status",
        "display_name": "Marital Status",
        "borrower_question": "What is your current marital status? (Married, Unmarried, or Separated)",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_citizenship_status",
        "display_name": "Citizenship Status",
        "borrower_question": "Are you a US Citizen, Permanent Resident, or Non-Permanent Resident?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_dependents",
        "display_name": "Number of Dependents",
        "borrower_question": "How many dependents do you have, and what are their ages?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "borrower_identity",
        "weight": 3,
        "virtual": True,
    },

    # -------------------------------------------------------------------------
    # SECTION 2 — Housing History  (8 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "property_address",
        "display_name": "Current Residence Address",
        "borrower_question": "What is your current home address?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "housing_history",
        "weight": 9,
        "note": "Used as subject property on purchase; current address on refi",
    },
    {
        "field_path": "_years_at_current_address",
        "display_name": "Years at Current Address",
        "borrower_question": "How long have you lived at your current address?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "housing_history",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_prior_address",
        "display_name": "Prior Residence Address (if < 2 years at current)",
        "borrower_question": "Since you have lived at your current address for less than 2 years, what was your previous address?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower has lived at current address less than 2 years",
        "section": "housing_history",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_housing_type",
        "display_name": "Current Housing Type (Own/Rent/Other)",
        "borrower_question": "Do you currently own, rent, or live rent-free?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "housing_history",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "present_housing_expense",
        "display_name": "Current Monthly Housing Payment",
        "borrower_question": "What is your current monthly rent or mortgage payment?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "housing_history",
        "weight": 8,
    },
    {
        "field_path": "_landlord_name",
        "display_name": "Landlord Name and Contact",
        "borrower_question": "Can you provide your landlord's name and phone number for verification?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower rents current residence",
        "section": "housing_history",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "property_county",
        "display_name": "Property County",
        "borrower_question": "What county is the property located in?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required for USDA eligibility determination",
        "section": "housing_history",
        "weight": 5,
    },
    {
        "field_path": "property_units",
        "display_name": "Number of Units",
        "borrower_question": "How many units does the property have? (1 for single family, 2-4 for multi-family)",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if property_type is multi_family",
        "section": "housing_history",
        "weight": 6,
    },

    # -------------------------------------------------------------------------
    # SECTION 3 — Employment / Income  (15 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "_employer_name",
        "display_name": "Current Employer Name",
        "borrower_question": "What is the name of your current employer?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 9,
        "virtual": True,
        "note": "Lead model has employer_name; may need to propagate to loan",
    },
    {
        "field_path": "_employer_address",
        "display_name": "Employer Address",
        "borrower_question": "What is your employer's street address?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_employer_phone",
        "display_name": "Employer Phone Number",
        "borrower_question": "What is your employer's phone number for verification?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_position_title",
        "display_name": "Job Title / Position",
        "borrower_question": "What is your job title or position?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_employment_start_date",
        "display_name": "Employment Start Date",
        "borrower_question": "When did you start at your current employer? (month/year)",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_years_at_job",
        "display_name": "Years at Current Employer",
        "borrower_question": "How many years have you been with your current employer?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_income_type",
        "display_name": "Income Type (W2 / Self-Employed / 1099 / Retirement)",
        "borrower_question": "How do you earn your income — are you a W2 employee, self-employed, 1099 contractor, or retired?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 9,
        "virtual": True,
    },
    {
        "field_path": "_base_monthly_income",
        "display_name": "Base Monthly Income",
        "borrower_question": "What is your gross (before taxes) base monthly income?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 10,
        "virtual": True,
    },
    {
        "field_path": "_overtime_income",
        "display_name": "Overtime Income",
        "borrower_question": "Do you receive overtime pay? If so, what is your average monthly overtime?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "employment",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_bonus_income",
        "display_name": "Bonus Income",
        "borrower_question": "Do you receive bonuses? If so, what was your bonus for the last two years?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "employment",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_commission_income",
        "display_name": "Commission Income",
        "borrower_question": "Do you earn commissions? If so, what is your average monthly commission?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "employment",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_self_employed_flag",
        "display_name": "Self-Employment Indicator",
        "borrower_question": "Are you self-employed or do you own 25% or more of a business?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "employment",
        "weight": 8,
        "virtual": True,
    },
    {
        "field_path": "_business_name",
        "display_name": "Business Name (if self-employed)",
        "borrower_question": "What is the name of your business?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if self-employed",
        "section": "employment",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_business_type",
        "display_name": "Business Type / Structure (if self-employed)",
        "borrower_question": "What type of business do you operate? (Sole proprietorship, LLC, S-Corp, C-Corp, Partnership)",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if self-employed",
        "section": "employment",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_years_in_business",
        "display_name": "Years in Business (if self-employed)",
        "borrower_question": "How many years has your business been in operation?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if self-employed",
        "section": "employment",
        "weight": 7,
        "virtual": True,
    },

    # -------------------------------------------------------------------------
    # SECTION 4 — Assets  (10 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "_checking_account",
        "display_name": "Checking Account Balance",
        "borrower_question": "What is the approximate current balance of your checking account(s)?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "assets",
        "weight": 8,
        "virtual": True,
    },
    {
        "field_path": "_savings_account",
        "display_name": "Savings Account Balance",
        "borrower_question": "What is the approximate current balance of your savings account(s)?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "assets",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_retirement_account",
        "display_name": "Retirement / 401k Balance",
        "borrower_question": "Do you have any retirement accounts (401k, IRA)? If so, what is the approximate balance?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "assets",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_investment_account",
        "display_name": "Investment / Brokerage Account Balance",
        "borrower_question": "Do you have any investment or brokerage accounts? What is the approximate balance?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "assets",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_gift_funds",
        "display_name": "Gift Funds",
        "borrower_question": "Will any part of your down payment or closing costs come from a gift? If so, how much and from whom?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if down payment includes gift funds",
        "section": "assets",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_down_payment_source",
        "display_name": "Down Payment Source",
        "borrower_question": "Where will your down payment come from? (Savings, checking, gift, sale of property, etc.)",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if loan_purpose is purchase",
        "section": "assets",
        "weight": 8,
        "virtual": True,
    },
    {
        "field_path": "down_payment",
        "display_name": "Down Payment Amount",
        "borrower_question": "How much are you planning to put as a down payment?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if loan_purpose is purchase",
        "section": "assets",
        "weight": 9,
    },
    {
        "field_path": "_earnest_money",
        "display_name": "Earnest Money Deposit Amount",
        "borrower_question": "Did you provide an earnest money deposit? If so, how much?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if loan_purpose is purchase and contract received",
        "section": "assets",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_other_assets",
        "display_name": "Other Assets / Real Estate Owned",
        "borrower_question": "Do you own any other properties or have other assets worth more than $1,000? Please describe.",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "assets",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_total_liquid_reserves",
        "display_name": "Total Liquid Reserves",
        "borrower_question": "After your down payment and closing costs, approximately how many months of mortgage payments would you have left in savings?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required for investment or second-home occupancy; jumbo loans",
        "section": "assets",
        "weight": 7,
        "virtual": True,
    },

    # -------------------------------------------------------------------------
    # SECTION 5 — Liabilities  (8 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "_monthly_debt_total",
        "display_name": "Total Monthly Debt Payments",
        "borrower_question": "What is your total monthly minimum payment across all debts? (auto loans, student loans, credit cards, etc.)",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "liabilities",
        "weight": 9,
        "virtual": True,
        "note": "May be populated from credit report pull",
    },
    {
        "field_path": "_auto_loan_payments",
        "display_name": "Auto Loan Monthly Payment",
        "borrower_question": "Do you have any auto loan or lease payments? What is the monthly amount?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "liabilities",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_student_loan_payments",
        "display_name": "Student Loan Monthly Payment",
        "borrower_question": "Do you have student loans? What is your monthly payment? (If in deferment, we may still count 0.5-1% of balance.)",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "liabilities",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_credit_card_payments",
        "display_name": "Credit Card Minimum Payments",
        "borrower_question": "What is the total minimum monthly payment across all your credit cards?",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "liabilities",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_child_support_obligation",
        "display_name": "Child Support Payments",
        "borrower_question": "Are you required to pay child support or alimony? If so, what is the monthly amount?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "liabilities",
        "weight": 7,
        "virtual": True,
        "note": "1003 declaration question — must be asked even if answer is zero",
    },
    {
        "field_path": "_alimony_obligation",
        "display_name": "Alimony / Maintenance Payments",
        "borrower_question": "Are you obligated to pay alimony or separate maintenance? What is the monthly amount?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "liabilities",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_other_debts",
        "display_name": "Other Recurring Debts",
        "borrower_question": "Do you have any other monthly obligations we should know about? (personal loans, 401k loans, etc.)",
        "required": FieldRequirement.OPTIONAL,
        "conditions": None,
        "section": "liabilities",
        "weight": 4,
        "virtual": True,
    },
    {
        "field_path": "_reo_mortgage_payments",
        "display_name": "Existing Mortgage Payments on Other Properties",
        "borrower_question": "Do you have mortgages on any other properties? What are the monthly payments?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns other real estate",
        "section": "liabilities",
        "weight": 7,
        "virtual": True,
    },

    # -------------------------------------------------------------------------
    # SECTION 6 — Real Estate Owned  (6 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "_reo_property_address",
        "display_name": "REO Property Address",
        "borrower_question": "What is the address of the other property you own?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns additional real estate",
        "section": "reo",
        "weight": 7,
        "virtual": True,
    },
    {
        "field_path": "_reo_property_type",
        "display_name": "REO Property Type",
        "borrower_question": "Is this other property a single family home, condo, multi-family, or other type?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns additional real estate",
        "section": "reo",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_reo_market_value",
        "display_name": "REO Estimated Market Value",
        "borrower_question": "What is the estimated current market value of your other property?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns additional real estate",
        "section": "reo",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_reo_mortgage_balance",
        "display_name": "REO Mortgage Balance",
        "borrower_question": "What is the current mortgage balance on your other property?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns additional real estate",
        "section": "reo",
        "weight": 6,
        "virtual": True,
    },
    {
        "field_path": "_reo_rental_income",
        "display_name": "REO Gross Monthly Rental Income",
        "borrower_question": "Is this property rented out? If so, what is the monthly rent you collect?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if REO property is rented",
        "section": "reo",
        "weight": 5,
        "virtual": True,
    },
    {
        "field_path": "_reo_intended_disposition",
        "display_name": "REO Intended Disposition",
        "borrower_question": "Do you plan to keep, sell, or rent out your other property after closing on this loan?",
        "required": FieldRequirement.CONDITIONAL,
        "conditions": "Required if borrower owns additional real estate",
        "section": "reo",
        "weight": 5,
        "virtual": True,
    },

    # -------------------------------------------------------------------------
    # SECTION 7 — Loan / Property Details  (5 fields)
    # -------------------------------------------------------------------------
    {
        "field_path": "property_address",
        "display_name": "Subject Property Address",
        "borrower_question": "What is the full address of the property you are purchasing or refinancing?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "loan_details",
        "weight": 10,
    },
    {
        "field_path": "purchase_price",
        "display_name": "Purchase Price / Estimated Value",
        "borrower_question": "What is the purchase price of the home? (For a refinance, what is the estimated current value?)",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "loan_details",
        "weight": 10,
    },
    {
        "field_path": "loan_purpose",
        "display_name": "Loan Purpose",
        "borrower_question": "Is this a purchase, rate-and-term refinance, or cash-out refinance?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "loan_details",
        "weight": 10,
    },
    {
        "field_path": "occupancy_type",
        "display_name": "Occupancy Type",
        "borrower_question": "Will this property be your primary residence, a second/vacation home, or an investment property?",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "loan_details",
        "weight": 9,
    },
    {
        "field_path": "property_type",
        "display_name": "Property Type",
        "borrower_question": "What type of property is this? (Single family, condo, townhouse, multi-family, manufactured home)",
        "required": FieldRequirement.ALWAYS,
        "conditions": None,
        "section": "loan_details",
        "weight": 9,
    },
]

# Build a set of all sections for completeness scoring
ALL_SECTIONS = sorted({f["section"] for f in FIELD_REGISTRY})


# =============================================================================
# DOCUMENT REQUIREMENTS MATRIX
#
# Maps (loan_type, income_type, property_type, loan_purpose, scenario flags)
# to a list of required document types. Each entry includes a borrower-friendly
# explanation of why the document is needed.
# =============================================================================

# Base documents required for all loan applications
BASE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "paystub",
        "display_name": "Most Recent Paystub (30 days)",
        "borrower_question": "Can you upload your most recent paystub? It needs to be within the last 30 days.",
        "conditions": "W2 employment",
        "section": "income",
    },
    {
        "doc_type": "w2",
        "display_name": "W-2 Forms (Last 2 Years)",
        "borrower_question": "Please upload your W-2 forms for the last two years.",
        "conditions": "W2 employment",
        "section": "income",
    },
    {
        "doc_type": "bank_statements",
        "display_name": "Bank Statements (Last 2 Months, All Pages)",
        "borrower_question": "Please upload your last two months of bank statements — all pages, even blank ones.",
        "conditions": "always",
        "section": "assets",
    },
    {
        "doc_type": "drivers_license",
        "display_name": "Government-Issued Photo ID",
        "borrower_question": "Please upload a clear photo of the front and back of your driver's license or passport.",
        "conditions": "always",
        "section": "identity",
    },
    {
        "doc_type": "credit_report",
        "display_name": "Credit Report Authorization",
        "borrower_question": "We need your authorization to pull your credit report. Have you signed the credit authorization?",
        "conditions": "always",
        "section": "credit",
    },
]

# Purchase-specific documents
PURCHASE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "purchase_contract",
        "display_name": "Fully Executed Purchase Contract",
        "borrower_question": "Please upload the signed purchase agreement for the property.",
        "conditions": "loan_purpose == purchase",
        "section": "property",
    },
    {
        "doc_type": "earnest_money_receipt",
        "display_name": "Earnest Money Deposit Receipt",
        "borrower_question": "Can you upload the receipt or cancelled check showing your earnest money deposit?",
        "conditions": "loan_purpose == purchase",
        "section": "assets",
    },
]

# Self-employment documents
SELF_EMPLOYED_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "tax_returns",
        "display_name": "Personal Tax Returns (Last 2 Years, All Schedules)",
        "borrower_question": "Please upload your personal federal tax returns for the last two years, including all schedules and attachments.",
        "conditions": "self-employed",
        "section": "income",
    },
    {
        "doc_type": "business_tax_returns",
        "display_name": "Business Tax Returns (Last 2 Years)",
        "borrower_question": "Please upload your business tax returns for the last two years (1120, 1120S, or 1065 as applicable).",
        "conditions": "self-employed",
        "section": "income",
    },
    {
        "doc_type": "profit_loss",
        "display_name": "Year-to-Date Profit & Loss Statement",
        "borrower_question": "Please provide a year-to-date profit and loss statement for your business, signed and dated.",
        "conditions": "self-employed",
        "section": "income",
    },
    {
        "doc_type": "business_license",
        "display_name": "Business License or Registration",
        "borrower_question": "Can you upload a copy of your business license, articles of incorporation, or state registration?",
        "conditions": "self-employed",
        "section": "income",
    },
]

# VA loan documents
VA_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "dd214",
        "display_name": "DD-214 (Certificate of Release / Discharge)",
        "borrower_question": "Please upload your DD-214 showing your military service history.",
        "conditions": "loan_type == va",
        "section": "va_eligibility",
    },
    {
        "doc_type": "coe",
        "display_name": "Certificate of Eligibility (COE)",
        "borrower_question": "We need your VA Certificate of Eligibility. Would you like us to request it electronically or do you have a copy?",
        "conditions": "loan_type == va",
        "section": "va_eligibility",
    },
]

# FHA loan documents
FHA_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "fha_case_number",
        "display_name": "FHA Case Number Assignment",
        "borrower_question": "We are working on obtaining your FHA case number. No action needed from you at this time.",
        "conditions": "loan_type == fha",
        "section": "loan_program",
        "internal_only": True,
    },
]

# Investment property documents
INVESTMENT_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "rental_agreement",
        "display_name": "Rental/Lease Agreement for Subject Property",
        "borrower_question": "If the property is currently rented or will be rented, please upload the lease agreement.",
        "conditions": "occupancy_type == investment",
        "section": "property",
    },
    {
        "doc_type": "reo_schedule",
        "display_name": "Real Estate Owned Schedule",
        "borrower_question": "Please provide a list of all properties you own, including addresses, values, mortgage balances, and rental income.",
        "conditions": "occupancy_type == investment",
        "section": "property",
    },
]

# Gift fund documents
GIFT_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "gift_letter",
        "display_name": "Gift Letter",
        "borrower_question": "Since part of your funds are a gift, we need a signed gift letter from the donor stating the amount, that no repayment is required, and the donor's relationship to you.",
        "conditions": "gift_funds_used",
        "section": "assets",
    },
    {
        "doc_type": "gift_source_docs",
        "display_name": "Gift Fund Source Documentation",
        "borrower_question": "We also need documentation showing the gift funds — the donor's bank statement showing the withdrawal and your bank statement showing the deposit.",
        "conditions": "gift_funds_used",
        "section": "assets",
    },
]

# High-DTI / credit issue documents
CREDIT_ISSUE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "lox_high_dti",
        "display_name": "Letter of Explanation — High Debt-to-Income",
        "borrower_question": "Your debt-to-income ratio is higher than typical. Can you provide a brief letter explaining any circumstances that would help us better understand your financial situation?",
        "conditions": "DTI > 43%",
        "section": "credit",
    },
    {
        "doc_type": "credit_explanation",
        "display_name": "Credit Explanation Letter",
        "borrower_question": "There are some items on your credit report that need clarification. Can you provide a brief written explanation for any late payments, collections, or derogatory marks?",
        "conditions": "credit_score < 680 or derogatory marks",
        "section": "credit",
    },
]

# Refinance documents
REFINANCE_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "doc_type": "mortgage_statement",
        "display_name": "Most Recent Mortgage Statement",
        "borrower_question": "Please upload your most recent mortgage statement showing the current balance and payment.",
        "conditions": "loan_purpose in (refinance, cash_out_refinance)",
        "section": "property",
    },
    {
        "doc_type": "insurance_dec_page",
        "display_name": "Homeowner's Insurance Declaration Page",
        "borrower_question": "Please upload the declarations page of your current homeowner's insurance policy.",
        "conditions": "loan_purpose in (refinance, cash_out_refinance)",
        "section": "property",
    },
]


# =============================================================================
# CONSISTENCY RULES
#
# Each rule is a callable that receives the loan dict and returns a finding
# dict (or None if the rule passes).
# =============================================================================

def _safe_decimal(value: Any) -> Optional[Decimal]:
    """Safely convert a value to Decimal, returning None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _days_between(d1: Any, d2: Any) -> Optional[int]:
    """Calculate days between two date-like objects. Returns None if either is None."""
    if d1 is None or d2 is None:
        return None
    if isinstance(d1, datetime):
        d1 = d1.date()
    if isinstance(d2, datetime):
        d2 = d2.date()
    if isinstance(d1, date) and isinstance(d2, date):
        return (d2 - d1).days
    return None


# Each rule function takes (loan_data: dict, docs_on_file: set) and returns
# Optional[dict] — a finding dict or None.

def _rule_occupancy_vs_reo(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when borrower claims primary residence but already has another
    property that is also listed as primary.
    """
    occupancy = (loan.get("occupancy_type") or "").lower()
    # If the borrower owns other properties (user_metadata may contain REO info)
    # and claims investment but the subject property looks like a primary address
    # match, we flag for review. In practice this cross-references REO data.
    # For the DB-only check, flag if occupancy is missing.
    if not occupancy:
        return {
            "item_type": FindingType.FIELD,
            "severity": Severity.HIGH,
            "field_path": "occupancy_type",
            "field_section": "loan_details",
            "borrower_question": "Will this property be your primary residence, a second home, or an investment property?",
            "internal_note": "Occupancy type is blank — required for program eligibility and pricing",
            "source_engine": "consistency_rules",
            "ai_confidence": 1.0,
            "current_value": None,
        }
    return None


def _rule_income_vs_employment(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when self-employment is indicated but no business info exists, or
    when employment data is entirely missing while income is stated.
    """
    loan_meta = loan.get("user_metadata") or {}
    is_self_employed = (
        loan_meta.get("self_employed") is True
        or (loan_meta.get("income_type") or "").lower() in ("self_employed", "self-employed", "1099")
    )

    if is_self_employed:
        has_business_name = bool(loan_meta.get("business_name"))
        if not has_business_name:
            return {
                "item_type": FindingType.CLARIFICATION,
                "severity": Severity.HIGH,
                "field_path": "_business_name",
                "field_section": "employment",
                "borrower_question": "You indicated you are self-employed. What is the name of your business?",
                "internal_note": "Self-employment indicated but no business name on file. Need business details for underwriting.",
                "source_engine": "consistency_rules",
                "ai_confidence": 0.95,
                "current_value": None,
            }
    return None


def _rule_housing_expense_vs_rent_own(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag mismatch between declared housing type and housing expense amount.
    If borrower says they own, we expect a mortgage payment; if rent, a rent payment.
    Missing housing expense when declared is a problem.
    """
    housing_expense = _safe_float(loan.get("present_housing_expense"))
    loan_meta = loan.get("user_metadata") or {}
    housing_type = (loan_meta.get("housing_type") or "").lower()

    if housing_type == "own" and (housing_expense is None or housing_expense == 0):
        return {
            "item_type": FindingType.CLARIFICATION,
            "severity": Severity.MEDIUM,
            "field_path": "present_housing_expense",
            "field_section": "housing_history",
            "borrower_question": "You indicated you own your current home, but we don't have a monthly mortgage payment on file. What is your current monthly mortgage payment (including taxes and insurance)?",
            "internal_note": "Housing type = own but present_housing_expense is zero/blank. Possible free-and-clear or data entry error.",
            "source_engine": "consistency_rules",
            "ai_confidence": 0.85,
            "current_value": str(housing_expense),
        }
    return None


def _rule_closing_date_vs_application(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when closing date is unrealistically close to application date
    (less than 14 days) or when closing date is in the past.
    """
    closing = loan.get("closing_date")
    application = loan.get("application_date")
    now = datetime.now(timezone.utc)

    if closing is not None:
        if isinstance(closing, datetime) and closing < now:
            return {
                "item_type": FindingType.EXCEPTION,
                "severity": Severity.HIGH,
                "field_path": "closing_date",
                "field_section": "loan_details",
                "borrower_question": "The closing date on file appears to be in the past. Has the closing date been rescheduled?",
                "internal_note": f"Closing date {closing.strftime('%m/%d/%Y')} is in the past. Needs update.",
                "source_engine": "consistency_rules",
                "ai_confidence": 1.0,
                "current_value": closing.strftime("%Y-%m-%d") if closing else None,
            }

        if closing is not None and application is not None:
            gap = _days_between(application, closing)
            if gap is not None and gap < 14:
                return {
                    "item_type": FindingType.EXCEPTION,
                    "severity": Severity.MEDIUM,
                    "field_path": "closing_date",
                    "field_section": "loan_details",
                    "borrower_question": "Your expected closing date is very close to the application date. Is there a specific reason for the tight timeline?",
                    "internal_note": f"Only {gap} days between application and closing. Typical minimum is 21-30 days. Rush processing likely needed.",
                    "source_engine": "consistency_rules",
                    "ai_confidence": 0.90,
                    "current_value": closing.strftime("%Y-%m-%d") if isinstance(closing, datetime) else str(closing),
                }
    return None


def _rule_down_payment_vs_purchase_price(loan: dict, docs: set) -> Optional[dict]:
    """
    Check that down payment + loan amount roughly equals purchase price.
    Flag large discrepancies.
    """
    purchase = _safe_float(loan.get("purchase_price"))
    dp = _safe_float(loan.get("down_payment"))
    amount = _safe_float(loan.get("amount"))
    purpose = (loan.get("loan_purpose") or "").lower()

    if purpose != "purchase":
        return None

    if purchase and dp and amount:
        expected = dp + amount
        variance = abs(expected - purchase) / purchase if purchase > 0 else 0
        if variance > 0.05:  # More than 5% discrepancy
            return {
                "item_type": FindingType.CLARIFICATION,
                "severity": Severity.MEDIUM,
                "field_path": "down_payment",
                "field_section": "assets",
                "borrower_question": "The down payment and loan amount don't quite add up to the purchase price. Can you confirm your planned down payment amount?",
                "internal_note": (
                    f"Purchase price: ${purchase:,.2f}, down payment: ${dp:,.2f}, "
                    f"loan amount: ${amount:,.2f}. Sum = ${expected:,.2f} "
                    f"({variance*100:.1f}% variance). Possible seller credits, "
                    f"closing cost financing, or data entry error."
                ),
                "source_engine": "consistency_rules",
                "ai_confidence": 0.88,
                "current_value": f"DP={dp}, Amount={amount}, Price={purchase}",
            }

    if purpose == "purchase" and purchase and not dp:
        return {
            "item_type": FindingType.FIELD,
            "severity": Severity.HIGH,
            "field_path": "down_payment",
            "field_section": "assets",
            "borrower_question": "How much are you planning to put as a down payment on the purchase?",
            "internal_note": "Purchase price entered but down payment is missing. Required for LTV calculation.",
            "source_engine": "consistency_rules",
            "ai_confidence": 1.0,
            "current_value": None,
        }
    return None


def _rule_employment_gap(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when the borrower has less than 2 years at current employer and
    no prior employment history is recorded.
    """
    loan_meta = loan.get("user_metadata") or {}
    years_at_job = loan_meta.get("years_at_job")

    if years_at_job is not None:
        try:
            years = float(years_at_job)
        except (TypeError, ValueError):
            years = None

        if years is not None and years < 2:
            has_prior = bool(loan_meta.get("prior_employer_name"))
            if not has_prior:
                return {
                    "item_type": FindingType.FIELD,
                    "severity": Severity.HIGH,
                    "field_path": "_prior_employer",
                    "field_section": "employment",
                    "borrower_question": f"You have been at your current employer for about {years:.0f} year(s). The application requires a 2-year employment history. Where were you working before?",
                    "internal_note": f"Less than 2 years at current job ({years:.1f} years). Need prior employer to satisfy 2-year history requirement.",
                    "source_engine": "consistency_rules",
                    "ai_confidence": 0.95,
                    "current_value": f"{years:.1f} years",
                }
    return None


def _rule_reo_completeness(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when the borrower owns property (occupancy=investment or user_metadata
    indicates REO) but no REO schedule data is present.
    """
    occupancy = (loan.get("occupancy_type") or "").lower()
    loan_meta = loan.get("user_metadata") or {}

    owns_other_property = (
        loan_meta.get("owns_other_property") is True
        or loan_meta.get("reo_count", 0) > 0
    )

    if owns_other_property:
        has_reo_data = bool(loan_meta.get("reo_properties"))
        if not has_reo_data:
            return {
                "item_type": FindingType.FIELD,
                "severity": Severity.HIGH,
                "field_path": "_reo_property_address",
                "field_section": "reo",
                "borrower_question": "It looks like you own additional property. Can you provide the address, estimated value, mortgage balance, and monthly payment for each property you own?",
                "internal_note": "Borrower indicates other property ownership but REO section is incomplete. Need full REO schedule.",
                "source_engine": "consistency_rules",
                "ai_confidence": 0.90,
                "current_value": None,
            }

    # Also flag if occupancy is investment but no rental income data
    if occupancy == "investment":
        has_rental = loan_meta.get("rental_income") is not None
        if not has_rental and "rental_agreement" not in docs:
            return {
                "item_type": FindingType.DOCUMENT,
                "severity": Severity.MEDIUM,
                "field_path": "_reo_rental_income",
                "field_section": "reo",
                "borrower_question": "Since this is an investment property, do you have existing tenants? If so, please provide the current lease agreement and the monthly rental income.",
                "internal_note": "Investment property but no rental income data or lease on file. Need for rental income offset calculation.",
                "source_engine": "consistency_rules",
                "ai_confidence": 0.85,
                "current_value": None,
            }
    return None


def _rule_income_type_vs_docs(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when the income type suggests self-employment but only W2 documents
    are on file, or vice versa.
    """
    loan_meta = loan.get("user_metadata") or {}
    income_type = (loan_meta.get("income_type") or "").lower()

    if income_type in ("self_employed", "self-employed", "1099"):
        has_tax_returns = "tax_returns" in docs or "business_tax_returns" in docs
        has_pnl = "profit_loss" in docs
        if not has_tax_returns and not has_pnl:
            return {
                "item_type": FindingType.DOCUMENT,
                "severity": Severity.CRITICAL,
                "field_path": "_self_employment_docs",
                "field_section": "employment",
                "borrower_question": "Since you are self-employed, we will need your personal and business tax returns for the last 2 years, plus a year-to-date profit and loss statement. Can you start gathering those?",
                "internal_note": "Self-employed borrower but no tax returns or P&L on file. These are critical for income calculation.",
                "source_engine": "consistency_rules",
                "ai_confidence": 0.98,
                "current_value": f"income_type={income_type}, docs_on_file={sorted(docs)}",
            }
    return None


def _rule_coborrower_incomplete(loan: dict, docs: set) -> Optional[dict]:
    """
    Flag when a co-borrower name exists but co-borrower contact info is missing.
    """
    coborrower = (loan.get("coborrower_name") or "").strip()
    co_email = (loan.get("co_borrower_email") or "").strip()

    if coborrower and not co_email:
        return {
            "item_type": FindingType.FIELD,
            "severity": Severity.HIGH,
            "field_path": "co_borrower_email",
            "field_section": "borrower_identity",
            "borrower_question": f"We have {coborrower} listed as a co-borrower. What is their email address so we can include them in the application?",
            "internal_note": f"Co-borrower '{coborrower}' listed but email is missing. Need for disclosures and e-signing.",
            "source_engine": "consistency_rules",
            "ai_confidence": 1.0,
            "current_value": None,
        }
    return None


# Collect all consistency rule functions
CONSISTENCY_RULES = [
    _rule_occupancy_vs_reo,
    _rule_income_vs_employment,
    _rule_housing_expense_vs_rent_own,
    _rule_closing_date_vs_application,
    _rule_down_payment_vs_purchase_price,
    _rule_employment_gap,
    _rule_reo_completeness,
    _rule_income_type_vs_docs,
    _rule_coborrower_incomplete,
]


# =============================================================================
# PLAUSIBILITY CHECKS
#
# These detect data that exists but looks "off" — not necessarily wrong, but
# unusual enough that a human should review it.
# =============================================================================

def _plausibility_income_vs_credit(loan: dict) -> Optional[dict]:
    """High income with very low credit score is unusual."""
    loan_meta = loan.get("user_metadata") or {}
    annual_income = _safe_float(
        loan_meta.get("annual_income")
        or loan_meta.get("base_annual_income")
    )
    credit_score = loan.get("risk_score") or loan_meta.get("credit_score")
    if credit_score:
        try:
            credit_score = int(credit_score)
        except (TypeError, ValueError):
            credit_score = None

    if annual_income and credit_score:
        if annual_income > 500000 and credit_score < 620:
            return {
                "item_type": FindingType.EXCEPTION,
                "severity": Severity.HIGH,
                "field_path": "_income_credit_mismatch",
                "field_section": "employment",
                "borrower_question": "We noticed your stated income is quite high relative to your credit profile. Can you provide any additional context?",
                "internal_note": (
                    f"Annual income ${annual_income:,.0f} with credit score {credit_score}. "
                    f"High income / low credit combination is unusual — verify income docs carefully and check for identity issues."
                ),
                "source_engine": "plausibility_checks",
                "ai_confidence": 0.80,
                "current_value": f"income={annual_income}, credit={credit_score}",
            }
    return None


def _plausibility_housing_ratio(loan: dict) -> Optional[dict]:
    """Monthly housing cost exceeding 45% of gross monthly income."""
    loan_meta = loan.get("user_metadata") or {}
    proposed_housing = _safe_float(loan.get("proposed_housing_expense"))
    monthly_payment = _safe_float(loan.get("monthly_payment"))
    housing = proposed_housing or monthly_payment

    annual_income = _safe_float(
        loan_meta.get("annual_income")
        or loan_meta.get("base_annual_income")
    )
    if annual_income and annual_income > 0:
        monthly_income = annual_income / 12.0
    else:
        monthly_income = None

    if housing and monthly_income and monthly_income > 0:
        ratio = housing / monthly_income
        if ratio > 0.45:
            return {
                "item_type": FindingType.EXCEPTION,
                "severity": Severity.HIGH,
                "field_path": "_housing_ratio",
                "field_section": "liabilities",
                "borrower_question": "Your projected housing payment would be a large portion of your monthly income. Do you have other income sources or compensating factors we should know about?",
                "internal_note": (
                    f"Front-end DTI approximately {ratio*100:.1f}%. "
                    f"Housing=${housing:,.0f}/mo vs gross income=${monthly_income:,.0f}/mo. "
                    f"Exceeds 45% threshold. Check for compensating factors (reserves, residual income, no other debt)."
                ),
                "source_engine": "plausibility_checks",
                "ai_confidence": 0.92,
                "current_value": f"ratio={ratio:.2%}",
            }
    return None


def _plausibility_down_payment_vs_assets(loan: dict) -> Optional[dict]:
    """Down payment exceeds stated liquid assets."""
    loan_meta = loan.get("user_metadata") or {}
    dp = _safe_float(loan.get("down_payment"))
    total_assets = _safe_float(loan_meta.get("total_liquid_assets"))

    if dp and total_assets and dp > total_assets:
        return {
            "item_type": FindingType.EXCEPTION,
            "severity": Severity.HIGH,
            "field_path": "_down_payment_vs_assets",
            "field_section": "assets",
            "borrower_question": "The down payment amount is more than the liquid assets we have on file. Will you be receiving gift funds, selling another asset, or using a different source?",
            "internal_note": (
                f"Down payment ${dp:,.0f} exceeds stated liquid assets ${total_assets:,.0f}. "
                f"Verify asset source — may need gift letter, proceeds from sale, or updated asset statements."
            ),
            "source_engine": "plausibility_checks",
            "ai_confidence": 0.90,
            "current_value": f"dp={dp}, assets={total_assets}",
        }
    return None


def _plausibility_self_employed_tenure(loan: dict) -> Optional[dict]:
    """Self-employed less than 2 years is harder to qualify."""
    loan_meta = loan.get("user_metadata") or {}
    is_self_employed = (
        loan_meta.get("self_employed") is True
        or (loan_meta.get("income_type") or "").lower() in ("self_employed", "self-employed", "1099")
    )
    years_in_business = loan_meta.get("years_in_business")

    if is_self_employed and years_in_business is not None:
        try:
            years = float(years_in_business)
        except (TypeError, ValueError):
            return None

        if years < 2:
            return {
                "item_type": FindingType.EXCEPTION,
                "severity": Severity.HIGH,
                "field_path": "_years_in_business",
                "field_section": "employment",
                "borrower_question": f"Your business has been operating for about {years:.0f} year(s). Most loan programs require a 2-year self-employment history. Can you provide any prior employment or business history?",
                "internal_note": (
                    f"Self-employed {years:.1f} years. Most agency guidelines require 2-year history. "
                    f"May need CPA letter, prior tax returns, or alternate income documentation."
                ),
                "source_engine": "plausibility_checks",
                "ai_confidence": 0.93,
                "current_value": f"{years:.1f} years",
            }
    return None


def _plausibility_employment_future_start(loan: dict) -> Optional[dict]:
    """Employment start date in the future."""
    loan_meta = loan.get("user_metadata") or {}
    start_date_str = loan_meta.get("employment_start_date")
    if not start_date_str:
        return None

    try:
        if isinstance(start_date_str, str):
            # Try common date formats
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
                try:
                    start_date = datetime.strptime(start_date_str, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return None
        elif isinstance(start_date_str, (datetime, date)):
            start_date = start_date_str if isinstance(start_date_str, date) else start_date_str.date()
        else:
            return None
    except Exception as _exc:  # noqa: BLE001
        return None

    if start_date > date.today():
        return {
            "item_type": FindingType.EXCEPTION,
            "severity": Severity.MEDIUM,
            "field_path": "_employment_start_date",
            "field_section": "employment",
            "borrower_question": "It looks like your employment start date is in the future. Are you starting a new job? If so, we may need an offer letter.",
            "internal_note": (
                f"Employment start date {start_date.strftime('%m/%d/%Y')} is in the future. "
                f"If new job, need offer letter with salary, start date, and no contingencies. "
                f"First paystub may be required before closing."
            ),
            "source_engine": "plausibility_checks",
            "ai_confidence": 0.95,
            "current_value": str(start_date),
        }
    return None


def _plausibility_closing_in_past(loan: dict) -> Optional[dict]:
    """Closing date is in the past — handled by consistency rule, skip here."""
    # Covered by _rule_closing_date_vs_application
    return None


def _plausibility_coborrower_data_missing(loan: dict) -> Optional[dict]:
    """Co-borrower name exists but other data is completely missing."""
    coborrower = (loan.get("coborrower_name") or "").strip()
    if not coborrower:
        return None

    # Check if we have ANY co-borrower detail beyond the name
    co_email = (loan.get("co_borrower_email") or "").strip()
    loan_meta = loan.get("user_metadata") or {}
    co_income = loan_meta.get("coborrower_income")
    co_employer = loan_meta.get("coborrower_employer")

    missing_items = []
    if not co_email:
        missing_items.append("email")
    if not co_income:
        missing_items.append("income")
    if not co_employer:
        missing_items.append("employment")

    if len(missing_items) >= 2:
        return {
            "item_type": FindingType.FIELD,
            "severity": Severity.HIGH,
            "field_path": "_coborrower_profile",
            "field_section": "borrower_identity",
            "borrower_question": f"We need some additional information about {coborrower}. Can they provide their employment details, income, and email address?",
            "internal_note": (
                f"Co-borrower '{coborrower}' listed but missing: {', '.join(missing_items)}. "
                f"Need complete 1003 data for co-borrower."
            ),
            "source_engine": "plausibility_checks",
            "ai_confidence": 0.95,
            "current_value": f"missing: {', '.join(missing_items)}",
        }
    return None


# Collect all plausibility checks
PLAUSIBILITY_CHECKS = [
    _plausibility_income_vs_credit,
    _plausibility_housing_ratio,
    _plausibility_down_payment_vs_assets,
    _plausibility_self_employed_tenure,
    _plausibility_employment_future_start,
    _plausibility_closing_in_past,
    _plausibility_coborrower_data_missing,
]


# =============================================================================
# APPLICATION REVIEW ENGINE
# =============================================================================

class ApplicationReviewEngine:
    """
    Core engine for reviewing submitted loan applications.

    Loads application data from the loans table, compares against the field
    registry, runs consistency rules, evaluates document requirements, and
    performs plausibility checks. Returns a structured review result that the
    orchestration layer uses to generate borrower follow-up items.

    Usage:
        engine = ApplicationReviewEngine(db, org_id="42")
        result = await engine.review_application(loan_id="123")
    """

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def review_application(self, loan_id: str) -> dict:
        """
        Review a submitted loan application and return all findings.

        Returns:
            {
                "loan_id": str,
                "loan_number": str,
                "findings": [Finding, ...],
                "section_completeness": {section: {completed, total, score}},
                "total_findings": int,
                "critical_count": int,
                "high_count": int,
                "complexity_indicators": [str],
                "review_timestamp": str,
            }
        """
        # 1. Load loan data
        loan_data = self._load_loan_data(loan_id)
        if loan_data is None:
            logger.warning("Loan %s not found for org %s", loan_id, self.org_id)
            return {
                "loan_id": loan_id,
                "findings": [],
                "section_completeness": {},
                "total_findings": 0,
                "critical_count": 0,
                "high_count": 0,
                "complexity_indicators": [],
                "error": f"Loan {loan_id} not found",
                "review_timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # 2. Load documents on file
        docs_on_file = self._load_documents(loan_id)

        # 3. Run all engines
        findings: List[dict] = []

        # 3a. Field completeness checks
        field_findings = self._check_field_completeness(loan_data)
        findings.extend(field_findings)

        # 3b. Consistency rules
        consistency_findings = self._run_consistency_rules(loan_data, docs_on_file)
        findings.extend(consistency_findings)

        # 3c. Document requirements
        doc_findings = self._check_document_requirements(loan_data, docs_on_file)
        findings.extend(doc_findings)

        # 3d. Plausibility checks
        plausibility_findings = self._run_plausibility_checks(loan_data)
        findings.extend(plausibility_findings)

        # 4. De-duplicate findings (same field_path from multiple engines)
        findings = self._deduplicate_findings(findings)

        # 5. Calculate section completeness
        section_completeness = self._calculate_section_completeness(loan_data, findings)

        # 6. Identify complexity indicators
        complexity = self._identify_complexity(loan_data, findings, docs_on_file)

        # 7. Count severities
        critical_count = len([f for f in findings if f["severity"] == Severity.CRITICAL])
        high_count = len([f for f in findings if f["severity"] == Severity.HIGH])

        result = {
            "loan_id": loan_id,
            "loan_number": loan_data.get("loan_number"),
            "findings": findings,
            "section_completeness": section_completeness,
            "total_findings": len(findings),
            "critical_count": critical_count,
            "high_count": high_count,
            "complexity_indicators": complexity,
            "review_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Application review complete for loan %s: %d findings (%d critical, %d high)",
            loan_id, len(findings), critical_count, high_count,
        )

        return result

    # =========================================================================
    # DATA LOADING
    # =========================================================================

    def _load_loan_data(self, loan_id: str) -> Optional[dict]:
        """
        Load loan application data from the loans table. Returns a flat
        dictionary with all columns, or None if the loan is not found or
        does not belong to the current organization.
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT
                        l.id, l.loan_number, l.organization_id,
                        l.borrower_name, l.borrower_email, l.borrower_phone,
                        l.preferred_communication,
                        l.coborrower_name, l.co_borrower_email,
                        l.stage, l.program, l.loan_type,
                        l.amount, l.purchase_price, l.down_payment,
                        l.rate, l.term,
                        l.property_address, l.property_city, l.property_state, l.property_zip,
                        l.property_type, l.occupancy_type, l.property_county, l.property_units,
                        l.closing_date, l.application_date, l.lock_expiration_date,
                        l.loan_purpose,
                        l.present_housing_expense, l.proposed_housing_expense,
                        l.present_monthly_payment, l.proposed_monthly_payment,
                        l.monthly_payment,
                        l.ltv, l.cltv,
                        l.rate_type,
                        l.risk_score,
                        l.user_metadata,
                        l.loan_officer_id, l.loan_officer_name,
                        l.contract_received_date,
                        l.realtor_agent, l.title_company, l.lender,
                        l.second_loan_amount
                    FROM loans l
                    WHERE l.id = :loan_id
                        AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": self.org_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return dict(row)
        except Exception as e:
            logger.exception("Failed to load loan %s: %s", loan_id, e)
            return None

    def _load_documents(self, loan_id: str) -> set:
        """
        Load the set of document types currently on file for a loan.
        Returns a set of lowercase doc_type strings.
        """
        try:
            result = self.db.execute(
                text("""
                    SELECT DISTINCT LOWER(doc_type) as doc_type
                    FROM documents
                    WHERE loan_id = :loan_id AND status = 'active'
                """),
                {"loan_id": loan_id},
            )
            return {row.doc_type for row in result}
        except Exception as e:
            logger.exception("Failed to load documents for loan %s: %s", loan_id, e)
            return set()

    # =========================================================================
    # ENGINE 1 — FIELD COMPLETENESS
    # =========================================================================

    def _check_field_completeness(self, loan_data: dict) -> List[dict]:
        """
        Walk the FIELD_REGISTRY and flag any required field that is blank,
        null, or missing on the loan record.
        """
        findings = []
        loan_meta = loan_data.get("user_metadata") or {}

        for field_def in FIELD_REGISTRY:
            field_path = field_def["field_path"]
            required = field_def["required"]

            # Determine if this field should be checked
            if required == FieldRequirement.OPTIONAL:
                continue  # Skip optional fields in the completeness check

            # Get the current value
            is_virtual = field_def.get("virtual", False)

            if is_virtual:
                # Virtual fields are stored in user_metadata or derived
                # Strip leading underscore for the metadata key
                meta_key = field_path.lstrip("_")
                current_value = loan_meta.get(meta_key)
            else:
                current_value = loan_data.get(field_path)

            # Check conditional requirements
            if required == FieldRequirement.CONDITIONAL:
                if not self._evaluate_condition(field_def, loan_data, loan_meta):
                    continue  # Condition not met, skip this field

            # Check if value is meaningfully present
            is_present = self._is_field_present(current_value)

            if not is_present:
                severity = self._severity_for_field(field_def)
                findings.append({
                    "item_type": FindingType.FIELD,
                    "severity": severity,
                    "field_path": field_path,
                    "field_section": field_def["section"],
                    "borrower_question": field_def["borrower_question"],
                    "internal_note": f"Required field '{field_def['display_name']}' is blank or missing",
                    "source_engine": "field_completeness",
                    "ai_confidence": 1.0,
                    "current_value": None,
                })

        return findings

    def _evaluate_condition(self, field_def: dict, loan_data: dict, loan_meta: dict) -> bool:
        """
        Evaluate whether a conditional field's prerequisite is met.
        Returns True if the field IS required (condition met), False otherwise.
        """
        conditions = field_def.get("conditions") or ""
        field_path = field_def["field_path"]

        # Loan-purpose-based conditions
        purpose = (loan_data.get("loan_purpose") or "").lower()
        if "loan_purpose" in conditions.lower():
            if "purchase" in conditions.lower() and purpose == "purchase":
                return True
            if "refinance" in conditions.lower() and purpose in ("refinance", "cash_out_refinance"):
                return True
            return False

        # Housing-type conditions (renter)
        if "rents" in conditions.lower() or "rent" in conditions.lower():
            housing_type = (loan_meta.get("housing_type") or "").lower()
            return housing_type == "rent"

        # Address duration conditions
        if "less than 2 years" in conditions.lower():
            years = loan_meta.get("years_at_current_address")
            if years is not None:
                try:
                    return float(years) < 2
                except (TypeError, ValueError):
                    pass
            return False  # Can't determine, don't require

        # Self-employment conditions
        if "self-employed" in conditions.lower() or "self_employed" in conditions.lower():
            is_se = (
                loan_meta.get("self_employed") is True
                or (loan_meta.get("income_type") or "").lower() in ("self_employed", "self-employed", "1099")
            )
            return is_se

        # Multi-family conditions
        if "multi_family" in conditions.lower():
            ptype = (loan_data.get("property_type") or "").lower()
            return ptype == "multi_family"

        # Investment / second-home conditions
        if "investment" in conditions.lower() or "second" in conditions.lower():
            occ = (loan_data.get("occupancy_type") or "").lower()
            return occ in ("investment", "second_home")

        # USDA conditions
        if "usda" in conditions.lower():
            lt = (loan_data.get("loan_type") or "").lower()
            return lt == "usda"

        # Gift funds conditions
        if "gift" in conditions.lower():
            return loan_meta.get("gift_funds_used") is True

        # Contract received conditions
        if "contract received" in conditions.lower():
            return loan_data.get("contract_received_date") is not None

        # Owns other real estate conditions
        if "additional real estate" in conditions.lower() or "other real estate" in conditions.lower():
            return (
                loan_meta.get("owns_other_property") is True
                or loan_meta.get("reo_count", 0) > 0
            )

        # REO rented conditions
        if "reo" in conditions.lower() and "rented" in conditions.lower():
            return loan_meta.get("reo_has_rental") is True

        # Jumbo conditions
        if "jumbo" in conditions.lower():
            lt = (loan_data.get("loan_type") or "").lower()
            return lt == "jumbo"

        # Default: treat as required
        return True

    def _is_field_present(self, value: Any) -> bool:
        """Check if a field value is meaningfully populated."""
        if value is None:
            return False
        if isinstance(value, str) and value.strip() == "":
            return False
        if isinstance(value, (int, float, Decimal)) and value == 0:
            # Zero can be valid for some fields, but for required fields
            # we generally expect non-zero values
            return False
        return True

    def _severity_for_field(self, field_def: dict) -> str:
        """Determine severity based on field weight and requirement level."""
        weight = field_def.get("weight", 5)
        if weight >= 9:
            return Severity.CRITICAL
        elif weight >= 7:
            return Severity.HIGH
        elif weight >= 5:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    # =========================================================================
    # ENGINE 2 — CONSISTENCY RULES
    # =========================================================================

    def _run_consistency_rules(self, loan_data: dict, docs_on_file: set) -> List[dict]:
        """Run all registered consistency rules against the loan data."""
        findings = []
        for rule_fn in CONSISTENCY_RULES:
            try:
                finding = rule_fn(loan_data, docs_on_file)
                if finding is not None:
                    findings.append(finding)
            except Exception as e:
                logger.warning(
                    "Consistency rule %s raised exception for loan %s: %s",
                    rule_fn.__name__, loan_data.get("loan_number"), e,
                )
        return findings

    # =========================================================================
    # ENGINE 3 — DOCUMENT REQUIREMENTS
    # =========================================================================

    def _check_document_requirements(self, loan_data: dict, docs_on_file: set) -> List[dict]:
        """
        Determine which documents are required based on the loan profile,
        then flag any that are not yet on file.
        """
        required_docs = self._build_document_requirements(loan_data)
        findings = []

        for doc_req in required_docs:
            doc_type = doc_req["doc_type"].lower()
            if doc_type not in docs_on_file:
                # Determine severity based on how critical the document is
                section = doc_req.get("section", "other")
                severity = Severity.HIGH
                if section in ("income", "identity", "credit"):
                    severity = Severity.CRITICAL
                elif section in ("property", "assets"):
                    severity = Severity.HIGH
                elif section in ("va_eligibility", "loan_program"):
                    severity = Severity.HIGH
                else:
                    severity = Severity.MEDIUM

                # Skip internal-only items from borrower-facing output
                if doc_req.get("internal_only"):
                    severity = Severity.LOW

                findings.append({
                    "item_type": FindingType.DOCUMENT,
                    "severity": severity,
                    "field_path": f"doc:{doc_req['doc_type']}",
                    "field_section": section,
                    "borrower_question": doc_req["borrower_question"],
                    "internal_note": f"Required document '{doc_req['display_name']}' not on file. Condition: {doc_req.get('conditions', 'always')}",
                    "source_engine": "document_requirements",
                    "ai_confidence": 1.0,
                    "current_value": None,
                })

        return findings

    def _build_document_requirements(self, loan_data: dict) -> List[Dict[str, Any]]:
        """
        Build the full document requirements list based on the loan profile.
        """
        required: List[Dict[str, Any]] = []
        loan_meta = loan_data.get("user_metadata") or {}

        loan_type = (loan_data.get("loan_type") or "").lower()
        loan_purpose = (loan_data.get("loan_purpose") or "").lower()
        occupancy = (loan_data.get("occupancy_type") or "").lower()
        income_type = (loan_meta.get("income_type") or "").lower()

        is_self_employed = (
            loan_meta.get("self_employed") is True
            or income_type in ("self_employed", "self-employed", "1099")
        )
        is_purchase = loan_purpose == "purchase"
        is_refinance = loan_purpose in ("refinance", "cash_out_refinance")
        is_investment = occupancy == "investment"
        has_gift_funds = loan_meta.get("gift_funds_used") is True

        # Base documents (always required)
        for doc in BASE_DOCUMENTS:
            cond = doc.get("conditions", "always").lower()
            if cond == "always":
                required.append(doc)
            elif cond == "w2 employment" and not is_self_employed:
                required.append(doc)

        # Self-employment documents
        if is_self_employed:
            required.extend(SELF_EMPLOYED_DOCUMENTS)

        # Purchase documents
        if is_purchase:
            required.extend(PURCHASE_DOCUMENTS)

        # Refinance documents
        if is_refinance:
            required.extend(REFINANCE_DOCUMENTS)

        # VA documents
        if loan_type == "va":
            required.extend(VA_DOCUMENTS)

        # FHA documents
        if loan_type == "fha":
            required.extend(FHA_DOCUMENTS)

        # Investment property documents
        if is_investment:
            required.extend(INVESTMENT_DOCUMENTS)

        # Gift fund documents
        if has_gift_funds:
            required.extend(GIFT_DOCUMENTS)

        # Credit issue documents (check DTI and credit indicators)
        dti_back = _safe_float(loan_data.get("cltv"))  # cltv may store back-end DTI in some configs
        ltv = _safe_float(loan_data.get("ltv"))

        # Check if high DTI is indicated in metadata
        if loan_meta.get("high_dti") is True or (loan_meta.get("dti_back_end") and float(loan_meta["dti_back_end"]) > 43):
            required.append(CREDIT_ISSUE_DOCUMENTS[0])  # LOX high DTI

        credit_score = loan_meta.get("credit_score")
        if credit_score:
            try:
                cs = int(credit_score)
                if cs < 680:
                    required.append(CREDIT_ISSUE_DOCUMENTS[1])  # Credit explanation
            except (TypeError, ValueError):
                pass

        return required

    # =========================================================================
    # ENGINE 4 — PLAUSIBILITY CHECKS
    # =========================================================================

    def _run_plausibility_checks(self, loan_data: dict) -> List[dict]:
        """Run all registered plausibility checks against the loan data."""
        findings = []
        for check_fn in PLAUSIBILITY_CHECKS:
            try:
                finding = check_fn(loan_data)
                if finding is not None:
                    findings.append(finding)
            except Exception as e:
                logger.warning(
                    "Plausibility check %s raised exception for loan %s: %s",
                    check_fn.__name__, loan_data.get("loan_number"), e,
                )
        return findings

    # =========================================================================
    # SECTION COMPLETENESS SCORING
    # =========================================================================

    def _calculate_section_completeness(
        self,
        loan_data: dict,
        findings: List[dict],
    ) -> Dict[str, dict]:
        """
        Calculate how complete each 1003 section is based on field registry
        checks and current findings.
        """
        # Count total fields per section
        section_totals: Dict[str, int] = {}
        for field_def in FIELD_REGISTRY:
            section = field_def["section"]
            req = field_def["required"]
            if req == FieldRequirement.OPTIONAL:
                continue  # Don't count optional in total
            section_totals[section] = section_totals.get(section, 0) + 1

        # Count findings (missing fields) per section from the field_completeness engine
        section_missing: Dict[str, int] = {}
        for f in findings:
            if f["source_engine"] == "field_completeness":
                section = f["field_section"]
                section_missing[section] = section_missing.get(section, 0) + 1

        # Build completeness report
        completeness = {}
        for section in ALL_SECTIONS:
            total = section_totals.get(section, 0)
            missing = section_missing.get(section, 0)
            completed = max(0, total - missing)
            score = round((completed / total) * 100, 1) if total > 0 else 100.0

            completeness[section] = {
                "completed": completed,
                "total": total,
                "score": score,
            }

        return completeness

    # =========================================================================
    # COMPLEXITY INDICATORS
    # =========================================================================

    def _identify_complexity(
        self,
        loan_data: dict,
        findings: List[dict],
        docs_on_file: set,
    ) -> List[str]:
        """
        Identify factors that make this application more complex than average.
        Useful for routing, prioritization, and setting borrower expectations.
        """
        indicators = []
        loan_meta = loan_data.get("user_metadata") or {}
        loan_type = (loan_data.get("loan_type") or "").lower()
        occupancy = (loan_data.get("occupancy_type") or "").lower()
        income_type = (loan_meta.get("income_type") or "").lower()
        has_coborrower = bool((loan_data.get("coborrower_name") or "").strip())

        # Self-employment
        is_se = (
            loan_meta.get("self_employed") is True
            or income_type in ("self_employed", "self-employed", "1099")
        )
        if is_se:
            indicators.append("SELF_EMPLOYED: Self-employment income requires 2-year tax return analysis")

        # Co-borrower
        if has_coborrower:
            indicators.append("CO_BORROWER: Joint application doubles document and data requirements")

        # Investment property
        if occupancy == "investment":
            indicators.append("INVESTMENT_PROPERTY: Requires REO schedule, rental analysis, and higher reserves")

        # Non-QM or jumbo
        if loan_type in ("non_qm", "jumbo"):
            indicators.append(f"{loan_type.upper()}: Non-standard loan program with additional overlays")

        # VA
        if loan_type == "va":
            indicators.append("VA_LOAN: Requires COE, residual income check, and VA-specific appraisal")

        # FHA
        if loan_type == "fha":
            indicators.append("FHA_LOAN: FHA case number, MIP, and self-sufficiency test (3-4 units) may apply")

        # High finding count
        critical_count = len([f for f in findings if f["severity"] == Severity.CRITICAL])
        if critical_count >= 5:
            indicators.append(f"HIGH_MISSING_DATA: {critical_count} critical items outstanding — application is substantially incomplete")

        # Multiple income sources
        if loan_meta.get("multiple_income_sources"):
            indicators.append("MULTIPLE_INCOME: Multiple income sources require separate analysis for each")

        # Gift funds
        if loan_meta.get("gift_funds_used"):
            indicators.append("GIFT_FUNDS: Gift documentation and source/seasoning tracking required")

        # Second subordinate financing
        if loan_data.get("second_loan_amount"):
            second_amt = _safe_float(loan_data["second_loan_amount"])
            if second_amt and second_amt > 0:
                indicators.append("SUBORDINATE_FINANCING: Second lien/subordinate financing adds CLTV considerations")

        # Recently started employment (< 1 year)
        years_at_job = loan_meta.get("years_at_job")
        if years_at_job is not None:
            try:
                if float(years_at_job) < 1:
                    indicators.append("NEW_EMPLOYMENT: Less than 1 year at current employer — need employment history and possible offer letter")
            except (TypeError, ValueError):
                pass

        return indicators

    # =========================================================================
    # DE-DUPLICATION
    # =========================================================================

    def _deduplicate_findings(self, findings: List[dict]) -> List[dict]:
        """
        Remove duplicate findings for the same field_path, keeping the one
        with the highest severity. Different source_engines may flag the same
        issue; we keep the most severe and informative finding.
        """
        severity_rank = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }

        seen: Dict[str, dict] = {}
        for finding in findings:
            key = finding["field_path"]
            existing = seen.get(key)
            if existing is None:
                seen[key] = finding
            else:
                # Keep the higher severity finding
                existing_rank = severity_rank.get(existing["severity"], 0)
                new_rank = severity_rank.get(finding["severity"], 0)
                if new_rank > existing_rank:
                    seen[key] = finding
                elif new_rank == existing_rank:
                    # Same severity — prefer consistency/plausibility engines
                    # over generic field_completeness as they have richer notes
                    preferred_engines = ("consistency_rules", "plausibility_checks", "document_requirements")
                    if finding["source_engine"] in preferred_engines:
                        seen[key] = finding

        return list(seen.values())


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_application_review_engine(db: Session, org_id: str) -> ApplicationReviewEngine:
    """Factory function to create an ApplicationReviewEngine instance."""
    return ApplicationReviewEngine(db=db, org_id=org_id)
