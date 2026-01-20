"""
Mortgage Knowledge Base for AI Agents

Comprehensive domain knowledge including:
- 1003/URLA field definitions and mappings
- Loan program guidelines (Conventional, FHA, VA, USDA)
- Document requirements by scenario
- Risk indicators and red flags
- Underwriting guidelines and overlays
- Industry terminology

This knowledge base enables agents to operate at expert level.
"""

# =============================================================================
# 1003/URLA FIELD DEFINITIONS (Uniform Residential Loan Application)
# =============================================================================

URLA_FIELDS = {
    # Section 1: Borrower Information
    "borrower": {
        "first_name": {"path": "borrower.first_name", "section": "1a", "required": True},
        "middle_name": {"path": "borrower.middle_name", "section": "1a", "required": False},
        "last_name": {"path": "borrower.last_name", "section": "1a", "required": True},
        "suffix": {"path": "borrower.suffix", "section": "1a", "required": False},
        "ssn": {"path": "borrower.ssn", "section": "1a", "required": True, "sensitive": True},
        "dob": {"path": "borrower.date_of_birth", "section": "1a", "required": True},
        "citizenship": {"path": "borrower.citizenship_status", "section": "1a", "required": True,
                       "options": ["us_citizen", "permanent_resident", "non_permanent_resident"]},
        "marital_status": {"path": "borrower.marital_status", "section": "1a", "required": True,
                         "options": ["married", "separated", "unmarried"]},
        "dependents_count": {"path": "borrower.dependents_count", "section": "1a", "required": True},
        "dependents_ages": {"path": "borrower.dependents_ages", "section": "1a", "required": False},
        "phone_home": {"path": "borrower.phone_home", "section": "1a", "required": False},
        "phone_cell": {"path": "borrower.phone_cell", "section": "1a", "required": True},
        "phone_work": {"path": "borrower.phone_work", "section": "1a", "required": False},
        "email": {"path": "borrower.email", "section": "1a", "required": True},
    },

    # Section 1b: Current Address
    "current_address": {
        "street": {"path": "borrower.current_address.street", "section": "1b", "required": True},
        "unit": {"path": "borrower.current_address.unit", "section": "1b", "required": False},
        "city": {"path": "borrower.current_address.city", "section": "1b", "required": True},
        "state": {"path": "borrower.current_address.state", "section": "1b", "required": True},
        "zip": {"path": "borrower.current_address.zip", "section": "1b", "required": True},
        "country": {"path": "borrower.current_address.country", "section": "1b", "required": False},
        "years_at_address": {"path": "borrower.current_address.years", "section": "1b", "required": True},
        "months_at_address": {"path": "borrower.current_address.months", "section": "1b", "required": False},
        "housing_type": {"path": "borrower.current_address.housing_type", "section": "1b", "required": True,
                        "options": ["own", "rent", "no_primary_housing"]},
        "monthly_rent": {"path": "borrower.current_address.monthly_rent", "section": "1b", "required": False},
    },

    # Section 1c: Employment/Income
    "employment": {
        "employer_name": {"path": "borrower.employment.employer_name", "section": "1c", "required": True},
        "employer_phone": {"path": "borrower.employment.employer_phone", "section": "1c", "required": True},
        "employer_address": {"path": "borrower.employment.employer_address", "section": "1c", "required": True},
        "position_title": {"path": "borrower.employment.position", "section": "1c", "required": True},
        "start_date": {"path": "borrower.employment.start_date", "section": "1c", "required": True},
        "years_in_profession": {"path": "borrower.employment.years_in_profession", "section": "1c", "required": True},
        "self_employed": {"path": "borrower.employment.self_employed", "section": "1c", "required": True},
        "ownership_share": {"path": "borrower.employment.ownership_share", "section": "1c", "required": False},
    },

    # Section 1d: Income
    "income": {
        "base_monthly": {"path": "borrower.income.base", "section": "1d", "required": True},
        "overtime_monthly": {"path": "borrower.income.overtime", "section": "1d", "required": False},
        "bonus_monthly": {"path": "borrower.income.bonus", "section": "1d", "required": False},
        "commission_monthly": {"path": "borrower.income.commission", "section": "1d", "required": False},
        "military_entitlements": {"path": "borrower.income.military", "section": "1d", "required": False},
        "other_income": {"path": "borrower.income.other", "section": "1d", "required": False},
        "other_income_source": {"path": "borrower.income.other_source", "section": "1d", "required": False},
    },

    # Section 2: Property Information
    "property": {
        "street": {"path": "property.address.street", "section": "2", "required": True},
        "unit": {"path": "property.address.unit", "section": "2", "required": False},
        "city": {"path": "property.address.city", "section": "2", "required": True},
        "state": {"path": "property.address.state", "section": "2", "required": True},
        "zip": {"path": "property.address.zip", "section": "2", "required": True},
        "county": {"path": "property.address.county", "section": "2", "required": True},
        "num_units": {"path": "property.num_units", "section": "2", "required": True},
        "property_value": {"path": "property.value", "section": "2", "required": True},
        "occupancy_type": {"path": "property.occupancy", "section": "2", "required": True,
                         "options": ["primary_residence", "second_home", "investment"]},
        "property_type": {"path": "property.type", "section": "2", "required": True,
                        "options": ["single_family", "condo", "townhouse", "coop", "manufactured",
                                   "pud", "multi_family_2_4"]},
        "mixed_use": {"path": "property.mixed_use", "section": "2", "required": True},
        "manufactured_type": {"path": "property.manufactured_type", "section": "2", "required": False},
    },

    # Section 3: Loan Information
    "loan": {
        "loan_amount": {"path": "loan.amount", "section": "3", "required": True},
        "loan_purpose": {"path": "loan.purpose", "section": "3", "required": True,
                        "options": ["purchase", "refinance_rate_term", "refinance_cash_out", "construction",
                                   "construction_permanent", "other"]},
        "product_type": {"path": "loan.product_type", "section": "3", "required": True,
                        "options": ["conventional", "fha", "va", "usda", "other"]},
        "amortization_type": {"path": "loan.amortization", "section": "3", "required": True,
                             "options": ["fixed", "arm", "gpm"]},
        "loan_term_months": {"path": "loan.term_months", "section": "3", "required": True},
        "interest_rate": {"path": "loan.interest_rate", "section": "3", "required": False},
    },

    # Section 4: Assets
    "assets": {
        "checking_accounts": {"path": "assets.checking", "section": "4a", "required": False},
        "savings_accounts": {"path": "assets.savings", "section": "4a", "required": False},
        "retirement_accounts": {"path": "assets.retirement", "section": "4a", "required": False},
        "stocks_bonds": {"path": "assets.stocks_bonds", "section": "4a", "required": False},
        "gift_amount": {"path": "assets.gift_amount", "section": "4a", "required": False},
        "gift_donor": {"path": "assets.gift_donor", "section": "4a", "required": False},
        "gift_donor_relationship": {"path": "assets.gift_donor_relationship", "section": "4a", "required": False},
    },

    # Section 5: Liabilities
    "liabilities": {
        "alimony_owed": {"path": "liabilities.alimony", "section": "5", "required": False},
        "child_support_owed": {"path": "liabilities.child_support", "section": "5", "required": False},
        "other_liabilities": {"path": "liabilities.other", "section": "5", "required": False},
    },

    # Section 6: Declarations
    "declarations": {
        "outstanding_judgments": {"path": "declarations.judgments", "section": "6", "required": True},
        "bankruptcy": {"path": "declarations.bankruptcy", "section": "6", "required": True},
        "foreclosure": {"path": "declarations.foreclosure", "section": "6", "required": True},
        "lawsuit_party": {"path": "declarations.lawsuit", "section": "6", "required": True},
        "delinquent_federal_debt": {"path": "declarations.federal_debt", "section": "6", "required": True},
        "alimony_child_support": {"path": "declarations.alimony_cs", "section": "6", "required": True},
        "borrowed_down_payment": {"path": "declarations.borrowed_dp", "section": "6", "required": True},
        "co_maker_endorser": {"path": "declarations.co_maker", "section": "6", "required": True},
        "us_citizen": {"path": "declarations.us_citizen", "section": "6", "required": True},
        "permanent_resident": {"path": "declarations.permanent_resident", "section": "6", "required": True},
        "primary_residence_intent": {"path": "declarations.primary_intent", "section": "6", "required": True},
        "ownership_interest_3yrs": {"path": "declarations.prior_ownership", "section": "6", "required": True},
        "property_type_prior": {"path": "declarations.prior_property_type", "section": "6", "required": False},
        "title_held_prior": {"path": "declarations.prior_title", "section": "6", "required": False},
    },
}


