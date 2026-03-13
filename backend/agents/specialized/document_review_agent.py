"""
Document Review Agent

AI agent specialized in deep document review and validation for mortgage lending.
While the Document Intelligence Agent handles broad document lifecycle (classification,
needs lists, income calculation, follow-ups), this agent focuses specifically on the
review pipeline -- quality assessment, fraud detection, cross-validation, and
underwriting condition generation.

Capabilities:
- Assess document image/scan quality (resolution, clarity, completeness)
- Verify document type matches its classified label
- Check document freshness against acceptable date ranges
- Match borrower names on documents to loan application data
- Verify all required pages are present
- Detect fraud indicators (tampering, alteration, inconsistency)
- Cross-validate data across multiple documents for consistency
- Validate employer info across paystubs, W2s, and VOE
- Validate bank account numbers across multiple statements
- Generate risk scores and review recommendations
- Create underwriting conditions from review findings
- Prioritize document review queues
- Bulk review all documents for a loan
- Generate comprehensive review summaries for underwriters

15 Tools:
1.  review_document_quality - Assess image/scan quality
2.  verify_document_type - Confirm document matches classified type
3.  check_document_freshness - Verify document within acceptable date range
4.  match_borrower_name - Compare document name to application borrower name
5.  check_document_completeness - Verify all required pages are present
6.  detect_fraud_indicators - Check for tampering, alteration, inconsistency
7.  cross_validate_documents - Compare data across multiple documents
8.  validate_employer_info - Cross-check employer across paystubs, W2s, VOE
9.  validate_account_numbers - Verify bank account numbers match across statements
10. assess_overall_document_risk - Generate risk score for a document
11. recommend_review_action - Recommend approve/reject/manual review
12. generate_condition_from_review - Create underwriting condition from finding
13. get_review_queue_priority - Prioritize documents in review queue
14. bulk_review_loan_documents - Review all documents for a loan at once
15. create_review_summary - Generate comprehensive review summary for underwriter
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry,
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class ReviewDocumentQualityInput(BaseModel):
    """Input schema for review_document_quality tool"""
    document_id: int = Field(..., description="SmartDocument ID to assess quality")


class VerifyDocumentTypeInput(BaseModel):
    """Input schema for verify_document_type tool"""
    document_id: int = Field(..., description="SmartDocument ID to verify type")


class CheckDocumentFreshnessInput(BaseModel):
    """Input schema for check_document_freshness tool"""
    document_id: int = Field(..., description="SmartDocument ID to check freshness")


class MatchBorrowerNameInput(BaseModel):
    """Input schema for match_borrower_name tool"""
    document_id: int = Field(..., description="SmartDocument ID to match name")
    loan_id: int = Field(..., description="Loan ID to get borrower name from application")


class CheckDocumentCompletenessInput(BaseModel):
    """Input schema for check_document_completeness tool"""
    document_id: int = Field(..., description="SmartDocument ID to check completeness")


class DetectFraudIndicatorsInput(BaseModel):
    """Input schema for detect_fraud_indicators tool"""
    document_id: int = Field(..., description="SmartDocument ID to check for fraud")


class CrossValidateDocumentsInput(BaseModel):
    """Input schema for cross_validate_documents tool"""
    loan_id: int = Field(..., description="Loan ID to cross-validate all documents")
    field_type: Optional[str] = Field(
        None,
        description="Specific field to validate: name, income, employer, address, or all (default)",
    )


class ValidateEmployerInfoInput(BaseModel):
    """Input schema for validate_employer_info tool"""
    loan_id: int = Field(..., description="Loan ID to validate employer info across docs")
    borrower_id: Optional[int] = Field(None, description="Specific borrower ID (optional)")


class ValidateAccountNumbersInput(BaseModel):
    """Input schema for validate_account_numbers tool"""
    loan_id: int = Field(..., description="Loan ID to validate account numbers")


class AssessOverallDocumentRiskInput(BaseModel):
    """Input schema for assess_overall_document_risk tool"""
    document_id: int = Field(..., description="SmartDocument ID to assess risk")


class RecommendReviewActionInput(BaseModel):
    """Input schema for recommend_review_action tool"""
    document_id: int = Field(..., description="SmartDocument ID to recommend action for")


class GenerateConditionFromReviewInput(BaseModel):
    """Input schema for generate_condition_from_review tool"""
    loan_id: int = Field(..., description="Loan ID to create condition for")
    document_id: int = Field(..., description="SmartDocument ID that triggered the condition")
    finding_type: str = Field(
        ...,
        description="Type of finding: quality_issue, type_mismatch, expired, name_mismatch, "
                     "incomplete, fraud_indicator, data_inconsistency",
    )
    description: str = Field(..., description="Description of the finding requiring a condition")
    severity: str = Field(
        "MEDIUM",
        description="Severity: CRITICAL, HIGH, MEDIUM, LOW",
    )


class GetReviewQueuePriorityInput(BaseModel):
    """Input schema for get_review_queue_priority tool"""
    loan_id: Optional[int] = Field(None, description="Optional loan ID to filter queue")
    limit: int = Field(50, description="Maximum number of documents to return")


class BulkReviewLoanDocumentsInput(BaseModel):
    """Input schema for bulk_review_loan_documents tool"""
    loan_id: int = Field(..., description="Loan ID whose documents should be reviewed")


class CreateReviewSummaryInput(BaseModel):
    """Input schema for create_review_summary tool"""
    loan_id: int = Field(..., description="Loan ID to generate review summary for")


# ============================================================================
# CONSTANTS
# ============================================================================

# Freshness requirements in days by document type
FRESHNESS_REQUIREMENTS = {
    "PAYSTUB": 30,
    "BANK_STATEMENT": 60,
    "INVESTMENT_STATEMENT": 90,
    "PROFIT_LOSS": 90,
    "BALANCE_SHEET": 90,
    "TAX_RETURN": 365,
    "W2": 365,
    "1099": 365,
    "DRIVERS_LICENSE": 0,  # Check expiration date, not age
    "PURCHASE_CONTRACT": 180,
    "APPRAISAL": 120,
    "TITLE_REPORT": 90,
    "HOMEOWNERS_INSURANCE": 365,
    "GIFT_LETTER": 90,
}

# Required fields per document type for completeness checks
REQUIRED_FIELDS = {
    "PAYSTUB": ["employer name", "pay period", "gross pay", "year to date"],
    "W2": ["employer ein", "wages", "federal tax withheld"],
    "BANK_STATEMENT": ["account number", "beginning balance", "ending balance", "statement period"],
    "TAX_RETURN": ["filing status", "adjusted gross income", "signature"],
    "DRIVERS_LICENSE": ["name", "date of birth", "license number", "expiration"],
    "PROFIT_LOSS": ["business name", "period", "revenue", "expenses", "net"],
    "INVESTMENT_STATEMENT": ["account holder", "account number", "account value", "statement date"],
    "PURCHASE_CONTRACT": ["buyer", "seller", "purchase price", "property address"],
    "APPRAISAL": ["appraised value", "property address", "comparable sales"],
    "GIFT_LETTER": ["donor name", "gift amount", "no repayment statement"],
}

# Minimum file sizes by MIME type (bytes) - smaller files are likely blank/corrupt
MIN_FILE_SIZES = {
    "application/pdf": 5_000,
    "image/png": 10_000,
    "image/jpeg": 5_000,
    "image/jpg": 5_000,
    "image/tiff": 10_000,
}

# Risk score weights
RISK_WEIGHTS = {
    "quality_low": 15,
    "type_mismatch": 20,
    "expired": 15,
    "name_mismatch": 25,
    "incomplete": 10,
    "fraud_indicator": 30,
    "screenshot_detected": 25,
}


# ============================================================================
# DOCUMENT REVIEW AGENT
# ============================================================================

@AgentRegistry.register
class DocumentReviewAgent(SpecializedAgent):
    """
    Document Review AI Agent for deep document validation in mortgage lending.

    I am specialized in the review pipeline for mortgage documents. I can:

    1. QUALITY ASSESSMENT: Evaluate image/scan quality including resolution,
       readability, and file integrity for uploaded documents.

    2. TYPE VERIFICATION: Confirm that a document's actual content matches
       its classified document type (e.g., a file labeled "W2" really is a W2).

    3. FRESHNESS VALIDATION: Check that documents fall within acceptable
       date ranges per underwriting guidelines (e.g., paystubs within 30 days).

    4. NAME MATCHING: Compare names found on documents against the loan
       application borrower/co-borrower names, handling common variations.

    5. COMPLETENESS CHECKS: Verify all required pages and fields are present
       per document type (e.g., all pages of a tax return, full bank statement).

    6. FRAUD DETECTION: Detect tampering indicators, altered text, metadata
       anomalies, suspicious creation tools, and inconsistent data patterns.

    7. CROSS-VALIDATION: Compare data across all documents for a loan to find
       inconsistencies in names, income, employer, and addresses.

    8. EMPLOYER VALIDATION: Cross-check employer information across paystubs,
       W2s, and verification of employment documents.

    9. ACCOUNT VALIDATION: Verify bank account numbers remain consistent
       across multiple statement periods.

    10. RISK SCORING: Generate an aggregate risk score for individual documents
        based on all review checks combined.

    11. ACTION RECOMMENDATIONS: Recommend approve, reject, or manual review
        based on comprehensive analysis of all review factors.

    12. CONDITION GENERATION: Create underwriting conditions from review
        findings that require borrower action or additional documentation.

    13. QUEUE PRIORITIZATION: Prioritize documents in the review queue based
        on loan stage, document importance, and risk indicators.

    14. BULK REVIEW: Review all documents for a loan in a single operation,
        producing a consolidated result set.

    15. SUMMARY GENERATION: Create comprehensive review summaries for
        underwriters with all findings, risk scores, and recommendations.
    """

    @property
    def name(self) -> str:
        return "DocumentReviewAgent"

    @property
    def description(self) -> str:
        return (
            "AI-powered document review agent for deep validation of mortgage documents "
            "including quality assessment, type verification, freshness checks, name matching, "
            "fraud detection, cross-validation, risk scoring, and underwriting condition generation"
        )

    def _register_tools(self):
        """Register all document review tools"""

        # Tool 1: Review Document Quality
        self.register_tool(AgentTool(
            name="review_document_quality",
            description="Assess the quality of an uploaded document including image/scan "
                       "resolution, readability, file size validation, and corruption checks. "
                       "Returns quality score (0-100) and specific quality issues found.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._review_document_quality,
            input_schema=ReviewDocumentQualityInput,
        ))

        # Tool 2: Verify Document Type
        self.register_tool(AgentTool(
            name="verify_document_type",
            description="Verify that a document's actual content matches its classified type. "
                       "Compares detected keywords and structural patterns against expected "
                       "patterns for the declared document type.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._verify_document_type,
            input_schema=VerifyDocumentTypeInput,
        ))

        # Tool 3: Check Document Freshness
        self.register_tool(AgentTool(
            name="check_document_freshness",
            description="Check whether a document is within the acceptable date range for "
                       "its type. Paystubs must be within 30 days, bank statements 60 days, "
                       "tax returns within the current/prior year, etc.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_document_freshness,
            input_schema=CheckDocumentFreshnessInput,
        ))

        # Tool 4: Match Borrower Name
        self.register_tool(AgentTool(
            name="match_borrower_name",
            description="Compare the name found on a document against the borrower and "
                       "co-borrower names on the loan application. Handles common name "
                       "variations (Bill/William, Bob/Robert, etc.).",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._match_borrower_name,
            input_schema=MatchBorrowerNameInput,
        ))

        # Tool 5: Check Document Completeness
        self.register_tool(AgentTool(
            name="check_document_completeness",
            description="Verify all required pages and key fields are present in a document "
                       "based on its type. For example, verifies paystubs have employer name, "
                       "pay period, gross pay, and YTD; tax returns have filing status and AGI.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._check_document_completeness,
            input_schema=CheckDocumentCompletenessInput,
        ))

        # Tool 6: Detect Fraud Indicators
        self.register_tool(AgentTool(
            name="detect_fraud_indicators",
            description="Check a document for fraud indicators including altered text, "
                       "suspicious metadata (creation tool), font inconsistencies, "
                       "round number patterns, and temporal anomalies.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._detect_fraud_indicators,
            input_schema=DetectFraudIndicatorsInput,
        ))

        # Tool 7: Cross Validate Documents
        self.register_tool(AgentTool(
            name="cross_validate_documents",
            description="Compare extracted data across all documents for a loan to find "
                       "inconsistencies in names, addresses, income amounts, employer info, "
                       "and account numbers. Can focus on a specific field type or check all.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._cross_validate_documents,
            input_schema=CrossValidateDocumentsInput,
        ))

        # Tool 8: Validate Employer Info
        self.register_tool(AgentTool(
            name="validate_employer_info",
            description="Cross-check employer information across paystubs, W2s, and "
                       "verification of employment (VOE) documents. Detects employer name "
                       "mismatches, EIN inconsistencies, and employment gap issues.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._validate_employer_info,
            input_schema=ValidateEmployerInfoInput,
        ))

        # Tool 9: Validate Account Numbers
        self.register_tool(AgentTool(
            name="validate_account_numbers",
            description="Verify that bank account numbers are consistent across multiple "
                       "statement periods for the same account. Detects account number "
                       "changes that may indicate document fabrication.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._validate_account_numbers,
            input_schema=ValidateAccountNumbersInput,
        ))

        # Tool 10: Assess Overall Document Risk
        self.register_tool(AgentTool(
            name="assess_overall_document_risk",
            description="Generate a comprehensive risk score (0-100) for a document by "
                       "combining quality, type verification, freshness, name match, "
                       "completeness, and fraud indicator checks into a single assessment.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_overall_document_risk,
            input_schema=AssessOverallDocumentRiskInput,
        ))

        # Tool 11: Recommend Review Action
        self.register_tool(AgentTool(
            name="recommend_review_action",
            description="Recommend an action for a document: APPROVE (auto-approve), "
                       "REJECT (with reason and fix instructions), or MANUAL_REVIEW "
                       "(requires human underwriter review). Based on comprehensive analysis.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._recommend_review_action,
            input_schema=RecommendReviewActionInput,
        ))

        # Tool 12: Generate Condition from Review
        self.register_tool(AgentTool(
            name="generate_condition_from_review",
            description="Create an underwriting condition record from a document review "
                       "finding. Conditions are tracked and must be cleared before the loan "
                       "can proceed. Includes condition type, description, and deadline.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._generate_condition_from_review,
            input_schema=GenerateConditionFromReviewInput,
        ))

        # Tool 13: Get Review Queue Priority
        self.register_tool(AgentTool(
            name="get_review_queue_priority",
            description="Get a prioritized queue of documents awaiting review, ranked by "
                       "loan stage urgency, document importance, time waiting, and "
                       "preliminary risk indicators.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_review_queue_priority,
            input_schema=GetReviewQueuePriorityInput,
        ))

        # Tool 14: Bulk Review Loan Documents
        self.register_tool(AgentTool(
            name="bulk_review_loan_documents",
            description="Run the full review pipeline on all unreviewed documents for a "
                       "loan. Returns per-document results with quality scores, risk "
                       "assessments, and recommendations. Identifies cross-document issues.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._bulk_review_loan_documents,
            input_schema=BulkReviewLoanDocumentsInput,
        ))

        # Tool 15: Create Review Summary
        self.register_tool(AgentTool(
            name="create_review_summary",
            description="Generate a comprehensive document review summary for an "
                       "underwriter. Includes per-document findings, cross-validation "
                       "results, risk scores, outstanding conditions, and a clear "
                       "recommendation for the overall document package.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._create_review_summary,
            input_schema=CreateReviewSummaryInput,
        ))

    # ========================================================================
    # TENANT ISOLATION HELPERS
    # ========================================================================

    def _verify_loan_org(self, db, loan_id: int) -> None:
        """Verify a loan belongs to this agent's organization.

        Raises ValueError if the loan does not exist for this org.
        Must be called at the START of every tool that accepts a loan_id.
        """
        org_id = self.require_org_id()
        row = db.execute(
            text("SELECT id FROM loans WHERE id = :loan_id AND organization_id = :org_id"),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: loan %s access denied for org %s by agent %s",
                loan_id, org_id, self.name,
            )
            raise ValueError(f"Loan {loan_id} not found")

    def _verify_document_org(self, db, document_id: int) -> None:
        """Verify a smart_document belongs to this agent's organization (via its parent loan).

        Raises ValueError if the document does not exist for this org.
        Must be called at the START of every tool that accepts a document_id.
        """
        org_id = self.require_org_id()
        row = db.execute(
            text("""
                SELECT sd.id FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.id = :document_id
            """),
            {"document_id": document_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: document %s access denied for org %s by agent %s",
                document_id, org_id, self.name,
            )
            raise ValueError(f"Document {document_id} not found")

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_document_with_org_check(self, db, document_id: int, org_id: str):
        """Fetch a smart document and verify it belongs to the caller's org."""
        row = db.execute(
            text("""
                SELECT sd.id, sd.filename, sd.mime_type, sd.doc_type,
                       sd.loan_id, sd.file_size, sd.page_count,
                       sd.uploaded_at, sd.review_decision,
                       sd.review_decision_at, sd.review_notes,
                       l.loan_number, l.borrower_name, l.coborrower_name,
                       l.stage as loan_stage
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                WHERE sd.id = :document_id
            """),
            {"document_id": document_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: document %s access denied for org %s by agent %s",
                document_id, org_id, self.name,
            )
        return row

    def _get_extraction_data(self, db, document_id: int):
        """Fetch extracted data for a document."""
        return db.execute(
            text("""
                SELECT extracted_data, extracted_name, extracted_address,
                       extracted_employer, extracted_income,
                       extracted_account_number, extracted_date,
                       page_count, confidence_score
                FROM smart_document_extractions
                WHERE document_id = :document_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"document_id": document_id},
        ).fetchone()

    def _get_fraud_analysis(self, db, document_id: int):
        """Fetch fraud analysis data for a document if available."""
        return db.execute(
            text("""
                SELECT fraud_score, indicators, metadata_analysis,
                       screenshot_detected, screenshot_confidence,
                       alteration_detected, analyzed_at
                FROM document_fraud_analyses
                WHERE document_id = :document_id
                ORDER BY analyzed_at DESC
                LIMIT 1
            """),
            {"document_id": document_id},
        ).fetchone()

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a name for comparison."""
        if not name:
            return ""
        import re
        # Remove suffixes, punctuation, extra spaces
        name = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b\.?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w\s]', '', name)
        return ' '.join(name.lower().split())

    @staticmethod
    def _names_match(name1: str, name2: str) -> bool:
        """Check if two names match, accounting for common variations."""
        if not name1 or not name2:
            return False

        n1 = DocumentReviewAgent._normalize_name(name1)
        n2 = DocumentReviewAgent._normalize_name(name2)

        if n1 == n2:
            return True

        # Check if one name contains the other (handles middle name presence/absence)
        parts1 = n1.split()
        parts2 = n2.split()

        # First and last name match
        if len(parts1) >= 2 and len(parts2) >= 2:
            if parts1[0] == parts2[0] and parts1[-1] == parts2[-1]:
                return True

        # Check common name variations
        NAME_VARIATIONS = {
            "william": ["will", "bill", "billy", "wm"],
            "robert": ["rob", "bob", "bobby", "robbie"],
            "richard": ["rich", "rick", "dick", "ricky"],
            "james": ["jim", "jimmy", "jamie"],
            "john": ["jon", "johnny", "jack"],
            "joseph": ["joe", "joey"],
            "michael": ["mike", "mikey", "mick"],
            "thomas": ["tom", "tommy"],
            "charles": ["charlie", "chuck", "chas"],
            "christopher": ["chris"],
            "daniel": ["dan", "danny"],
            "matthew": ["matt", "matty"],
            "anthony": ["tony", "ant"],
            "david": ["dave", "davey"],
            "andrew": ["andy", "drew"],
            "nicholas": ["nick", "nicky"],
            "steven": ["steve", "stephen"],
            "edward": ["ed", "eddie", "ted", "teddy"],
            "benjamin": ["ben", "benny"],
            "elizabeth": ["liz", "beth", "betty", "lizzy", "eliza"],
            "jennifer": ["jen", "jenny"],
            "katherine": ["kate", "kathy", "katie", "cathy", "catherine"],
            "patricia": ["pat", "patty", "tricia"],
            "margaret": ["maggie", "meg", "peggy", "marge"],
            "jessica": ["jess", "jessie"],
            "susan": ["sue", "susie", "suzy"],
            "deborah": ["deb", "debbie", "debra"],
            "stephanie": ["steph"],
            "rebecca": ["becky", "becca"],
            "timothy": ["tim", "timmy"],
            "samuel": ["sam", "sammy"],
            "alexander": ["alex"],
            "raymond": ["ray"],
            "kenneth": ["ken", "kenny"],
            "gregory": ["greg"],
            "ronald": ["ron", "ronnie"],
            "donald": ["don", "donnie"],
        }

        # Build reverse lookup
        reverse = {}
        for formal, variants in NAME_VARIATIONS.items():
            reverse[formal] = formal
            for v in variants:
                reverse[v] = formal

        if len(parts1) >= 1 and len(parts2) >= 1:
            canonical1 = reverse.get(parts1[0], parts1[0])
            canonical2 = reverse.get(parts2[0], parts2[0])
            if canonical1 == canonical2:
                # First names match via variation, check last name
                if len(parts1) >= 2 and len(parts2) >= 2:
                    if parts1[-1] == parts2[-1]:
                        return True

        return False

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _review_document_quality(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Assess document image/scan quality."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            issues = []
            quality_score = 100

            # File size check
            file_size = doc.file_size or 0
            min_size = MIN_FILE_SIZES.get(doc.mime_type, 3_000)
            if file_size < min_size:
                issues.append({
                    "type": "FILE_TOO_SMALL",
                    "severity": "HIGH",
                    "description": f"File size ({file_size} bytes) below minimum ({min_size} bytes) - may be blank or corrupt",
                })
                quality_score -= 30

            if file_size > 50 * 1024 * 1024:  # 50 MB
                issues.append({
                    "type": "FILE_TOO_LARGE",
                    "severity": "MEDIUM",
                    "description": f"File size ({file_size / (1024*1024):.1f} MB) exceeds 50 MB limit",
                })
                quality_score -= 10

            # Page count check
            page_count = doc.page_count or 0
            if page_count == 0:
                issues.append({
                    "type": "NO_PAGES_DETECTED",
                    "severity": "HIGH",
                    "description": "No pages detected - document may be corrupt or empty",
                })
                quality_score -= 25

            # MIME type validation
            valid_mime_types = [
                "application/pdf", "image/png", "image/jpeg", "image/jpg",
                "image/tiff", "image/bmp",
            ]
            if doc.mime_type and doc.mime_type not in valid_mime_types:
                issues.append({
                    "type": "UNSUPPORTED_FORMAT",
                    "severity": "MEDIUM",
                    "description": f"Unsupported file format: {doc.mime_type}",
                })
                quality_score -= 15

            # Check extraction confidence as proxy for readability
            extraction = self._get_extraction_data(db, document_id)
            if extraction:
                confidence = extraction.confidence_score or 0
                if confidence < 50:
                    issues.append({
                        "type": "LOW_READABILITY",
                        "severity": "HIGH",
                        "description": f"Low extraction confidence ({confidence}%) - document may be blurry or low resolution",
                    })
                    quality_score -= 25
                elif confidence < 70:
                    issues.append({
                        "type": "MODERATE_READABILITY",
                        "severity": "MEDIUM",
                        "description": f"Moderate extraction confidence ({confidence}%) - some fields may be unreadable",
                    })
                    quality_score -= 10

            # Check for screenshot detection
            fraud_data = self._get_fraud_analysis(db, document_id)
            if fraud_data and fraud_data.screenshot_detected:
                screenshot_conf = fraud_data.screenshot_confidence or 0
                if screenshot_conf > 85:
                    issues.append({
                        "type": "SCREENSHOT_DETECTED",
                        "severity": "CRITICAL",
                        "description": f"Document appears to be a screenshot ({screenshot_conf}% confidence) - original document required",
                    })
                    quality_score -= 40

            quality_score = max(0, quality_score)

            quality_rating = "GOOD"
            if quality_score < 40:
                quality_rating = "POOR"
            elif quality_score < 70:
                quality_rating = "FAIR"

            self.audit_log(
                "review_document_quality", "document",
                entity_id=str(document_id),
                details={"quality_score": quality_score, "issues": len(issues)},
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "quality_score": quality_score,
                    "quality_rating": quality_rating,
                    "file_size": file_size,
                    "page_count": page_count,
                    "mime_type": doc.mime_type,
                    "issues": issues,
                    "issue_count": len(issues),
                },
                message=f"Quality: {quality_rating} ({quality_score}/100) - {len(issues)} issues",
            )

        except Exception as e:
            logger.exception(f"review_document_quality failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _verify_document_type(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Verify document content matches its classified type."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            declared_type = doc.doc_type

            # Get AI classification result
            classification = db.execute(
                text("""
                    SELECT predicted_type, confidence, alternatives
                    FROM smart_document_classifications
                    WHERE document_id = :document_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"document_id": document_id},
            ).fetchone()

            if not classification:
                return ToolResult(
                    success=True,
                    data={
                        "document_id": document_id,
                        "filename": doc.filename,
                        "declared_type": declared_type,
                        "verified": None,
                        "status": "no_classification",
                        "message": "No AI classification available - run classify_document first",
                    },
                    message="No classification data available for verification",
                )

            predicted_type = classification.predicted_type
            confidence = classification.confidence or 0
            type_match = (declared_type == predicted_type)

            # Determine verification result
            if type_match and confidence >= 80:
                verification = "CONFIRMED"
                verification_confidence = confidence
            elif type_match and confidence >= 50:
                verification = "LIKELY_MATCH"
                verification_confidence = confidence
            elif not type_match and confidence >= 90:
                verification = "MISMATCH"
                verification_confidence = confidence
            elif not type_match and confidence >= 70:
                verification = "POSSIBLE_MISMATCH"
                verification_confidence = confidence
            else:
                verification = "INCONCLUSIVE"
                verification_confidence = confidence

            alternatives = classification.alternatives if classification.alternatives else []

            self.audit_log(
                "verify_document_type", "document",
                entity_id=str(document_id),
                details={
                    "declared_type": declared_type,
                    "predicted_type": predicted_type,
                    "type_match": type_match,
                    "verification": verification,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "declared_type": declared_type,
                    "predicted_type": predicted_type,
                    "type_match": type_match,
                    "verification": verification,
                    "verification_confidence": verification_confidence,
                    "alternatives": alternatives,
                },
                message=f"Type verification: {verification} (declared={declared_type}, predicted={predicted_type})",
            )

        except Exception as e:
            logger.exception(f"verify_document_type failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_document_freshness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check if document is within acceptable date range."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            extraction = self._get_extraction_data(db, document_id)
            doc_type = doc.doc_type or ""
            max_age_days = FRESHNESS_REQUIREMENTS.get(doc_type, 90)

            today = date.today()
            is_fresh = True
            days_old = None
            doc_date = None
            freshness_status = "UNKNOWN"

            if extraction and extraction.extracted_date:
                extracted = extraction.extracted_date
                if isinstance(extracted, datetime):
                    extracted = extracted.date()
                elif isinstance(extracted, str):
                    try:
                        extracted = datetime.strptime(extracted[:10], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        extracted = None

                if extracted:
                    doc_date = extracted.isoformat()
                    days_old = (today - extracted).days

                    if max_age_days == 0:
                        # For IDs, check expiration (date should be in the future)
                        if extracted < today:
                            is_fresh = False
                            freshness_status = "EXPIRED"
                        else:
                            freshness_status = "VALID"
                    elif days_old > max_age_days:
                        is_fresh = False
                        freshness_status = "STALE"
                    elif days_old > max_age_days * 0.8:
                        freshness_status = "EXPIRING_SOON"
                    else:
                        freshness_status = "FRESH"

                    # Check for future-dated documents (fraud indicator)
                    if days_old < 0 and doc_type not in ("DRIVERS_LICENSE", "HOMEOWNERS_INSURANCE"):
                        is_fresh = False
                        freshness_status = "FUTURE_DATED"
            else:
                freshness_status = "NO_DATE_EXTRACTED"

            self.audit_log(
                "check_document_freshness", "document",
                entity_id=str(document_id),
                details={
                    "doc_type": doc_type,
                    "freshness_status": freshness_status,
                    "days_old": days_old,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc_type,
                    "loan_number": doc.loan_number,
                    "document_date": doc_date,
                    "days_old": days_old,
                    "max_age_days": max_age_days,
                    "is_fresh": is_fresh,
                    "freshness_status": freshness_status,
                },
                message=f"Freshness: {freshness_status} ({days_old} days old, max {max_age_days})",
            )

        except Exception as e:
            logger.exception(f"check_document_freshness failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _match_borrower_name(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Compare document name to application borrower name."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            extraction = self._get_extraction_data(db, document_id)
            extracted_name = extraction.extracted_name if extraction else None

            if not extracted_name:
                return ToolResult(
                    success=True,
                    data={
                        "document_id": document_id,
                        "filename": doc.filename,
                        "match_result": "NO_NAME_EXTRACTED",
                        "message": "No name could be extracted from the document",
                    },
                    message="No name extracted from document - manual review required",
                )

            borrower_name = doc.borrower_name or ""
            coborrower_name = doc.coborrower_name or ""

            borrower_match = self._names_match(extracted_name, borrower_name)
            coborrower_match = False
            if coborrower_name:
                coborrower_match = self._names_match(extracted_name, coborrower_name)

            if borrower_match:
                match_result = "BORROWER_MATCH"
                match_target = borrower_name
            elif coborrower_match:
                match_result = "COBORROWER_MATCH"
                match_target = coborrower_name
            else:
                match_result = "NO_MATCH"
                match_target = None

            self.audit_log(
                "match_borrower_name", "document",
                entity_id=str(document_id),
                details={
                    "extracted_name": extracted_name,
                    "match_result": match_result,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "extracted_name": extracted_name,
                    "borrower_name": borrower_name,
                    "coborrower_name": coborrower_name,
                    "match_result": match_result,
                    "matched_to": match_target,
                    "is_match": borrower_match or coborrower_match,
                },
                message=f"Name match: {match_result} (doc='{extracted_name}', borrower='{borrower_name}')",
            )

        except Exception as e:
            logger.exception(f"match_borrower_name failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_document_completeness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Verify all required pages and fields are present."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            doc_type = doc.doc_type or ""
            required_fields = REQUIRED_FIELDS.get(doc_type, [])

            extraction = self._get_extraction_data(db, document_id)
            extracted_data = {}
            if extraction and extraction.extracted_data:
                if isinstance(extraction.extracted_data, dict):
                    extracted_data = extraction.extracted_data
                elif isinstance(extraction.extracted_data, str):
                    try:
                        import json
                        extracted_data = json.loads(extraction.extracted_data)
                    except (json.JSONDecodeError, TypeError):
                        extracted_data = {}

            # Check which required fields are present
            found_fields = []
            missing_fields = []
            extracted_text_lower = str(extracted_data).lower()

            for field_name in required_fields:
                # Check if the field name or a close variant appears in extracted data
                if field_name.lower() in extracted_text_lower:
                    found_fields.append(field_name)
                else:
                    missing_fields.append(field_name)

            total_required = len(required_fields)
            total_found = len(found_fields)
            completeness_pct = round((total_found / total_required) * 100, 1) if total_required > 0 else 100

            # Page count check for multi-page document types
            page_count = doc.page_count or (extraction.page_count if extraction else 0) or 0
            page_issues = []

            if doc_type == "TAX_RETURN" and page_count < 2:
                page_issues.append("Tax return typically has 2+ pages - may be incomplete")
            elif doc_type == "BANK_STATEMENT" and page_count < 2:
                page_issues.append("Bank statement with only 1 page - verify all pages included")
            elif doc_type == "PURCHASE_CONTRACT" and page_count < 3:
                page_issues.append("Purchase contract appears short - verify all pages and addenda included")

            is_complete = len(missing_fields) == 0 and len(page_issues) == 0

            self.audit_log(
                "check_document_completeness", "document",
                entity_id=str(document_id),
                details={
                    "completeness_pct": completeness_pct,
                    "missing_fields": len(missing_fields),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc_type,
                    "loan_number": doc.loan_number,
                    "is_complete": is_complete,
                    "completeness_pct": completeness_pct,
                    "required_fields": required_fields,
                    "found_fields": found_fields,
                    "missing_fields": missing_fields,
                    "page_count": page_count,
                    "page_issues": page_issues,
                },
                message=f"Completeness: {completeness_pct}% ({total_found}/{total_required} fields, {len(page_issues)} page issues)",
            )

        except Exception as e:
            logger.exception(f"check_document_completeness failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _detect_fraud_indicators(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check for fraud indicators on a document."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            indicators = []

            # Check existing fraud analysis
            fraud_data = self._get_fraud_analysis(db, document_id)
            if fraud_data:
                fraud_score = fraud_data.fraud_score or 0

                if fraud_data.screenshot_detected and (fraud_data.screenshot_confidence or 0) > 70:
                    indicators.append({
                        "type": "SCREENSHOT_DETECTED",
                        "severity": "CRITICAL",
                        "description": "Document appears to be a screenshot rather than an original",
                        "confidence": fraud_data.screenshot_confidence,
                    })

                if fraud_data.alteration_detected:
                    indicators.append({
                        "type": "ALTERATION_DETECTED",
                        "severity": "CRITICAL",
                        "description": "Document shows signs of digital alteration or tampering",
                        "confidence": 85,
                    })

                # Parse stored indicators
                stored_indicators = fraud_data.indicators
                if stored_indicators:
                    if isinstance(stored_indicators, str):
                        try:
                            import json
                            stored_indicators = json.loads(stored_indicators)
                        except (json.JSONDecodeError, TypeError):
                            stored_indicators = []
                    if isinstance(stored_indicators, list):
                        for ind in stored_indicators:
                            if isinstance(ind, dict):
                                indicators.append({
                                    "type": ind.get("indicator_type", ind.get("type", "UNKNOWN")),
                                    "severity": ind.get("severity", "MEDIUM"),
                                    "description": ind.get("description", ""),
                                    "confidence": ind.get("confidence", 50),
                                })

                # Parse metadata analysis
                metadata = fraud_data.metadata_analysis
                if metadata:
                    if isinstance(metadata, str):
                        try:
                            import json
                            metadata = json.loads(metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = {}
                    if isinstance(metadata, dict):
                        creator = metadata.get("creator", "").lower()
                        suspicious_creators = {
                            "photoshop", "gimp", "illustrator", "inkscape", "paint",
                            "canva", "pixlr", "affinity", "corel", "sketch",
                            "figma", "procreate",
                        }
                        if any(tool in creator for tool in suspicious_creators):
                            indicators.append({
                                "type": "SUSPICIOUS_CREATOR_TOOL",
                                "severity": "HIGH",
                                "description": f"Document created with image editing tool: {metadata.get('creator', 'unknown')}",
                                "confidence": 90,
                            })
            else:
                fraud_score = 0

            # Check extraction data for additional red flags
            extraction = self._get_extraction_data(db, document_id)
            if extraction and extraction.extracted_data:
                data = extraction.extracted_data
                if isinstance(data, str):
                    try:
                        import json
                        data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        data = {}

                if isinstance(data, dict):
                    # Check for suspiciously round numbers in financial docs
                    income = extraction.extracted_income
                    if income:
                        try:
                            income_val = float(income)
                            if income_val > 0 and income_val % 1000 == 0 and income_val >= 50000:
                                indicators.append({
                                    "type": "ROUND_INCOME_NUMBER",
                                    "severity": "LOW",
                                    "description": f"Income amount (${income_val:,.0f}) is suspiciously round",
                                    "confidence": 30,
                                })
                        except (ValueError, TypeError):
                            pass

            # Determine overall fraud risk
            if any(i["severity"] == "CRITICAL" for i in indicators):
                risk_level = "CRITICAL"
            elif any(i["severity"] == "HIGH" for i in indicators):
                risk_level = "HIGH"
            elif indicators:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            self.audit_log(
                "detect_fraud_indicators", "document",
                entity_id=str(document_id),
                details={
                    "indicator_count": len(indicators),
                    "risk_level": risk_level,
                    "fraud_score": fraud_score,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "fraud_score": fraud_score,
                    "risk_level": risk_level,
                    "indicator_count": len(indicators),
                    "indicators": indicators,
                    "has_critical": any(i["severity"] == "CRITICAL" for i in indicators),
                },
                message=f"Fraud detection: {risk_level} risk, {len(indicators)} indicators found",
            )

        except Exception as e:
            logger.exception(f"detect_fraud_indicators failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _cross_validate_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Cross-validate data across all documents for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        field_type = input_data.get("field_type", "all")
        db = SessionLocal()
        try:
            # Tenant isolation: verify loan belongs to this organization
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            # Get all documents with extraction data
            docs = db.execute(
                text("""
                    SELECT
                        sd.id, sd.doc_type, sd.filename,
                        sde.extracted_name, sde.extracted_address,
                        sde.extracted_employer, sde.extracted_income,
                        sde.extracted_account_number
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                    ORDER BY sd.doc_type
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not docs or len(docs) < 2:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "status": "insufficient_data",
                        "message": "Need at least 2 documents to cross-validate",
                    },
                    message="Insufficient documents for cross-validation",
                )

            inconsistencies = []

            # Collect field values keyed by doc label
            names = {}
            addresses = {}
            employers = {}
            incomes = {}
            accounts = {}

            for doc in docs:
                label = f"{doc.doc_type} ({doc.filename})"
                if doc.extracted_name:
                    names[label] = doc.extracted_name
                if doc.extracted_address:
                    addresses[label] = doc.extracted_address
                if doc.extracted_employer:
                    employers[label] = doc.extracted_employer
                if doc.extracted_income:
                    incomes[label] = doc.extracted_income
                if doc.extracted_account_number:
                    accounts[label] = doc.extracted_account_number

            # Name consistency
            if field_type in ("all", "name") and len(names) >= 2:
                unique_names = set(self._normalize_name(n) for n in names.values() if n)
                if len(unique_names) > 1:
                    inconsistencies.append({
                        "field": "name",
                        "severity": "HIGH",
                        "description": "Name discrepancy across documents",
                        "values": names,
                    })

            # Address consistency
            if field_type in ("all", "address") and len(addresses) >= 2:
                unique_addrs = set(a.strip().lower() for a in addresses.values() if a)
                if len(unique_addrs) > 1:
                    inconsistencies.append({
                        "field": "address",
                        "severity": "MEDIUM",
                        "description": "Address discrepancy across documents",
                        "values": addresses,
                    })

            # Employer consistency
            if field_type in ("all", "employer") and len(employers) >= 2:
                unique_emp = set(e.strip().lower() for e in employers.values() if e)
                if len(unique_emp) > 1:
                    inconsistencies.append({
                        "field": "employer",
                        "severity": "MEDIUM",
                        "description": "Employer name discrepancy across documents",
                        "values": employers,
                    })

            # Income consistency (> 10% variance)
            if field_type in ("all", "income") and len(incomes) >= 2:
                income_values = []
                for v in incomes.values():
                    try:
                        income_values.append(float(v))
                    except (ValueError, TypeError):
                        pass
                if len(income_values) >= 2:
                    max_inc = max(income_values)
                    min_inc = min(income_values)
                    if min_inc > 0:
                        variance_pct = ((max_inc - min_inc) / min_inc) * 100
                        if variance_pct > 10:
                            inconsistencies.append({
                                "field": "income",
                                "severity": "HIGH",
                                "description": f"Income variance of {variance_pct:.1f}% across documents",
                                "values": incomes,
                            })

            # Determine risk assessment
            if any(i["severity"] == "HIGH" for i in inconsistencies):
                risk_assessment = "HIGH_RISK"
            elif inconsistencies:
                risk_assessment = "REVIEW_RECOMMENDED"
            else:
                risk_assessment = "CLEAN"

            self.audit_log(
                "cross_validate_documents", "loan",
                entity_id=str(loan_id),
                details={
                    "documents_checked": len(docs),
                    "inconsistencies": len(inconsistencies),
                    "risk": risk_assessment,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "documents_checked": len(docs),
                    "field_type_checked": field_type,
                    "risk_assessment": risk_assessment,
                    "inconsistency_count": len(inconsistencies),
                    "inconsistencies": inconsistencies,
                },
                message=f"Cross-validation: {len(inconsistencies)} inconsistencies, risk={risk_assessment}",
            )

        except Exception as e:
            logger.exception(f"cross_validate_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _validate_employer_info(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Cross-check employer info across paystubs, W2s, and VOE."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data.get("borrower_id")
        db = SessionLocal()
        try:
            # Tenant isolation: verify loan belongs to this organization
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            # Get employer data from employment-related documents
            employment_docs = db.execute(
                text("""
                    SELECT
                        sd.id as document_id, sd.doc_type, sd.filename,
                        sde.extracted_employer, sde.extracted_data
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                        AND sd.doc_type IN ('PAYSTUB', 'W2', 'VOE', '1099', 'TAX_RETURN')
                    ORDER BY sd.doc_type, sd.uploaded_at DESC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not employment_docs:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "status": "no_employment_docs",
                        "message": "No employment-related documents found",
                    },
                    message="No employment documents to validate",
                )

            # Group employers by document type
            employers_by_type = {}
            all_employers = []
            for doc in employment_docs:
                employer = doc.extracted_employer
                if employer:
                    employers_by_type.setdefault(doc.doc_type, []).append({
                        "document_id": doc.document_id,
                        "filename": doc.filename,
                        "employer": employer,
                    })
                    all_employers.append(employer.strip().lower())

            issues = []

            # Check for consistency across document types
            unique_employers = set(all_employers)
            if len(unique_employers) > 1:
                # May be multiple employers (acceptable) or inconsistency
                # Check within same doc type for inconsistency
                for doc_type, entries in employers_by_type.items():
                    type_employers = set(e["employer"].strip().lower() for e in entries)
                    if len(type_employers) > 1 and doc_type not in ("TAX_RETURN", "1099"):
                        issues.append({
                            "type": "INTRA_TYPE_MISMATCH",
                            "severity": "HIGH",
                            "description": f"Different employer names within {doc_type} documents",
                            "doc_type": doc_type,
                            "values": [e["employer"] for e in entries],
                        })

                # Cross-type validation: paystub employer should match W2 employer
                paystub_employers = set(
                    e["employer"].strip().lower()
                    for e in employers_by_type.get("PAYSTUB", [])
                )
                w2_employers = set(
                    e["employer"].strip().lower()
                    for e in employers_by_type.get("W2", [])
                )
                if paystub_employers and w2_employers:
                    if not paystub_employers.intersection(w2_employers):
                        issues.append({
                            "type": "PAYSTUB_W2_MISMATCH",
                            "severity": "HIGH",
                            "description": "Employer on paystub does not match any W2 employer",
                            "paystub_employers": list(paystub_employers),
                            "w2_employers": list(w2_employers),
                        })

            is_consistent = len(issues) == 0

            self.audit_log(
                "validate_employer_info", "loan",
                entity_id=str(loan_id),
                details={
                    "docs_checked": len(employment_docs),
                    "unique_employers": len(unique_employers),
                    "issues": len(issues),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "documents_checked": len(employment_docs),
                    "unique_employers_found": len(unique_employers),
                    "employers_by_doc_type": {
                        k: [e["employer"] for e in v]
                        for k, v in employers_by_type.items()
                    },
                    "is_consistent": is_consistent,
                    "issues": issues,
                },
                message=f"Employer validation: {'consistent' if is_consistent else f'{len(issues)} issues found'} across {len(employment_docs)} docs",
            )

        except Exception as e:
            logger.exception(f"validate_employer_info failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _validate_account_numbers(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Verify bank account numbers are consistent across statements."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            # Tenant isolation: verify loan belongs to this organization
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            # Get account numbers from bank statements and investment statements
            account_docs = db.execute(
                text("""
                    SELECT
                        sd.id as document_id, sd.doc_type, sd.filename,
                        sde.extracted_account_number, sde.extracted_date
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                        AND sd.doc_type IN ('BANK_STATEMENT', 'INVESTMENT_STATEMENT')
                        AND sde.extracted_account_number IS NOT NULL
                    ORDER BY sd.doc_type, sde.extracted_date DESC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not account_docs:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "status": "no_account_data",
                        "message": "No account numbers extracted from documents",
                    },
                    message="No account number data available",
                )

            # Group by last 4 digits to identify unique accounts
            accounts = {}
            issues = []

            for doc in account_docs:
                acct_num = doc.extracted_account_number.strip()
                # Use last 4 as account identifier for grouping
                last4 = acct_num[-4:] if len(acct_num) >= 4 else acct_num
                key = f"{doc.doc_type}_{last4}"

                if key not in accounts:
                    accounts[key] = {
                        "doc_type": doc.doc_type,
                        "last4": last4,
                        "full_numbers": [],
                        "documents": [],
                    }

                accounts[key]["full_numbers"].append(acct_num)
                accounts[key]["documents"].append({
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "account_number": acct_num,
                    "date": str(doc.extracted_date) if doc.extracted_date else None,
                })

            # Check for inconsistencies within account groups
            for key, acct_info in accounts.items():
                unique_nums = set(acct_info["full_numbers"])
                if len(unique_nums) > 1:
                    issues.append({
                        "type": "ACCOUNT_NUMBER_MISMATCH",
                        "severity": "HIGH",
                        "description": f"Different account numbers found for account ending in {acct_info['last4']}",
                        "doc_type": acct_info["doc_type"],
                        "account_numbers": list(unique_nums),
                        "affected_documents": [d["document_id"] for d in acct_info["documents"]],
                    })

            is_consistent = len(issues) == 0

            self.audit_log(
                "validate_account_numbers", "loan",
                entity_id=str(loan_id),
                details={
                    "accounts_found": len(accounts),
                    "issues": len(issues),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "accounts_found": len(accounts),
                    "documents_checked": len(account_docs),
                    "is_consistent": is_consistent,
                    "accounts": {
                        k: {
                            "doc_type": v["doc_type"],
                            "last4": v["last4"],
                            "statement_count": len(v["documents"]),
                        }
                        for k, v in accounts.items()
                    },
                    "issues": issues,
                },
                message=f"Account validation: {len(accounts)} accounts, {'consistent' if is_consistent else f'{len(issues)} issues'}",
            )

        except Exception as e:
            logger.exception(f"validate_account_numbers failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _assess_overall_document_risk(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate a comprehensive risk score for a document."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            risk_score = 0
            risk_factors = []

            # 1. Quality assessment
            file_size = doc.file_size or 0
            min_size = MIN_FILE_SIZES.get(doc.mime_type, 3_000)
            if file_size < min_size:
                risk_score += RISK_WEIGHTS["quality_low"]
                risk_factors.append({"factor": "quality_low", "weight": RISK_WEIGHTS["quality_low"], "detail": "File size below minimum"})

            # 2. Extraction confidence
            extraction = self._get_extraction_data(db, document_id)
            if extraction:
                confidence = extraction.confidence_score or 0
                if confidence < 50:
                    risk_score += 15
                    risk_factors.append({"factor": "low_extraction_confidence", "weight": 15, "detail": f"Confidence: {confidence}%"})

                # 3. Name check
                if extraction.extracted_name and doc.borrower_name:
                    if not self._names_match(extraction.extracted_name, doc.borrower_name):
                        coborrower_match = False
                        if doc.coborrower_name:
                            coborrower_match = self._names_match(extraction.extracted_name, doc.coborrower_name)
                        if not coborrower_match:
                            risk_score += RISK_WEIGHTS["name_mismatch"]
                            risk_factors.append({"factor": "name_mismatch", "weight": RISK_WEIGHTS["name_mismatch"], "detail": f"'{extraction.extracted_name}' vs '{doc.borrower_name}'"})

                # 4. Freshness
                if extraction.extracted_date:
                    doc_type = doc.doc_type or ""
                    max_age = FRESHNESS_REQUIREMENTS.get(doc_type, 90)
                    extracted_dt = extraction.extracted_date
                    if isinstance(extracted_dt, datetime):
                        extracted_dt = extracted_dt.date()
                    elif isinstance(extracted_dt, str):
                        try:
                            extracted_dt = datetime.strptime(extracted_dt[:10], "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            extracted_dt = None
                    if extracted_dt and max_age > 0:
                        days_old = (date.today() - extracted_dt).days
                        if days_old > max_age:
                            risk_score += RISK_WEIGHTS["expired"]
                            risk_factors.append({"factor": "expired", "weight": RISK_WEIGHTS["expired"], "detail": f"{days_old} days old (max {max_age})"})

            # 5. Type verification
            classification = db.execute(
                text("""
                    SELECT predicted_type, confidence
                    FROM smart_document_classifications
                    WHERE document_id = :document_id
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"document_id": document_id},
            ).fetchone()

            if classification:
                if classification.predicted_type != doc.doc_type and (classification.confidence or 0) >= 80:
                    risk_score += RISK_WEIGHTS["type_mismatch"]
                    risk_factors.append({"factor": "type_mismatch", "weight": RISK_WEIGHTS["type_mismatch"], "detail": f"Classified as {classification.predicted_type}, declared as {doc.doc_type}"})

            # 6. Fraud indicators
            fraud_data = self._get_fraud_analysis(db, document_id)
            if fraud_data:
                if fraud_data.screenshot_detected and (fraud_data.screenshot_confidence or 0) > 70:
                    risk_score += RISK_WEIGHTS["screenshot_detected"]
                    risk_factors.append({"factor": "screenshot_detected", "weight": RISK_WEIGHTS["screenshot_detected"], "detail": f"Screenshot confidence: {fraud_data.screenshot_confidence}%"})
                if fraud_data.alteration_detected:
                    risk_score += RISK_WEIGHTS["fraud_indicator"]
                    risk_factors.append({"factor": "alteration_detected", "weight": RISK_WEIGHTS["fraud_indicator"], "detail": "Digital alteration detected"})
                if fraud_data.fraud_score and fraud_data.fraud_score > 50:
                    additional = min(20, fraud_data.fraud_score // 5)
                    risk_score += additional
                    risk_factors.append({"factor": "fraud_score_elevated", "weight": additional, "detail": f"Fraud analysis score: {fraud_data.fraud_score}"})

            # Cap at 100
            risk_score = min(100, risk_score)

            # Determine risk level
            if risk_score >= 71:
                risk_level = "CRITICAL"
            elif risk_score >= 46:
                risk_level = "HIGH"
            elif risk_score >= 21:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            self.audit_log(
                "assess_overall_document_risk", "document",
                entity_id=str(document_id),
                details={"risk_score": risk_score, "risk_level": risk_level, "factors": len(risk_factors)},
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "risk_factors": risk_factors,
                    "factor_count": len(risk_factors),
                },
                message=f"Risk assessment: {risk_level} ({risk_score}/100) - {len(risk_factors)} factors",
            )

        except Exception as e:
            logger.exception(f"assess_overall_document_risk failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_review_action(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Recommend approve, reject, or manual review for a document."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = self._get_document_with_org_check(db, document_id, org_id)
            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found or access denied")

            # Run the risk assessment internally
            risk_result = await self._assess_overall_document_risk(
                {"document_id": document_id}, context
            )

            if not risk_result.success:
                return ToolResult(success=False, error=f"Risk assessment failed: {risk_result.error}")

            risk_data = risk_result.data
            risk_score = risk_data["risk_score"]
            risk_level = risk_data["risk_level"]
            risk_factors = risk_data["risk_factors"]

            # Determine recommendation
            reasons = []
            fix_instructions = None

            if risk_level == "CRITICAL":
                recommendation = "REJECT"
                reasons = [f["detail"] for f in risk_factors if f["weight"] >= 20]
                critical_factors = [f for f in risk_factors if f["factor"] in ("screenshot_detected", "alteration_detected", "name_mismatch")]
                if any(f["factor"] == "screenshot_detected" for f in critical_factors):
                    fix_instructions = "Please upload the original document (not a screenshot). Use a scanner or the document's native export function."
                elif any(f["factor"] == "alteration_detected" for f in critical_factors):
                    fix_instructions = "Document shows signs of alteration. Please provide the original, unmodified document."
                elif any(f["factor"] == "name_mismatch" for f in critical_factors):
                    fix_instructions = "Name on document does not match borrower name. Provide a document in the borrower's legal name or a name affidavit."
                else:
                    fix_instructions = "Please address the critical issues and resubmit the document."

            elif risk_level == "HIGH":
                recommendation = "MANUAL_REVIEW"
                reasons = [f["detail"] for f in risk_factors]

            elif risk_level == "MEDIUM":
                # Medium risk: auto-approve if no high-weight factors
                if any(f["weight"] >= 20 for f in risk_factors):
                    recommendation = "MANUAL_REVIEW"
                    reasons = [f["detail"] for f in risk_factors if f["weight"] >= 15]
                else:
                    recommendation = "APPROVE"
                    reasons = ["Minor issues detected but within acceptable thresholds"]

            else:
                recommendation = "APPROVE"
                reasons = ["Document passed all quality and validation checks"]

            # Determine review priority
            if recommendation == "REJECT":
                review_priority = "CRITICAL"
            elif recommendation == "MANUAL_REVIEW":
                review_priority = "HIGH"
            else:
                review_priority = "NORMAL"

            self.audit_log(
                "recommend_review_action", "document",
                entity_id=str(document_id),
                details={
                    "recommendation": recommendation,
                    "risk_score": risk_score,
                    "review_priority": review_priority,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "recommendation": recommendation,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "reasons": reasons,
                    "fix_instructions": fix_instructions,
                    "review_priority": review_priority,
                    "can_auto_approve": recommendation == "APPROVE",
                    "risk_factors": risk_factors,
                },
                message=f"Recommendation: {recommendation} (risk={risk_score}, priority={review_priority})",
            )

        except Exception as e:
            logger.exception(f"recommend_review_action failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_condition_from_review(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create an underwriting condition from a review finding."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        document_id = input_data["document_id"]
        finding_type = input_data["finding_type"]
        description = input_data["description"]
        severity = input_data.get("severity", "MEDIUM")
        db = SessionLocal()
        try:
            # Tenant isolation: verify both loan and document belong to this organization
            self._verify_loan_org(db, loan_id)
            self._verify_document_org(db, document_id)

            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            # Map finding type to condition category
            condition_categories = {
                "quality_issue": "PRIOR_TO_DOCS",
                "type_mismatch": "PRIOR_TO_DOCS",
                "expired": "PRIOR_TO_DOCS",
                "name_mismatch": "PRIOR_TO_DOCS",
                "incomplete": "PRIOR_TO_DOCS",
                "fraud_indicator": "PRIOR_TO_APPROVAL",
                "data_inconsistency": "PRIOR_TO_APPROVAL",
            }
            condition_category = condition_categories.get(finding_type, "PRIOR_TO_DOCS")

            # Set deadline based on severity
            from datetime import timedelta
            deadline_days = {
                "CRITICAL": 3,
                "HIGH": 5,
                "MEDIUM": 7,
                "LOW": 14,
            }
            deadline = date.today() + timedelta(days=deadline_days.get(severity, 7))

            # Create the condition in compliance_alerts table
            condition_title = f"Document Review: {finding_type.replace('_', ' ').title()}"

            db.execute(
                text("""
                    INSERT INTO compliance_alerts
                        (loan_id, alert_type, severity, title, description,
                         status, deadline_date, created_at)
                    VALUES
                        (:loan_id, :alert_type, :severity, :title, :description,
                         'open', :deadline, NOW())
                """),
                {
                    "loan_id": loan_id,
                    "alert_type": f"DOC_REVIEW_{finding_type.upper()}",
                    "severity": severity.lower(),
                    "title": condition_title,
                    "description": f"Document ID {document_id}: {description}",
                    "deadline": deadline,
                },
            )
            db.commit()

            self.audit_log(
                "generate_condition_from_review", "loan",
                entity_id=str(loan_id),
                details={
                    "document_id": document_id,
                    "finding_type": finding_type,
                    "severity": severity,
                    "condition_category": condition_category,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "document_id": document_id,
                    "condition_title": condition_title,
                    "condition_category": condition_category,
                    "finding_type": finding_type,
                    "severity": severity,
                    "description": description,
                    "deadline": deadline.isoformat(),
                    "status": "open",
                },
                message=f"Condition created: {condition_title} (deadline: {deadline.isoformat()})",
            )

        except Exception as e:
            logger.exception(f"generate_condition_from_review failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_review_queue_priority(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get prioritized queue of documents awaiting review."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        limit = input_data.get("limit", 50)
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Tenant isolation: if specific loan_id provided, verify it first
            if loan_id:
                self._verify_loan_org(db, loan_id)

            params = {"org_id": org_id, "limit": limit}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND sd.loan_id = :loan_id"
                params["loan_id"] = loan_id

            queue = db.execute(
                text(f"""
                    SELECT
                        sd.id as document_id, sd.filename, sd.doc_type,
                        sd.uploaded_at, sd.loan_id, sd.file_size,
                        l.loan_number, l.borrower_name, l.stage as loan_stage,
                        l.closing_date,
                        EXTRACT(EPOCH FROM (NOW() - sd.uploaded_at)) / 3600 as hours_waiting
                    FROM smart_documents sd
                    JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                    WHERE (sd.review_decision IS NULL OR sd.review_decision = '')
                        {loan_filter}
                    ORDER BY
                        CASE l.stage
                            WHEN 'CTC' THEN 1
                            WHEN 'CLEAR_TO_CLOSE' THEN 1
                            WHEN 'CLOSING' THEN 1
                            WHEN 'DOCS' THEN 2
                            WHEN 'DOCS_OUT' THEN 2
                            WHEN 'APPROVED' THEN 3
                            WHEN 'CONDITIONAL_APPROVAL' THEN 3
                            WHEN 'UNDERWRITING' THEN 4
                            WHEN 'SUBMITTED' THEN 5
                            ELSE 6
                        END,
                        sd.uploaded_at ASC
                    LIMIT :limit
                """),
                params,
            ).fetchall()

            if not queue:
                return ToolResult(
                    success=True,
                    data={
                        "queue_length": 0,
                        "documents": [],
                        "message": "No documents awaiting review",
                    },
                    message="Review queue is empty",
                )

            documents = []
            for item in queue:
                hours = float(item.hours_waiting or 0)
                # Calculate priority score
                priority_score = 0

                # Loan stage urgency
                stage_scores = {
                    "CTC": 50, "CLEAR_TO_CLOSE": 50, "CLOSING": 50,
                    "DOCS": 45, "DOCS_OUT": 45,
                    "APPROVED": 35, "CONDITIONAL_APPROVAL": 35,
                    "UNDERWRITING": 25, "SUBMITTED": 20,
                }
                priority_score += stage_scores.get(item.loan_stage, 10)

                # Time waiting
                if hours > 48:
                    priority_score += 30
                elif hours > 24:
                    priority_score += 20
                elif hours > 8:
                    priority_score += 10

                # Closing date proximity
                if item.closing_date:
                    days_to_close = (item.closing_date - date.today()).days
                    if days_to_close <= 3:
                        priority_score += 25
                    elif days_to_close <= 7:
                        priority_score += 15
                    elif days_to_close <= 14:
                        priority_score += 5

                if priority_score >= 70:
                    priority_label = "CRITICAL"
                elif priority_score >= 50:
                    priority_label = "HIGH"
                elif priority_score >= 30:
                    priority_label = "MEDIUM"
                else:
                    priority_label = "LOW"

                documents.append({
                    "document_id": item.document_id,
                    "filename": item.filename,
                    "doc_type": item.doc_type,
                    "loan_id": item.loan_id,
                    "loan_number": item.loan_number,
                    "borrower": item.borrower_name,
                    "loan_stage": item.loan_stage,
                    "hours_waiting": round(hours, 1),
                    "closing_date": item.closing_date.isoformat() if item.closing_date else None,
                    "priority_score": priority_score,
                    "priority_label": priority_label,
                })

            # Sort by priority score descending
            documents.sort(key=lambda d: d["priority_score"], reverse=True)

            self.audit_log(
                "get_review_queue_priority", "system",
                details={"queue_length": len(documents)},
            )

            return ToolResult(
                success=True,
                data={
                    "queue_length": len(documents),
                    "critical_count": len([d for d in documents if d["priority_label"] == "CRITICAL"]),
                    "high_count": len([d for d in documents if d["priority_label"] == "HIGH"]),
                    "documents": documents,
                },
                message=f"Review queue: {len(documents)} documents ({len([d for d in documents if d['priority_label'] == 'CRITICAL'])} critical)",
            )

        except Exception as e:
            logger.exception("get_review_queue_priority failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _bulk_review_loan_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Review all unreviewed documents for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            # Tenant isolation: verify loan belongs to this organization
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            # Get all unreviewed documents
            unreviewed = db.execute(
                text("""
                    SELECT id, filename, doc_type
                    FROM smart_documents
                    WHERE loan_id = :loan_id
                        AND (review_decision IS NULL OR review_decision = '')
                    ORDER BY uploaded_at ASC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not unreviewed:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "total_reviewed": 0,
                        "message": "No unreviewed documents found",
                    },
                    message="No unreviewed documents for this loan",
                )

            results = []
            approved = 0
            rejected = 0
            needs_review = 0
            errors = 0

            for doc_row in unreviewed:
                try:
                    # Run risk assessment for each document
                    risk_result = await self._assess_overall_document_risk(
                        {"document_id": doc_row.id}, context
                    )

                    if not risk_result.success:
                        errors += 1
                        results.append({
                            "document_id": doc_row.id,
                            "filename": doc_row.filename,
                            "doc_type": doc_row.doc_type,
                            "recommendation": "ERROR",
                            "error": risk_result.error,
                        })
                        continue

                    risk_data = risk_result.data
                    risk_score = risk_data["risk_score"]
                    risk_level = risk_data["risk_level"]

                    if risk_level == "CRITICAL":
                        recommendation = "REJECT"
                        rejected += 1
                    elif risk_level == "HIGH":
                        recommendation = "MANUAL_REVIEW"
                        needs_review += 1
                    elif risk_level == "MEDIUM" and any(f["weight"] >= 20 for f in risk_data["risk_factors"]):
                        recommendation = "MANUAL_REVIEW"
                        needs_review += 1
                    else:
                        recommendation = "APPROVE"
                        approved += 1

                    results.append({
                        "document_id": doc_row.id,
                        "filename": doc_row.filename,
                        "doc_type": doc_row.doc_type,
                        "recommendation": recommendation,
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "factor_count": risk_data["factor_count"],
                    })

                except Exception as doc_err:
                    logger.warning(f"Bulk review: error reviewing doc {doc_row.id}: {doc_err}")
                    errors += 1
                    results.append({
                        "document_id": doc_row.id,
                        "filename": doc_row.filename,
                        "doc_type": doc_row.doc_type,
                        "recommendation": "ERROR",
                        "error": str(doc_err),
                    })

            self.audit_log(
                "bulk_review_loan_documents", "loan",
                entity_id=str(loan_id),
                details={
                    "total": len(unreviewed),
                    "approved": approved,
                    "rejected": rejected,
                    "needs_review": needs_review,
                    "errors": errors,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "total_reviewed": len(unreviewed),
                    "approved": approved,
                    "rejected": rejected,
                    "needs_review": needs_review,
                    "errors": errors,
                    "results": results,
                },
                message=(
                    f"Bulk review: {approved} approve, {rejected} reject, "
                    f"{needs_review} manual review out of {len(unreviewed)}"
                ),
            )

        except Exception as e:
            logger.exception(f"bulk_review_loan_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_review_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate comprehensive review summary for an underwriter."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            # Tenant isolation: verify loan belongs to this organization
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("""
                    SELECT id, loan_number, borrower_name, coborrower_name,
                           stage, loan_type, amount, closing_date
                    FROM loans
                    WHERE id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            # Get all documents with their review status
            all_docs = db.execute(
                text("""
                    SELECT
                        sd.id, sd.doc_type, sd.filename, sd.file_size,
                        sd.page_count, sd.review_decision, sd.review_notes,
                        sd.uploaded_at,
                        sde.extracted_name, sde.extracted_employer,
                        sde.extracted_income, sde.confidence_score
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                    ORDER BY sd.doc_type
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not all_docs:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "status": "no_documents",
                        "message": "No documents found for this loan",
                    },
                    message="No documents to summarize",
                )

            # Aggregate stats
            total_docs = len(all_docs)
            approved_docs = [d for d in all_docs if d.review_decision == "ACCEPT"]
            rejected_docs = [d for d in all_docs if d.review_decision == "REJECT"]
            pending_docs = [d for d in all_docs if not d.review_decision or d.review_decision == ""]

            # Get outstanding conditions
            conditions = db.execute(
                text("""
                    SELECT id, alert_type, severity, title, description, status, deadline_date
                    FROM compliance_alerts
                    WHERE loan_id = :loan_id
                        AND alert_type LIKE 'DOC_REVIEW_%'
                        AND status = 'open'
                    ORDER BY
                        CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3 ELSE 4 END
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Build per-document summary
            doc_summaries = []
            for doc in all_docs:
                doc_summaries.append({
                    "document_id": doc.id,
                    "doc_type": doc.doc_type,
                    "filename": doc.filename,
                    "review_decision": doc.review_decision or "PENDING",
                    "review_notes": doc.review_notes,
                    "extracted_name": doc.extracted_name,
                    "extracted_employer": doc.extracted_employer,
                    "extraction_confidence": doc.confidence_score,
                })

            # Run cross-validation for summary
            cross_val_result = await self._cross_validate_documents(
                {"loan_id": loan_id, "field_type": "all"}, context
            )
            cross_validation = cross_val_result.data if cross_val_result.success else None

            # Determine overall package recommendation
            if rejected_docs or (conditions and any(c.severity in ("critical", "high") for c in conditions)):
                overall_recommendation = "CONDITIONS_OUTSTANDING"
            elif pending_docs:
                overall_recommendation = "REVIEW_IN_PROGRESS"
            elif cross_validation and cross_validation.get("risk_assessment") == "HIGH_RISK":
                overall_recommendation = "RISK_REVIEW_REQUIRED"
            else:
                overall_recommendation = "PACKAGE_COMPLETE"

            condition_summaries = []
            for cond in conditions:
                condition_summaries.append({
                    "id": cond.id,
                    "type": cond.alert_type,
                    "severity": cond.severity,
                    "title": cond.title,
                    "description": cond.description,
                    "deadline": cond.deadline_date.isoformat() if cond.deadline_date else None,
                })

            self.audit_log(
                "create_review_summary", "loan",
                entity_id=str(loan_id),
                details={
                    "total_docs": total_docs,
                    "approved": len(approved_docs),
                    "rejected": len(rejected_docs),
                    "pending": len(pending_docs),
                    "recommendation": overall_recommendation,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "coborrower": loan.coborrower_name,
                    "loan_stage": loan.stage,
                    "loan_type": loan.loan_type,
                    "loan_amount": float(loan.amount) if loan.amount else None,
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "summary": {
                        "total_documents": total_docs,
                        "approved": len(approved_docs),
                        "rejected": len(rejected_docs),
                        "pending_review": len(pending_docs),
                        "outstanding_conditions": len(conditions),
                    },
                    "overall_recommendation": overall_recommendation,
                    "documents": doc_summaries,
                    "outstanding_conditions": condition_summaries,
                    "cross_validation": {
                        "risk_assessment": cross_validation.get("risk_assessment") if cross_validation else None,
                        "inconsistency_count": cross_validation.get("inconsistency_count", 0) if cross_validation else 0,
                        "inconsistencies": cross_validation.get("inconsistencies", []) if cross_validation else [],
                    },
                    "generated_at": datetime.utcnow().isoformat(),
                },
                message=(
                    f"Review summary: {overall_recommendation} - "
                    f"{len(approved_docs)} approved, {len(rejected_docs)} rejected, "
                    f"{len(pending_docs)} pending, {len(conditions)} conditions"
                ),
            )

        except Exception as e:
            logger.exception(f"create_review_summary failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
