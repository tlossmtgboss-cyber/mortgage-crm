"""
Document Lifecycle Agent

Specialized agent that orchestrates the entire document journey from
request to approval. Coordinates across document collection, intelligence,
review, and follow-up to ensure every loan has a complete, compliant
document package by closing.

15 Tools:
1. assess_loan_document_needs - Determine ALL documents needed based on loan attributes
2. generate_smart_needs_list - Create prioritized needs list with due dates
3. check_document_completeness - Percentage of required docs received/approved/pending
4. identify_blocking_documents - Which missing docs block loan progression
5. trigger_intelligent_followup - Start follow-up campaign for missing docs
6. route_document_for_review - Route uploaded doc through classification -> review pipeline
7. escalate_stale_documents - Find docs stuck in review > X days and escalate
8. generate_condition_checklist - Create UW condition checklist from AUS + missing docs
9. predict_document_completion - Predict when all docs will be collected
10. recommend_next_action - Single most impactful action to move docs forward
11. batch_process_uploads - Process multiple uploaded documents in one operation
12. generate_borrower_status_update - Borrower-friendly status update of doc progress
13. check_expiring_documents - Find docs about to expire and trigger re-collection
14. coordinate_third_party_orders - Check appraisal/title/insurance status and recommend
15. generate_processor_briefing - Daily briefing for processor on pipeline doc status
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
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


# =============================================================================
# CONSTANTS
# =============================================================================

# Document requirements by loan type / income type / occupancy
LOAN_TYPE_REQUIREMENTS = {
    "conventional": {
        "base": ["paystubs", "w2", "bank_statements", "credit_report", "appraisal",
                 "purchase_contract", "drivers_license", "title", "insurance"],
        "extra": [],
    },
    "fha": {
        "base": ["paystubs", "w2", "bank_statements", "credit_report", "appraisal",
                 "purchase_contract", "drivers_license", "title", "insurance"],
        "extra": ["fha_case_number", "upfront_mip"],
    },
    "va": {
        "base": ["paystubs", "w2", "bank_statements", "credit_report", "appraisal",
                 "purchase_contract", "drivers_license", "title", "insurance"],
        "extra": ["dd214", "certificate_of_eligibility", "va_funding_fee"],
    },
    "usda": {
        "base": ["paystubs", "w2", "bank_statements", "credit_report", "appraisal",
                 "purchase_contract", "drivers_license", "title", "insurance"],
        "extra": ["usda_eligibility", "income_eligibility"],
    },
    "jumbo": {
        "base": ["paystubs", "w2", "bank_statements", "credit_report", "appraisal",
                 "purchase_contract", "drivers_license", "title", "insurance"],
        "extra": ["additional_bank_statements", "investment_statements"],
    },
}

SELF_EMPLOYED_DOCS = ["tax_returns", "profit_loss", "1099", "business_bank_statements"]
INVESTMENT_PROPERTY_DOCS = ["rental_agreement", "rental_income_schedule"]
GIFT_FUND_DOCS = ["gift_letter", "gift_donor_bank_statements"]

# Priority tiers for document collection
DOC_PRIORITY = {
    "critical": ["paystubs", "w2", "bank_statements", "drivers_license", "credit_report"],
    "high": ["purchase_contract", "appraisal", "tax_returns", "title"],
    "medium": ["insurance", "profit_loss", "1099", "investment_statements"],
    "low": ["gift_letter", "divorce_decree", "hoa", "ssn_card"],
}

# Stages where specific docs become blocking
STAGE_BLOCKERS = {
    "PROCESSING": ["paystubs", "w2", "bank_statements", "drivers_license"],
    "SUBMITTED": ["appraisal", "title", "credit_report"],
    "UNDERWRITING": ["appraisal", "tax_returns", "profit_loss"],
    "CONDITIONAL_APPROVAL": [],  # Conditions are dynamic
    "CLEAR_TO_CLOSE": ["insurance", "title"],
}


# =============================================================================
# INPUT SCHEMAS
# =============================================================================

class AssessLoanDocumentNeedsInput(BaseModel):
    """Input for assess_loan_document_needs"""
    loan_id: int = Field(..., description="Loan ID to assess")


class GenerateSmartNeedsListInput(BaseModel):
    """Input for generate_smart_needs_list"""
    loan_id: int = Field(..., description="Loan ID to generate needs list for")


class CheckDocumentCompletenessInput(BaseModel):
    """Input for check_document_completeness"""
    loan_id: int = Field(..., description="Loan ID to check")


class IdentifyBlockingDocumentsInput(BaseModel):
    """Input for identify_blocking_documents"""
    loan_id: int = Field(..., description="Loan ID to check for blocking docs")


class TriggerIntelligentFollowupInput(BaseModel):
    """Input for trigger_intelligent_followup"""
    loan_id: int = Field(..., description="Loan ID for follow-up")
    document_types: Optional[List[str]] = Field(None, description="Specific doc types to follow up on (all missing if omitted)")
    channel: str = Field(default="auto", description="Channel: auto, email, sms, both")


class RouteDocumentForReviewInput(BaseModel):
    """Input for route_document_for_review"""
    document_id: int = Field(..., description="Document ID to route for review")


class EscalateStaleDocumentsInput(BaseModel):
    """Input for escalate_stale_documents"""
    stale_threshold_days: int = Field(default=3, description="Days in review before escalation")
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")


class GenerateConditionChecklistInput(BaseModel):
    """Input for generate_condition_checklist"""
    loan_id: int = Field(..., description="Loan ID to generate conditions for")


class PredictDocumentCompletionInput(BaseModel):
    """Input for predict_document_completion"""
    loan_id: int = Field(..., description="Loan ID for prediction")


class RecommendNextActionInput(BaseModel):
    """Input for recommend_next_action"""
    loan_id: int = Field(..., description="Loan ID for recommendation")


class BatchProcessUploadsInput(BaseModel):
    """Input for batch_process_uploads"""
    loan_id: int = Field(..., description="Loan ID with new uploads to process")
    document_ids: Optional[List[int]] = Field(None, description="Specific document IDs (all unprocessed if omitted)")


class GenerateBorrowerStatusUpdateInput(BaseModel):
    """Input for generate_borrower_status_update"""
    loan_id: int = Field(..., description="Loan ID for borrower update")


class CheckExpiringDocumentsInput(BaseModel):
    """Input for check_expiring_documents"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID (all active loans if omitted)")
    days_ahead: int = Field(default=30, description="Days ahead to check for expiration")