# =============================================================================
# LOAN PROGRAM GUIDELINES
# =============================================================================

LOAN_PROGRAM_GUIDELINES = {
    "conventional": {
        "name": "Conventional (Fannie Mae/Freddie Mac)",
        "min_credit_score": {
            "standard": 620,
            "high_balance": 680,
            "investment": 640,
        },
        "max_dti": {
            "standard": 45,
            "with_compensating": 50,
        },
        "max_ltv": {
            "purchase_primary": 97,
            "purchase_second_home": 90,
            "purchase_investment": 85,
            "refi_rate_term": 97,
            "refi_cash_out": 80,
        },
        "reserves_months": {
            "primary_1_unit": 0,
            "primary_2_4_unit": 2,
            "second_home": 2,
            "investment": 6,
        },
        "income_requirements": {
            "w2_employment": "2 years history, current employed",
            "self_employment": "2 years tax returns, current YTD P&L",
            "bonus_commission": "2 year history, averaged",
            "overtime": "2 year history, averaged",
            "rental_income": "Schedule E or lease if <2 years",
        },
        "pmi_required": "LTV > 80%",
        "key_guidelines": [
            "Fannie Mae Selling Guide B3-3.1 (Income Assessment)",
            "Fannie Mae Selling Guide B3-4 (Asset Assessment)",
            "Freddie Mac Guide 5000 Series (Eligibility)",
        ],
    },

    "fha": {
        "name": "FHA (Federal Housing Administration)",
        "min_credit_score": {
            "standard_3.5_down": 580,
            "with_10_down": 500,
        },
        "max_dti": {
            "standard": 43,
            "with_compensating": 56.99,
        },
        "max_ltv": {
            "purchase": 96.5,
            "streamline_refi": 97.75,
            "cash_out_refi": 80,
        },
        "reserves_months": {
            "1_2_unit": 0,
            "3_4_unit": 3,
        },
        "mip_required": "All loans - upfront 1.75% + monthly",
        "waiting_periods": {
            "bankruptcy_ch7": "2 years from discharge",
            "bankruptcy_ch13": "1 year with court approval",
            "foreclosure": "3 years from transfer date",
            "short_sale": "3 years from sale date",
        },
        "key_guidelines": [
            "HUD Handbook 4000.1 Section II.A (Borrower Eligibility)",
            "HUD Handbook 4000.1 Section II.B (Property Requirements)",
            "FHA TOTAL Scorecard requirements",
        ],
    },

    "va": {
        "name": "VA (Veterans Affairs)",
        "min_credit_score": {
            "standard": 620,  # Lender overlay, no VA minimum
            "manual_underwrite": 580,
        },
        "max_dti": {
            "standard": 41,
            "with_residual": 50,
        },
        "max_ltv": {
            "purchase": 100,
            "irrrl": 100,
            "cash_out": 90,
        },
        "funding_fee": {
            "first_use_0_down": "2.15%",
            "first_use_5_down": "1.5%",
            "first_use_10_down": "1.25%",
            "subsequent_0_down": "3.3%",
            "exempt": "Disabled veterans, surviving spouses",
        },
        "residual_income_required": True,
        "eligibility_requirements": [
            "Certificate of Eligibility (COE)",
            "Active duty: 90 continuous days",
            "Veterans: Depends on service period",
            "National Guard/Reserve: 6 years or called to active duty",
            "Surviving spouse: Unremarried spouse of service member KIA",
        ],
        "key_guidelines": [
            "VA Pamphlet 26-7 Chapter 4 (Credit Underwriting)",
            "VA Circular 26-18-13 (Income)",
            "VA Regional Loan Center overlays",
        ],
    },

    "usda": {
        "name": "USDA (Rural Development)",
        "min_credit_score": {
            "guaranteed_automated": 640,
            "guaranteed_manual": 640,
            "direct": "No minimum",
        },
        "max_dti": {
            "standard": 41,
            "with_gus_approval": 44,
        },
        "max_ltv": {
            "purchase": 100,
        },
        "income_limits": "115% of area median income",
        "location_requirement": "Eligible rural areas only",
        "guarantee_fee": {
            "upfront": "1.0%",
            "annual": "0.35%",
        },
        "key_guidelines": [
            "7 CFR 3555 (Guaranteed Loan Program)",
            "USDA GUS requirements",
            "Area eligibility maps",
        ],
    },
}


