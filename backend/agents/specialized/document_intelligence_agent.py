"""
Document Intelligence Agent

AI agent specialized in intelligent document management for mortgage lending.
Capabilities:
- Analyze loan applications to determine required documents
- Classify uploaded documents automatically
- Detect document needs from call transcripts
- Review and approve/reject documents
- Calculate income from financial documents
- Analyze bank statements for red flags
- Cross-validate documents for fraud detection
- Generate follow-up campaigns for missing documents
- Schedule appointments for document issues

This agent serves as the central intelligence hub for all document operations,
integrating with the Smart Docs service layer for AI-powered document processing.

15 Tools:
1. analyze_application_for_documents - POS analyzer for document requirements
2. classify_document - AI document classification
3. review_document - AI document review (approve/reject)
4. batch_review_loan_documents - Review all unreviewed docs for a loan
5. calculate_income - Income calculation from financial documents
6. analyze_bank_statements - Bank statement analysis for red flags
7. analyze_call_for_documents - Extract document needs from call transcripts
8. get_missing_documents - Compare requirements vs received documents
9. get_document_completeness - Overall completeness percentage
10. cross_validate_documents - Cross-document fraud detection
11. create_follow_up - Create follow-up campaign for missing documents
12. get_income_tasks - Pending income verification tasks
13. get_bank_analysis_flags - All flags from bank statement analysis
14. generate_needs_list - Generate complete needs list from POS data
15. get_document_status_summary - Comprehensive document status
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

class AnalyzeApplicationInput(BaseModel):
    """Input schema for analyze_application_for_documents tool"""
    loan_id: int = Field(..., description="Loan ID to analyze for document requirements")


class ClassifyDocumentInput(BaseModel):
    """Input schema for classify_document tool"""
    document_id: int = Field(..., description="SmartDocument ID to classify")


class ReviewDocumentInput(BaseModel):
    """Input schema for review_document tool"""
    document_id: int = Field(..., description="SmartDocument ID to review")


class BatchReviewInput(BaseModel):
    """Input schema for batch_review_loan_documents tool"""
    loan_id: int = Field(..., description="Loan ID whose unreviewed documents should be reviewed")


class CalculateIncomeInput(BaseModel):
    """Input schema for calculate_income tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID for income calculation")


class AnalyzeBankStatementsInput(BaseModel):
    """Input schema for analyze_bank_statements tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID for bank statement analysis")


class AnalyzeCallInput(BaseModel):
    """Input schema for analyze_call_for_documents tool"""
    call_id: int = Field(..., description="Call ID from call intelligence system")
    transcript: str = Field(..., description="Full call transcript text")
    loan_id: int = Field(..., description="Associated loan ID")


class GetMissingDocumentsInput(BaseModel):
    """Input schema for get_missing_documents tool"""
    loan_id: int = Field(..., description="Loan ID to check for missing documents")


class GetDocumentCompletenessInput(BaseModel):
    """Input schema for get_document_completeness tool"""
    loan_id: int = Field(..., description="Loan ID to check completeness")


class CrossValidateInput(BaseModel):
    """Input schema for cross_validate_documents tool"""
    loan_id: int = Field(..., description="Loan ID to cross-validate documents")


class CreateFollowUpInput(BaseModel):
    """Input schema for create_follow_up tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower ID to send follow-up to")
    request_ids: str = Field(
        ..., description="Comma-separated document request IDs to follow up on"
    )


class GetIncomeTasksInput(BaseModel):
    """Input schema for get_income_tasks tool"""
    loan_id: int = Field(..., description="Loan ID to get pending income tasks")


class GetBankAnalysisFlagsInput(BaseModel):
    """Input schema for get_bank_analysis_flags tool"""
    loan_id: int = Field(..., description="Loan ID to get bank analysis flags")


class GenerateNeedsListInput(BaseModel):
    """Input schema for generate_needs_list tool"""
    loan_id: int = Field(..., description="Loan ID")
    loan_program: str = Field(
        ..., description="Loan program: conventional, fha, va, usda, jumbo, non_qm"
    )
    occupancy_type: str = Field(
        ..., description="Occupancy: primary, second_home, investment"
    )
    income_type: str = Field(
        ..., description="Income type: w2, self_employed, retired, military"
    )
    borrower_id: int = Field(..., description="Primary borrower ID")


class GetDocumentStatusSummaryInput(BaseModel):
    """Input schema for get_document_status_summary tool"""
    loan_id: int = Field(..., description="Loan ID for status summary")


# ============================================================================
# DOCUMENT INTELLIGENCE AGENT
# ============================================================================

