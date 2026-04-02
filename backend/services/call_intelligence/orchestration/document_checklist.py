"""
Document Checklist Service

Generates required document lists based on extracted call data,
loan type, and regulatory requirements.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class DocumentCategory(str, Enum):
    """Document categories."""
    INCOME = "income"
    ASSETS = "assets"
    IDENTITY = "identity"
    PROPERTY = "property"
    CREDIT = "credit"
    COMPLIANCE = "compliance"


class DocumentPriority(str, Enum):
    """Document priority levels."""
    REQUIRED = "required"
    CONDITIONAL = "conditional"
    OPTIONAL = "optional"


class LoanPurpose(str, Enum):
    """Loan purpose types."""
    PURCHASE = "purchase"
    REFINANCE = "refinance"
    CASH_OUT = "cash_out"


@dataclass
class DocumentRequirement:
    """A single document requirement."""
    document_type: str
    category: DocumentCategory
    priority: DocumentPriority
    description: str
    reason: str = ""
    alternatives: List[str] = field(default_factory=list)
    expiration_days: Optional[int] = None  # How long document is valid
    special_instructions: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "category": self.category.value,
            "priority": self.priority.value,
            "description": self.description,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "expiration_days": self.expiration_days,
            "special_instructions": self.special_instructions,
        }


@dataclass
class DocumentChecklist:
    """Complete document checklist for a loan."""
    loan_id: Optional[int]
    call_id: str
    loan_type: str
    loan_purpose: str

    # Documents by category
    required_documents: List[DocumentRequirement] = field(default_factory=list)
    conditional_documents: List[DocumentRequirement] = field(default_factory=list)
    optional_documents: List[DocumentRequirement] = field(default_factory=list)

    # Metadata
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: List[str] = field(default_factory=list)

    @property
    def total_required(self) -> int:
        return len(self.required_documents)

    @property
    def total_conditional(self) -> int:
        return len(self.conditional_documents)

    @property
    def all_documents(self) -> List[DocumentRequirement]:
        return self.required_documents + self.conditional_documents + self.optional_documents

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "call_id": self.call_id,
            "loan_type": self.loan_type,
            "loan_purpose": self.loan_purpose,
            "required_documents": [d.to_dict() for d in self.required_documents],
            "conditional_documents": [d.to_dict() for d in self.conditional_documents],
            "optional_documents": [d.to_dict() for d in self.optional_documents],
            "total_required": self.total_required,
            "total_conditional": self.total_conditional,
            "generated_at": self.generated_at.isoformat(),
            "notes": self.notes,
        }


# =============================================================================
# Document Definitions
# =============================================================================

# Base documents required for all loans
BASE_INCOME_DOCS = [
    DocumentRequirement(
        document_type="paystubs",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.REQUIRED,
        description="Most recent 30 days of pay stubs",
        reason="Verify current employment and income",
        expiration_days=30,
    ),
    DocumentRequirement(
        document_type="w2",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.REQUIRED,
        description="W-2 forms for the past 2 years",
        reason="Verify employment history and income consistency",
    ),
    DocumentRequirement(
        document_type="tax_returns",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.REQUIRED,
        description="Federal tax returns for the past 2 years (all pages)",
        reason="Verify reported income",
        special_instructions="Include all schedules and attachments",
    ),
]

BASE_ASSET_DOCS = [
    DocumentRequirement(
        document_type="bank_statements",
        category=DocumentCategory.ASSETS,
        priority=DocumentPriority.REQUIRED,
        description="Bank statements for the past 2 months (all pages)",
        reason="Verify funds for down payment and closing costs",
        expiration_days=60,
        special_instructions="All pages required, even blank ones",
    ),
]

BASE_IDENTITY_DOCS = [
    DocumentRequirement(
        document_type="government_id",
        category=DocumentCategory.IDENTITY,
        priority=DocumentPriority.REQUIRED,
        description="Valid government-issued photo ID",
        reason="Identity verification",
        alternatives=["driver's license", "passport", "state ID"],
    ),
    DocumentRequirement(
        document_type="ssn_verification",
        category=DocumentCategory.IDENTITY,
        priority=DocumentPriority.REQUIRED,
        description="Social Security card or SSA-1099",
        reason="Social Security number verification",
    ),
]

# Self-employment documents
SELF_EMPLOYED_DOCS = [
    DocumentRequirement(
        document_type="business_tax_returns",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.REQUIRED,
        description="Business tax returns for the past 2 years",
        reason="Verify business income for self-employed borrowers",
    ),
    DocumentRequirement(
        document_type="profit_loss_statement",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.REQUIRED,
        description="Year-to-date profit and loss statement",
        reason="Verify current business performance",
        expiration_days=30,
    ),
    DocumentRequirement(
        document_type="business_license",
        category=DocumentCategory.INCOME,
        priority=DocumentPriority.CONDITIONAL,
        description="Current business license",
        reason="Verify business legitimacy",
    ),
]

# Purchase-specific documents
PURCHASE_DOCS = [
    DocumentRequirement(
        document_type="purchase_contract",
        category=DocumentCategory.PROPERTY,
        priority=DocumentPriority.REQUIRED,
        description="Signed purchase agreement/contract",
        reason="Verify property details and purchase price",
    ),
    DocumentRequirement(
        document_type="earnest_money",
        category=DocumentCategory.PROPERTY,
        priority=DocumentPriority.REQUIRED,
        description="Earnest money deposit receipt",
        reason="Verify deposit amount and source",
    ),
]

# Refinance-specific documents
REFINANCE_DOCS = [
    DocumentRequirement(
        document_type="current_mortgage_statement",
        category=DocumentCategory.PROPERTY,
        priority=DocumentPriority.REQUIRED,
        description="Current mortgage statement",
        reason="Verify current loan balance and payment history",
        expiration_days=30,
    ),
    DocumentRequirement(
        document_type="homeowners_insurance",
        category=DocumentCategory.PROPERTY,
        priority=DocumentPriority.REQUIRED,
        description="Current homeowners insurance policy",
        reason="Verify adequate coverage",
    ),
]

# Gift fund documents
GIFT_FUND_DOCS = [
    DocumentRequirement(
        document_type="gift_letter",
        category=DocumentCategory.ASSETS,
        priority=DocumentPriority.REQUIRED,
        description="Signed gift letter from donor",
        reason="Verify gift funds don't need to be repaid",
        special_instructions="Must state gift amount, donor relationship, and no repayment required",
    ),
    DocumentRequirement(
        document_type="gift_donor_bank_statement",
        category=DocumentCategory.ASSETS,
        priority=DocumentPriority.REQUIRED,
        description="Donor's bank statement showing ability to give gift",
        reason="Verify donor has funds available",
        expiration_days=60,
    ),
]

# FHA-specific documents
FHA_DOCS = [
    DocumentRequirement(
        document_type="fha_case_number",
        category=DocumentCategory.COMPLIANCE,
        priority=DocumentPriority.REQUIRED,
        description="FHA case number assignment",
        reason="Required for FHA loan processing",
    ),
]

# VA-specific documents
VA_DOCS = [
    DocumentRequirement(
        document_type="dd214",
        category=DocumentCategory.COMPLIANCE,
        priority=DocumentPriority.REQUIRED,
        description="DD-214 Certificate of Release or Discharge",
        reason="Verify veteran status and eligibility",
        alternatives=["Statement of Service for active duty"],
    ),
    DocumentRequirement(
        document_type="coe",
        category=DocumentCategory.COMPLIANCE,
        priority=DocumentPriority.REQUIRED,
        description="Certificate of Eligibility (COE)",
        reason="Verify VA loan entitlement",
        special_instructions="Can be obtained online through VA portal",
    ),
]

# Credit-related documents
CREDIT_DOCS = [
    DocumentRequirement(
        document_type="credit_explanation",
        category=DocumentCategory.CREDIT,
        priority=DocumentPriority.CONDITIONAL,
        description="Letter of explanation for credit inquiries",
        reason="Explain recent credit inquiries",
    ),
    DocumentRequirement(
        document_type="bankruptcy_discharge",
        category=DocumentCategory.CREDIT,
        priority=DocumentPriority.CONDITIONAL,
        description="Bankruptcy discharge papers",
        reason="Verify bankruptcy was discharged and waiting period met",
    ),
]


class DocumentChecklistService:
    """
    Generate document checklists based on loan characteristics.

    Usage:
        service = DocumentChecklistService()
        checklist = service.generate_checklist(extracted_data, call_id, loan_type)

        for doc in checklist.required_documents:
            print(f"Required: {doc.document_type} - {doc.description}")
    """

    def generate_checklist(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        loan_type: str = "conventional",
        loan_purpose: str = "purchase",
        loan_id: Optional[int] = None,
    ) -> DocumentChecklist:
        """
        Generate document checklist based on extracted call data.

        Args:
            extracted_data: Data extracted from the call
            call_id: Unique call identifier
            loan_type: Type of loan (conventional, FHA, VA, etc.)
            loan_purpose: Purpose (purchase, refinance, cash_out)
            loan_id: Associated loan ID if exists

        Returns:
            DocumentChecklist with required documents
        """
        checklist = DocumentChecklist(
            loan_id=loan_id,
            call_id=call_id,
            loan_type=loan_type.lower(),
            loan_purpose=loan_purpose.lower(),
        )

        # Start with base documents
        required: List[DocumentRequirement] = []
        conditional: List[DocumentRequirement] = []
        optional: List[DocumentRequirement] = []

        # Add base income documents
        required.extend(BASE_INCOME_DOCS)

        # Add base asset documents
        required.extend(BASE_ASSET_DOCS)

        # Add base identity documents
        required.extend(BASE_IDENTITY_DOCS)

        # Add purpose-specific documents
        if loan_purpose.lower() in ["purchase", "buy"]:
            required.extend(PURCHASE_DOCS)
        elif loan_purpose.lower() in ["refinance", "refi", "cash_out"]:
            required.extend(REFINANCE_DOCS)

        # Check for self-employment
        employment = extracted_data.get("employment", {})
        if self._is_self_employed(employment):
            required.extend(SELF_EMPLOYED_DOCS)
            checklist.notes.append("Self-employment documentation required")

        # Check for gift funds
        financial = extracted_data.get("financial", {})
        if self._has_gift_funds(financial):
            required.extend(GIFT_FUND_DOCS)
            checklist.notes.append("Gift fund documentation required")

        # Add loan type specific documents
        if loan_type.lower() == "fha":
            required.extend(FHA_DOCS)
        elif loan_type.lower() == "va":
            required.extend(VA_DOCS)

        # Check for credit issues
        compliance = extracted_data.get("compliance", {})
        if self._has_bankruptcy(compliance):
            conditional.append(
                DocumentRequirement(
                    document_type="bankruptcy_discharge",
                    category=DocumentCategory.CREDIT,
                    priority=DocumentPriority.CONDITIONAL,
                    description="Bankruptcy discharge papers",
                    reason="Borrower indicated bankruptcy history",
                )
            )
            checklist.notes.append("Bankruptcy documentation needed - verify waiting period")

        if self._has_foreclosure(compliance):
            conditional.append(
                DocumentRequirement(
                    document_type="foreclosure_documentation",
                    category=DocumentCategory.CREDIT,
                    priority=DocumentPriority.CONDITIONAL,
                    description="Foreclosure documentation and timeline",
                    reason="Borrower indicated foreclosure history",
                )
            )
            checklist.notes.append("Foreclosure documentation needed - verify waiting period")

        # Check for alimony/child support
        if self._has_alimony(compliance):
            conditional.append(
                DocumentRequirement(
                    document_type="divorce_decree",
                    category=DocumentCategory.COMPLIANCE,
                    priority=DocumentPriority.CONDITIONAL,
                    description="Divorce decree or separation agreement",
                    reason="Verify alimony/child support obligations",
                )
            )

        # Check for rental income
        if self._has_rental_income(financial):
            conditional.append(
                DocumentRequirement(
                    document_type="rental_agreements",
                    category=DocumentCategory.INCOME,
                    priority=DocumentPriority.CONDITIONAL,
                    description="Signed lease agreements for rental properties",
                    reason="Verify rental income",
                )
            )

        # Add investment account documentation if mentioned
        if self._has_investment_accounts(financial):
            conditional.append(
                DocumentRequirement(
                    document_type="investment_statements",
                    category=DocumentCategory.ASSETS,
                    priority=DocumentPriority.CONDITIONAL,
                    description="Investment account statements (past 2 months)",
                    reason="Verify investment assets",
                    expiration_days=60,
                )
            )

        # Deduplicate documents
        required = self._deduplicate_documents(required)
        conditional = self._deduplicate_documents(conditional)

        checklist.required_documents = required
        checklist.conditional_documents = conditional
        checklist.optional_documents = optional

        logger.info(
            f"Generated document checklist for call {call_id}: "
            f"{len(required)} required, {len(conditional)} conditional"
        )

        return checklist

    def _is_self_employed(self, employment: Dict) -> bool:
        """Check if borrower is self-employed."""
        is_self = self._get_value(employment, "is_self_employed")
        emp_type = self._get_value(employment, "employment_type")

        return is_self is True or str(emp_type).lower() == "self-employed"

    def _has_gift_funds(self, financial: Dict) -> bool:
        """Check if gift funds are mentioned."""
        gift_funds = self._get_value(financial, "gift_funds")
        return gift_funds is not None and float(gift_funds or 0) > 0

    def _has_bankruptcy(self, compliance: Dict) -> bool:
        """Check if bankruptcy is mentioned."""
        return self._get_value(compliance, "has_bankruptcy") is True

    def _has_foreclosure(self, compliance: Dict) -> bool:
        """Check if foreclosure is mentioned."""
        return self._get_value(compliance, "has_foreclosure") is True

    def _has_alimony(self, compliance: Dict) -> bool:
        """Check if alimony/child support is mentioned."""
        has_alimony = self._get_value(compliance, "has_alimony")
        alimony_amount = self._get_value(compliance, "alimony_amount")
        return has_alimony is True or (alimony_amount is not None and float(alimony_amount or 0) > 0)

    def _has_rental_income(self, financial: Dict) -> bool:
        """Check if rental income is mentioned."""
        rental = self._get_value(financial, "rental_income")
        return rental is not None and float(rental or 0) > 0

    def _has_investment_accounts(self, financial: Dict) -> bool:
        """Check if investment accounts are mentioned."""
        retirement = self._get_value(financial, "retirement_balance")
        investment = self._get_value(financial, "investment_balance")
        return (
            (retirement is not None and float(retirement or 0) > 0) or
            (investment is not None and float(investment or 0) > 0)
        )

    def _get_value(self, data: Dict, field: str) -> Any:
        """Get value from extraction dict."""
        if not data:
            return None

        value = data.get(field)
        if isinstance(value, dict):
            return value.get("value")
        return value

    def _deduplicate_documents(
        self,
        documents: List[DocumentRequirement],
    ) -> List[DocumentRequirement]:
        """Remove duplicate document requirements."""
        seen: Set[str] = set()
        unique: List[DocumentRequirement] = []

        for doc in documents:
            if doc.document_type not in seen:
                seen.add(doc.document_type)
                unique.append(doc)

        return unique

    def get_document_by_type(
        self,
        checklist: DocumentChecklist,
        document_type: str,
    ) -> Optional[DocumentRequirement]:
        """Find a specific document in the checklist."""
        for doc in checklist.all_documents:
            if doc.document_type == document_type:
                return doc
        return None

    def get_expiring_soon(
        self,
        checklist: DocumentChecklist,
        days: int = 14,
    ) -> List[DocumentRequirement]:
        """Get documents that expire soon."""
        expiring = []
        for doc in checklist.all_documents:
            if doc.expiration_days and doc.expiration_days <= days:
                expiring.append(doc)
        return expiring


# =============================================================================
# Factory
# =============================================================================

def create_document_checklist_service() -> DocumentChecklistService:
    """Create document checklist service instance."""
    return DocumentChecklistService()