# =============================================================================
# DOCUMENT REQUIREMENTS BY SCENARIO
# =============================================================================

DOCUMENT_REQUIREMENTS = {
    # By income type
    "income": {
        "w2_employed": {
            "required": [
                {"doc": "paystubs_30_days", "desc": "Most recent 30 days of pay stubs"},
                {"doc": "w2_2_years", "desc": "W-2 forms for most recent 2 years"},
            ],
            "conditional": [
                {"doc": "voe", "condition": "employment < 2 years", "desc": "Verbal/Written VOE"},
                {"doc": "offer_letter", "condition": "new job", "desc": "Offer letter with terms"},
            ],
        },
        "self_employed": {
            "required": [
                {"doc": "tax_returns_2_years", "desc": "Personal federal tax returns (2 years)"},
                {"doc": "business_tax_returns", "desc": "Business tax returns if > 25% ownership"},
                {"doc": "ytd_pl", "desc": "Year-to-date Profit & Loss statement"},
                {"doc": "business_license", "desc": "Business license or registration"},
            ],
            "conditional": [
                {"doc": "cpa_letter", "condition": "business < 2 years", "desc": "CPA letter"},
                {"doc": "bank_statements_12_months", "condition": "bank statement income",
                 "desc": "12 months business bank statements"},
            ],
        },
        "commission": {
            "required": [
                {"doc": "paystubs_30_days", "desc": "Most recent 30 days of pay stubs"},
                {"doc": "w2_2_years", "desc": "W-2 forms for most recent 2 years"},
                {"doc": "tax_returns_2_years", "desc": "Tax returns if commission > 25%"},
            ],
        },
        "retirement": {
            "required": [
                {"doc": "award_letter", "desc": "Social Security/Pension award letter"},
                {"doc": "bank_statements_2_months", "desc": "2 months bank statements showing deposits"},
            ],
            "conditional": [
                {"doc": "tax_returns", "condition": "1099-R income", "desc": "Tax returns"},
            ],
        },
        "rental_income": {
            "required": [
                {"doc": "schedule_e", "desc": "Schedule E from tax returns (2 years)"},
                {"doc": "lease_agreements", "desc": "Current executed lease agreements"},
            ],
            "conditional": [
                {"doc": "rent_survey", "condition": "new rental", "desc": "Appraisal rent survey"},
            ],
        },
    },

    # By loan purpose
    "loan_purpose": {
        "purchase": {
            "required": [
                {"doc": "purchase_contract", "desc": "Fully executed purchase contract"},
                {"doc": "earnest_money", "desc": "Proof of earnest money deposit"},
            ],
        },
        "refinance": {
            "required": [
                {"doc": "mortgage_statement", "desc": "Most recent mortgage statement"},
                {"doc": "homeowners_insurance", "desc": "Current insurance declaration"},
            ],
            "conditional": [
                {"doc": "payoff_statement", "condition": "always", "desc": "Lender payoff statement"},
            ],
        },
        "cash_out": {
            "required": [
                {"doc": "mortgage_statement", "desc": "Most recent mortgage statement"},
                {"doc": "purpose_letter", "desc": "Letter explaining use of funds"},
            ],
        },
    },

    # By asset type
    "assets": {
        "standard": {
            "required": [
                {"doc": "bank_statements_2_months", "desc": "2 months all account statements"},
            ],
        },
        "gift_funds": {
            "required": [
                {"doc": "gift_letter", "desc": "Signed gift letter"},
                {"doc": "donor_bank_statements", "desc": "Donor bank statements showing ability"},
                {"doc": "transfer_proof", "desc": "Wire/check showing transfer"},
            ],
        },
        "retirement_funds": {
            "required": [
                {"doc": "retirement_statement", "desc": "Retirement account statement"},
                {"doc": "vesting_schedule", "condition": "if vesting applies", "desc": "Vesting schedule"},
            ],
        },
        "large_deposits": {
            "required": [
                {"doc": "deposit_explanation", "desc": "Written explanation of source"},
                {"doc": "source_documentation", "desc": "Paper trail (sale receipt, insurance claim, etc.)"},
            ],
        },
    },

    # By borrower situation
    "special_situations": {
        "divorce": {
            "required": [
                {"doc": "divorce_decree", "desc": "Final divorce decree"},
                {"doc": "settlement_agreement", "desc": "Property settlement agreement"},
            ],
            "conditional": [
                {"doc": "alimony_order", "condition": "receiving alimony", "desc": "Alimony/support order"},
            ],
        },
        "bankruptcy": {
            "required": [
                {"doc": "bk_discharge", "desc": "Bankruptcy discharge papers"},
                {"doc": "bk_schedules", "desc": "Bankruptcy schedules"},
            ],
        },
        "foreclosure_short_sale": {
            "required": [
                {"doc": "settlement_statement", "desc": "HUD-1/Closing Disclosure from sale"},
                {"doc": "explanation_letter", "desc": "Letter explaining circumstances"},
            ],
        },
        "non_permanent_resident": {
            "required": [
                {"doc": "work_visa", "desc": "Valid work authorization (H1B, L1, etc.)"},
                {"doc": "passport", "desc": "Passport copy"},
                {"doc": "i94", "desc": "I-94 arrival record"},
            ],
        },
    },
}