class CoordinateThirdPartyOrdersInput(BaseModel):
    """Input for coordinate_third_party_orders"""
    loan_id: int = Field(..., description="Loan ID to coordinate orders for")


class GenerateProcessorBriefingInput(BaseModel):
    """Input for generate_processor_briefing"""
    lo_id: Optional[int] = Field(None, description="Filter by loan officer")
    processor_id: Optional[int] = Field(None, description="Filter by processor")


# =============================================================================
# DOCUMENT LIFECYCLE AGENT
# =============================================================================

@AgentRegistry.register
class DocumentLifecycleAgent(SpecializedAgent):
    """
    Orchestrates the entire document journey from request to approval.

    Coordinates across document collection, intelligence, review, and
    follow-up to ensure every loan has a complete, compliant document
    package by closing. Prioritizes based on closing date, pipeline stage,
    and blocking impact.
    """

    @property
    def name(self) -> str:
        return "DocumentLifecycleAgent"

    @property
    def description(self) -> str:
        return (
            "Orchestrates the full document lifecycle: needs assessment, "
            "collection, review, approval, and compliance tracking"
        )

    def _register_tools(self):
        """Register all 15 document lifecycle tools"""

        self.register_tool(AgentTool(
            name="assess_loan_document_needs",
            description=(
                "Given a loan, determine ALL documents needed based on loan type, "
                "income type, occupancy, and property type. Returns categorized list "
                "with priority tiers."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_loan_document_needs,
            input_schema=AssessLoanDocumentNeedsInput,
        ))

        self.register_tool(AgentTool(
            name="generate_smart_needs_list",
            description=(
                "Create a prioritized needs list with due dates calculated backwards "
                "from the closing date. Groups by urgency tier."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_smart_needs_list,
            input_schema=GenerateSmartNeedsListInput,
        ))

        self.register_tool(AgentTool(
            name="check_document_completeness",
            description=(
                "What percentage of required docs are received, approved, or pending. "
                "Returns detailed breakdown by category."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_document_completeness,
            input_schema=CheckDocumentCompletenessInput,
        ))

        self.register_tool(AgentTool(
            name="identify_blocking_documents",
            description=(
                "Which missing docs are blocking loan progression to the next stage. "
                "Considers current stage and required docs for advancement."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_blocking_documents,
            input_schema=IdentifyBlockingDocumentsInput,
        ))

        self.register_tool(AgentTool(
            name="trigger_intelligent_followup",
            description=(
                "Start follow-up campaign for specific missing docs, choosing optimal "
                "channel based on borrower preferences and doc urgency."
            ),
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._trigger_intelligent_followup,
            input_schema=TriggerIntelligentFollowupInput,
        ))

        self.register_tool(AgentTool(
            name="route_document_for_review",
            description=(
                "Route a newly uploaded document through the AI classification, "
                "review, and approval pipeline."
            ),
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.LOW,
            handler=self._route_document_for_review,
            input_schema=RouteDocumentForReviewInput,
        ))

        self.register_tool(AgentTool(
            name="escalate_stale_documents",
            description=(
                "Find documents stuck in review for more than X days and escalate "
                "to the appropriate reviewer or manager."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._escalate_stale_documents,
            input_schema=EscalateStaleDocumentsInput,
        ))

        self.register_tool(AgentTool(
            name="generate_condition_checklist",
            description=(
                "Create an underwriter condition checklist from AUS findings and "
                "missing documents for a loan."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_condition_checklist,
            input_schema=GenerateConditionChecklistInput,
        ))

        self.register_tool(AgentTool(
            name="predict_document_completion",
            description=(
                "Based on historical patterns, predict when all documents will be "
                "collected for a loan. Flags risk to closing date."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._predict_document_completion,
            input_schema=PredictDocumentCompletionInput,
        ))

        self.register_tool(AgentTool(
            name="recommend_next_action",
            description=(
                "For a loan, determine the single most impactful action to move "
                "the document package forward toward completion."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_next_action,
            input_schema=RecommendNextActionInput,
        ))

        self.register_tool(AgentTool(
            name="batch_process_uploads",
            description=(
                "Process multiple uploaded documents in one operation. Classifies, "
                "validates, and routes each document."
            ),
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.MEDIUM,
            handler=self._batch_process_uploads,
            input_schema=BatchProcessUploadsInput,
        ))

        self.register_tool(AgentTool(
            name="generate_borrower_status_update",
            description=(
                "Create a borrower-friendly status update of their document progress. "
                "Uses warm, clear language with specific next steps."
            ),
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_borrower_status_update,
            input_schema=GenerateBorrowerStatusUpdateInput,
        ))

        self.register_tool(AgentTool(
            name="check_expiring_documents",
            description=(
                "Find documents about to expire (credit, appraisal) and trigger "
                "re-collection before they become stale."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_expiring_documents,
            input_schema=CheckExpiringDocumentsInput,
        ))

        self.register_tool(AgentTool(
            name="coordinate_third_party_orders",
            description=(
                "Check appraisal, title, and insurance order status. Recommend "
                "actions for pending or missing orders."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._coordinate_third_party_orders,
            input_schema=CoordinateThirdPartyOrdersInput,
        ))

        self.register_tool(AgentTool(
            name="generate_processor_briefing",
            description=(
                "Create a daily briefing for a processor showing document status "
                "across their pipeline, highlighting urgent items."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_processor_briefing,
            input_schema=GenerateProcessorBriefingInput,
        ))

    # =========================================================================
    # TOOL IMPLEMENTATIONS
    # =========================================================================

    async def _assess_loan_document_needs(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Determine all documents needed for a loan based on its attributes."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.loan_type, l.stage,
                    l.occupancy_type, l.property_type,
                    l.borrower_name, l.closing_date,
                    l.self_employed, l.gift_funds_used
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            loan_type = (loan.loan_type or "conventional").lower()
            type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])

            required = list(type_reqs["base"]) + list(type_reqs["extra"])

            # Add self-employed docs
            if loan.self_employed:
                required.extend(SELF_EMPLOYED_DOCS)

            # Add investment property docs
            if loan.occupancy_type and loan.occupancy_type.lower() == "investment":
                required.extend(INVESTMENT_PROPERTY_DOCS)

            # Add gift fund docs
            if loan.gift_funds_used:
                required.extend(GIFT_FUND_DOCS)

            # Deduplicate
            required = list(dict.fromkeys(required))

            # Categorize by priority
            categorized = {"critical": [], "high": [], "medium": [], "low": []}
            for doc in required:
                placed = False
                for priority, docs in DOC_PRIORITY.items():
                    if doc in docs:
                        categorized[priority].append(doc)
                        placed = True
                        break
                if not placed:
                    categorized["medium"].append(doc)

            self.audit_log("assess_loan_document_needs", "loan", entity_id=str(loan_id), details={
                "loan_type": loan_type,
                "total_required": len(required),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "loan_type": loan_type,
                    "borrower": loan.borrower_name,
                    "total_required": len(required),
                    "all_required": required,
                    "by_priority": categorized,
                    "flags": {
                        "self_employed": bool(loan.self_employed),
                        "investment_property": (loan.occupancy_type or "").lower() == "investment",
                        "gift_funds": bool(loan.gift_funds_used),
                    },
                },
                message=f"Loan {loan.loan_number}: {len(required)} documents required ({loan_type})",
            )
        except Exception as e:
            logger.exception(f"assess_loan_document_needs failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_smart_needs_list(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Create prioritized needs list with due dates based on closing date."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.loan_type, l.stage,
                    l.closing_date, l.borrower_name,
                    l.self_employed, l.occupancy_type, l.gift_funds_used
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            closing = loan.closing_date
            today = date.today()

            # Calculate milestone dates working backwards from closing
            if closing:
                if isinstance(closing, datetime):
                    closing = closing.date()
                days_to_close = (closing - today).days
            else:
                days_to_close = 30  # Default assumption
                closing = today + timedelta(days=30)

            # Due date tiers relative to closing
            due_dates = {
                "critical": today + timedelta(days=min(3, max(0, days_to_close - 21))),
                "high": today + timedelta(days=min(7, max(0, days_to_close - 14))),
                "medium": today + timedelta(days=min(14, max(0, days_to_close - 7))),
                "low": today + timedelta(days=min(21, max(0, days_to_close - 3))),
            }

            # Get existing docs
            existing = db.execute(text("""
                SELECT doc_type, status FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
            existing_types = {row.doc_type for row in existing if row.status == "active"}

            # Determine required docs
            loan_type = (loan.loan_type or "conventional").lower()
            type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])
            required = list(type_reqs["base"]) + list(type_reqs["extra"])
            if loan.self_employed:
                required.extend(SELF_EMPLOYED_DOCS)
            if loan.occupancy_type and loan.occupancy_type.lower() == "investment":
                required.extend(INVESTMENT_PROPERTY_DOCS)
            if loan.gift_funds_used:
                required.extend(GIFT_FUND_DOCS)
            required = list(dict.fromkeys(required))

            needs_list = []
            for doc in required:
                if doc in existing_types:
                    continue
                # Determine priority
                priority = "medium"
                for p, docs in DOC_PRIORITY.items():
                    if doc in docs:
                        priority = p
                        break
                needs_list.append({
                    "document_type": doc,
                    "priority": priority,
                    "due_date": due_dates[priority].isoformat(),
                    "days_until_due": (due_dates[priority] - today).days,
                    "status": "missing",
                })

            # Sort by due date then priority
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            needs_list.sort(key=lambda x: (priority_order.get(x["priority"], 9), x["due_date"]))

            self.audit_log("generate_smart_needs_list", "loan", entity_id=str(loan_id), details={
                "missing_count": len(needs_list),
                "days_to_close": days_to_close,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "closing_date": closing.isoformat() if closing else None,
                    "days_to_close": days_to_close,
                    "needs_list": needs_list,
                    "total_missing": len(needs_list),
                    "total_required": len(required),
                    "total_received": len(existing_types),
                },
                message=f"{len(needs_list)} docs needed, {days_to_close} days to close",
            )
        except Exception as e:
            logger.exception(f"generate_smart_needs_list failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_document_completeness(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Check what percentage of required docs are received/approved/pending."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.loan_type, l.self_employed,
                       l.occupancy_type, l.gift_funds_used
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Build required list
            loan_type = (loan.loan_type or "conventional").lower()
            type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])
            required = list(type_reqs["base"]) + list(type_reqs["extra"])
            if loan.self_employed:
                required.extend(SELF_EMPLOYED_DOCS)
            if loan.occupancy_type and loan.occupancy_type.lower() == "investment":
                required.extend(INVESTMENT_PROPERTY_DOCS)
            if loan.gift_funds_used:
                required.extend(GIFT_FUND_DOCS)
            required = list(dict.fromkeys(required))

            # Get existing docs with status
            docs = db.execute(text("""
                SELECT doc_type, status FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()

            doc_status_map = {}
            for d in docs:
                doc_status_map[d.doc_type] = d.status

            received = []
            missing = []
            for doc in required:
                status = doc_status_map.get(doc)
                if status == "active":
                    received.append(doc)
                else:
                    missing.append(doc)

            total = len(required)
            pct = round((len(received) / total) * 100, 1) if total > 0 else 0

            self.audit_log("check_document_completeness", "loan", entity_id=str(loan_id), details={
                "completeness_pct": pct,
                "received": len(received),
                "missing": len(missing),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "completeness_pct": pct,
                    "total_required": total,
                    "received_count": len(received),
                    "missing_count": len(missing),
                    "received": received,
                    "missing": missing,
                },
                message=f"Document completeness: {pct}% ({len(received)}/{total})",
            )
        except Exception as e:
            logger.exception(f"check_document_completeness failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_blocking_documents(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Identify which missing docs are blocking loan progression."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.stage, l.closing_date, l.borrower_name
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            stage = loan.stage or "PROCESSING"

            # Get existing active docs
            existing = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id AND status = 'active'
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
            existing_types = {row.doc_type for row in existing}

            # Determine what blocks this stage and the next stage
            stage_order = [
                "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
                "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
                "APPROVED", "CLEAR_TO_CLOSE", "CLOSING", "DOCS_OUT",
            ]
            current_idx = stage_order.index(stage) if stage in stage_order else 2

            blocking_docs = []
            # Check current stage blockers
            current_blockers = STAGE_BLOCKERS.get(stage, [])
            for doc in current_blockers:
                if doc not in existing_types:
                    blocking_docs.append({
                        "document_type": doc,
                        "blocking_stage": stage,
                        "impact": "current_stage",
                        "severity": "critical",
                    })

            # Check next stage blockers
            if current_idx + 1 < len(stage_order):
                next_stage = stage_order[current_idx + 1]
                next_blockers = STAGE_BLOCKERS.get(next_stage, [])
                for doc in next_blockers:
                    if doc not in existing_types and doc not in [b["document_type"] for b in blocking_docs]:
                        blocking_docs.append({
                            "document_type": doc,
                            "blocking_stage": next_stage,
                            "impact": "next_stage",
                            "severity": "high",
                        })

            # Check compliance-required open alerts
            alerts = db.execute(text("""
                SELECT title, description, severity FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
                ORDER BY CASE severity
                    WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3 ELSE 4 END
                LIMIT 5
            """), {"loan_id": loan_id}).fetchall()

            open_conditions = [
                {"title": a.title, "severity": a.severity}
                for a in alerts
            ]

            self.audit_log("identify_blocking_documents", "loan", entity_id=str(loan_id), details={
                "blocking_count": len(blocking_docs),
                "open_conditions": len(open_conditions),
                "stage": stage,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "current_stage": stage,
                    "blocking_documents": blocking_docs,
                    "open_conditions": open_conditions,
                    "total_blocking": len(blocking_docs),
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                },
                message=f"{len(blocking_docs)} documents blocking progression from {stage}",
            )
        except Exception as e:
            logger.exception(f"identify_blocking_documents failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _trigger_intelligent_followup(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Start follow-up campaign for missing docs with optimal channel selection."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        doc_types = input_data.get("document_types")
        channel = input_data.get("channel", "auto")
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name,
                       l.borrower_email, l.borrower_phone,
                       l.closing_date, l.stage
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # If no specific doc types, find all missing
            if not doc_types:
                existing = db.execute(text("""
                    SELECT doc_type FROM documents
                    WHERE loan_id = :loan_id AND organization_id = :org_id AND status = 'active'
                """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
                existing_types = {row.doc_type for row in existing}

                loan_type = "conventional"  # Default
                type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])
                all_required = list(type_reqs["base"])
                doc_types = [d for d in all_required if d not in existing_types]

            if not doc_types:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "message": "No missing documents to follow up on"},
                    message="No missing documents",
                )

            # Auto-select channel based on urgency and availability
            if channel == "auto":
                closing_soon = False
                if loan.closing_date:
                    close_dt = loan.closing_date
                    if isinstance(close_dt, datetime):
                        close_dt = close_dt.date()
                    closing_soon = (close_dt - date.today()).days <= 7

                if closing_soon and loan.borrower_phone:
                    selected_channel = "both"
                elif loan.borrower_email:
                    selected_channel = "email"
                elif loan.borrower_phone:
                    selected_channel = "sms"
                else:
                    selected_channel = "email"
            else:
                selected_channel = channel

            # Determine priority for each doc
            followup_items = []
            for doc in doc_types:
                priority = "medium"
                for p, docs in DOC_PRIORITY.items():
                    if doc in docs:
                        priority = p
                        break
                followup_items.append({
                    "document_type": doc,
                    "priority": priority,
                    "channel": selected_channel,
                })

            self.audit_log("trigger_intelligent_followup", "loan", entity_id=str(loan_id), details={
                "doc_count": len(followup_items),
                "channel": selected_channel,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "channel": selected_channel,
                    "followup_items": followup_items,
                    "total_items": len(followup_items),
                    "contact": {
                        "email": loan.borrower_email if selected_channel in ("email", "both") else None,
                        "phone": loan.borrower_phone if selected_channel in ("sms", "both") else None,
                    },
                    "status": "pending_approval",
                },
                message=f"Follow-up ready for {len(followup_items)} docs via {selected_channel}",
            )
        except Exception as e:
            logger.exception(f"trigger_intelligent_followup failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _route_document_for_review(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Route a newly uploaded document through the review pipeline."""
        from database import SessionLocal

        document_id = input_data["document_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            doc = db.execute(text("""
                SELECT d.id, d.doc_type, d.doc_category, d.status,
                       d.filename, d.loan_id, d.uploaded_at,
                       l.loan_number, l.borrower_name, l.stage as loan_stage
                FROM documents d
                LEFT JOIN loans l ON l.id = d.loan_id
                WHERE d.id = :doc_id AND d.organization_id = :org_id
            """), {"doc_id": document_id, "org_id": org_id}).fetchone()

            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found")

            # Determine review routing
            review_steps = []

            # Step 1: Classification verification
            if doc.doc_type:
                review_steps.append({
                    "step": "classification",
                    "status": "completed",
                    "result": doc.doc_type,
                })
            else:
                review_steps.append({
                    "step": "classification",
                    "status": "needs_ai_classification",
                    "result": None,
                })

            # Step 2: Completeness check
            review_steps.append({
                "step": "completeness_check",
                "status": "pending",
                "description": "Verify document is complete and legible",
            })

            # Step 3: Freshness validation
            review_steps.append({
                "step": "freshness_validation",
                "status": "pending",
                "description": "Verify document is within acceptable date range",
            })

            # Step 4: Final approval routing
            loan_stage = doc.loan_stage or "PROCESSING"
            if loan_stage in ("UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL"):
                reviewer = "underwriter"
            else:
                reviewer = "processor"

            review_steps.append({
                "step": "final_approval",
                "status": "pending",
                "assigned_to": reviewer,
            })

            self.audit_log("route_document_for_review", "document", entity_id=str(document_id), details={
                "doc_type": doc.doc_type,
                "loan_id": doc.loan_id,
                "reviewer": reviewer,
            })

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "loan_number": doc.loan_number,
                    "borrower": doc.borrower_name,
                    "review_pipeline": review_steps,
                    "assigned_reviewer": reviewer,
                    "loan_stage": loan_stage,
                },
                message=f"Document routed to {reviewer} for review",
            )
        except Exception as e:
            logger.exception(f"route_document_for_review failed for doc {document_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _escalate_stale_documents(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Find documents stuck in review and escalate."""
        from database import SessionLocal

        threshold_days = input_data.get("stale_threshold_days", 3)
        lo_id = input_data.get("lo_id")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            params = {"org_id": org_id, "threshold": threshold_days}
            lo_filter = ""
            if lo_id:
                lo_filter = "AND l.loan_officer_id = :lo_id"
                params["lo_id"] = lo_id

            stale = db.execute(text(f"""
                SELECT
                    d.id as doc_id, d.filename, d.doc_type,
                    d.uploaded_at, d.status,
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    l.closing_date, l.stage,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                    EXTRACT(DAY FROM CURRENT_TIMESTAMP - d.uploaded_at) as days_since_upload
                FROM documents d
                JOIN loans l ON l.id = d.loan_id
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE d.organization_id = :org_id
                    AND d.status = 'active'
                    AND d.uploaded_at < CURRENT_TIMESTAMP - INTERVAL '{threshold_days} days'
                    {lo_filter}
                ORDER BY d.uploaded_at ASC
                LIMIT 50
            """), params).fetchall()

            escalations = []
            for row in stale:
                closing_risk = False
                if row.closing_date:
                    close_dt = row.closing_date
                    if isinstance(close_dt, datetime):
                        close_dt = close_dt.date()
                    closing_risk = (close_dt - date.today()).days <= 14

                escalations.append({
                    "document_id": row.doc_id,
                    "filename": row.filename,
                    "doc_type": row.doc_type,
                    "days_in_review": int(row.days_since_upload or 0),
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower": row.borrower_name,
                    "lo_name": row.lo_name,
                    "closing_at_risk": closing_risk,
                    "severity": "critical" if closing_risk else "medium",
                })

            self.audit_log("escalate_stale_documents", details={
                "threshold_days": threshold_days,
                "escalation_count": len(escalations),
            })

            return ToolResult(
                success=True,
                data={
                    "threshold_days": threshold_days,
                    "escalations": escalations,
                    "total_stale": len(escalations),
                    "critical_count": len([e for e in escalations if e["severity"] == "critical"]),
                },
                message=f"{len(escalations)} documents stale (>{threshold_days} days)",
            )
        except Exception as e:
            logger.exception("escalate_stale_documents failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_condition_checklist(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate underwriter condition checklist from compliance alerts and missing docs."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.stage, l.loan_type, l.borrower_name
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get open compliance alerts as conditions
            alerts = db.execute(text("""
                SELECT id, alert_type, severity, title, description,
                       status, deadline_date
                FROM compliance_alerts
                WHERE loan_id = :loan_id AND status = 'open'
                ORDER BY CASE severity
                    WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3 ELSE 4 END
            """), {"loan_id": loan_id}).fetchall()

            # Get missing docs
            existing = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id AND status = 'active'
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
            existing_types = {row.doc_type for row in existing}

            loan_type = (loan.loan_type or "conventional").lower()
            type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])
            required = list(type_reqs["base"]) + list(type_reqs["extra"])
            required = list(dict.fromkeys(required))
            missing = [d for d in required if d not in existing_types]

            # Build checklist
            checklist = []
            condition_id = 1

            # Conditions from compliance alerts
            for alert in alerts:
                checklist.append({
                    "condition_number": condition_id,
                    "category": "compliance",
                    "source": "compliance_alert",
                    "title": alert.title,
                    "description": alert.description,
                    "severity": alert.severity,
                    "status": alert.status,
                    "deadline": alert.deadline_date.isoformat() if alert.deadline_date else None,
                })
                condition_id += 1

            # Conditions from missing docs
            for doc in missing:
                checklist.append({
                    "condition_number": condition_id,
                    "category": "document",
                    "source": "missing_document",
                    "title": f"Provide {doc.replace('_', ' ').title()}",
                    "description": f"Required {doc} not yet received",
                    "severity": "high" if doc in DOC_PRIORITY.get("critical", []) else "medium",
                    "status": "open",
                    "deadline": None,
                })
                condition_id += 1

            self.audit_log("generate_condition_checklist", "loan", entity_id=str(loan_id), details={
                "condition_count": len(checklist),
                "from_alerts": len(alerts),
                "from_missing_docs": len(missing),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "checklist": checklist,
                    "total_conditions": len(checklist),
                    "summary": {
                        "from_compliance": len(alerts),
                        "from_missing_docs": len(missing),
                        "critical": len([c for c in checklist if c["severity"] == "critical"]),
                        "high": len([c for c in checklist if c["severity"] == "high"]),
                    },
                },
                message=f"Condition checklist: {len(checklist)} items ({len(alerts)} compliance, {len(missing)} docs)",
            )
        except Exception as e:
            logger.exception(f"generate_condition_checklist failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _predict_document_completion(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Predict when all documents will be collected based on historical patterns."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.closing_date,
                       l.application_date, l.borrower_name
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get document upload history for this loan
            doc_timeline = db.execute(text("""
                SELECT doc_type, uploaded_at
                FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id AND status = 'active'
                ORDER BY uploaded_at ASC
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()

            # Get historical average collection time from funded loans
            historical = db.execute(text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (
                        (SELECT MAX(d2.uploaded_at) FROM documents d2 WHERE d2.loan_id = l2.id)
                        - l2.application_date
                    )) / 86400) as avg_collection_days
                FROM loans l2
                WHERE l2.organization_id = :org_id
                    AND l2.stage = 'FUNDED'
                    AND l2.funded_date >= CURRENT_DATE - 180
            """), {"org_id": org_id}).fetchone()

            avg_days = float(historical.avg_collection_days or 14) if historical and historical.avg_collection_days else 14

            # Calculate prediction
            today = date.today()
            docs_received = len(doc_timeline)
            app_date = loan.application_date
            if app_date:
                if isinstance(app_date, datetime):
                    app_date = app_date.date()
                days_elapsed = (today - app_date).days
            else:
                days_elapsed = 0

            predicted_remaining = max(0, avg_days - days_elapsed)
            predicted_complete = today + timedelta(days=int(predicted_remaining))

            # Check against closing date
            closing_risk = False
            if loan.closing_date:
                close_dt = loan.closing_date
                if isinstance(close_dt, datetime):
                    close_dt = close_dt.date()
                closing_risk = predicted_complete > close_dt

            confidence = "high" if docs_received > 5 else "medium" if docs_received > 2 else "low"

            self.audit_log("predict_document_completion", "loan", entity_id=str(loan_id), details={
                "predicted_days": predicted_remaining,
                "closing_risk": closing_risk,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "documents_received": docs_received,
                    "days_elapsed": days_elapsed,
                    "predicted_remaining_days": round(predicted_remaining),
                    "predicted_completion_date": predicted_complete.isoformat(),
                    "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                    "closing_at_risk": closing_risk,
                    "confidence": confidence,
                    "historical_avg_days": round(avg_days, 1),
                },
                message=f"Predicted complete in {round(predicted_remaining)} days "
                        f"({'at risk' if closing_risk else 'on track'})",
            )
        except Exception as e:
            logger.exception(f"predict_document_completion failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_next_action(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Determine the single most impactful action to move docs forward."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.stage, l.closing_date,
                       l.borrower_name, l.borrower_email, l.borrower_phone,
                       l.appraisal_ordered_date, l.appraisal_received_date,
                       l.title_ordered_date, l.title_received_date,
                       l.insurance_ordered_date, l.insurance_received_date,
                       l.credit_docs_expire_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get existing active docs
            existing = db.execute(text("""
                SELECT doc_type FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id AND status = 'active'
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
            existing_types = {row.doc_type for row in existing}

            today = date.today()
            recommendations = []

            # Priority 1: Expiring documents
            if loan.credit_docs_expire_date:
                expire = loan.credit_docs_expire_date
                if isinstance(expire, datetime):
                    expire = expire.date()
                if expire <= today + timedelta(days=14):
                    recommendations.append({
                        "action": "renew_expiring_credit_docs",
                        "priority": 1,
                        "impact": "critical",
                        "reason": f"Credit docs expire {expire.isoformat()}",
                        "instruction": "Order new credit report immediately",
                    })

            # Priority 2: Blocking documents for current stage
            stage = loan.stage or "PROCESSING"
            blockers = STAGE_BLOCKERS.get(stage, [])
            missing_blockers = [d for d in blockers if d not in existing_types]
            if missing_blockers:
                recommendations.append({
                    "action": "collect_blocking_document",
                    "priority": 2,
                    "impact": "high",
                    "reason": f"{missing_blockers[0]} blocks {stage} progression",
                    "instruction": f"Request {missing_blockers[0].replace('_', ' ')} from borrower",
                    "document_type": missing_blockers[0],
                })

            # Priority 3: Third-party orders not placed
            if not loan.appraisal_ordered_date and "appraisal" not in existing_types:
                recommendations.append({
                    "action": "order_appraisal",
                    "priority": 3,
                    "impact": "high",
                    "reason": "Appraisal not ordered - typically longest lead time",
                    "instruction": "Order appraisal immediately",
                })

            if not loan.title_ordered_date and "title" not in existing_types:
                recommendations.append({
                    "action": "order_title",
                    "priority": 4,
                    "impact": "medium",
                    "reason": "Title not ordered",
                    "instruction": "Order title work",
                })

            # Priority 5: Critical missing docs
            critical_missing = [d for d in DOC_PRIORITY.get("critical", []) if d not in existing_types]
            if critical_missing and not any(r["priority"] <= 2 for r in recommendations):
                recommendations.append({
                    "action": "collect_critical_document",
                    "priority": 5,
                    "impact": "high",
                    "reason": f"{len(critical_missing)} critical documents still missing",
                    "instruction": f"Request {critical_missing[0].replace('_', ' ')} from borrower",
                    "document_type": critical_missing[0],
                })

            # Sort by priority
            recommendations.sort(key=lambda x: x["priority"])

            top_action = recommendations[0] if recommendations else {
                "action": "no_action_needed",
                "priority": 99,
                "impact": "none",
                "reason": "All documents appear to be on track",
                "instruction": "Monitor for any changes",
            }

            self.audit_log("recommend_next_action", "loan", entity_id=str(loan_id), details={
                "recommended_action": top_action["action"],
                "impact": top_action["impact"],
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "top_recommendation": top_action,
                    "all_recommendations": recommendations[:5],
                    "current_stage": stage,
                },
                message=f"Top action: {top_action['instruction']}",
            )
        except Exception as e:
            logger.exception(f"recommend_next_action failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _batch_process_uploads(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Process multiple uploaded documents in one operation."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        document_ids = input_data.get("document_ids")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Verify loan exists with tenant isolation
            loan = db.execute(text("""
                SELECT id, loan_number FROM loans
                WHERE id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get documents to process
            if document_ids:
                id_list = ",".join(str(int(d)) for d in document_ids)
                docs = db.execute(text(f"""
                    SELECT id, doc_type, doc_category, filename, status, uploaded_at
                    FROM documents
                    WHERE loan_id = :loan_id AND organization_id = :org_id
                        AND id IN ({id_list})
                    ORDER BY uploaded_at DESC
                """), {"loan_id": loan_id, "org_id": org_id}).fetchall()
            else:
                docs = db.execute(text("""
                    SELECT id, doc_type, doc_category, filename, status, uploaded_at
                    FROM documents
                    WHERE loan_id = :loan_id AND organization_id = :org_id
                    ORDER BY uploaded_at DESC
                    LIMIT 50
                """), {"loan_id": loan_id, "org_id": org_id}).fetchall()

            if not docs:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "processed": [], "count": 0},
                    message="No documents to process",
                )

            processed = []
            for doc in docs:
                result = {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "status": doc.status,
                    "classification": doc.doc_type or "needs_classification",
                    "review_status": "routed" if doc.doc_type else "needs_classification",
                }
                processed.append(result)

            self.audit_log("batch_process_uploads", "loan", entity_id=str(loan_id), details={
                "processed_count": len(processed),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "processed": processed,
                    "count": len(processed),
                    "needs_classification": len([p for p in processed if p["review_status"] == "needs_classification"]),
                },
                message=f"Processed {len(processed)} documents for loan {loan.loan_number}",
            )
        except Exception as e:
            logger.exception(f"batch_process_uploads failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_borrower_status_update(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Create a borrower-friendly status update of document progress."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT l.id, l.loan_number, l.borrower_name, l.closing_date,
                       l.stage, l.loan_type
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get doc counts
            docs = db.execute(text("""
                SELECT doc_type, status FROM documents
                WHERE loan_id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchall()

            active_docs = [d for d in docs if d.status == "active"]

            # Build required list
            loan_type = (loan.loan_type or "conventional").lower()
            type_reqs = LOAN_TYPE_REQUIREMENTS.get(loan_type, LOAN_TYPE_REQUIREMENTS["conventional"])
            required = list(dict.fromkeys(type_reqs["base"] + type_reqs["extra"]))
            existing_types = {d.doc_type for d in active_docs}
            missing = [d for d in required if d not in existing_types]

            total_req = len(required)
            received = len(existing_types & set(required))
            pct = round((received / total_req) * 100) if total_req > 0 else 0

            first_name = (loan.borrower_name or "").split()[0] if loan.borrower_name else "there"

            # Generate borrower-friendly message
            if pct == 100:
                status_message = (
                    f"Hi {first_name}, great news! We have received all the documents "
                    f"we need for your loan. Your file is being reviewed and we will "
                    f"keep you updated on next steps."
                )
                next_step = "No action needed from you right now."
            elif pct >= 75:
                still_needed = [d.replace("_", " ").title() for d in missing[:3]]
                status_message = (
                    f"Hi {first_name}, we are making great progress! We have {received} "
                    f"of {total_req} documents. We just need a few more items to complete "
                    f"your file."
                )
                next_step = f"Please provide: {', '.join(still_needed)}."
            elif pct >= 50:
                still_needed = [d.replace("_", " ").title() for d in missing[:3]]
                status_message = (
                    f"Hi {first_name}, we are halfway there with your documents! "
                    f"We have {received} of {total_req} items."
                )
                next_step = f"Your next priority items: {', '.join(still_needed)}."
            else:
                critical_missing = [d for d in missing if d in DOC_PRIORITY.get("critical", [])]
                if critical_missing:
                    items = [d.replace("_", " ").title() for d in critical_missing[:3]]
                    next_step = f"Most important items to send first: {', '.join(items)}."
                else:
                    next_step = "Please start uploading your documents at your earliest convenience."
                status_message = (
                    f"Hi {first_name}, we are ready to get started on your documents. "
                    f"We need {len(missing)} items to move your loan forward."
                )

            self.audit_log("generate_borrower_status_update", "loan", entity_id=str(loan_id), details={
                "completeness_pct": pct,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "completeness_pct": pct,
                    "received_count": received,
                    "total_required": total_req,
                    "missing_count": len(missing),
                    "status_message": status_message,
                    "next_step": next_step,
                    "missing_items": [d.replace("_", " ").title() for d in missing],
                },
                message=f"Borrower update: {pct}% complete ({received}/{total_req})",
            )
        except Exception as e:
            logger.exception(f"generate_borrower_status_update failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _check_expiring_documents(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Find documents about to expire and flag for re-collection."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id")
        days_ahead = input_data.get("days_ahead", 30)
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            params = {"org_id": org_id, "days_ahead": days_ahead}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND l.id = :loan_id"
                params["loan_id"] = loan_id

            # Check loan-level expiration dates
            expiring = db.execute(text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    l.credit_docs_expire_date,
                    l.appraisal_docs_expire_date,
                    l.closing_date
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN (
                        'FUNDED', 'CANCELLED', 'DENIED', 'DEAD',
                        'WITHDRAWN', 'DOES_NOT_QUALIFY'
                    )
                    {loan_filter}
                    AND (
                        (l.credit_docs_expire_date IS NOT NULL
                         AND l.credit_docs_expire_date <= CURRENT_DATE + :days_ahead)
                        OR
                        (l.appraisal_docs_expire_date IS NOT NULL
                         AND l.appraisal_docs_expire_date <= CURRENT_DATE + :days_ahead)
                    )
                ORDER BY LEAST(
                    COALESCE(l.credit_docs_expire_date, '9999-12-31'::date),
                    COALESCE(l.appraisal_docs_expire_date, '9999-12-31'::date)
                ) ASC
            """), params).fetchall()

            today = date.today()
            expired_items = []
            expiring_items = []

            for row in expiring:
                for doc_label, col_name in [
                    ("credit_docs", "credit_docs_expire_date"),
                    ("appraisal_docs", "appraisal_docs_expire_date"),
                ]:
                    expire_date = getattr(row, col_name, None)
                    if expire_date is None:
                        continue
                    if isinstance(expire_date, datetime):
                        expire_date = expire_date.date()
                    if expire_date > today + timedelta(days=days_ahead):
                        continue

                    item = {
                        "loan_id": row.loan_id,
                        "loan_number": row.loan_number,
                        "borrower": row.borrower_name,
                        "document_type": doc_label,
                        "expiration_date": expire_date.isoformat(),
                    }

                    if expire_date < today:
                        item["days_expired"] = (today - expire_date).days
                        expired_items.append(item)
                    else:
                        item["days_until_expiry"] = (expire_date - today).days
                        expiring_items.append(item)

            self.audit_log("check_expiring_documents", details={
                "expired_count": len(expired_items),
                "expiring_count": len(expiring_items),
                "days_ahead": days_ahead,
            })

            return ToolResult(
                success=True,
                data={
                    "days_ahead": days_ahead,
                    "expired": expired_items,
                    "expiring_soon": expiring_items,
                    "expired_count": len(expired_items),
                    "expiring_count": len(expiring_items),
                },
                message=f"{len(expired_items)} expired, {len(expiring_items)} expiring within {days_ahead} days",
            )
        except Exception as e:
            logger.exception("check_expiring_documents failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _coordinate_third_party_orders(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Check appraisal, title, insurance status and recommend actions."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(text("""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.closing_date,
                    l.appraisal_ordered_date, l.appraisal_scheduled_date,
                    l.appraisal_completed_date, l.appraisal_received_date,
                    l.appraisal_value,
                    l.title_ordered_date, l.title_received_date,
                    l.insurance_ordered_date, l.insurance_received_date
                FROM loans l
                WHERE l.id = :loan_id AND l.organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            today = date.today()
            orders = []
            recommendations = []

            # --- Appraisal ---
            if loan.appraisal_received_date:
                appraisal_status = "completed"
            elif loan.appraisal_completed_date:
                appraisal_status = "completed_awaiting_receipt"
            elif loan.appraisal_scheduled_date:
                appraisal_status = "scheduled"
            elif loan.appraisal_ordered_date:
                appraisal_status = "ordered"
                # Check if overdue
                ordered = loan.appraisal_ordered_date
                if isinstance(ordered, datetime):
                    ordered = ordered.date()
                if (today - ordered).days > 14:
                    recommendations.append({
                        "order_type": "appraisal",
                        "action": "follow_up",
                        "urgency": "high",
                        "reason": f"Appraisal ordered {(today - ordered).days} days ago with no completion",
                    })
            else:
                appraisal_status = "not_ordered"
                recommendations.append({
                    "order_type": "appraisal",
                    "action": "order_now",
                    "urgency": "critical" if loan.stage in ("PROCESSING", "SUBMITTED", "UNDERWRITING") else "medium",
                    "reason": "Appraisal not yet ordered",
                })

            orders.append({
                "type": "appraisal",
                "status": appraisal_status,
                "ordered": loan.appraisal_ordered_date.isoformat() if loan.appraisal_ordered_date else None,
                "scheduled": loan.appraisal_scheduled_date.isoformat() if loan.appraisal_scheduled_date else None,
                "completed": loan.appraisal_completed_date.isoformat() if loan.appraisal_completed_date else None,
                "received": loan.appraisal_received_date.isoformat() if loan.appraisal_received_date else None,
                "value": float(loan.appraisal_value) if loan.appraisal_value else None,
            })

            # --- Title ---
            if loan.title_received_date:
                title_status = "completed"
            elif loan.title_ordered_date:
                title_status = "ordered"
                ordered = loan.title_ordered_date
                if isinstance(ordered, datetime):
                    ordered = ordered.date()
                if (today - ordered).days > 10:
                    recommendations.append({
                        "order_type": "title",
                        "action": "follow_up",
                        "urgency": "medium",
                        "reason": f"Title ordered {(today - ordered).days} days ago",
                    })
            else:
                title_status = "not_ordered"
                if loan.stage not in ("APPLICATION", "DISCLOSED"):
                    recommendations.append({
                        "order_type": "title",
                        "action": "order_now",
                        "urgency": "medium",
                        "reason": "Title work not yet ordered",
                    })

            orders.append({
                "type": "title",
                "status": title_status,
                "ordered": loan.title_ordered_date.isoformat() if loan.title_ordered_date else None,
                "received": loan.title_received_date.isoformat() if loan.title_received_date else None,
            })

            # --- Insurance ---
            if loan.insurance_received_date:
                insurance_status = "completed"
            elif loan.insurance_ordered_date:
                insurance_status = "ordered"
            else:
                insurance_status = "not_ordered"
                if loan.stage in ("APPROVED", "CLEAR_TO_CLOSE", "CLOSING", "DOCS_OUT"):
                    recommendations.append({
                        "order_type": "insurance",
                        "action": "request_from_borrower",
                        "urgency": "high",
                        "reason": "Insurance needed before closing",
                    })

            orders.append({
                "type": "insurance",
                "status": insurance_status,
                "ordered": loan.insurance_ordered_date.isoformat() if loan.insurance_ordered_date else None,
                "received": loan.insurance_received_date.isoformat() if loan.insurance_received_date else None,
            })

            completed = len([o for o in orders if o["status"] == "completed"])
            pending = len([o for o in orders if o["status"] not in ("completed", "not_ordered")])

            self.audit_log("coordinate_third_party_orders", "loan", entity_id=str(loan_id), details={
                "completed": completed,
                "pending": pending,
                "recommendations": len(recommendations),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "orders": orders,
                    "recommendations": recommendations,
                    "summary": {
                        "completed": completed,
                        "pending": pending,
                        "not_ordered": len([o for o in orders if o["status"] == "not_ordered"]),
                    },
                },
                message=f"Third-party orders: {completed} done, {pending} pending, {len(recommendations)} actions needed",
            )
        except Exception as e:
            logger.exception(f"coordinate_third_party_orders failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_processor_briefing(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Create daily briefing for processor on pipeline document status."""
        from database import SessionLocal

        lo_id = input_data.get("lo_id")
        processor_id = input_data.get("processor_id")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            params = {"org_id": org_id}
            filters = [
                "l.organization_id = :org_id",
                "l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')",
            ]

            if lo_id:
                filters.append("l.loan_officer_id = :lo_id")
                params["lo_id"] = lo_id
            if processor_id:
                filters.append("l.processor_id = :processor_id")
                params["processor_id"] = processor_id

            where_sql = " AND ".join(filters)

            loans = db.execute(text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.closing_date, l.loan_type,
                    l.credit_docs_expire_date, l.appraisal_docs_expire_date,
                    (SELECT COUNT(*) FROM documents d
                     WHERE d.loan_id = l.id AND d.status = 'active') as doc_count,
                    (SELECT COUNT(*) FROM compliance_alerts ca
                     WHERE ca.loan_id = l.id AND ca.status = 'open') as open_conditions
                FROM loans l
                WHERE {where_sql}
                ORDER BY l.closing_date ASC NULLS LAST
                LIMIT 50
            """), params).fetchall()

            if not loans:
                return ToolResult(
                    success=True,
                    data={"loans": [], "summary": {"total": 0}},
                    message="No active loans in pipeline",
                )

            today = date.today()
            urgent = []
            attention = []
            on_track = []

            for loan in loans:
                closing = loan.closing_date
                if closing and isinstance(closing, datetime):
                    closing = closing.date()
                days_to_close = (closing - today).days if closing else 999

                has_expiring = False
                if loan.credit_docs_expire_date:
                    exp = loan.credit_docs_expire_date
                    if isinstance(exp, datetime):
                        exp = exp.date()
                    has_expiring = exp <= today + timedelta(days=14)
                if not has_expiring and loan.appraisal_docs_expire_date:
                    exp = loan.appraisal_docs_expire_date
                    if isinstance(exp, datetime):
                        exp = exp.date()
                    has_expiring = exp <= today + timedelta(days=14)

                item = {
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "days_to_close": days_to_close if days_to_close < 999 else None,
                    "doc_count": loan.doc_count or 0,
                    "open_conditions": loan.open_conditions or 0,
                    "has_expiring_docs": has_expiring,
                }

                if days_to_close <= 7 or has_expiring or (loan.open_conditions or 0) >= 3:
                    item["urgency"] = "urgent"
                    urgent.append(item)
                elif days_to_close <= 14 or (loan.open_conditions or 0) >= 1:
                    item["urgency"] = "attention"
                    attention.append(item)
                else:
                    item["urgency"] = "on_track"
                    on_track.append(item)

            self.audit_log("generate_processor_briefing", details={
                "total_loans": len(loans),
                "urgent": len(urgent),
                "attention": len(attention),
                "on_track": len(on_track),
            })

            return ToolResult(
                success=True,
                data={
                    "briefing_date": today.isoformat(),
                    "urgent": urgent,
                    "attention_needed": attention,
                    "on_track": on_track,
                    "summary": {
                        "total_loans": len(loans),
                        "urgent_count": len(urgent),
                        "attention_count": len(attention),
                        "on_track_count": len(on_track),
                    },
                },
                message=f"Processor briefing: {len(urgent)} urgent, {len(attention)} need attention, {len(on_track)} on track",
            )
        except Exception as e:
            logger.exception("generate_processor_briefing failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