@AgentRegistry.register
class DocumentIntelligenceAgent(SpecializedAgent):
    """
    Document Intelligence AI Agent for mortgage document management.

    I am the central intelligence hub for all document operations. I can:

    1. ANALYZE APPLICATIONS: Tell me a loan ID and I'll analyze the application
       to determine exactly which documents are needed based on loan type,
       borrower profile, income type, and special circumstances.

    2. CLASSIFY DOCUMENTS: Upload a document and I'll identify what type it is
       (paystub, W2, tax return, bank statement, etc.) with high accuracy.

    3. REVIEW DOCUMENTS: I automatically review uploaded documents checking
       quality, freshness, type match, name match, completeness, and fraud
       indicators. I auto-approve clear passes and flag issues.

    4. CALCULATE INCOME: I read paystubs, W2s, and tax returns to calculate
       qualifying income per Fannie Mae guidelines, including trending
       analysis and DTI calculations.

    5. ANALYZE BANK STATEMENTS: I identify large deposits needing sourcing,
       NSF/overdrafts, IRS payment plans, verify income deposits match
       stated income, and find undisclosed recurring debts.

    6. DETECT FROM CALLS: When a call transcript is provided, I extract any
       document-related discussion and create requests automatically.

    7. CROSS-VALIDATE: I compare data across all documents for a loan to find
       inconsistencies that may indicate errors or fraud.

    8. MANAGE FOLLOW-UPS: I create and manage automated follow-up campaigns
       for missing documents, including email, SMS, and appointment scheduling.
    """

    @property
    def name(self) -> str:
        return "DocumentIntelligenceAgent"

    @property
    def description(self) -> str:
        return (
            "AI-powered document intelligence hub for mortgage document management "
            "including classification, review, income calculation, bank statement "
            "analysis, call transcript extraction, cross-validation, and follow-up automation"
        )

    def _register_tools(self):
        """Register all document intelligence tools"""

        # Tool 1: Analyze Application for Documents
        self.register_tool(AgentTool(
            name="analyze_application_for_documents",
            description="Analyze a loan application (POS data) to determine exactly which "
                       "documents are required based on loan type, borrower profile, income "
                       "type, occupancy, and special circumstances.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_application_for_documents,
            input_schema=AnalyzeApplicationInput,
        ))

        # Tool 2: Classify Document
        self.register_tool(AgentTool(
            name="classify_document",
            description="Run AI classification on an uploaded document to identify its type "
                       "(paystub, W2, tax return, bank statement, etc.) with confidence "
                       "scoring and alternative predictions.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._classify_document,
            input_schema=ClassifyDocumentInput,
        ))

        # Tool 3: Review Document
        self.register_tool(AgentTool(
            name="review_document",
            description="Run AI-powered review on an uploaded document checking quality, "
                       "freshness, type match, name match, completeness, screenshot "
                       "detection, and fraud indicators. Returns approve/reject decision.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._review_document,
            input_schema=ReviewDocumentInput,
        ))

        # Tool 4: Batch Review Loan Documents
        self.register_tool(AgentTool(
            name="batch_review_loan_documents",
            description="Review all unreviewed documents for a loan at once. Returns "
                       "summary with counts of approved, rejected, and needs-review documents.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._batch_review_loan_documents,
            input_schema=BatchReviewInput,
        ))

        # Tool 5: Calculate Income
        self.register_tool(AgentTool(
            name="calculate_income",
            description="Calculate qualifying income from income documents (paystubs, W2s, "
                       "tax returns) per underwriting guidelines. Returns total qualifying "
                       "income, sources, DTI ratios, and flags.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_income,
            input_schema=CalculateIncomeInput,
        ))

        # Tool 6: Analyze Bank Statements
        self.register_tool(AgentTool(
            name="analyze_bank_statements",
            description="Analyze bank statements for large deposits needing sourcing, "
                       "NSF/overdrafts, IRS payment plans, income deposit verification, "
                       "and undisclosed recurring debts.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_bank_statements,
            input_schema=AnalyzeBankStatementsInput,
        ))

        # Tool 7: Analyze Call for Documents
        self.register_tool(AgentTool(
            name="analyze_call_for_documents",
            description="Analyze a call transcript to detect any document-related "
                       "discussion and automatically create document requests for "
                       "high-confidence needs.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._analyze_call_for_documents,
            input_schema=AnalyzeCallInput,
        ))

        # Tool 8: Get Missing Documents
        self.register_tool(AgentTool(
            name="get_missing_documents",
            description="Compare required documents (from needs list) against received "
                       "documents to identify what is still missing for a loan.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_missing_documents,
            input_schema=GetMissingDocumentsInput,
        ))

        # Tool 9: Get Document Completeness
        self.register_tool(AgentTool(
            name="get_document_completeness",
            description="Get overall document completeness percentage and per-category "
                       "breakdown (income, assets, property, identity, credit).",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_document_completeness,
            input_schema=GetDocumentCompletenessInput,
        ))

        # Tool 10: Cross Validate Documents
        self.register_tool(AgentTool(
            name="cross_validate_documents",
            description="Cross-validate data across all documents for a loan to detect "
                       "inconsistencies that may indicate errors or fraud. Compares "
                       "names, addresses, income, and employment across documents.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._cross_validate_documents,
            input_schema=CrossValidateInput,
        ))

        # Tool 11: Create Follow-Up
        self.register_tool(AgentTool(
            name="create_follow_up",
            description="Create an automated follow-up campaign for specified outstanding "
                       "document requests. Sends email/SMS reminders and can schedule "
                       "appointments.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._create_follow_up,
            input_schema=CreateFollowUpInput,
        ))

        # Tool 12: Get Income Tasks
        self.register_tool(AgentTool(
            name="get_income_tasks",
            description="Get all pending income verification tasks for a loan, including "
                       "items flagged by income calculation (declining income, employment "
                       "gaps, document inconsistencies).",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_income_tasks,
            input_schema=GetIncomeTasksInput,
        ))

        # Tool 13: Get Bank Analysis Flags
        self.register_tool(AgentTool(
            name="get_bank_analysis_flags",
            description="Get all flags from bank statement analysis for a loan, including "
                       "large deposits, NSF events, IRS payments, and irregular patterns.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_bank_analysis_flags,
            input_schema=GetBankAnalysisFlagsInput,
        ))

        # Tool 14: Generate Needs List
        self.register_tool(AgentTool(
            name="generate_needs_list",
            description="Generate a complete document needs list based on loan program, "
                       "occupancy type, income type, and borrower profile. Creates "
                       "document request records.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_needs_list,
            input_schema=GenerateNeedsListInput,
        ))

        # Tool 15: Get Document Status Summary
        self.register_tool(AgentTool(
            name="get_document_status_summary",
            description="Get comprehensive document status summary: total needed, "
                       "received, approved, rejected, missing, expired, and follow-up "
                       "campaign status.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_document_status_summary,
            input_schema=GetDocumentStatusSummaryInput,
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _analyze_application_for_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Analyze a loan application to determine required documents."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan belongs to this organization
            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.pos_analyzer_service import get_pos_analyzer_service
            service = get_pos_analyzer_service(db)
            result = service.analyze_application(loan_id)

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "POS analysis failed",
                )

            requirements = []
            for req in result.requirements:
                requirements.append({
                    "doc_type": req.doc_type,
                    "title": req.title,
                    "description": req.description,
                    "category": req.category,
                    "priority": req.priority,
                    "applies_to": req.applies_to,
                    "required_count": req.required_count,
                    "freshness_days": req.freshness_days,
                    "reason": req.reason,
                })

            self.audit_log(
                "analyze_application_for_documents", "loan",
                entity_id=str(loan_id),
                details={"total_needed": result.total_documents_needed},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "total_documents_needed": result.total_documents_needed,
                    "categories": result.categories,
                    "requirements": requirements,
                    "analysis_notes": result.analysis_notes,
                },
                message=f"Loan {loan.loan_number}: {result.total_documents_needed} documents required",
            )

        except Exception as e:
            logger.exception(f"analyze_application_for_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _classify_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Run AI classification on an uploaded document."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify document belongs to org via loan
            doc = db.execute(
                text("""
                    SELECT sd.id, sd.filename, sd.mime_type, sd.doc_type,
                           sd.loan_id, l.loan_number
                    FROM smart_documents sd
                    JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                    WHERE sd.id = :document_id
                """),
                {"document_id": document_id, "org_id": org_id},
            ).fetchone()

            if not doc:
                return ToolResult(
                    success=False,
                    error=f"Document {document_id} not found or access denied",
                )

            from services.smart_docs.ai_classifier_service import get_ai_classifier_service
            classifier = get_ai_classifier_service()

            # Fetch file content from S3
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3_service = get_smart_docs_s3_service()
            file_bytes = s3_service.download_file(document_id)

            if not file_bytes:
                return ToolResult(
                    success=False,
                    error="Could not retrieve document content for classification",
                )

            result = classifier.classify_document(
                file_bytes, doc.mime_type, doc.filename
            )

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "Classification failed",
                )

            self.audit_log(
                "classify_document", "document",
                entity_id=str(document_id),
                details={
                    "predicted_type": result.predicted_type,
                    "confidence": result.confidence,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "loan_number": doc.loan_number,
                    "current_type": doc.doc_type,
                    "predicted_type": result.predicted_type,
                    "confidence": result.confidence,
                    "alternatives": result.alternatives,
                    "features_detected": result.features_detected,
                    "model_used": result.model_used,
                    "duration_ms": result.duration_ms,
                },
                message=f"Classified as {result.predicted_type} ({result.confidence}% confidence)",
            )

        except Exception as e:
            logger.exception(f"classify_document failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _review_document(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Run AI-powered review on an uploaded document."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify document belongs to org
            doc = db.execute(
                text("""
                    SELECT sd.id, sd.filename, sd.doc_type, sd.loan_id,
                           l.loan_number
                    FROM smart_documents sd
                    JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id
                    WHERE sd.id = :document_id
                """),
                {"document_id": document_id, "org_id": org_id},
            ).fetchone()

            if not doc:
                return ToolResult(
                    success=False,
                    error=f"Document {document_id} not found or access denied",
                )

            from services.smart_docs.ai_review_service import get_ai_review_service
            review_service = get_ai_review_service(db)
            decision = review_service.review_document(document_id)

            self.audit_log(
                "review_document", "document",
                entity_id=str(document_id),
                details={
                    "decision": decision.decision,
                    "auto_approved": decision.auto_approved,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "decision": decision.decision,
                    "confidence": decision.confidence,
                    "reasons": decision.reasons,
                    "rejection_category": decision.rejection_category,
                    "fix_instructions": decision.fix_instructions,
                    "quality_score": decision.quality_score,
                    "completeness_score": decision.completeness_score,
                    "readability_score": decision.readability_score,
                    "freshness_valid": decision.freshness_valid,
                    "type_match": decision.type_match,
                    "name_match": decision.name_match,
                    "auto_approved": decision.auto_approved,
                    "needs_human_review": decision.needs_human_review,
                    "review_priority": decision.review_priority,
                },
                message=f"Review: {decision.decision} (confidence {decision.confidence}%)",
            )

        except Exception as e:
            logger.exception(f"review_document failed for document {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _batch_review_loan_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Review all unreviewed documents for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Find all unreviewed documents
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
                    message="No unreviewed documents found for this loan",
                )

            from services.smart_docs.ai_review_service import get_ai_review_service
            review_service = get_ai_review_service(db)

            results = []
            accepted = 0
            rejected = 0
            needs_review = 0
            errors = 0

            for doc in unreviewed:
                try:
                    decision = review_service.review_document(doc.id)
                    status = decision.decision
                    if status == "ACCEPT":
                        accepted += 1
                    elif status == "REJECT":
                        rejected += 1
                    else:
                        needs_review += 1

                    results.append({
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "doc_type": doc.doc_type,
                        "decision": status,
                        "confidence": decision.confidence,
                        "reasons": decision.reasons[:2],  # Truncate for summary
                    })
                except Exception as doc_err:
                    logger.warning(
                        f"Batch review: error reviewing doc {doc.id}: {doc_err}"
                    )
                    errors += 1
                    results.append({
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "doc_type": doc.doc_type,
                        "decision": "ERROR",
                        "error": str(doc_err),
                    })

            self.audit_log(
                "batch_review_loan_documents", "loan",
                entity_id=str(loan_id),
                details={
                    "total": len(unreviewed),
                    "accepted": accepted,
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
                    "total_reviewed": len(unreviewed),
                    "accepted": accepted,
                    "rejected": rejected,
                    "needs_review": needs_review,
                    "errors": errors,
                    "results": results,
                },
                message=(
                    f"Batch review: {accepted} accepted, {rejected} rejected, "
                    f"{needs_review} needs review out of {len(unreviewed)}"
                ),
            )

        except Exception as e:
            logger.exception(f"batch_review_loan_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_income(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Calculate qualifying income from income documents."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.income_calculator_service import (
                get_income_calculator_service,
            )
            service = get_income_calculator_service(db)
            result = service.calculate_income(loan_id=loan_id, borrower_id=borrower_id)

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "Income calculation failed",
                )

            sources = []
            for src in result.sources:
                sources.append({
                    "source_type": src.source_type,
                    "employer": getattr(src, "employer", None),
                    "monthly_amount": float(src.monthly_amount),
                    "annual_amount": float(src.annual_amount),
                    "method": src.calculation_method,
                    "confidence": getattr(src, "confidence", None),
                })

            self.audit_log(
                "calculate_income", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "total_monthly": float(result.total_qualifying_monthly),
                    "source_count": len(result.sources),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "total_qualifying_monthly": float(result.total_qualifying_monthly),
                    "total_qualifying_annual": float(result.total_qualifying_annual),
                    "calculation_method": result.calculation_method,
                    "dti_front_end": float(result.dti_front_end) if result.dti_front_end else None,
                    "dti_back_end": float(result.dti_back_end) if result.dti_back_end else None,
                    "confidence": result.confidence,
                    "sources": sources,
                    "flags": result.flags,
                    "recommendations": result.recommendations,
                    "tasks_to_create": result.tasks_to_create,
                },
                message=(
                    f"Qualifying income: ${float(result.total_qualifying_monthly):,.2f}/mo "
                    f"({len(result.sources)} sources, {len(result.flags)} flags)"
                ),
            )

        except Exception as e:
            logger.exception(f"calculate_income failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_bank_statements(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Analyze bank statements for red flags and verification."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Query bank statement analysis results from the DB
            # (bank_statement_analyses table populated by extraction service)
            analyses = db.execute(
                text("""
                    SELECT
                        id, document_id, statement_period_start, statement_period_end,
                        beginning_balance, ending_balance, total_deposits,
                        total_withdrawals, large_deposit_count, nsf_count,
                        flags, status, analyzed_at
                    FROM bank_statement_analyses
                    WHERE loan_id = :loan_id AND borrower_id = :borrower_id
                    ORDER BY statement_period_start DESC
                """),
                {"loan_id": loan_id, "borrower_id": borrower_id},
            ).fetchall()

            if not analyses:
                # No existing analysis -- check if bank statements exist
                stmt_count = db.execute(
                    text("""
                        SELECT COUNT(*) as cnt
                        FROM smart_documents
                        WHERE loan_id = :loan_id AND doc_type = 'BANK_STATEMENT'
                    """),
                    {"loan_id": loan_id},
                ).fetchone()

                if stmt_count and stmt_count.cnt > 0:
                    return ToolResult(
                        success=True,
                        data={
                            "loan_id": loan_id,
                            "loan_number": loan.loan_number,
                            "status": "pending_analysis",
                            "bank_statements_found": stmt_count.cnt,
                            "message": "Bank statements found but not yet analyzed. "
                                       "Run extraction service first.",
                        },
                        message=f"{stmt_count.cnt} bank statements awaiting analysis",
                    )
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "status": "no_statements",
                        "message": "No bank statements found for this borrower",
                    },
                    message="No bank statements found",
                )

            total_large_deposits = 0
            total_nsf = 0
            all_flags = []
            statements = []

            for a in analyses:
                large_deps = a.large_deposit_count or 0
                nsf = a.nsf_count or 0
                total_large_deposits += large_deps
                total_nsf += nsf

                flags = a.flags if isinstance(a.flags, list) else []
                all_flags.extend(flags)

                statements.append({
                    "analysis_id": a.id,
                    "document_id": a.document_id,
                    "period": f"{a.statement_period_start} to {a.statement_period_end}",
                    "beginning_balance": float(a.beginning_balance or 0),
                    "ending_balance": float(a.ending_balance or 0),
                    "total_deposits": float(a.total_deposits or 0),
                    "total_withdrawals": float(a.total_withdrawals or 0),
                    "large_deposit_count": large_deps,
                    "nsf_count": nsf,
                    "flags": flags,
                    "status": a.status,
                })

            risk_level = "low"
            if total_large_deposits > 3 or total_nsf > 2:
                risk_level = "high"
            elif total_large_deposits > 0 or total_nsf > 0:
                risk_level = "medium"

            self.audit_log(
                "analyze_bank_statements", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "statements_analyzed": len(analyses),
                    "risk_level": risk_level,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "statements_analyzed": len(analyses),
                    "risk_level": risk_level,
                    "total_large_deposits": total_large_deposits,
                    "total_nsf_events": total_nsf,
                    "all_flags": all_flags,
                    "statements": statements,
                },
                message=(
                    f"Analyzed {len(analyses)} statements: risk={risk_level}, "
                    f"{total_large_deposits} large deposits, {total_nsf} NSF events"
                ),
            )

        except Exception as e:
            logger.exception(f"analyze_bank_statements failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _analyze_call_for_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Analyze a call transcript to detect document needs."""
        from database import SessionLocal

        call_id = input_data["call_id"]
        transcript = input_data["transcript"]
        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.call_intel_extractor import get_call_intel_extractor
            extractor = get_call_intel_extractor(db)
            result = extractor.analyze_call(
                call_id=call_id,
                transcript=transcript,
                loan_id=loan_id,
            )

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "Call analysis failed",
                )

            needs = []
            for need in result.document_needs:
                needs.append({
                    "doc_type": need.doc_type,
                    "confidence": need.confidence,
                    "source": need.source,
                    "reason": need.reason,
                    "auto_created": need.auto_created,
                })

            self.audit_log(
                "analyze_call_for_documents", "loan",
                entity_id=str(loan_id),
                details={
                    "call_id": call_id,
                    "total_needs": result.total_needs,
                    "auto_created": result.auto_create_count,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "call_id": call_id,
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "total_needs_detected": result.total_needs,
                    "auto_created_requests": result.auto_create_count,
                    "circumstances_detected": result.circumstances_detected,
                    "summary": result.summary,
                    "document_needs": needs,
                },
                message=(
                    f"Detected {result.total_needs} document needs from call "
                    f"({result.auto_create_count} auto-created)"
                ),
            )

        except Exception as e:
            logger.exception(f"analyze_call_for_documents failed for call {call_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_missing_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get missing documents by comparing requirements vs received."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get all open/pending requests (the needs list)
            open_requests = db.execute(
                text("""
                    SELECT id, doc_type, title, priority, applies_to, status
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id AND status IN ('OPEN', 'REJECTED')
                    ORDER BY
                        CASE priority
                            WHEN 'CRITICAL' THEN 1
                            WHEN 'HIGH' THEN 2
                            WHEN 'NORMAL' THEN 3
                            WHEN 'LOW' THEN 4
                        END
                """),
                {"loan_id": loan_id},
            ).fetchall()

            missing = []
            for req in open_requests:
                missing.append({
                    "request_id": req.id,
                    "doc_type": req.doc_type,
                    "title": req.title,
                    "priority": req.priority,
                    "applies_to": req.applies_to,
                    "status": req.status,
                })

            # Count received/accepted
            received = db.execute(
                text("""
                    SELECT COUNT(*) as cnt FROM smart_document_requests
                    WHERE loan_id = :loan_id AND status = 'ACCEPTED'
                """),
                {"loan_id": loan_id},
            ).fetchone()

            total_requests = db.execute(
                text("""
                    SELECT COUNT(*) as cnt FROM smart_document_requests
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            self.audit_log(
                "get_missing_documents", "loan",
                entity_id=str(loan_id),
                details={"missing_count": len(missing)},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "total_required": total_requests.cnt if total_requests else 0,
                    "received": received.cnt if received else 0,
                    "missing_count": len(missing),
                    "missing_documents": missing,
                    "critical_missing": len([m for m in missing if m["priority"] == "CRITICAL"]),
                    "high_missing": len([m for m in missing if m["priority"] == "HIGH"]),
                },
                message=(
                    f"Missing: {len(missing)} documents "
                    f"({len([m for m in missing if m['priority'] == 'CRITICAL'])} critical)"
                ),
            )

        except Exception as e:
            logger.exception(f"get_missing_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_document_completeness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get document completeness percentage and per-category breakdown."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get counts by category and status
            category_stats = db.execute(
                text("""
                    SELECT
                        COALESCE(category, 'other') as category,
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'ACCEPTED' THEN 1 END) as accepted,
                        COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open,
                        COUNT(CASE WHEN status = 'REJECTED' THEN 1 END) as rejected,
                        COUNT(CASE WHEN status = 'PENDING_REVIEW' THEN 1 END) as pending_review,
                        COUNT(CASE WHEN status = 'WAIVED' THEN 1 END) as waived
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id
                    GROUP BY COALESCE(category, 'other')
                    ORDER BY category
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not category_stats:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "loan_number": loan.loan_number,
                        "overall_completeness": 0,
                        "message": "No document requests found. Generate needs list first.",
                    },
                    message="No document requests found for this loan",
                )

            total_all = 0
            completed_all = 0
            categories = []

            for cat in category_stats:
                total = cat.total
                completed = cat.accepted + cat.waived
                total_all += total
                completed_all += completed
                pct = round((completed / total) * 100, 1) if total > 0 else 0

                categories.append({
                    "category": cat.category,
                    "total": total,
                    "accepted": cat.accepted,
                    "open": cat.open,
                    "rejected": cat.rejected,
                    "pending_review": cat.pending_review,
                    "waived": cat.waived,
                    "completeness_pct": pct,
                })

            overall_pct = round(
                (completed_all / total_all) * 100, 1
            ) if total_all > 0 else 0

            self.audit_log(
                "get_document_completeness", "loan",
                entity_id=str(loan_id),
                details={"completeness_pct": overall_pct},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "overall_completeness": overall_pct,
                    "total_required": total_all,
                    "total_completed": completed_all,
                    "categories": categories,
                },
                message=f"Document completeness: {overall_pct}% ({completed_all}/{total_all})",
            )

        except Exception as e:
            logger.exception(f"get_document_completeness failed for loan {loan_id}")
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
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get all accepted smart documents with their extracted data
            docs = db.execute(
                text("""
                    SELECT
                        sd.id, sd.doc_type, sd.filename,
                        sde.extracted_data, sde.extracted_name,
                        sde.extracted_address, sde.extracted_employer,
                        sde.extracted_income
                    FROM smart_documents sd
                    LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
                    WHERE sd.loan_id = :loan_id
                        AND sd.review_decision = 'ACCEPT'
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
                        "message": "Need at least 2 accepted documents to cross-validate",
                    },
                    message="Insufficient documents for cross-validation",
                )

            # Build cross-validation checks
            inconsistencies = []
            names = {}
            addresses = {}
            employers = {}
            incomes = {}

            for doc in docs:
                doc_type = doc.doc_type
                doc_label = f"{doc_type} ({doc.filename})"

                if doc.extracted_name:
                    names[doc_label] = doc.extracted_name
                if doc.extracted_address:
                    addresses[doc_label] = doc.extracted_address
                if doc.extracted_employer:
                    employers[doc_label] = doc.extracted_employer
                if doc.extracted_income:
                    incomes[doc_label] = doc.extracted_income

            # Check name consistency
            unique_names = set(
                n.strip().lower() for n in names.values() if n
            )
            if len(unique_names) > 1:
                inconsistencies.append({
                    "field": "name",
                    "severity": "high",
                    "description": "Name discrepancy across documents",
                    "details": names,
                })

            # Check address consistency
            unique_addresses = set(
                a.strip().lower() for a in addresses.values() if a
            )
            if len(unique_addresses) > 1:
                inconsistencies.append({
                    "field": "address",
                    "severity": "medium",
                    "description": "Address discrepancy across documents",
                    "details": addresses,
                })

            # Check employer consistency
            unique_employers = set(
                e.strip().lower() for e in employers.values() if e
            )
            if len(unique_employers) > 1:
                inconsistencies.append({
                    "field": "employer",
                    "severity": "medium",
                    "description": "Employer name discrepancy across documents",
                    "details": employers,
                })

            # Check income consistency (> 10% variance)
            income_values = [
                float(v) for v in incomes.values() if v is not None
            ]
            if len(income_values) >= 2:
                max_income = max(income_values)
                min_income = min(income_values)
                if min_income > 0:
                    variance_pct = ((max_income - min_income) / min_income) * 100
                    if variance_pct > 10:
                        inconsistencies.append({
                            "field": "income",
                            "severity": "high",
                            "description": f"Income variance of {variance_pct:.1f}% across documents",
                            "details": incomes,
                        })

            risk_assessment = "clean"
            if any(i["severity"] == "high" for i in inconsistencies):
                risk_assessment = "high_risk"
            elif inconsistencies:
                risk_assessment = "review_recommended"

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
                    "risk_assessment": risk_assessment,
                    "inconsistency_count": len(inconsistencies),
                    "inconsistencies": inconsistencies,
                },
                message=(
                    f"Cross-validation: {len(inconsistencies)} inconsistencies, "
                    f"risk={risk_assessment}"
                ),
            )

        except Exception as e:
            logger.exception(f"cross_validate_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_follow_up(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create a follow-up campaign for outstanding document requests."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        request_ids_str = input_data["request_ids"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Parse comma-separated IDs
            try:
                request_ids = [
                    int(rid.strip())
                    for rid in request_ids_str.split(",")
                    if rid.strip()
                ]
            except ValueError:
                return ToolResult(
                    success=False,
                    error="Invalid request_ids format. Use comma-separated integers.",
                )

            if not request_ids:
                return ToolResult(
                    success=False,
                    error="No request IDs provided",
                )

            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)

            user_id = context.get("user_id")
            result = service.create_campaign(
                loan_id=loan_id,
                borrower_id=borrower_id,
                organization_id=int(org_id) if org_id else 0,
                campaign_type="INITIAL_REQUEST",
                request_ids=request_ids,
                created_by_user_id=int(user_id) if user_id else None,
            )

            self.audit_log(
                "create_follow_up", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "request_ids": request_ids,
                    "campaign_id": result.get("campaign_id"),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "campaign_id": result.get("campaign_id"),
                    "request_ids": request_ids,
                    "steps": result.get("steps", []),
                    "status": result.get("status", "created"),
                },
                message=(
                    f"Follow-up campaign created for {len(request_ids)} document requests"
                ),
            )

        except Exception as e:
            logger.exception(f"create_follow_up failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_income_tasks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get pending income verification tasks for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            tasks = db.execute(
                text("""
                    SELECT
                        id, task_type, description, priority,
                        status, assigned_to_user_id,
                        created_at, due_date
                    FROM income_verification_tasks
                    WHERE loan_id = :loan_id AND status != 'completed'
                    ORDER BY
                        CASE priority
                            WHEN 'CRITICAL' THEN 1
                            WHEN 'HIGH' THEN 2
                            WHEN 'NORMAL' THEN 3
                            WHEN 'LOW' THEN 4
                        END,
                        due_date ASC NULLS LAST
                """),
                {"loan_id": loan_id},
            ).fetchall()

            task_list = []
            for t in tasks:
                task_list.append({
                    "task_id": t.id,
                    "task_type": t.task_type,
                    "description": t.description,
                    "priority": t.priority,
                    "status": t.status,
                    "assigned_to": t.assigned_to_user_id,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                })

            self.audit_log(
                "get_income_tasks", "loan",
                entity_id=str(loan_id),
                details={"pending_count": len(task_list)},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "pending_count": len(task_list),
                    "tasks": task_list,
                },
                message=f"{len(task_list)} pending income verification tasks",
            )

        except Exception as e:
            logger.exception(f"get_income_tasks failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_bank_analysis_flags(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get all flags from bank statement analysis for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get all flags from bank statement analyses
            analyses = db.execute(
                text("""
                    SELECT
                        id, document_id, statement_period_start,
                        statement_period_end, flags, large_deposit_count,
                        nsf_count, status
                    FROM bank_statement_analyses
                    WHERE loan_id = :loan_id
                    ORDER BY statement_period_start DESC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            all_flags = []
            for a in analyses:
                flags = a.flags if isinstance(a.flags, list) else []
                for flag in flags:
                    if isinstance(flag, dict):
                        flag["analysis_id"] = a.id
                        flag["period"] = (
                            f"{a.statement_period_start} to {a.statement_period_end}"
                        )
                        all_flags.append(flag)
                    else:
                        all_flags.append({
                            "analysis_id": a.id,
                            "period": f"{a.statement_period_start} to {a.statement_period_end}",
                            "flag": str(flag),
                        })

            self.audit_log(
                "get_bank_analysis_flags", "loan",
                entity_id=str(loan_id),
                details={"flag_count": len(all_flags)},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "total_flags": len(all_flags),
                    "statements_analyzed": len(analyses),
                    "flags": all_flags,
                },
                message=f"{len(all_flags)} bank statement flags across {len(analyses)} statements",
            )

        except Exception as e:
            logger.exception(f"get_bank_analysis_flags failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_needs_list(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate complete document needs list from POS data."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        loan_program = input_data["loan_program"]
        occupancy_type = input_data["occupancy_type"]
        income_type = input_data["income_type"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number, borrower_name FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            from services.smart_docs.needs_list_generator import NeedsListGenerator
            generator = NeedsListGenerator()
            requests = generator.generate(
                db=db,
                loan_id=loan_id,
                loan_program=loan_program,
                occupancy_type=occupancy_type,
                income_type=income_type,
                borrower_id=borrower_id,
            )

            created = []
            for req in requests:
                created.append({
                    "request_id": req.id if hasattr(req, "id") else None,
                    "doc_type": req.doc_type if hasattr(req, "doc_type") else str(req),
                    "title": req.title if hasattr(req, "title") else None,
                    "priority": req.priority if hasattr(req, "priority") else "NORMAL",
                    "applies_to": req.applies_to if hasattr(req, "applies_to") else "BORROWER",
                    "category": req.category if hasattr(req, "category") else None,
                })

            self.audit_log(
                "generate_needs_list", "loan",
                entity_id=str(loan_id),
                details={
                    "loan_program": loan_program,
                    "occupancy_type": occupancy_type,
                    "income_type": income_type,
                    "documents_generated": len(created),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "loan_program": loan_program,
                    "occupancy_type": occupancy_type,
                    "income_type": income_type,
                    "total_documents": len(created),
                    "requests": created,
                },
                message=f"Generated needs list: {len(created)} documents required",
            )

        except Exception as e:
            logger.exception(f"generate_needs_list failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_document_status_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get comprehensive document status summary."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number, borrower_name, stage FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Request status counts
            request_stats = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open,
                        COUNT(CASE WHEN status = 'PENDING_REVIEW' THEN 1 END) as pending_review,
                        COUNT(CASE WHEN status = 'ACCEPTED' THEN 1 END) as accepted,
                        COUNT(CASE WHEN status = 'REJECTED' THEN 1 END) as rejected,
                        COUNT(CASE WHEN status = 'WAIVED' THEN 1 END) as waived
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            # Smart document counts
            doc_stats = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total_uploaded,
                        COUNT(CASE WHEN review_decision = 'ACCEPT' THEN 1 END) as approved,
                        COUNT(CASE WHEN review_decision = 'REJECT' THEN 1 END) as rejected,
                        COUNT(CASE WHEN review_decision = 'NEEDS_REVIEW' THEN 1 END) as needs_review,
                        COUNT(CASE WHEN review_decision IS NULL OR review_decision = '' THEN 1 END) as unreviewed
                    FROM smart_documents
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            # Check for expired documents
            expired = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM smart_documents
                    WHERE loan_id = :loan_id
                        AND freshness_expires_at IS NOT NULL
                        AND freshness_expires_at < CURRENT_TIMESTAMP
                """),
                {"loan_id": loan_id},
            ).fetchone()

            # Active follow-up campaigns
            campaigns = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM followup_campaigns
                    WHERE loan_id = :loan_id AND status = 'ACTIVE'
                """),
                {"loan_id": loan_id},
            ).fetchone()

            total_req = request_stats.total if request_stats else 0
            completed = (
                (request_stats.accepted if request_stats else 0) +
                (request_stats.waived if request_stats else 0)
            )
            completeness_pct = round(
                (completed / total_req) * 100, 1
            ) if total_req > 0 else 0

            self.audit_log(
                "get_document_status_summary", "loan",
                entity_id=str(loan_id),
                details={"completeness_pct": completeness_pct},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "loan_stage": loan.stage,
                    "completeness_pct": completeness_pct,
                    "requests": {
                        "total": total_req,
                        "open": request_stats.open if request_stats else 0,
                        "pending_review": request_stats.pending_review if request_stats else 0,
                        "accepted": request_stats.accepted if request_stats else 0,
                        "rejected": request_stats.rejected if request_stats else 0,
                        "waived": request_stats.waived if request_stats else 0,
                    },
                    "documents": {
                        "total_uploaded": doc_stats.total_uploaded if doc_stats else 0,
                        "approved": doc_stats.approved if doc_stats else 0,
                        "rejected": doc_stats.rejected if doc_stats else 0,
                        "needs_review": doc_stats.needs_review if doc_stats else 0,
                        "unreviewed": doc_stats.unreviewed if doc_stats else 0,
                    },
                    "expired_count": expired.cnt if expired else 0,
                    "active_followup_campaigns": campaigns.cnt if campaigns else 0,
                },
                message=(
                    f"Documents: {completeness_pct}% complete "
                    f"({completed}/{total_req} fulfilled, "
                    f"{expired.cnt if expired else 0} expired)"
                ),
            )

        except Exception as e:
            logger.exception(
                f"get_document_status_summary failed for loan {loan_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