# =============================================================================
# RISK INDICATORS AND RED FLAGS
# =============================================================================

RISK_INDICATORS = {
    "fraud_red_flags": {
        "occupancy": [
            "Lives far from subject property with no relocation explanation",
            "Already owns home near subject property (investment disguised as primary)",
            "Property being purchased from family member",
            "Very short time between purchase and listing for sale",
            "Rental income claimed but borrower occupying property",
        ],
        "income": [
            "Income increase doesn't match promotion/job change",
            "Round numbers on paystubs",
            "Employer phone number is cell phone or disconnected",
            "Can't verify employer exists",
            "YTD income doesn't match recent paystubs",
            "Tax returns show significantly different income than application",
        ],
        "assets": [
            "Large deposits with no source explanation",
            "Bank statements appear altered",
            "Gifted funds from non-family without explanation",
            "Asset account opened recently with large balance",
            "Borrower working with unknown third party on funds",
        ],
        "identity": [
            "SSN doesn't match credit report",
            "Address history doesn't match stated history",
            "Multiple SSNs associated with borrower",
            "Credit file is thin or new relative to borrower age",
        ],
        "transaction": [
            "Seller is also the listing agent",
            "Non-arm's length transaction without disclosure",
            "Sales price significantly above or below market",
            "Power of attorney usage without clear need",
            "Property flipping (multiple sales in short period)",
        ],
    },

    "credit_concerns": {
        "recent_negative": [
            "Late payments in last 12 months",
            "New collections or charge-offs",
            "Recent credit inquiries indicating new debt",
            "Credit utilization above 30%",
            "Authorized user accounts inflating score",
        ],
        "patterns": [
            "Maxed out credit cards",
            "History of only paying minimums",
            "Cycling debt between cards",
            "Recent rapid debt paydown (possible gifted funds)",
        ],
        "major_events": [
            "Bankruptcy not yet discharged",
            "Active foreclosure",
            "Tax liens (federal or state)",
            "Civil judgments",
            "Deed in lieu or short sale",
        ],
    },

    "income_concerns": {
        "stability": [
            "Job gaps in last 2 years",
            "Frequent job changes (same industry OK)",
            "Income trending downward",
            "Seasonal employment",
            "Commission income declining",
        ],
        "documentation": [
            "Self-employed less than 2 years",
            "Business losses on tax returns",
            "Unreimbursed business expenses reducing income",
            "K-1 income from business borrower doesn't control",
            "Rental property showing losses",
        ],
        "calculation": [
            "Overtime/bonus not likely to continue",
            "Part-time income used as full-time",
            "Non-taxable income grossed up incorrectly",
            "Child support/alimony expiring soon",
        ],
    },

    "property_concerns": {
        "eligibility": [
            "Non-warrantable condo",
            "Manufactured home on leased land",
            "Mixed-use property with >25% commercial",
            "Condo hotel or timeshare",
            "Property in litigation",
        ],
        "condition": [
            "Major deferred maintenance",
            "Health and safety issues",
            "Non-permitted additions",
            "Foundation/structural problems",
            "Environmental hazards (mold, asbestos, lead)",
        ],
        "value": [
            "Appraisal value significantly above contract",
            "Excessive seller concessions",
            "Comparable sales are distressed",
            "Market declining in area",
        ],
    },
}


