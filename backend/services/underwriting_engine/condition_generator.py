"""
Condition Generator Module
Automatically generates and manages underwriting conditions per agency guidelines.
Key capabilities:
- Prior-to-Document (PTD) condition generation
- Prior-to-Funding (PTF) condition generation
- Condition clearing logic
- Smart condition bundling
- Condition priority and dependencies
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class ConditionType(str, Enum):
    """Types of underwriting conditions."""
    PRIOR_TO_DOC = "PTD"  # Prior to Documents
    PRIOR_TO_FUND = "PTF"  # Prior to Funding
    PRIOR_TO_CLOSE = "PTC"  # Prior to Close
    PRIOR_TO_APPROVAL = "PTA"  # Prior to Approval
    POST_CLOSE = "PC"  # Post-Closing


class ConditionCategory(str, Enum):
    """Categories of conditions."""
    INCOME = "income"
    EMPLOYMENT = "employment"
    ASSETS = "assets"
    CREDIT = "credit"
    PROPERTY = "property"
    TITLE = "title"
    INSURANCE = "insurance"
    LEGAL = "legal"
    COMPLIANCE = "compliance"
    OTHER = "other"


class ConditionPriority(str, Enum):
    """Condition priority levels."""
    CRITICAL = "critical"  # Must be cleared before approval
    HIGH = "high"  # Standard underwriting conditions
    MEDIUM = "medium"  # Important but not blocking
    LOW = "low"  # Nice to have / documentation


class ConditionStatus(str, Enum):
    """Status of a condition."""
    OPEN = "open"
    IN_REVIEW = "in_review"
    CLEARED = "cleared"
    WAIVED = "waived"
    NOT_APPLICABLE = "n/a"


@dataclass
class Condition:
    """Represents an underwriting condition."""
    id: str
    condition_type: ConditionType
    category: ConditionCategory
    priority: ConditionPriority
    title: str
    description: str
    clearing_instructions: str
    acceptable_documents: List[str]
    status: ConditionStatus = ConditionStatus.OPEN
    created_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[date] = None
    cleared_at: Optional[datetime] = None
    cleared_by: Optional[str] = None
    clearing_notes: Optional[str] = None
    source: str = "automated"  # automated, manual, aus
    aus_reference: Optional[str] = None  # DU/LP condition reference
    dependencies: List[str] = field(default_factory=list)
    related_conditions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConditionClearingResult:
    """Result of attempting to clear a condition."""
    condition_id: str
    success: bool
    new_status: ConditionStatus
    message: str
    cleared_by: Optional[str] = None
    remaining_issues: List[str] = field(default_factory=list)
    created_followup_conditions: List[str] = field(default_factory=list)


# Standard condition templates
CONDITION_TEMPLATES = {
    # =============== INCOME CONDITIONS ===============
    "income_voe": {
        "title": "Verification of Employment",
        "description": "Provide current verification of employment dated within 10 days of closing.",
        "clearing_instructions": "VOE must confirm: current employment status, hire date, position/title, and current income. For salary employees, provide base pay. For hourly employees, provide hourly rate and average hours.",
        "acceptable_documents": ["voe_form", "paystub_current", "employer_letter"],
        "category": ConditionCategory.EMPLOYMENT,
        "priority": ConditionPriority.HIGH,
    },
    "income_voe_verbal": {
        "title": "Verbal Verification of Employment",
        "description": "Complete verbal verification of employment within 10 business days of closing.",
        "clearing_instructions": "Underwriter or processor must complete verbal VOE with HR or supervisor. Document: contact name, title, phone number, and employment confirmation.",
        "acceptable_documents": ["vvoe_form"],
        "category": ConditionCategory.EMPLOYMENT,
        "priority": ConditionPriority.HIGH,
        "condition_type": ConditionType.PRIOR_TO_FUND,
    },
    "income_paystubs": {
        "title": "Current Paystubs",
        "description": "Provide most recent 30 days of paystubs covering complete pay periods.",
        "clearing_instructions": "Paystubs must show: borrower name, employer name, pay period dates, YTD earnings breakdown, deductions.",
        "acceptable_documents": ["paystub"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_w2_prior": {
        "title": "W-2 Forms - Prior Year",
        "description": "Provide W-2 forms for the prior tax year.",
        "clearing_instructions": "W-2 must show employer name and address matching VOE, borrower SSN, and all income boxes.",
        "acceptable_documents": ["w2"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_w2_2years": {
        "title": "W-2 Forms - Two Year History",
        "description": "Provide W-2 forms for the most recent two tax years.",
        "clearing_instructions": "W-2s must show consistent employment history. If employer changed, provide W-2s from all employers.",
        "acceptable_documents": ["w2"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_tax_returns": {
        "title": "Tax Returns",
        "description": "Provide complete signed federal tax returns for most recent two years including all schedules.",
        "clearing_instructions": "Returns must be signed and dated. Include all schedules (A, B, C, D, E, K-1). If filed electronically, include e-file confirmation.",
        "acceptable_documents": ["tax_return_1040", "tax_transcript"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_4506c": {
        "title": "IRS Transcript Request (4506-C)",
        "description": "Provide signed IRS Form 4506-C for tax transcript validation.",
        "clearing_instructions": "Form must be signed by all borrowers with income. Verify SSN and addresses match loan application.",
        "acceptable_documents": ["4506c_form"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_tax_transcripts": {
        "title": "IRS Tax Transcripts",
        "description": "Provide IRS tax transcripts for most recent two tax years.",
        "clearing_instructions": "Transcripts must match tax returns provided. Any discrepancies require explanation.",
        "acceptable_documents": ["tax_transcript"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_variable_doc": {
        "title": "Variable Income Documentation",
        "description": "Provide documentation supporting variable income (overtime, bonus, commission).",
        "clearing_instructions": "Document 2-year history of variable income. Provide employer verification that income is likely to continue.",
        "acceptable_documents": ["employer_letter", "paystub", "w2"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_ytd_profit_loss": {
        "title": "Year-to-Date Profit & Loss Statement",
        "description": "Provide current year-to-date profit and loss statement for self-employment income.",
        "clearing_instructions": "P&L must be dated within 60 days of closing. Show gross receipts, expenses by category, and net profit. Signed by borrower or prepared by accountant.",
        "acceptable_documents": ["profit_loss_statement"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_business_license": {
        "title": "Business License/Registration",
        "description": "Provide current business license or registration documentation.",
        "clearing_instructions": "Document must show business is active and in good standing. If sole proprietor, provide DBA registration or equivalent.",
        "acceptable_documents": ["business_license", "articles_of_incorporation"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.MEDIUM,
    },
    "income_rental_schedule_e": {
        "title": "Schedule E Documentation",
        "description": "Provide Schedule E from tax returns for rental income properties.",
        "clearing_instructions": "Schedule E must show all rental properties. Provide rental agreements for any properties not shown on Schedule E.",
        "acceptable_documents": ["schedule_e", "rental_agreement"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_social_security": {
        "title": "Social Security Income Verification",
        "description": "Provide SSA benefit verification letter or 1099-SSA.",
        "clearing_instructions": "Award letter must show current benefit amount and continuation. If using gross-up, verify non-taxable status.",
        "acceptable_documents": ["ssa_award_letter", "1099_ssa"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_pension": {
        "title": "Pension/Retirement Income Verification",
        "description": "Provide pension award letter and recent distribution statements.",
        "clearing_instructions": "Verify pension is in pay status and show current monthly amount. Include proof of receipt (bank statements showing deposits).",
        "acceptable_documents": ["pension_award_letter", "1099_r", "bank_statement"],
        "category": ConditionCategory.INCOME,
        "priority": ConditionPriority.HIGH,
    },
    "income_gap_explanation": {
        "title": "Employment Gap Explanation",
        "description": "Provide written explanation for gap in employment history.",
        "clearing_instructions": "Letter must explain reason for employment gap exceeding 30 days within past 2 years. Signed and dated by borrower.",
        "acceptable_documents": ["loe_employment_gap"],
        "category": ConditionCategory.EMPLOYMENT,
        "priority": ConditionPriority.MEDIUM,
    },

    # =============== ASSET CONDITIONS ===============
    "asset_bank_statements": {
        "title": "Bank Statements - Most Recent",
        "description": "Provide complete bank statements for most recent two months for all accounts.",
        "clearing_instructions": "Statements must show: account holder name, account number (can be redacted last 4), all pages including blank pages, all transactions, ending balance.",
        "acceptable_documents": ["bank_statement"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },
    "asset_large_deposit": {
        "title": "Large Deposit Documentation",
        "description": "Provide documentation for large deposit(s) identified on bank statements.",
        "clearing_instructions": "Document source of each deposit exceeding 50% of qualifying income. Acceptable sources: payroll, gift, sale of asset, insurance proceeds. Provide paper trail.",
        "acceptable_documents": ["deposit_explanation", "cancelled_check", "wire_confirmation"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },
    "asset_gift_letter": {
        "title": "Gift Letter",
        "description": "Provide gift letter for gift funds being used for closing.",
        "clearing_instructions": "Letter must state: donor name and relationship, amount of gift, statement that no repayment is expected, property address. Signed by donor.",
        "acceptable_documents": ["gift_letter"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },
    "asset_gift_transfer": {
        "title": "Gift Fund Transfer Documentation",
        "description": "Provide documentation of gift fund transfer.",
        "clearing_instructions": "Show transfer of funds from donor account to borrower account or directly to title. Include donor bank statement showing withdrawal.",
        "acceptable_documents": ["bank_statement", "wire_confirmation", "cancelled_check"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },
    "asset_retirement_statements": {
        "title": "Retirement Account Statements",
        "description": "Provide most recent quarterly statements for retirement accounts.",
        "clearing_instructions": "Statements must show: account holder name, account type (401k, IRA, etc.), vested balance, terms for withdrawal if using for reserves.",
        "acceptable_documents": ["retirement_statement", "401k_statement"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.MEDIUM,
    },
    "asset_earnest_money": {
        "title": "Earnest Money Deposit Verification",
        "description": "Provide documentation of earnest money deposit.",
        "clearing_instructions": "Show: copy of cancelled check or wire confirmation, source bank statement showing withdrawal, receipt from title company or escrow.",
        "acceptable_documents": ["cancelled_check", "wire_confirmation", "escrow_receipt"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },
    "asset_sale_proceeds": {
        "title": "Sale Proceeds Documentation",
        "description": "Provide documentation for proceeds from sale of asset.",
        "clearing_instructions": "Provide: bill of sale or settlement statement, proof of ownership prior to sale, deposit of funds to borrower account.",
        "acceptable_documents": ["bill_of_sale", "closing_statement", "bank_statement"],
        "category": ConditionCategory.ASSETS,
        "priority": ConditionPriority.HIGH,
    },

    # =============== CREDIT CONDITIONS ===============
    "credit_loe_inquiry": {
        "title": "Letter of Explanation - Credit Inquiry",
        "description": "Provide written explanation for recent credit inquiry/inquiries.",
        "clearing_instructions": "Explain purpose of each inquiry within past 90-120 days. If new debt was obtained, provide payment information.",
        "acceptable_documents": ["loe_credit_inquiry"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.MEDIUM,
    },
    "credit_loe_late_payment": {
        "title": "Letter of Explanation - Late Payment",
        "description": "Provide written explanation for late payment(s) on credit report.",
        "clearing_instructions": "Explain reason for each late payment. Describe circumstances and steps taken to prevent recurrence.",
        "acceptable_documents": ["loe_late_payment"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.MEDIUM,
    },
    "credit_loe_collection": {
        "title": "Letter of Explanation - Collection Account",
        "description": "Provide written explanation for collection account(s).",
        "clearing_instructions": "Explain circumstances of collection. If medical, provide verification. If disputed, provide dispute documentation.",
        "acceptable_documents": ["loe_collection", "medical_verification"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.MEDIUM,
    },
    "credit_payoff_statement": {
        "title": "Payoff Statement",
        "description": "Provide payoff statement for account(s) to be paid at closing.",
        "clearing_instructions": "Payoff must show: creditor name, account number, per diem interest, good-through date, wire instructions.",
        "acceptable_documents": ["payoff_statement"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.HIGH,
    },
    "credit_subordination": {
        "title": "Subordination Agreement",
        "description": "Provide executed subordination agreement for existing lien(s).",
        "clearing_instructions": "Agreement must be executed by existing lienholder agreeing to subordinate to new first mortgage.",
        "acceptable_documents": ["subordination_agreement"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.CRITICAL,
    },
    "credit_bk_discharge": {
        "title": "Bankruptcy Discharge Documents",
        "description": "Provide bankruptcy discharge documentation.",
        "clearing_instructions": "Provide: petition filing date, chapter filed, discharge order, list of debts discharged. Verify waiting period met.",
        "acceptable_documents": ["bk_discharge", "bk_petition"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.HIGH,
    },
    "credit_judgment_satisfaction": {
        "title": "Judgment Satisfaction",
        "description": "Provide satisfaction of judgment documentation.",
        "clearing_instructions": "Provide recorded satisfaction or proof of payment. If to remain open, obtain subordination.",
        "acceptable_documents": ["judgment_satisfaction", "payoff_confirmation"],
        "category": ConditionCategory.CREDIT,
        "priority": ConditionPriority.HIGH,
    },

    # =============== PROPERTY CONDITIONS ===============
    "property_appraisal": {
        "title": "Property Appraisal",
        "description": "Order and obtain property appraisal.",
        "clearing_instructions": "Appraisal must meet agency guidelines. Review for: value support, condition rating, property type confirmation, marketability.",
        "acceptable_documents": ["appraisal_report"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.CRITICAL,
    },
    "property_appraisal_rebuttal": {
        "title": "Appraisal Value Review",
        "description": "Value came in below contract price. Review options with borrower.",
        "clearing_instructions": "Options: renegotiate purchase price, borrower covers difference, provide additional comps for reconsideration, order second appraisal.",
        "acceptable_documents": ["appraisal_rebuttal", "price_amendment"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.CRITICAL,
    },
    "property_repairs": {
        "title": "Property Repairs Required",
        "description": "Complete required repairs as noted on appraisal.",
        "clearing_instructions": "Obtain completion certificate from appraiser after repairs completed. Repairs must address all items noted on original appraisal.",
        "acceptable_documents": ["repair_completion_cert", "contractor_invoice"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.HIGH,
    },
    "property_survey": {
        "title": "Property Survey",
        "description": "Provide current property survey.",
        "clearing_instructions": "Survey must be dated within 6 months or certified as unchanged. Show all structures, easements, and encroachments.",
        "acceptable_documents": ["survey"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.MEDIUM,
    },
    "property_flood_cert": {
        "title": "Flood Certification",
        "description": "Obtain flood zone determination.",
        "clearing_instructions": "If property is in flood zone, flood insurance is required. Provide evidence of flood insurance if applicable.",
        "acceptable_documents": ["flood_certificate"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.HIGH,
    },
    "property_condo_cert": {
        "title": "Condominium Documentation",
        "description": "Provide condominium certification and project documentation.",
        "clearing_instructions": "Include: HOA questionnaire, master insurance policy, budget, reserve study, litigation disclosure.",
        "acceptable_documents": ["hoa_certification", "condo_questionnaire"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.HIGH,
    },
    "property_purchase_contract": {
        "title": "Purchase Contract",
        "description": "Provide fully executed purchase contract with all addenda.",
        "clearing_instructions": "Contract must be signed by all parties. Include all amendments, counter-offers, and addenda.",
        "acceptable_documents": ["purchase_contract"],
        "category": ConditionCategory.PROPERTY,
        "priority": ConditionPriority.CRITICAL,
    },

    # =============== TITLE CONDITIONS ===============
    "title_commitment": {
        "title": "Title Commitment",
        "description": "Provide title commitment/preliminary title report.",
        "clearing_instructions": "Review for: vesting, liens, judgments, easements, legal description. All exceptions must be acceptable.",
        "acceptable_documents": ["title_commitment"],
        "category": ConditionCategory.TITLE,
        "priority": ConditionPriority.CRITICAL,
    },
    "title_clear_requirements": {
        "title": "Clear Title Requirements",
        "description": "Satisfy title requirements as listed on commitment.",
        "clearing_instructions": "Provide documentation clearing each requirement listed in Schedule B-1 of title commitment.",
        "acceptable_documents": ["title_clearance_docs"],
        "category": ConditionCategory.TITLE,
        "priority": ConditionPriority.HIGH,
    },
    "title_vesting_change": {
        "title": "Vesting/Name Change Documentation",
        "description": "Provide documentation for name/vesting difference between title and application.",
        "clearing_instructions": "Acceptable documents: marriage certificate, divorce decree, court order for name change.",
        "acceptable_documents": ["marriage_certificate", "divorce_decree", "name_change_order"],
        "category": ConditionCategory.TITLE,
        "priority": ConditionPriority.HIGH,
    },

    # =============== INSURANCE CONDITIONS ===============
    "insurance_homeowners": {
        "title": "Homeowners Insurance",
        "description": "Provide evidence of homeowners insurance.",
        "clearing_instructions": "Policy must show: property address, coverage amount (min dwelling replacement cost), effective date, mortgagee clause with lender name.",
        "acceptable_documents": ["insurance_binder", "insurance_policy"],
        "category": ConditionCategory.INSURANCE,
        "priority": ConditionPriority.HIGH,
    },
    "insurance_flood": {
        "title": "Flood Insurance",
        "description": "Provide evidence of flood insurance (property in flood zone).",
        "clearing_instructions": "Coverage must meet minimum requirements. Show NFIP policy or private equivalent with mortgagee clause.",
        "acceptable_documents": ["flood_insurance_policy"],
        "category": ConditionCategory.INSURANCE,
        "priority": ConditionPriority.CRITICAL,
    },
    "insurance_condo_master": {
        "title": "Condominium Master Insurance Policy",
        "description": "Provide HOA master insurance policy.",
        "clearing_instructions": "Master policy must include: hazard, liability, fidelity coverage. Verify adequate coverage limits.",
        "acceptable_documents": ["condo_master_policy"],
        "category": ConditionCategory.INSURANCE,
        "priority": ConditionPriority.HIGH,
    },
    "insurance_ho6": {
        "title": "Condo Unit Owner Insurance (HO-6)",
        "description": "Provide unit owner/walls-in insurance policy.",
        "clearing_instructions": "HO-6 policy covering interior improvements and personal liability. Mortgagee clause required.",
        "acceptable_documents": ["ho6_policy"],
        "category": ConditionCategory.INSURANCE,
        "priority": ConditionPriority.HIGH,
    },

    # =============== COMPLIANCE CONDITIONS ===============
    "compliance_id": {
        "title": "Government-Issued Photo ID",
        "description": "Provide copy of valid government-issued photo identification.",
        "clearing_instructions": "Acceptable: driver's license, passport, state ID, military ID. Must not be expired.",
        "acceptable_documents": ["drivers_license", "passport", "government_id"],
        "category": ConditionCategory.COMPLIANCE,
        "priority": ConditionPriority.HIGH,
    },
    "compliance_ss_verification": {
        "title": "Social Security Number Verification",
        "description": "Verify borrower Social Security number.",
        "clearing_instructions": "Acceptable: SS card, tax return, W-2, SSA letter. Name must match or provide name change documentation.",
        "acceptable_documents": ["ss_card", "tax_return_1040", "w2"],
        "category": ConditionCategory.COMPLIANCE,
        "priority": ConditionPriority.HIGH,
    },
    "compliance_occupancy_cert": {
        "title": "Occupancy Certification",
        "description": "Provide signed occupancy certification.",
        "clearing_instructions": "Borrower must certify intent to occupy property as primary residence within 60 days of closing.",
        "acceptable_documents": ["occupancy_certification"],
        "category": ConditionCategory.COMPLIANCE,
        "priority": ConditionPriority.HIGH,
    },
    "compliance_4506c_results": {
        "title": "IRS 4506-C Transcript Results",
        "description": "Receive and validate IRS tax transcript results.",
        "clearing_instructions": "Transcripts must match provided tax returns. Any discrepancies require resolution before closing.",
        "acceptable_documents": ["tax_transcript"],
        "category": ConditionCategory.COMPLIANCE,
        "priority": ConditionPriority.HIGH,
        "condition_type": ConditionType.PRIOR_TO_FUND,
    },
}


class ConditionGenerator:
    """
    Generates underwriting conditions based on loan file analysis.
    Conditions are generated per agency guidelines and can be customized
    based on loan program, property type, and file specifics.
    """

    def __init__(self):
        self.templates = CONDITION_TEMPLATES
        self._condition_counter = 0

    def _generate_condition_id(self) -> str:
        """Generate unique condition ID."""
        self._condition_counter += 1
        return f"COND-{datetime.now().strftime('%Y%m%d')}-{self._condition_counter:04d}"

    def generate_from_template(
        self,
        template_key: str,
        condition_type: Optional[ConditionType] = None,
        custom_description: Optional[str] = None,
        custom_instructions: Optional[str] = None,
        due_date: Optional[date] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Condition]:
        """Generate a condition from a template."""
        template = self.templates.get(template_key)
        if not template:
            logger.warning(f"Template not found: {template_key}")
            return None

        cond_type = condition_type or template.get("condition_type", ConditionType.PRIOR_TO_DOC)

        condition = Condition(
            id=self._generate_condition_id(),
            condition_type=cond_type,
            category=template["category"],
            priority=template["priority"],
            title=template["title"],
            description=custom_description or template["description"],
            clearing_instructions=custom_instructions or template["clearing_instructions"],
            acceptable_documents=template["acceptable_documents"].copy(),
            due_date=due_date,
            metadata=metadata or {},
        )

        return condition

    def generate_standard_conditions(
        self,
        loan_type: str,
        property_type: str,
        occupancy_type: str,
        income_types: List[str],
        has_gift_funds: bool = False,
        is_purchase: bool = True,
    ) -> List[Condition]:
        """Generate standard conditions based on loan characteristics."""
        conditions = []

        # Income documentation conditions
        if "w2" in income_types or "salary" in income_types:
            conditions.append(self.generate_from_template("income_paystubs"))
            conditions.append(self.generate_from_template("income_w2_2years"))
            conditions.append(self.generate_from_template("income_voe"))
            conditions.append(self.generate_from_template("income_voe_verbal"))

        if "self_employed" in income_types:
            conditions.append(self.generate_from_template("income_tax_returns"))
            conditions.append(self.generate_from_template("income_ytd_profit_loss"))
            conditions.append(self.generate_from_template("income_business_license"))
            conditions.append(self.generate_from_template("income_4506c"))

        if "variable" in income_types or "bonus" in income_types or "overtime" in income_types:
            conditions.append(self.generate_from_template("income_variable_doc"))

        if "rental" in income_types:
            conditions.append(self.generate_from_template("income_rental_schedule_e"))

        if "social_security" in income_types or "retirement" in income_types:
            conditions.append(self.generate_from_template("income_social_security"))

        if "pension" in income_types:
            conditions.append(self.generate_from_template("income_pension"))

        # Asset conditions
        conditions.append(self.generate_from_template("asset_bank_statements"))

        if has_gift_funds:
            conditions.append(self.generate_from_template("asset_gift_letter"))
            conditions.append(self.generate_from_template("asset_gift_transfer"))

        if is_purchase:
            conditions.append(self.generate_from_template("asset_earnest_money"))

        # Property conditions
        conditions.append(self.generate_from_template("property_appraisal"))
        conditions.append(self.generate_from_template("property_flood_cert"))

        if is_purchase:
            conditions.append(self.generate_from_template("property_purchase_contract"))

        if property_type == "condo":
            conditions.append(self.generate_from_template("property_condo_cert"))

        # Title conditions
        conditions.append(self.generate_from_template("title_commitment"))

        # Insurance conditions
        conditions.append(self.generate_from_template("insurance_homeowners"))

        if property_type == "condo":
            conditions.append(self.generate_from_template("insurance_condo_master"))
            conditions.append(self.generate_from_template("insurance_ho6"))

        # Compliance conditions
        conditions.append(self.generate_from_template("compliance_id"))
        conditions.append(self.generate_from_template("compliance_ss_verification"))

        if occupancy_type == "primary":
            conditions.append(self.generate_from_template("compliance_occupancy_cert"))

        # 4506-C results (PTF)
        conditions.append(self.generate_from_template("compliance_4506c_results"))

        # Filter out None values
        return [c for c in conditions if c is not None]

    def generate_income_conditions(
        self,
        income_result: Dict[str, Any],
    ) -> List[Condition]:
        """Generate conditions based on income analysis results."""
        conditions = []

        issues = income_result.get("issues", [])

        for issue in issues:
            # Handle both string and dict formats for issues
            if isinstance(issue, str):
                issue_type = issue.lower()
                issue_description = issue
            else:
                issue_type = str(issue.get("type", "")).lower()
                issue_description = issue.get("description", str(issue))

            if "employment_gap" in issue_type:
                conditions.append(self.generate_from_template(
                    "income_gap_explanation",
                    custom_description=f"Explain employment gap: {issue_description}",
                ))

            if "variable_income" in issue_type or "variable" in issue_type:
                conditions.append(self.generate_from_template("income_variable_doc"))

            if "declining" in issue_type:
                cond = self.generate_from_template(
                    "income_paystubs",
                    custom_description="Provide most recent paystubs showing current income level to address declining income trend.",
                )
                if cond:
                    cond.priority = ConditionPriority.CRITICAL
                    conditions.append(cond)

        return [c for c in conditions if c is not None]

    def generate_asset_conditions(
        self,
        asset_result: Dict[str, Any],
    ) -> List[Condition]:
        """Generate conditions based on asset analysis results."""
        conditions = []

        large_deposits = asset_result.get("large_deposits", [])

        for deposit in large_deposits:
            if not deposit.get("documented", False):
                conditions.append(self.generate_from_template(
                    "asset_large_deposit",
                    custom_description=f"Document large deposit of {deposit.get('amount', 0):,.2f} on {deposit.get('date', 'unknown date')}.",
                    metadata={"deposit_amount": deposit.get("amount"), "deposit_date": deposit.get("date")},
                ))

        insufficient_funds = asset_result.get("insufficient_funds", False)
        if insufficient_funds:
            shortfall = asset_result.get("shortfall_amount", 0)
            cond = Condition(
                id=self._generate_condition_id(),
                condition_type=ConditionType.PRIOR_TO_DOC,
                category=ConditionCategory.ASSETS,
                priority=ConditionPriority.CRITICAL,
                title="Insufficient Funds to Close",
                description=f"Verified assets are insufficient to cover funds to close. Shortfall: ${shortfall:,.2f}",
                clearing_instructions="Provide additional asset documentation or source of funds to cover shortfall. Gift funds, employer assistance, or additional savings acceptable with proper documentation.",
                acceptable_documents=["bank_statement", "gift_letter", "employer_assistance_letter"],
            )
            conditions.append(cond)

        return conditions

    def generate_credit_conditions(
        self,
        credit_result: Dict[str, Any],
    ) -> List[Condition]:
        """Generate conditions based on credit analysis results."""
        conditions = []

        # Recent inquiries
        inquiries = credit_result.get("recent_inquiries", [])
        if len(inquiries) > 2:
            cond = self.generate_from_template(
                "credit_loe_inquiry",
                custom_description=f"Explain {len(inquiries)} credit inquiries in the past 90-120 days.",
                metadata={"inquiry_count": len(inquiries)},
            )
            if cond:
                conditions.append(cond)

        # Late payments
        late_payments = credit_result.get("late_payments", [])
        if late_payments:
            mortgage_lates = [lp for lp in late_payments if lp.get("account_type") == "mortgage"]
            if mortgage_lates:
                cond = self.generate_from_template(
                    "credit_loe_late_payment",
                    custom_description="Explain late payment(s) on mortgage account.",
                )
                if cond:
                    cond.priority = ConditionPriority.HIGH
                    conditions.append(cond)

        # Collections
        collections = credit_result.get("collections", [])
        for collection in collections:
            if collection.get("balance", 0) > 0:
                cond = self.generate_from_template(
                    "credit_loe_collection",
                    custom_description=f"Explain collection account: {collection.get('creditor', 'Unknown')} - ${collection.get('balance', 0):,.2f}",
                    metadata={"collection_amount": collection.get("balance")},
                )
                if cond:
                    conditions.append(cond)

        # Accounts to be paid off
        payoffs = credit_result.get("payoff_required", [])
        for payoff in payoffs:
            cond = self.generate_from_template(
                "credit_payoff_statement",
                custom_description=f"Provide payoff for {payoff.get('creditor', 'account')} - current balance ${payoff.get('balance', 0):,.2f}",
                metadata={"payoff_creditor": payoff.get("creditor"), "payoff_balance": payoff.get("balance")},
            )
            if cond:
                conditions.append(cond)

        # Bankruptcy
        bankruptcy = credit_result.get("bankruptcy")
        if bankruptcy and not bankruptcy.get("discharged_documented"):
            conditions.append(self.generate_from_template("credit_bk_discharge"))

        return [c for c in conditions if c is not None]

    def generate_from_aus_findings(
        self,
        aus_findings: List[Dict[str, Any]],
    ) -> List[Condition]:
        """
        Generate conditions from AUS (DU/LP) findings.
        Maps AUS condition codes to appropriate templates.
        """
        conditions = []

        # AUS condition code mappings
        aus_mapping = {
            "V001": "income_voe",
            "V002": "income_voe_verbal",
            "V003": "income_paystubs",
            "V004": "income_tax_returns",
            "V005": "income_4506c",
            "V006": "income_w2_2years",
            "A001": "asset_bank_statements",
            "A002": "asset_large_deposit",
            "A003": "asset_gift_letter",
            "C001": "credit_loe_inquiry",
            "C002": "credit_loe_late_payment",
            "P001": "property_appraisal",
            "P002": "title_commitment",
            "I001": "insurance_homeowners",
        }

        for finding in aus_findings:
            code = finding.get("code", "")
            template_key = aus_mapping.get(code)

            if template_key:
                cond = self.generate_from_template(
                    template_key,
                    metadata={"aus_code": code, "aus_message": finding.get("message")},
                )
                if cond:
                    cond.aus_reference = code
                    cond.source = "aus"
                    conditions.append(cond)
            else:
                # Create custom condition for unmapped findings
                cond = Condition(
                    id=self._generate_condition_id(),
                    condition_type=ConditionType.PRIOR_TO_DOC,
                    category=ConditionCategory.OTHER,
                    priority=ConditionPriority.MEDIUM,
                    title=f"AUS Condition: {code}",
                    description=finding.get("message", "AUS-generated condition"),
                    clearing_instructions=finding.get("instructions", "Review and satisfy per AUS requirements"),
                    acceptable_documents=finding.get("documents", []),
                    source="aus",
                    aus_reference=code,
                )
                conditions.append(cond)

        return conditions


class ConditionClearing:
    """
    Handles condition clearing logic and validation.
    Determines if provided documentation satisfies condition requirements.
    """

    def __init__(self):
        self.clearing_rules = self._load_clearing_rules()

    def _load_clearing_rules(self) -> Dict[str, Dict]:
        """Load condition clearing rules."""
        return {
            "income_voe": {
                "required_fields": ["employer_name", "hire_date", "position", "salary"],
                "date_within_days": 10,
                "validation_rules": ["employer_match", "income_match"],
            },
            "income_paystubs": {
                "required_fields": ["borrower_name", "employer_name", "pay_period", "ytd_earnings"],
                "min_coverage_days": 30,
                "validation_rules": ["name_match", "employer_match"],
            },
            "asset_bank_statements": {
                "required_fields": ["account_holder", "account_number", "ending_balance"],
                "min_coverage_months": 2,
                "validation_rules": ["name_match", "sufficient_funds"],
            },
            "asset_large_deposit": {
                "required_fields": ["deposit_source", "amount", "documentation"],
                "validation_rules": ["source_verified", "paper_trail_complete"],
            },
            "asset_gift_letter": {
                "required_fields": ["donor_name", "relationship", "amount", "no_repayment_statement", "signature"],
                "validation_rules": ["relationship_eligible", "signed"],
            },
            "property_appraisal": {
                "required_fields": ["property_address", "appraised_value", "condition_rating"],
                "validation_rules": ["value_supports_loan", "condition_acceptable"],
            },
            "insurance_homeowners": {
                "required_fields": ["property_address", "coverage_amount", "effective_date", "mortgagee_clause"],
                "validation_rules": ["coverage_adequate", "mortgagee_correct"],
            },
        }

    def evaluate_clearing(
        self,
        condition: Condition,
        document_data: Dict[str, Any],
        loan_data: Dict[str, Any],
    ) -> ConditionClearingResult:
        """
        Evaluate if a document satisfies a condition.

        Args:
            condition: The condition to clear
            document_data: Data extracted from submitted document
            loan_data: Current loan file data for validation

        Returns:
            ConditionClearingResult indicating success/failure
        """
        template_key = self._get_template_key(condition)
        rules = self.clearing_rules.get(template_key, {})

        issues = []

        # Check required fields
        required_fields = rules.get("required_fields", [])
        for field in required_fields:
            if field not in document_data or not document_data[field]:
                issues.append(f"Missing required field: {field}")

        # Check date requirements
        date_within_days = rules.get("date_within_days")
        if date_within_days:
            doc_date = document_data.get("document_date")
            if doc_date:
                days_old = (datetime.now().date() - doc_date).days
                if days_old > date_within_days:
                    issues.append(f"Document is {days_old} days old (max {date_within_days} days)")

        # Run validation rules
        validation_rules = rules.get("validation_rules", [])
        for rule in validation_rules:
            rule_result = self._run_validation_rule(rule, document_data, loan_data, condition)
            if not rule_result["passed"]:
                issues.append(rule_result["message"])

        if issues:
            return ConditionClearingResult(
                condition_id=condition.id,
                success=False,
                new_status=ConditionStatus.OPEN,
                message=f"Condition not cleared: {len(issues)} issue(s) found",
                remaining_issues=issues,
            )

        return ConditionClearingResult(
            condition_id=condition.id,
            success=True,
            new_status=ConditionStatus.CLEARED,
            message="Condition cleared successfully",
        )

    def _get_template_key(self, condition: Condition) -> str:
        """Extract template key from condition."""
        # Try to match based on title
        title_lower = condition.title.lower().replace(" ", "_").replace("-", "_")
        for key in CONDITION_TEMPLATES:
            if key in title_lower or title_lower in key:
                return key
        return ""

    def _run_validation_rule(
        self,
        rule: str,
        document_data: Dict[str, Any],
        loan_data: Dict[str, Any],
        condition: Condition,
    ) -> Dict[str, Any]:
        """Run a specific validation rule."""

        if rule == "employer_match":
            doc_employer = document_data.get("employer_name", "").lower()
            loan_employer = loan_data.get("employer_name", "").lower()
            if doc_employer and loan_employer and doc_employer not in loan_employer and loan_employer not in doc_employer:
                return {"passed": False, "message": f"Employer name mismatch: {doc_employer} vs {loan_employer}"}

        elif rule == "name_match":
            doc_name = document_data.get("borrower_name", "").lower()
            loan_name = loan_data.get("borrower_name", "").lower()
            if doc_name and loan_name:
                doc_parts = set(doc_name.split())
                loan_parts = set(loan_name.split())
                if not doc_parts.intersection(loan_parts):
                    return {"passed": False, "message": f"Borrower name mismatch: {doc_name} vs {loan_name}"}

        elif rule == "income_match":
            doc_income = document_data.get("monthly_income", 0)
            loan_income = loan_data.get("stated_monthly_income", 0)
            if doc_income and loan_income:
                variance = abs(doc_income - loan_income) / loan_income if loan_income > 0 else 0
                if variance > 0.10:  # 10% tolerance
                    return {"passed": False, "message": f"Income variance {variance:.1%} exceeds 10% tolerance"}

        elif rule == "sufficient_funds":
            available = document_data.get("available_balance", 0)
            required = loan_data.get("funds_to_close", 0)
            if available < required:
                shortfall = required - available
                return {"passed": False, "message": f"Insufficient funds: ${shortfall:,.2f} shortfall"}

        elif rule == "value_supports_loan":
            appraised_value = document_data.get("appraised_value", 0)
            loan_amount = loan_data.get("loan_amount", 0)
            max_ltv = loan_data.get("max_ltv", 0.80)
            if appraised_value > 0:
                max_loan = appraised_value * max_ltv
                if loan_amount > max_loan:
                    return {"passed": False, "message": f"Appraised value ${appraised_value:,.0f} doesn't support loan amount at {max_ltv:.0%} LTV"}

        elif rule == "coverage_adequate":
            coverage = document_data.get("coverage_amount", 0)
            required = loan_data.get("dwelling_coverage_required", 0)
            if coverage < required:
                return {"passed": False, "message": f"Insurance coverage ${coverage:,.0f} below required ${required:,.0f}"}

        elif rule == "relationship_eligible":
            relationship = document_data.get("relationship", "").lower()
            eligible_relationships = ["parent", "grandparent", "spouse", "child", "sibling", "aunt", "uncle"]
            if relationship and relationship not in eligible_relationships:
                return {"passed": False, "message": f"Gift donor relationship '{relationship}' may not be eligible"}

        return {"passed": True, "message": ""}

    def bulk_clear_conditions(
        self,
        conditions: List[Condition],
        documents: List[Dict[str, Any]],
        loan_data: Dict[str, Any],
    ) -> List[ConditionClearingResult]:
        """
        Attempt to clear multiple conditions with available documents.
        Matches documents to conditions and evaluates clearing.
        """
        results = []

        # Map documents by type
        docs_by_type = {}
        for doc in documents:
            doc_type = doc.get("document_type", "unknown")
            if doc_type not in docs_by_type:
                docs_by_type[doc_type] = []
            docs_by_type[doc_type].append(doc)

        for condition in conditions:
            if condition.status != ConditionStatus.OPEN:
                continue

            # Find matching documents
            matching_docs = []
            for acceptable_type in condition.acceptable_documents:
                if acceptable_type in docs_by_type:
                    matching_docs.extend(docs_by_type[acceptable_type])

            if not matching_docs:
                results.append(ConditionClearingResult(
                    condition_id=condition.id,
                    success=False,
                    new_status=ConditionStatus.OPEN,
                    message="No matching documents found",
                    remaining_issues=["Required document not provided"],
                ))
                continue

            # Try to clear with best matching document
            best_result = None
            for doc in matching_docs:
                result = self.evaluate_clearing(condition, doc, loan_data)
                if result.success:
                    best_result = result
                    break
                elif best_result is None or len(result.remaining_issues) < len(best_result.remaining_issues):
                    best_result = result

            if best_result:
                results.append(best_result)

        return results


def generate_loan_conditions(
    loan_data: Dict[str, Any],
    income_result: Optional[Dict[str, Any]] = None,
    asset_result: Optional[Dict[str, Any]] = None,
    credit_result: Optional[Dict[str, Any]] = None,
    aus_findings: Optional[List[Dict[str, Any]]] = None,
) -> List[Condition]:
    """
    Main function to generate all conditions for a loan.
    Combines standard conditions with issue-specific conditions.
    """
    generator = ConditionGenerator()
    all_conditions = []

    # Standard conditions based on loan characteristics
    standard = generator.generate_standard_conditions(
        loan_type=loan_data.get("loan_type", "conventional"),
        property_type=loan_data.get("property_type", "single_family"),
        occupancy_type=loan_data.get("occupancy_type", "primary"),
        income_types=loan_data.get("income_types", ["w2"]),
        has_gift_funds=loan_data.get("has_gift_funds", False),
        is_purchase=loan_data.get("is_purchase", True),
    )
    all_conditions.extend(standard)

    # Income-specific conditions
    if income_result:
        income_conditions = generator.generate_income_conditions(income_result)
        all_conditions.extend(income_conditions)

    # Asset-specific conditions
    if asset_result:
        asset_conditions = generator.generate_asset_conditions(asset_result)
        all_conditions.extend(asset_conditions)

    # Credit-specific conditions
    if credit_result:
        credit_conditions = generator.generate_credit_conditions(credit_result)
        all_conditions.extend(credit_conditions)

    # AUS-generated conditions
    if aus_findings:
        aus_conditions = generator.generate_from_aus_findings(aus_findings)
        all_conditions.extend(aus_conditions)

    # Deduplicate conditions by title
    seen_titles = set()
    unique_conditions = []
    for cond in all_conditions:
        if cond.title not in seen_titles:
            seen_titles.add(cond.title)
            unique_conditions.append(cond)

    # Sort by priority and category
    priority_order = {
        ConditionPriority.CRITICAL: 0,
        ConditionPriority.HIGH: 1,
        ConditionPriority.MEDIUM: 2,
        ConditionPriority.LOW: 3,
    }
    unique_conditions.sort(key=lambda c: (priority_order.get(c.priority, 99), c.category.value))

    return unique_conditions