# =============================================================================
# STANDARD CONDITIONS BY CATEGORY
# =============================================================================

STANDARD_CONDITIONS = {
    "prior_to_approval": {
        "income": [
            {"code": "INCOME-1", "text": "Provide written Verification of Employment (VOE) for all borrowers"},
            {"code": "INCOME-2", "text": "Provide most recent 30 days consecutive pay stubs for all borrowers"},
            {"code": "INCOME-3", "text": "Provide 2 years W-2s for all borrowers"},
            {"code": "INCOME-4", "text": "Provide complete signed federal tax returns for most recent 2 years"},
            {"code": "INCOME-5", "text": "Provide year-to-date Profit & Loss statement prepared by CPA or borrower"},
            {"code": "INCOME-6", "text": "Provide 4506-C signed for IRS tax transcript verification"},
        ],
        "assets": [
            {"code": "ASSET-1", "text": "Provide 2 months complete bank statements for all asset accounts"},
            {"code": "ASSET-2", "text": "Provide explanation and documentation for all deposits over $500 not from payroll"},
            {"code": "ASSET-3", "text": "Provide gift letter, donor bank statements, and transfer documentation for gift funds"},
            {"code": "ASSET-4", "text": "Provide documentation of earnest money deposit"},
        ],
        "credit": [
            {"code": "CREDIT-1", "text": "Provide letter of explanation for late payments on credit report"},
            {"code": "CREDIT-2", "text": "Provide letter of explanation for credit inquiries in last 120 days"},
            {"code": "CREDIT-3", "text": "Provide bankruptcy discharge and schedules"},
            {"code": "CREDIT-4", "text": "Provide documentation showing collection accounts paid or in payment plan"},
        ],
        "property": [
            {"code": "PROP-1", "text": "Subject to satisfactory appraisal"},
            {"code": "PROP-2", "text": "Subject to clear title commitment with no exceptions"},
            {"code": "PROP-3", "text": "Provide executed purchase contract and all addenda"},
            {"code": "PROP-4", "text": "Provide proof of homeowners insurance with loss payee clause"},
            {"code": "PROP-5", "text": "Provide flood zone determination; if in flood zone, provide flood insurance"},
        ],
        "legal": [
            {"code": "LEGAL-1", "text": "Provide copy of government-issued photo ID for all borrowers"},
            {"code": "LEGAL-2", "text": "Provide signed and dated borrower authorizations"},
            {"code": "LEGAL-3", "text": "Provide divorce decree and property settlement agreement"},
            {"code": "LEGAL-4", "text": "Provide power of attorney if applicable (must be reviewed by legal)"},
        ],
    },

    "prior_to_docs": [
        {"code": "PTD-1", "text": "Verbal VOE within 10 business days of closing"},
        {"code": "PTD-2", "text": "Updated paystub within 30 days of closing"},
        {"code": "PTD-3", "text": "Updated bank statement within 45 days of closing"},
        {"code": "PTD-4", "text": "Clear termite inspection"},
        {"code": "PTD-5", "text": "Well and septic inspection (if applicable)"},
        {"code": "PTD-6", "text": "Appraisal repairs completed with photos"},
    ],

    "prior_to_funding": [
        {"code": "PTF-1", "text": "Executed Closing Disclosure with all fees accurate"},
        {"code": "PTF-2", "text": "Signed and notarized loan documents"},
        {"code": "PTF-3", "text": "Wire instructions verification call"},
        {"code": "PTF-4", "text": "Final title policy commitment"},
        {"code": "PTF-5", "text": "Funding authorization from all parties"},
    ],
}


# =============================================================================
# CALL OUTCOME PATTERNS
# =============================================================================

CALL_OUTCOME_PATTERNS = {
    "positive": [
        "Application taken during call",
        "Borrower committed to moving forward",
        "Scheduled follow-up appointment",
        "Borrower agreed to send documents",
        "Pre-approval issued",
        "Lock requested/confirmed",
        "Closing scheduled",
    ],
    "neutral": [
        "Information gathering call",
        "Answering borrower questions",
        "Discussing options without decision",
        "Rate shopping/comparison",
        "Document collection follow-up",
    ],
    "needs_follow_up": [
        "Borrower needs to discuss with spouse/family",
        "Borrower comparing multiple lenders",
        "Waiting on documents or information",
        "Credit improvement needed",
        "Down payment sourcing in progress",
    ],
    "negative": [
        "Borrower declined to proceed",
        "Does not qualify at this time",
        "Went with another lender",
        "Property issue - deal fell through",
        "Changed mind about purchasing",
    ],
}


# =============================================================================
# FOLLOW-UP MESSAGE TEMPLATES
# =============================================================================

FOLLOW_UP_TEMPLATES = {
    "after_application": {
        "subject": "Thank You for Your Loan Application - Next Steps",
        "body": """Hi {borrower_name},

Thank you for completing your loan application with me today. I'm excited to help you {loan_purpose} your home!

Here's what happens next:
1. I'll review your application and documentation
2. {next_step_specific}
3. I'll keep you updated throughout the process

Documents still needed:
{document_list}

Please send these at your earliest convenience to keep things moving.

Questions? I'm here to help!

Best regards,
{lo_name}
{lo_phone}""",
    },

    "document_request": {
        "subject": "Documents Needed for Your Mortgage Application",
        "body": """Hi {borrower_name},

To continue processing your loan application, I need the following documents:

{document_list}

You can:
• Reply to this email with attachments
• Upload securely at: {upload_link}
• Fax to: {fax_number}

If you have questions about any of these items, please let me know!

{lo_name}
{lo_phone}""",
    },

    "rate_lock": {
        "subject": "Your Interest Rate Has Been Locked!",
        "body": """Hi {borrower_name},

Great news! I've locked your interest rate as we discussed:

Rate: {interest_rate}%
Term: {loan_term} years
Lock Expiration: {lock_expiration}

This rate is guaranteed as long as we close by {lock_expiration}.

Next steps:
{next_steps}

Let me know if you have any questions!

{lo_name}
{lo_phone}""",
    },

    "closing_scheduled": {
        "subject": "Your Closing is Scheduled! {closing_date}",
        "body": """Hi {borrower_name},

Congratulations! Your closing is scheduled:

Date: {closing_date}
Time: {closing_time}
Location: {closing_location}

What to bring:
• Government-issued photo ID
• Certified/cashier's check for ${cash_to_close} payable to {title_company}
• (Or wire funds - I'll send wire instructions separately)

I'll send your Closing Disclosure at least 3 business days before closing for your review.

Almost there! Let me know if you have questions.

{lo_name}
{lo_phone}""",
    },
}


# =============================================================================
# FEW-SHOT EXAMPLES
# =============================================================================

FEW_SHOT_EXAMPLES = {
    "scribe_summary": {
        "input": """[LO]: Good morning, this is Sarah from ABC Mortgage. Am I speaking with John?
[Borrower]: Yes, this is John.
[LO]: Great! I'm calling about your pre-approval application. I've reviewed everything and you're approved for up to $450,000.
[Borrower]: That's great news! My wife and I were hoping for around $400,000.
[LO]: Perfect, that's well within your approval. Your rate would be around 6.75% for a 30-year fixed.
[Borrower]: That sounds good. We're looking at a house on Maple Street this weekend.
[LO]: Excellent! Once you have an accepted offer, send me the contract and we'll get started right away.
[Borrower]: Will do. What documents do you need from me?
[LO]: I'll need your 2 most recent pay stubs, last 2 months of bank statements, and your W-2s from last year.
[Borrower]: Got it. I'll get those together this week.""",
        "output": {
            "executive_summary": "John received pre-approval confirmation for $450,000. He's planning to offer around $400,000 on a property this weekend and will submit required documentation.",
            "detailed_summary": "Sarah from ABC Mortgage called John to confirm his pre-approval. He's approved for up to $450,000 at approximately 6.75% for a 30-year fixed. John and his wife are looking at a property on Maple Street this weekend with a target price of $400,000. John agreed to send pay stubs, bank statements, and W-2s.",
            "key_points": [
                "Pre-approved for $450,000",
                "Target purchase price: $400,000",
                "Rate quoted: ~6.75% 30-year fixed",
                "Viewing property on Maple Street this weekend",
                "Documents needed: pay stubs, bank statements, W-2s"
            ],
            "action_items": [
                {
                    "title": "Submit income documentation",
                    "description": "Send 2 most recent pay stubs and W-2s from last year",
                    "owner": "Borrower",
                    "deadline": "This week",
                    "priority": "high"
                },
                {
                    "title": "Submit bank statements",
                    "description": "Provide last 2 months of bank statements",
                    "owner": "Borrower",
                    "deadline": "This week",
                    "priority": "high"
                },
                {
                    "title": "Send purchase contract",
                    "description": "Once offer is accepted on Maple Street property, send contract",
                    "owner": "Borrower",
                    "deadline": "After offer accepted",
                    "priority": "medium"
                }
            ],
            "call_outcome": "positive",
            "next_call_recommended": True,
            "next_call_topic": "Follow up on property showing and document submission"
        }
    },

    "junior_lo_extraction": {
        "input": """[LO]: Let me get some information for your application. What's your current employer?
[Borrower]: I work at Tech Solutions Inc. Been there about 3 years now.
[LO]: Great, and what's your position and annual salary?
[Borrower]: I'm a Senior Developer, making $125,000 base plus usually around $15,000 in bonus.
[LO]: Perfect. Do you have any other income?
[Borrower]: My wife works part-time at the hospital, she makes about $35,000 a year.
[LO]: And for the down payment, how much are you putting down?
[Borrower]: We've saved $80,000, but my parents are also giving us $20,000 as a gift.
[LO]: That's helpful. What about debts - any car payments or student loans?
[Borrower]: I have a car payment of $450 a month, about 3 years left. And student loans at $300 a month.""",
        "output": {
            "intake_fields": [
                {"field_name": "Employer Name", "field_path": "borrower.employment.employer_name",
                 "value": "Tech Solutions Inc.", "confidence": 0.95, "evidence": "I work at Tech Solutions Inc."},
                {"field_name": "Years at Employer", "field_path": "borrower.employment.years",
                 "value": "3", "confidence": 0.90, "evidence": "Been there about 3 years now"},
                {"field_name": "Position Title", "field_path": "borrower.employment.position",
                 "value": "Senior Developer", "confidence": 0.95, "evidence": "I'm a Senior Developer"},
                {"field_name": "Base Income (Annual)", "field_path": "borrower.income.base_annual",
                 "value": "125000", "confidence": 0.95, "evidence": "making $125,000 base"},
                {"field_name": "Bonus Income (Annual)", "field_path": "borrower.income.bonus_annual",
                 "value": "15000", "confidence": 0.85, "evidence": "usually around $15,000 in bonus"},
                {"field_name": "Co-Borrower Income (Annual)", "field_path": "coborrower.income.base_annual",
                 "value": "35000", "confidence": 0.90, "evidence": "she makes about $35,000 a year"},
                {"field_name": "Savings for Down Payment", "field_path": "assets.savings_downpayment",
                 "value": "80000", "confidence": 0.95, "evidence": "We've saved $80,000"},
                {"field_name": "Gift Amount", "field_path": "assets.gift_amount",
                 "value": "20000", "confidence": 0.95, "evidence": "parents are also giving us $20,000 as a gift"},
                {"field_name": "Car Payment", "field_path": "liabilities.auto_payment",
                 "value": "450", "confidence": 0.95, "evidence": "car payment of $450 a month"},
                {"field_name": "Student Loan Payment", "field_path": "liabilities.student_loan_payment",
                 "value": "300", "confidence": 0.95, "evidence": "student loans at $300 a month"}
            ],
            "document_requests": [
                {"document_type": "paystubs", "document_name": "Pay Stubs (30 days)",
                 "reason": "Verify base salary and employment", "priority": "high"},
                {"document_type": "w2", "document_name": "W-2s (2 years)",
                 "reason": "Verify income history and bonus pattern", "priority": "high"},
                {"document_type": "bank_statements", "document_name": "Bank Statements (2 months)",
                 "reason": "Verify $80,000 savings for down payment", "priority": "high"},
                {"document_type": "gift_letter", "document_name": "Gift Letter",
                 "reason": "$20,000 gift from parents", "priority": "high"},
                {"document_type": "donor_bank_statements", "document_name": "Parents' Bank Statements",
                 "reason": "Verify gift fund source", "priority": "high"}
            ],
            "borrower_profile": {
                "employment_type": "W2",
                "income_sources": ["Base salary", "Annual bonus", "Spouse part-time income"],
                "property_use": "Primary",
                "estimated_credit": "Unknown",
                "first_time_buyer": None
            }
        }
    },

    "underwriter_risk_analysis": {
        "input": """[LO]: I see you mentioned you're self-employed. How long have you had your business?
[Borrower]: About 18 months now. I left my corporate job to start my consulting firm.
[LO]: I understand. And how's the business doing?
[Borrower]: It's been great! Last year I made about $180,000, though the first few months were slow.
[LO]: That's good. Just so you know, we'll need two years of tax returns for self-employment.
[Borrower]: I only have one year of self-employment returns. Before that I was W-2.
[LO]: We can work with that, but it may require additional documentation. Any other income?
[Borrower]: I have some rental income from a property I bought 2 years ago. About $1,500 a month.
[LO]: Perfect. Now, I noticed on your credit there was a late payment a few months ago?
[Borrower]: Yes, that was during my transition. I missed one mortgage payment but caught up right away.
[LO]: Okay, we'll need a letter explaining that. What's your current credit score?
[Borrower]: Around 690 last time I checked.""",
        "output": {
            "risk_flags": [
                {
                    "category": "income",
                    "severity": "high",
                    "title": "Self-Employment Less Than 2 Years",
                    "description": "Borrower has only 18 months of self-employment history. Standard guidelines require 2 years. Previous W-2 employment may help mitigate.",
                    "evidence": "About 18 months now. I left my corporate job to start my consulting firm.",
                    "recommended_action": "Request W-2 history from prior employer, full 2 years of tax returns (1 year SE + prior W-2), and YTD P&L"
                },
                {
                    "category": "credit",
                    "severity": "medium",
                    "title": "Recent Mortgage Late Payment",
                    "description": "Borrower had a late mortgage payment during employment transition. Single late payment is explainable but should be documented.",
                    "evidence": "I missed one mortgage payment but caught up right away.",
                    "recommended_action": "Obtain letter of explanation, verify payment history is current, check credit supplement for accuracy"
                },
                {
                    "category": "income",
                    "severity": "medium",
                    "title": "Income Ramp-Up Period",
                    "description": "First few months of self-employment were slow, which may affect income averaging. Need to see month-by-month breakdown.",
                    "evidence": "Last year I made about $180,000, though the first few months were slow.",
                    "recommended_action": "Request detailed P&L showing monthly income trend, verify income is stabilized"
                }
            ],
            "suggested_conditions": [
                {
                    "condition_type": "prior_to_approval",
                    "category": "income",
                    "title": "Self-Employment Documentation",
                    "description": "Provide 2 years complete tax returns (personal and business if applicable), YTD P&L, and business license",
                    "reason": "Self-employment income verification required"
                },
                {
                    "condition_type": "prior_to_approval",
                    "category": "credit",
                    "title": "Late Payment Letter of Explanation",
                    "description": "Provide signed letter explaining mortgage late payment during employment transition",
                    "reason": "Recent derogatory credit requires explanation"
                },
                {
                    "condition_type": "prior_to_docs",
                    "category": "income",
                    "title": "Verbal VOE - Prior Employer",
                    "description": "Verbal verification of employment from prior corporate employer to confirm separation date and income",
                    "reason": "Bridge income gap in self-employment history"
                }
            ],
            "uw_notes": [
                {
                    "category": "observation",
                    "note": "Borrower transitioned from W-2 to self-employment 18 months ago. Will need prior W-2 history to supplement SE income.",
                    "priority": "high"
                },
                {
                    "category": "positive",
                    "note": "Strong reported income of $180,000 in first full year of self-employment. 690 credit score is within conventional guidelines.",
                    "priority": "medium"
                },
                {
                    "category": "concern",
                    "note": "Rental income claimed - need Schedule E to verify, check if property is owned free and clear or has debt service.",
                    "priority": "medium"
                }
            ],
            "overall_assessment": {
                "risk_level": "moderate",
                "key_concerns": [
                    "Self-employment less than 2 years",
                    "Recent mortgage late payment",
                    "Income trending needs verification"
                ],
                "strengths": [
                    "Strong income level",
                    "Credit score 690 meets guidelines",
                    "Prior W-2 employment history",
                    "Additional rental income stream"
                ],
                "recommendation": "approve_with_conditions"
            }
        }
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_required_documents(loan_type: str, employment_type: str, loan_purpose: str,
                           special_situations: list = None) -> list:
    """
    Get complete list of required documents based on loan scenario.

    Args:
        loan_type: conventional, fha, va, usda
        employment_type: w2_employed, self_employed, commission, retirement
        loan_purpose: purchase, refinance, cash_out
        special_situations: list of situations like 'divorce', 'bankruptcy', etc.

    Returns:
        List of required document dictionaries
    """
    documents = []

    # Add income documents
    income_docs = DOCUMENT_REQUIREMENTS.get("income", {}).get(employment_type, {})
    documents.extend(income_docs.get("required", []))

    # Add loan purpose documents
    purpose_docs = DOCUMENT_REQUIREMENTS.get("loan_purpose", {}).get(loan_purpose, {})
    documents.extend(purpose_docs.get("required", []))

    # Add asset documents
    documents.extend(DOCUMENT_REQUIREMENTS["assets"]["standard"]["required"])

    # Add special situation documents
    if special_situations:
        for situation in special_situations:
            sit_docs = DOCUMENT_REQUIREMENTS.get("special_situations", {}).get(situation, {})
            documents.extend(sit_docs.get("required", []))

    # Add loan type specific documents
    if loan_type == "va":
        documents.append({"doc": "va_coe", "desc": "VA Certificate of Eligibility"})
    elif loan_type == "fha":
        documents.append({"doc": "fha_case_number", "desc": "FHA case number assignment"})

    return documents


def get_waiting_period(event_type: str, loan_type: str) -> str:
    """
    Get waiting period for credit events by loan type.

    Args:
        event_type: bankruptcy_ch7, bankruptcy_ch13, foreclosure, short_sale
        loan_type: conventional, fha, va, usda

    Returns:
        String describing waiting period
    """
    waiting_periods = {
        "conventional": {
            "bankruptcy_ch7": "4 years from discharge",
            "bankruptcy_ch13": "2 years from discharge, 4 years from dismissal",
            "foreclosure": "7 years from completion",
            "short_sale": "4 years (or 2 years with extenuating circumstances)",
        },
        "fha": {
            "bankruptcy_ch7": "2 years from discharge",
            "bankruptcy_ch13": "1 year with court approval, 2 years from discharge",
            "foreclosure": "3 years from transfer date",
            "short_sale": "3 years from sale date",
        },
        "va": {
            "bankruptcy_ch7": "2 years from discharge",
            "bankruptcy_ch13": "1 year with court approval",
            "foreclosure": "2 years from transfer date",
            "short_sale": "2 years from sale date",
        },
    }

    return waiting_periods.get(loan_type, {}).get(event_type, "Consult guidelines")


def calculate_max_dti(loan_type: str, credit_score: int, ltv: float,
                      has_compensating_factors: bool = False) -> float:
    """
    Calculate maximum DTI based on loan scenario.

    Returns the maximum allowable DTI percentage.
    """
    guidelines = LOAN_PROGRAM_GUIDELINES.get(loan_type, {})
    max_dti = guidelines.get("max_dti", {})

    if has_compensating_factors:
        return max_dti.get("with_compensating", max_dti.get("standard", 43))
    else:
        return max_dti.get("standard", 43)
