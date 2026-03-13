"""
Processor Productivity Agent

Specialized agent for loan processor workflow optimization with 15 tools:
1. get_daily_priority_queue - Prioritized list of documents needing attention today
2. triage_new_uploads - Quick triage of newly uploaded documents
3. batch_approve_routine_docs - Identify docs eligible for batch approval
4. identify_stacking_order_issues - Check document stacking order for UW
5. generate_condition_response - Map conditions to required documents
6. calculate_workload_capacity - Processor capacity analysis
7. suggest_task_delegation - Identify tasks for delegation to LOA/junior staff
8. track_touch_time - Track processor time spent per loan
9. generate_pipeline_report - Processor's document pipeline status report
10. identify_reusable_documents - Find reusable docs from prior loans
11. automate_data_entry - Extract data from approved docs for loan fields
12. flag_quality_issues - Predict UW kickbacks from document quality
13. generate_submission_checklist - Pre-submission document completeness checklist
14. compare_doc_versions - Compare new upload vs. previously rejected version
15. estimate_time_to_clear - Estimate time to clear all docs per loan
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
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class DailyPriorityQueueInput(BaseModel):
    """Input schema for get_daily_priority_queue tool"""
    processor_id: Optional[int] = Field(None, description="Processor user ID (default: current user)")
    include_upcoming: bool = Field(default=True, description="Include items due in next 48 hours")
    limit: int = Field(default=50, description="Maximum items to return")


class TriageNewUploadsInput(BaseModel):
    """Input schema for triage_new_uploads tool"""
    loan_id: Optional[int] = Field(None, description="Filter by specific loan ID")
    hours: int = Field(default=24, description="Look back window in hours")
    limit: int = Field(default=50, description="Maximum uploads to triage")


class BatchApproveInput(BaseModel):
    """Input schema for batch_approve_routine_docs tool"""
    processor_id: Optional[int] = Field(None, description="Filter by processor")
    loan_id: Optional[int] = Field(None, description="Filter by specific loan")


class StackingOrderInput(BaseModel):
    """Input schema for identify_stacking_order_issues tool"""
    loan_id: int = Field(..., description="Loan ID to check stacking order")


class ConditionResponseInput(BaseModel):
    """Input schema for generate_condition_response tool"""
    loan_id: int = Field(..., description="Loan ID with conditions to respond to")
    condition_ids: Optional[List[int]] = Field(None, description="Specific condition IDs to address")


class WorkloadCapacityInput(BaseModel):
    """Input schema for calculate_workload_capacity tool"""
    processor_id: Optional[int] = Field(None, description="Processor user ID")
    max_loans: int = Field(default=35, description="Maximum loan capacity per processor")


class TaskDelegationInput(BaseModel):
    """Input schema for suggest_task_delegation tool"""
    processor_id: Optional[int] = Field(None, description="Processor to analyze")
    loan_id: Optional[int] = Field(None, description="Specific loan to analyze")


class TouchTimeInput(BaseModel):
    """Input schema for track_touch_time tool"""
    processor_id: Optional[int] = Field(None, description="Processor to analyze")
    loan_id: Optional[int] = Field(None, description="Specific loan ID")
    period_days: int = Field(default=30, description="Period to analyze")


class PipelineReportInput(BaseModel):
    """Input schema for generate_pipeline_report tool"""
    processor_id: Optional[int] = Field(None, description="Processor user ID")
    report_type: str = Field(default="daily", description="Report type: daily, weekly, monthly")


class ReusableDocumentsInput(BaseModel):
    """Input schema for identify_reusable_documents tool"""
    loan_id: int = Field(..., description="Current loan ID")
    borrower_email: Optional[str] = Field(None, description="Borrower email for cross-loan lookup")


class AutomateDataEntryInput(BaseModel):
    """Input schema for automate_data_entry tool"""
    document_id: int = Field(..., description="Document ID to extract data from")
    loan_id: int = Field(..., description="Loan ID to populate")


class FlagQualityIssuesInput(BaseModel):
    """Input schema for flag_quality_issues tool"""
    loan_id: int = Field(..., description="Loan ID to check document quality")


class SubmissionChecklistInput(BaseModel):
    """Input schema for generate_submission_checklist tool"""
    loan_id: int = Field(..., description="Loan ID to generate checklist for")
    lender: Optional[str] = Field(None, description="Target lender/investor for specific requirements")


class CompareDocVersionsInput(BaseModel):
    """Input schema for compare_doc_versions tool"""
    document_id: int = Field(..., description="Current/new document ID")
    previous_document_id: int = Field(..., description="Previously rejected document ID")


class EstimateTimeToClearInput(BaseModel):
    """Input schema for estimate_time_to_clear tool"""
    loan_id: Optional[int] = Field(None, description="Specific loan ID (null for full queue)")
    processor_id: Optional[int] = Field(None, description="Processor to estimate for")


# ============================================================================
# PROCESSOR PRODUCTIVITY AGENT
# ============================================================================

@AgentRegistry.register
class ProcessorProductivityAgent(SpecializedAgent):
    """
    Specialized agent for loan processor workflow optimization.

    Helps processors manage their document workload efficiently by
    prioritizing tasks, identifying batch-approval opportunities,
    tracking capacity, and ensuring submission readiness with 15 tools.
    """

    @property
    def name(self) -> str:
        return "ProcessorProductivityAgent"

    @property
    def description(self) -> str:
        return "Optimizes processor workflow: priority queues, batch approval, workload capacity, submission checklists"

    def _register_tools(self):
        """Register all processor productivity tools"""

        # Tool 1: Daily Priority Queue
        self.register_tool(AgentTool(
            name="get_daily_priority_queue",
            description="Get prioritized list of documents needing processor attention today. "
                       "Ordered by: closing date urgency > outstanding conditions > "
                       "document expirations > completeness gaps.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_daily_priority_queue,
            input_schema=DailyPriorityQueueInput
        ))

        # Tool 2: Triage New Uploads
        self.register_tool(AgentTool(
            name="triage_new_uploads",
            description="Quick triage of newly uploaded documents: classify type, "
                       "route to correct loan section, and flag potential issues.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._triage_new_uploads,
            input_schema=TriageNewUploadsInput
        ))

        # Tool 3: Batch Approve Routine Docs
        self.register_tool(AgentTool(
            name="batch_approve_routine_docs",
            description="Identify documents that pass all validation checks and can "
                       "be batch-approved without individual review.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            handler=self._batch_approve_routine_docs,
            input_schema=BatchApproveInput
        ))

        # Tool 4: Stacking Order Issues
        self.register_tool(AgentTool(
            name="identify_stacking_order_issues",
            description="Check if loan documents are in correct stacking order "
                       "for underwriting submission per investor guidelines.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._identify_stacking_order_issues,
            input_schema=StackingOrderInput
        ))

        # Tool 5: Condition Response
        self.register_tool(AgentTool(
            name="generate_condition_response",
            description="Help processor respond to underwriting conditions by "
                       "mapping each condition to the required documents on file.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_condition_response,
            input_schema=ConditionResponseInput
        ))

        # Tool 6: Workload Capacity
        self.register_tool(AgentTool(
            name="calculate_workload_capacity",
            description="Calculate how many additional loans a processor can handle "
                       "given their current queue, stage distribution, and closing dates.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._calculate_workload_capacity,
            input_schema=WorkloadCapacityInput
        ))

        # Tool 7: Task Delegation
        self.register_tool(AgentTool(
            name="suggest_task_delegation",
            description="Identify tasks that can be delegated to LOA or junior staff: "
                       "routine verifications, data entry, follow-up calls.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._suggest_task_delegation,
            input_schema=TaskDelegationInput
        ))

        # Tool 8: Touch Time Tracking
        self.register_tool(AgentTool(
            name="track_touch_time",
            description="Track and analyze how much time processor spends on each "
                       "loan's documents. Identify time sinks and efficiency gains.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._track_touch_time,
            input_schema=TouchTimeInput
        ))

        # Tool 9: Pipeline Report
        self.register_tool(AgentTool(
            name="generate_pipeline_report",
            description="Generate daily or weekly report of processor's document "
                       "pipeline: received, reviewed, approved, pending, escalated.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_pipeline_report,
            input_schema=PipelineReportInput
        ))

        # Tool 10: Reusable Documents
        self.register_tool(AgentTool(
            name="identify_reusable_documents",
            description="Find documents from previous loans that could apply to "
                       "current application (refinance, repeat borrower scenarios).",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._identify_reusable_documents,
            input_schema=ReusableDocumentsInput
        ))

        # Tool 11: Automate Data Entry
        self.register_tool(AgentTool(
            name="automate_data_entry",
            description="Extract key data from approved documents and suggest "
                       "loan field population (income, assets, employment).",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._automate_data_entry,
            input_schema=AutomateDataEntryInput,
            requires_confirmation=True
        ))

        # Tool 12: Flag Quality Issues
        self.register_tool(AgentTool(
            name="flag_quality_issues",
            description="Analyze documents for issues that will likely get kicked "
                       "back by underwriting: expired docs, missing pages, "
                       "name mismatches, unsigned forms.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._flag_quality_issues,
            input_schema=FlagQualityIssuesInput
        ))

        # Tool 13: Submission Checklist
        self.register_tool(AgentTool(
            name="generate_submission_checklist",
            description="Pre-submission checklist ensuring all documents are "
                       "complete, current, and properly ordered for UW submission.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._generate_submission_checklist,
            input_schema=SubmissionChecklistInput
        ))

        # Tool 14: Compare Doc Versions
        self.register_tool(AgentTool(
            name="compare_doc_versions",
            description="Compare newly uploaded document against previously rejected "
                       "version to verify the flagged issues have been resolved.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._compare_doc_versions,
            input_schema=CompareDocVersionsInput
        ))

        # Tool 15: Estimate Time to Clear
        self.register_tool(AgentTool(
            name="estimate_time_to_clear",
            description="For each loan in queue, estimate hours needed to get "
                       "all documents reviewed, approved, and submission-ready.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._estimate_time_to_clear,
            input_schema=EstimateTimeToClearInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_daily_priority_queue(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get prioritized list of documents needing processor attention today."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            processor_id = input_data.get("processor_id") or context.get("user_id")
            include_upcoming = input_data.get("include_upcoming", True)
            limit = input_data.get("limit", 50)

            params = {"org_id": org_id, "limit": limit}
            processor_filter = ""
            if processor_id:
                processor_filter = "AND l.processor_id = :processor_id"
                params["processor_id"] = processor_id

            # Priority 1: Loans closing within 7 days with incomplete docs
            closing_urgent = db.execute(text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    l.closing_date, l.stage, l.amount,
                    COUNT(CASE WHEN d.status != 'active' THEN 1 END) as pending_docs,
                    COUNT(d.id) as total_docs
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    AND l.closing_date IS NOT NULL
                    AND l.closing_date <= CURRENT_DATE + 7
                    {processor_filter}
                GROUP BY l.id, l.loan_number, l.borrower_name, l.closing_date, l.stage, l.amount
                ORDER BY l.closing_date ASC
                LIMIT :limit
            """), params).fetchall()

            # Priority 2: Loans with outstanding conditions
            condition_urgent = db.execute(text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    l.closing_date, l.stage,
                    COUNT(ca.id) as open_conditions,
                    MIN(ca.deadline_date) as earliest_deadline
                FROM loans l
                JOIN compliance_alerts ca ON ca.loan_id = l.id AND ca.status = 'open'
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {processor_filter}
                GROUP BY l.id, l.loan_number, l.borrower_name, l.closing_date, l.stage
                ORDER BY earliest_deadline ASC NULLS LAST
                LIMIT :limit
            """), params).fetchall()

            # Priority 3: Expiring documents
            expiring_docs = db.execute(text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name,
                    CASE
                        WHEN l.credit_docs_expire_date <= CURRENT_DATE + 14 THEN 'credit_docs'
                        WHEN l.appraisal_docs_expire_date <= CURRENT_DATE + 14 THEN 'appraisal_docs'
                    END as expiring_type,
                    LEAST(
                        COALESCE(l.credit_docs_expire_date, '9999-12-31'),
                        COALESCE(l.appraisal_docs_expire_date, '9999-12-31')
                    ) as earliest_expiry
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    AND (
                        l.credit_docs_expire_date <= CURRENT_DATE + 14
                        OR l.appraisal_docs_expire_date <= CURRENT_DATE + 14
                    )
                    {processor_filter}
                ORDER BY earliest_expiry ASC
                LIMIT :limit
            """), params).fetchall()

            queue = []

            for row in closing_urgent:
                days_to_close = (row.closing_date - date.today()).days if row.closing_date else 999
                queue.append({
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower": row.borrower_name,
                    "priority": "critical" if days_to_close <= 3 else "high",
                    "reason": f"Closing in {days_to_close} days, {row.pending_docs} docs pending",
                    "closing_date": row.closing_date.isoformat() if row.closing_date else None,
                    "stage": row.stage,
                    "category": "closing_urgency",
                })

            for row in condition_urgent:
                queue.append({
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower": row.borrower_name,
                    "priority": "high",
                    "reason": f"{row.open_conditions} open conditions",
                    "earliest_deadline": row.earliest_deadline.isoformat() if row.earliest_deadline else None,
                    "stage": row.stage,
                    "category": "conditions",
                })

            for row in expiring_docs:
                queue.append({
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower": row.borrower_name,
                    "priority": "medium",
                    "reason": f"{row.expiring_type} expiring soon",
                    "category": "expirations",
                })

            # Deduplicate by loan_id, keeping highest priority
            seen = {}
            for item in queue:
                lid = item["loan_id"]
                if lid not in seen:
                    seen[lid] = item
                else:
                    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                    if priority_order.get(item["priority"], 3) < priority_order.get(seen[lid]["priority"], 3):
                        seen[lid] = item

            final_queue = sorted(
                seen.values(),
                key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["priority"], 3)
            )

            self.audit_log("get_daily_priority_queue", details={
                "queue_size": len(final_queue),
                "critical_count": len([q for q in final_queue if q["priority"] == "critical"]),
            })

            return ToolResult(
                success=True,
                data={
                    "queue": final_queue[:limit],
                    "total_items": len(final_queue),
                    "critical": len([q for q in final_queue if q["priority"] == "critical"]),
                    "high": len([q for q in final_queue if q["priority"] == "high"]),
                    "medium": len([q for q in final_queue if q["priority"] == "medium"]),
                    "generated_at": datetime.now().isoformat(),
                },
                message=f"Priority queue: {len(final_queue)} items ({len([q for q in final_queue if q['priority'] == 'critical'])} critical)"
            )

        except Exception as e:
            logger.exception("get_daily_priority_queue failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _triage_new_uploads(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Quick triage of newly uploaded documents."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            hours = input_data.get("hours", 24)
            loan_id = input_data.get("loan_id")
            limit = input_data.get("limit", 50)

            params = {"org_id": org_id, "hours": hours, "limit": limit}
            loan_filter = ""
            if loan_id:
                loan_filter = "AND d.loan_id = :loan_id"
                params["loan_id"] = loan_id

            uploads = db.execute(text(f"""
                SELECT
                    d.id as doc_id, d.doc_type, d.doc_category, d.filename,
                    d.status, d.uploaded_at, d.source,
                    l.id as loan_id, l.loan_number, l.borrower_name, l.stage
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.uploaded_at >= CURRENT_TIMESTAMP - INTERVAL ':hours hours'
                    {loan_filter}
                ORDER BY d.uploaded_at DESC
                LIMIT :limit
            """), params).fetchall()

            triaged = []
            needs_review = 0
            auto_classified = 0

            for doc in uploads:
                # Classification based on doc_type and doc_category
                issues = []
                routing = "standard"

                # Flag potential issues
                if not doc.doc_type:
                    issues.append("Unclassified document type")
                    routing = "manual_review"
                    needs_review += 1
                elif doc.doc_type in ("paystubs", "w2", "tax_returns", "1099", "profit_loss"):
                    routing = "income_verification"
                    auto_classified += 1
                elif doc.doc_type in ("bank_statements", "investment_statements", "gift_letter"):
                    routing = "asset_verification"
                    auto_classified += 1
                elif doc.doc_type in ("appraisal", "title", "insurance"):
                    routing = "third_party"
                    auto_classified += 1
                else:
                    auto_classified += 1

                # Check if the loan stage suggests this doc is late
                late_stages = ("SUBMITTED", "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED")
                if doc.stage in late_stages and doc.doc_category == "income":
                    issues.append("Income doc received after submission — may require revised LE")

                triaged.append({
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "doc_type": doc.doc_type,
                    "doc_category": doc.doc_category,
                    "loan_id": doc.loan_id,
                    "loan_number": doc.loan_number,
                    "borrower": doc.borrower_name,
                    "routing": routing,
                    "issues": issues,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                    "source": doc.source,
                })

            self.audit_log("triage_new_uploads", details={
                "total": len(triaged),
                "needs_review": needs_review,
                "auto_classified": auto_classified,
            })

            return ToolResult(
                success=True,
                data={
                    "uploads": triaged,
                    "total": len(triaged),
                    "auto_classified": auto_classified,
                    "needs_manual_review": needs_review,
                    "lookback_hours": hours,
                },
                message=f"Triaged {len(triaged)} uploads: {auto_classified} auto-classified, {needs_review} need review"
            )

        except Exception as e:
            logger.exception("triage_new_uploads failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _batch_approve_routine_docs(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify documents eligible for batch approval."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            processor_id = input_data.get("processor_id")

            params = {"org_id": org_id}
            filters = ["l.organization_id = :org_id"]

            if loan_id:
                filters.append("d.loan_id = :loan_id")
                params["loan_id"] = loan_id
            if processor_id:
                filters.append("l.processor_id = :processor_id")
                params["processor_id"] = processor_id

            where_sql = " AND ".join(filters)

            # Find documents that are uploaded but not yet active and look routine
            candidates = db.execute(text(f"""
                SELECT
                    d.id as doc_id, d.doc_type, d.doc_category,
                    d.filename, d.status, d.uploaded_at,
                    l.id as loan_id, l.loan_number, l.borrower_name
                FROM documents d
                JOIN loans l ON l.id = d.loan_id
                WHERE {where_sql}
                    AND d.status IN ('pending', 'uploaded')
                    AND d.doc_type IS NOT NULL
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                ORDER BY d.uploaded_at ASC
            """), params).fetchall()

            # Routine doc types that typically pass without special review
            routine_types = {
                "drivers_license", "ssn_card", "passport",
                "insurance", "hoa",
            }

            approvable = []
            requires_review = []

            for doc in candidates:
                if doc.doc_type in routine_types:
                    approvable.append({
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type,
                        "filename": doc.filename,
                        "loan_id": doc.loan_id,
                        "loan_number": doc.loan_number,
                        "borrower": doc.borrower_name,
                        "reason": "Routine document type — standard validation sufficient",
                    })
                else:
                    requires_review.append({
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type,
                        "filename": doc.filename,
                        "loan_id": doc.loan_id,
                        "loan_number": doc.loan_number,
                        "reason": "Requires individual review (income/asset/credit doc)",
                    })

            self.audit_log("batch_approve_routine_docs", details={
                "approvable": len(approvable),
                "requires_review": len(requires_review),
            })

            return ToolResult(
                success=True,
                data={
                    "approvable": approvable,
                    "requires_review": requires_review,
                    "approvable_count": len(approvable),
                    "review_required_count": len(requires_review),
                },
                message=f"{len(approvable)} docs eligible for batch approval, {len(requires_review)} need individual review"
            )

        except Exception as e:
            logger.exception("batch_approve_routine_docs failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_stacking_order_issues(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Check document stacking order for underwriting."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)

            # Required stacking order for UW submission
            stacking_order = [
                {"position": 1, "category": "identity", "types": ["drivers_license", "passport", "ssn_card"]},
                {"position": 2, "category": "credit", "types": ["credit_report"]},
                {"position": 3, "category": "income", "types": ["paystubs", "w2", "tax_returns", "1099", "profit_loss"]},
                {"position": 4, "category": "assets", "types": ["bank_statements", "investment_statements", "gift_letter"]},
                {"position": 5, "category": "property", "types": ["purchase_contract", "appraisal", "title", "insurance", "hoa"]},
            ]

            # Get current documents
            docs = db.execute(text("""
                SELECT doc_type, doc_category, status, filename
                FROM documents
                WHERE loan_id = :loan_id
                ORDER BY doc_category, doc_type
            """), {"loan_id": loan_id}).fetchall()

            doc_types_on_file = {d.doc_type for d in docs if d.status == "active"}
            doc_categories_on_file = {d.doc_category for d in docs if d.status == "active"}

            issues = []
            order_status = []

            for section in stacking_order:
                section_types_present = [t for t in section["types"] if t in doc_types_on_file]
                section_complete = len(section_types_present) > 0

                status = "complete" if section_complete else "missing"
                if not section_complete:
                    issues.append({
                        "position": section["position"],
                        "category": section["category"],
                        "issue": f"No {section['category']} documents found",
                        "required_types": section["types"],
                        "severity": "high" if section["category"] in ("income", "credit") else "medium",
                    })

                order_status.append({
                    "position": section["position"],
                    "category": section["category"],
                    "status": status,
                    "docs_present": section_types_present,
                    "required": section["types"],
                })

            self.audit_log("identify_stacking_order_issues", "loan", entity_id=loan_id, details={
                "issues_found": len(issues),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "stacking_order": order_status,
                    "issues": issues,
                    "issue_count": len(issues),
                    "is_submission_ready": len(issues) == 0,
                    "total_docs_on_file": len(docs),
                },
                message=f"Stacking order: {len(issues)} issues found, {'submission-ready' if len(issues) == 0 else 'NOT ready'}"
            )

        except Exception as e:
            logger.exception("identify_stacking_order_issues failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_condition_response(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Map underwriting conditions to required documents."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)

            condition_ids = input_data.get("condition_ids")

            # Get open conditions from compliance_alerts
            params = {"loan_id": loan_id}
            cond_filter = ""
            if condition_ids:
                cond_filter = "AND ca.id = ANY(:condition_ids)"
                params["condition_ids"] = condition_ids

            conditions = db.execute(text(f"""
                SELECT ca.id, ca.alert_type, ca.title, ca.description, ca.status, ca.deadline_date
                FROM compliance_alerts ca
                WHERE ca.loan_id = :loan_id
                    AND ca.status = 'open'
                    {cond_filter}
                ORDER BY ca.deadline_date ASC NULLS LAST
            """), params).fetchall()

            if not conditions:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "conditions": [], "responses": []},
                    message="No open conditions found"
                )

            # Get documents on file
            docs = db.execute(text("""
                SELECT doc_type, doc_category, status, filename, uploaded_at
                FROM documents WHERE loan_id = :loan_id AND status = 'active'
            """), {"loan_id": loan_id}).fetchall()

            doc_types_on_file = {d.doc_type: d for d in docs}

            # Condition-to-document mapping
            condition_doc_map = {
                "income_verification": ["paystubs", "w2", "tax_returns", "1099"],
                "asset_verification": ["bank_statements", "investment_statements"],
                "credit": ["credit_report", "credit_explanation"],
                "property": ["appraisal", "title", "insurance", "purchase_contract"],
                "identity": ["drivers_license", "passport"],
            }

            responses = []
            for cond in conditions:
                # Match condition type to document requirements
                alert_type_lower = (cond.alert_type or "").lower()
                matching_docs = []
                missing_docs = []

                for category, doc_types in condition_doc_map.items():
                    if category in alert_type_lower or category in (cond.description or "").lower():
                        for dt in doc_types:
                            if dt in doc_types_on_file:
                                d = doc_types_on_file[dt]
                                matching_docs.append({
                                    "doc_type": dt,
                                    "filename": d.filename,
                                    "uploaded": d.uploaded_at.isoformat() if d.uploaded_at else None,
                                })
                            else:
                                missing_docs.append(dt)

                responses.append({
                    "condition_id": cond.id,
                    "condition_title": cond.title,
                    "condition_description": cond.description,
                    "deadline": cond.deadline_date.isoformat() if cond.deadline_date else None,
                    "documents_available": matching_docs,
                    "documents_missing": missing_docs,
                    "can_respond": len(missing_docs) == 0 and len(matching_docs) > 0,
                    "action_needed": "Submit available documents" if matching_docs and not missing_docs
                                    else f"Collect: {', '.join(missing_docs)}" if missing_docs
                                    else "Review condition manually",
                })

            self.audit_log("generate_condition_response", "loan", entity_id=loan_id, details={
                "conditions_analyzed": len(conditions),
                "can_respond": len([r for r in responses if r["can_respond"]]),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "total_conditions": len(conditions),
                    "can_respond_now": len([r for r in responses if r["can_respond"]]),
                    "needs_collection": len([r for r in responses if not r["can_respond"]]),
                    "responses": responses,
                },
                message=f"{len([r for r in responses if r['can_respond']])} of {len(conditions)} conditions can be responded to now"
            )

        except Exception as e:
            logger.exception("generate_condition_response failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _calculate_workload_capacity(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Calculate processor workload and remaining capacity."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            processor_id = input_data.get("processor_id") or context.get("user_id")
            max_loans = input_data.get("max_loans", 35)

            params = {"org_id": org_id}
            processor_filter = ""
            if processor_id:
                processor_filter = "AND l.processor_id = :processor_id"
                params["processor_id"] = processor_id

            # Current active pipeline
            workload = db.execute(text(f"""
                SELECT
                    l.stage,
                    COUNT(*) as loan_count,
                    COALESCE(SUM(l.amount), 0) as total_volume,
                    COUNT(CASE WHEN l.closing_date <= CURRENT_DATE + 7 THEN 1 END) as closing_7_days,
                    COUNT(CASE WHEN l.closing_date <= CURRENT_DATE + 14 THEN 1 END) as closing_14_days
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {processor_filter}
                GROUP BY l.stage
            """), params).fetchall()

            total_active = sum(row.loan_count for row in workload)
            total_volume = sum(float(row.total_volume or 0) for row in workload)
            closing_7 = sum(row.closing_7_days or 0 for row in workload)
            closing_14 = sum(row.closing_14_days or 0 for row in workload)

            # Weight complexity: UW and closing stages take more time
            high_touch_stages = ("UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "DOCS_OUT")
            high_touch_count = sum(row.loan_count for row in workload if row.stage in high_touch_stages)

            # Weighted capacity: high-touch loans count as 1.5x
            weighted_load = (total_active - high_touch_count) + (high_touch_count * 1.5)
            capacity_pct = round((weighted_load / max_loans) * 100, 1) if max_loans > 0 else 0
            remaining_capacity = max(0, max_loans - int(weighted_load))

            # Capacity status
            if capacity_pct >= 100:
                status = "over_capacity"
            elif capacity_pct >= 85:
                status = "near_capacity"
            elif capacity_pct >= 60:
                status = "healthy"
            else:
                status = "under_utilized"

            by_stage = [
                {
                    "stage": row.stage,
                    "count": row.loan_count,
                    "volume": float(row.total_volume or 0),
                    "is_high_touch": row.stage in high_touch_stages,
                }
                for row in workload
            ]

            self.audit_log("calculate_workload_capacity", details={
                "total_active": total_active,
                "capacity_pct": capacity_pct,
                "status": status,
            })

            return ToolResult(
                success=True,
                data={
                    "processor_id": processor_id,
                    "total_active_loans": total_active,
                    "total_volume": total_volume,
                    "max_capacity": max_loans,
                    "weighted_load": round(weighted_load, 1),
                    "capacity_pct": capacity_pct,
                    "remaining_capacity": remaining_capacity,
                    "status": status,
                    "closing_7_days": closing_7,
                    "closing_14_days": closing_14,
                    "high_touch_loans": high_touch_count,
                    "by_stage": by_stage,
                },
                message=f"Capacity: {capacity_pct}% ({total_active}/{max_loans} loans, {remaining_capacity} slots open)"
            )

        except Exception as e:
            logger.exception("calculate_workload_capacity failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _suggest_task_delegation(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Identify tasks that can be delegated to LOA or junior staff."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            processor_id = input_data.get("processor_id") or context.get("user_id")
            loan_id = input_data.get("loan_id")

            params = {"org_id": org_id}
            filters = ["l.organization_id = :org_id",
                       "l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"]
            if processor_id:
                filters.append("l.processor_id = :processor_id")
                params["processor_id"] = processor_id
            if loan_id:
                filters.append("l.id = :loan_id")
                params["loan_id"] = loan_id

            where_sql = " AND ".join(filters)

            # Get loans with pending tasks
            loans = db.execute(text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.borrower_email,
                    l.borrower_phone, l.stage,
                    COUNT(d.id) FILTER (WHERE d.status IN ('pending', 'uploaded')) as pending_docs
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id
                WHERE {where_sql}
                GROUP BY l.id, l.loan_number, l.borrower_name, l.borrower_email,
                         l.borrower_phone, l.stage
                HAVING COUNT(d.id) FILTER (WHERE d.status IN ('pending', 'uploaded')) > 0
                   OR l.stage IN ('APPLICATION', 'DISCLOSED', 'PROCESSING')
                ORDER BY l.closing_date ASC NULLS LAST
            """), params).fetchall()

            # Define delegatable task categories
            delegatable = []
            keep = []

            for loan in loans:
                # Tasks safe for LOA delegation
                loa_tasks = []
                # Tasks that require processor expertise
                processor_tasks = []

                if loan.stage in ("APPLICATION", "DISCLOSED"):
                    loa_tasks.append({
                        "task": "Initial document collection follow-up",
                        "description": f"Contact {loan.borrower_name} for missing documents",
                        "skill_level": "junior",
                    })
                    loa_tasks.append({
                        "task": "Verify contact information",
                        "description": "Confirm borrower email, phone, mailing address",
                        "skill_level": "junior",
                    })

                if loan.pending_docs > 0:
                    loa_tasks.append({
                        "task": "Document reminder follow-up",
                        "description": f"{loan.pending_docs} pending documents — send reminder",
                        "skill_level": "junior",
                    })

                if loan.stage in ("PROCESSING",):
                    loa_tasks.append({
                        "task": "Order third-party services",
                        "description": "Order appraisal, title, flood cert if not yet ordered",
                        "skill_level": "junior",
                    })
                    processor_tasks.append({
                        "task": "Income calculation and verification",
                        "description": "Calculate qualifying income from submitted docs",
                        "skill_level": "senior",
                    })

                if loan.stage in ("CONDITIONAL_APPROVAL", "APPROVED"):
                    processor_tasks.append({
                        "task": "Clear underwriting conditions",
                        "description": "Review and respond to UW conditions",
                        "skill_level": "senior",
                    })
                    loa_tasks.append({
                        "task": "Collect condition-clearing documents from borrower",
                        "description": "Request specific documents to clear conditions",
                        "skill_level": "junior",
                    })

                if loa_tasks:
                    delegatable.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "tasks": loa_tasks,
                    })
                if processor_tasks:
                    keep.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "tasks": processor_tasks,
                    })

            total_delegatable_tasks = sum(len(d["tasks"]) for d in delegatable)
            total_keep_tasks = sum(len(k["tasks"]) for k in keep)

            self.audit_log("suggest_task_delegation", details={
                "delegatable_tasks": total_delegatable_tasks,
                "keep_tasks": total_keep_tasks,
            })

            return ToolResult(
                success=True,
                data={
                    "delegatable": delegatable,
                    "keep_for_processor": keep,
                    "total_delegatable_tasks": total_delegatable_tasks,
                    "total_processor_tasks": total_keep_tasks,
                    "time_savings_estimate_hours": round(total_delegatable_tasks * 0.5, 1),
                },
                message=f"{total_delegatable_tasks} tasks can be delegated, saving ~{round(total_delegatable_tasks * 0.5, 1)} hours"
            )

        except Exception as e:
            logger.exception("suggest_task_delegation failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_touch_time(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Track processor time spent on each loan's documents."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            processor_id = input_data.get("processor_id") or context.get("user_id")
            loan_id = input_data.get("loan_id")
            period_days = input_data.get("period_days", 30)

            params = {"org_id": org_id, "period_days": period_days}
            filters = ["l.organization_id = :org_id"]
            if processor_id:
                filters.append("a.user_id = :processor_id")
                params["processor_id"] = processor_id
            if loan_id:
                filters.append("l.id = :loan_id")
                params["loan_id"] = loan_id

            where_sql = " AND ".join(filters)

            # Get activity durations from the activities table
            touch_data = db.execute(text(f"""
                SELECT
                    l.id as loan_id, l.loan_number, l.borrower_name, l.stage,
                    COUNT(a.id) as activity_count,
                    COALESCE(SUM(a.duration), 0) as total_duration_minutes
                FROM loans l
                JOIN activities a ON a.lead_id IS NOT NULL
                WHERE {where_sql}
                    AND a.created_at >= CURRENT_DATE - :period_days
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                GROUP BY l.id, l.loan_number, l.borrower_name, l.stage
                ORDER BY total_duration_minutes DESC
            """), params).fetchall()

            # Also get document-related activity by loan
            doc_activity = db.execute(text(f"""
                SELECT
                    l.id as loan_id,
                    COUNT(d.id) as total_docs,
                    COUNT(d.id) FILTER (WHERE d.status = 'active') as approved_docs,
                    COUNT(d.id) FILTER (WHERE d.status IN ('pending', 'uploaded')) as pending_docs
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {"AND l.id = :loan_id" if loan_id else ""}
                GROUP BY l.id
            """), params).fetchall()

            doc_map = {r.loan_id: r for r in doc_activity}

            loan_times = []
            total_minutes = 0

            for row in touch_data:
                doc_info = doc_map.get(row.loan_id)
                minutes = int(row.total_duration_minutes or 0)
                total_minutes += minutes

                loan_times.append({
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower": row.borrower_name,
                    "stage": row.stage,
                    "total_minutes": minutes,
                    "total_hours": round(minutes / 60, 1),
                    "activity_count": row.activity_count,
                    "docs_on_file": doc_info.total_docs if doc_info else 0,
                    "docs_approved": doc_info.approved_docs if doc_info else 0,
                    "docs_pending": doc_info.pending_docs if doc_info else 0,
                })

            self.audit_log("track_touch_time", details={
                "loans_tracked": len(loan_times),
                "total_hours": round(total_minutes / 60, 1),
            })

            return ToolResult(
                success=True,
                data={
                    "period_days": period_days,
                    "loans": loan_times,
                    "total_loans": len(loan_times),
                    "total_minutes": total_minutes,
                    "total_hours": round(total_minutes / 60, 1),
                    "avg_minutes_per_loan": round(total_minutes / len(loan_times), 1) if loan_times else 0,
                },
                message=f"Touch time: {round(total_minutes / 60, 1)} hours across {len(loan_times)} loans"
            )

        except Exception as e:
            logger.exception("track_touch_time failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_pipeline_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Generate processor document pipeline status report."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            processor_id = input_data.get("processor_id") or context.get("user_id")
            report_type = input_data.get("report_type", "daily")

            period_map = {"daily": 1, "weekly": 7, "monthly": 30}
            period_days = period_map.get(report_type, 1)

            params = {"org_id": org_id, "period_days": period_days}
            processor_filter = ""
            if processor_id:
                processor_filter = "AND l.processor_id = :processor_id"
                params["processor_id"] = processor_id

            # Active pipeline summary
            pipeline = db.execute(text(f"""
                SELECT
                    l.stage,
                    COUNT(*) as loan_count,
                    COALESCE(SUM(l.amount), 0) as volume
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
                    {processor_filter}
                GROUP BY l.stage
                ORDER BY l.stage
            """), params).fetchall()

            # Document activity in period
            doc_activity = db.execute(text(f"""
                SELECT
                    COUNT(*) as total_uploads,
                    COUNT(CASE WHEN d.status = 'active' THEN 1 END) as approved,
                    COUNT(CASE WHEN d.status IN ('pending', 'uploaded') THEN 1 END) as pending
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.uploaded_at >= CURRENT_DATE - :period_days
                    {processor_filter}
            """), params).fetchone()

            # Loans funded in period
            funded = db.execute(text(f"""
                SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as volume
                FROM loans l
                WHERE l.organization_id = :org_id
                    AND l.funded_date >= CURRENT_DATE - :period_days
                    {processor_filter}
            """), params).fetchone()

            total_active = sum(row.loan_count for row in pipeline)
            total_volume = sum(float(row.volume or 0) for row in pipeline)

            report = {
                "report_type": report_type,
                "period_days": period_days,
                "generated_at": datetime.now().isoformat(),
                "pipeline_summary": {
                    "total_active_loans": total_active,
                    "total_volume": total_volume,
                    "by_stage": [
                        {
                            "stage": row.stage,
                            "count": row.loan_count,
                            "volume": float(row.volume or 0),
                        }
                        for row in pipeline
                    ],
                },
                "document_activity": {
                    "total_uploads": doc_activity.total_uploads if doc_activity else 0,
                    "approved": doc_activity.approved if doc_activity else 0,
                    "pending_review": doc_activity.pending if doc_activity else 0,
                },
                "funded_in_period": {
                    "count": funded.count if funded else 0,
                    "volume": float(funded.volume or 0) if funded else 0,
                },
            }

            self.audit_log("generate_pipeline_report", details={
                "report_type": report_type,
                "total_active": total_active,
            })

            return ToolResult(
                success=True,
                data=report,
                message=f"{report_type.title()} report: {total_active} active loans, ${total_volume:,.0f} volume"
            )

        except Exception as e:
            logger.exception("generate_pipeline_report failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _identify_reusable_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Find reusable documents from previous loans."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)

            borrower_email = input_data.get("borrower_email")

            # If no email provided, get it from the loan
            if not borrower_email:
                loan = db.execute(text("""
                    SELECT borrower_email, borrower_name FROM loans
                    WHERE id = :loan_id AND organization_id = :org_id
                """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

                if loan:
                    borrower_email = loan.borrower_email

            if not borrower_email:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "reusable_docs": [], "message": "No borrower email to cross-reference"},
                    message="Cannot identify reusable documents without borrower email"
                )

            # Find documents from other loans with the same borrower email
            prior_docs = db.execute(text("""
                SELECT
                    d.id as doc_id, d.doc_type, d.doc_category,
                    d.filename, d.uploaded_at, d.status,
                    l.id as source_loan_id, l.loan_number as source_loan_number,
                    l.funded_date
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE l.borrower_email = :borrower_email
                    AND l.id != :loan_id
                    AND d.status = 'active'
                ORDER BY d.uploaded_at DESC
            """), {
                "org_id": org_id,
                "borrower_email": borrower_email,
                "loan_id": loan_id,
            }).fetchall()

            # Filter to documents that are still potentially valid
            reusable = []
            expired = []
            today = date.today()

            # Doc types that can be reused (typically valid for 60-120 days)
            reusable_types = {
                "drivers_license": 365,  # Valid for a year typically
                "passport": 365,
                "ssn_card": 365,
                "tax_returns": 365,  # Prior year returns remain valid
                "w2": 365,
                "credit_explanation": 180,
                "bankruptcy_docs": 365,
            }

            for doc in prior_docs:
                max_age_days = reusable_types.get(doc.doc_type)
                if max_age_days is None:
                    continue  # Not a reusable type

                doc_age = (today - doc.uploaded_at.date()).days if doc.uploaded_at else 999
                if doc_age <= max_age_days:
                    reusable.append({
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type,
                        "doc_category": doc.doc_category,
                        "filename": doc.filename,
                        "source_loan": doc.source_loan_number,
                        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                        "age_days": doc_age,
                        "max_valid_days": max_age_days,
                    })
                else:
                    expired.append({
                        "doc_type": doc.doc_type,
                        "source_loan": doc.source_loan_number,
                        "age_days": doc_age,
                        "reason": f"Expired ({doc_age} days old, max {max_age_days})",
                    })

            self.audit_log("identify_reusable_documents", "loan", entity_id=loan_id, details={
                "reusable_count": len(reusable),
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_email": borrower_email,
                    "reusable_docs": reusable,
                    "expired_docs": expired,
                    "reusable_count": len(reusable),
                    "prior_loans_checked": len(set(d.source_loan_id for d in prior_docs)),
                },
                message=f"Found {len(reusable)} reusable documents from prior loans"
            )

        except Exception as e:
            logger.exception("identify_reusable_documents failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _automate_data_entry(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Extract data from approved documents and suggest loan field population."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            document_id = input_data["document_id"]
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)

            # Get document info
            doc = db.execute(text("""
                SELECT d.id, d.doc_type, d.doc_category, d.filename, d.status
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.id = :document_id AND d.loan_id = :loan_id
            """), {"document_id": document_id, "loan_id": loan_id, "org_id": org_id}).fetchone()

            if not doc:
                return ToolResult(success=False, error=f"Document {document_id} not found for loan {loan_id}")

            if doc.status != "active":
                return ToolResult(
                    success=False,
                    error=f"Document status is '{doc.status}' — must be 'active' for data extraction"
                )

            # Define field extraction map by document type
            extraction_map = {
                "paystubs": {
                    "fields": ["gross_monthly_income", "ytd_earnings", "employer_name"],
                    "loan_columns": ["borrower_employer", "borrower_income"],
                },
                "w2": {
                    "fields": ["annual_income", "employer_name", "employer_ein"],
                    "loan_columns": ["borrower_employer", "borrower_income"],
                },
                "bank_statements": {
                    "fields": ["account_balance", "avg_monthly_balance", "institution_name"],
                    "loan_columns": ["total_assets"],
                },
                "appraisal": {
                    "fields": ["appraised_value", "property_type", "year_built", "living_area_sqft"],
                    "loan_columns": ["appraisal_value", "property_type"],
                },
                "purchase_contract": {
                    "fields": ["purchase_price", "closing_date", "seller_name"],
                    "loan_columns": ["amount", "closing_date"],
                },
                "credit_report": {
                    "fields": ["credit_score", "total_monthly_debts"],
                    "loan_columns": ["credit_score"],
                },
            }

            doc_type = doc.doc_type
            if doc_type not in extraction_map:
                return ToolResult(
                    success=True,
                    data={
                        "document_id": document_id,
                        "doc_type": doc_type,
                        "extractable": False,
                        "message": f"No automated extraction available for {doc_type}",
                    },
                    message=f"No extraction template for {doc_type}"
                )

            mapping = extraction_map[doc_type]

            self.audit_log("automate_data_entry", "document", entity_id=document_id, details={
                "doc_type": doc_type,
                "fields": mapping["fields"],
            })

            return ToolResult(
                success=True,
                data={
                    "document_id": document_id,
                    "loan_id": loan_id,
                    "doc_type": doc_type,
                    "extractable": True,
                    "fields_to_extract": mapping["fields"],
                    "target_loan_columns": mapping["loan_columns"],
                    "requires_review": True,
                    "note": "Extracted values require processor verification before updating loan record",
                },
                message=f"Data extraction ready for {doc_type}: {len(mapping['fields'])} fields"
            )

        except Exception as e:
            logger.exception("automate_data_entry failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _flag_quality_issues(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Flag documents likely to be kicked back by underwriting."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)

            # Get loan info and documents
            loan = db.execute(text("""
                SELECT id, loan_number, borrower_name, stage, loan_type,
                       credit_docs_expire_date, appraisal_docs_expire_date
                FROM loans WHERE id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = db.execute(text("""
                SELECT id, doc_type, doc_category, status, filename, uploaded_at
                FROM documents WHERE loan_id = :loan_id
                ORDER BY doc_category, doc_type
            """), {"loan_id": loan_id}).fetchall()

            quality_issues = []
            today = date.today()

            # Check 1: Document freshness (income docs older than 120 days)
            for doc in docs:
                if doc.doc_type in ("paystubs",) and doc.uploaded_at:
                    age_days = (today - doc.uploaded_at.date()).days
                    if age_days > 60:
                        quality_issues.append({
                            "doc_id": doc.id,
                            "doc_type": doc.doc_type,
                            "issue": "stale_document",
                            "severity": "high" if age_days > 90 else "medium",
                            "detail": f"Pay stubs are {age_days} days old (max 60 days for most lenders)",
                            "action": "Request current pay stubs",
                        })

                if doc.doc_type in ("bank_statements",) and doc.uploaded_at:
                    age_days = (today - doc.uploaded_at.date()).days
                    if age_days > 90:
                        quality_issues.append({
                            "doc_id": doc.id,
                            "doc_type": doc.doc_type,
                            "issue": "stale_document",
                            "severity": "high" if age_days > 120 else "medium",
                            "detail": f"Bank statements are {age_days} days old (max 90 days typically)",
                            "action": "Request current bank statements",
                        })

            # Check 2: Credit docs expiration
            if loan.credit_docs_expire_date:
                days_until = (loan.credit_docs_expire_date - today).days
                if days_until < 0:
                    quality_issues.append({
                        "doc_type": "credit_report",
                        "issue": "expired_document",
                        "severity": "critical",
                        "detail": f"Credit docs expired {abs(days_until)} days ago",
                        "action": "Order new credit report immediately",
                    })
                elif days_until < 14:
                    quality_issues.append({
                        "doc_type": "credit_report",
                        "issue": "expiring_soon",
                        "severity": "high",
                        "detail": f"Credit docs expire in {days_until} days",
                        "action": "Expedite submission before credit expires",
                    })

            # Check 3: Appraisal docs expiration
            if loan.appraisal_docs_expire_date:
                days_until = (loan.appraisal_docs_expire_date - today).days
                if days_until < 0:
                    quality_issues.append({
                        "doc_type": "appraisal",
                        "issue": "expired_document",
                        "severity": "critical",
                        "detail": f"Appraisal expired {abs(days_until)} days ago",
                        "action": "Order appraisal update or recertification",
                    })
                elif days_until < 14:
                    quality_issues.append({
                        "doc_type": "appraisal",
                        "issue": "expiring_soon",
                        "severity": "high",
                        "detail": f"Appraisal expires in {days_until} days",
                        "action": "Expedite submission before appraisal expires",
                    })

            # Check 4: Missing critical document categories
            doc_categories_on_file = {d.doc_category for d in docs if d.status == "active"}
            required_categories = {"income", "assets", "credit"}
            missing_categories = required_categories - doc_categories_on_file

            for cat in missing_categories:
                quality_issues.append({
                    "doc_type": cat,
                    "issue": "missing_category",
                    "severity": "critical",
                    "detail": f"No {cat} documents on file",
                    "action": f"Collect {cat} documentation before submission",
                })

            # Sort by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            quality_issues.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))

            critical_count = len([q for q in quality_issues if q["severity"] == "critical"])

            self.audit_log("flag_quality_issues", "loan", entity_id=loan_id, details={
                "total_issues": len(quality_issues),
                "critical": critical_count,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "quality_issues": quality_issues,
                    "total_issues": len(quality_issues),
                    "critical_count": critical_count,
                    "uw_ready": len(quality_issues) == 0,
                },
                message=f"Quality check: {len(quality_issues)} issues ({critical_count} critical), {'UW-ready' if not quality_issues else 'NOT UW-ready'}"
            )

        except Exception as e:
            logger.exception("flag_quality_issues failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_submission_checklist(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Pre-submission checklist for underwriting."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            loan_id = input_data["loan_id"]
            org_id = self.require_org_id()
            self.verify_loan_tenant(db, loan_id)
            lender = input_data.get("lender")

            loan = db.execute(text("""
                SELECT id, loan_number, borrower_name, stage, loan_type, amount,
                       application_date, initial_disclosures_sent_date,
                       initial_disclosures_signed_date,
                       appraisal_ordered_date, appraisal_received_date,
                       title_ordered_date, title_received_date,
                       credit_docs_expire_date, appraisal_docs_expire_date,
                       closing_date
                FROM loans WHERE id = :loan_id AND organization_id = :org_id
            """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            docs = db.execute(text("""
                SELECT doc_type, doc_category, status
                FROM documents WHERE loan_id = :loan_id
            """), {"loan_id": loan_id}).fetchall()

            active_types = {d.doc_type for d in docs if d.status == "active"}
            active_categories = {d.doc_category for d in docs if d.status == "active"}

            checklist = []

            # Section 1: Application & Disclosures
            checklist.append({
                "section": "Application & Disclosures",
                "items": [
                    {
                        "item": "Application signed",
                        "status": "complete" if loan.application_date else "missing",
                        "required": True,
                    },
                    {
                        "item": "Initial disclosures sent",
                        "status": "complete" if loan.initial_disclosures_sent_date else "missing",
                        "required": True,
                    },
                    {
                        "item": "Initial disclosures signed by borrower",
                        "status": "complete" if loan.initial_disclosures_signed_date else "missing",
                        "required": True,
                    },
                ],
            })

            # Section 2: Income Documentation
            income_items = [
                {"type": "paystubs", "label": "Most recent pay stubs (30 days)"},
                {"type": "w2", "label": "W-2s (2 years)"},
                {"type": "tax_returns", "label": "Tax returns (2 years, if applicable)"},
            ]
            checklist.append({
                "section": "Income Documentation",
                "items": [
                    {
                        "item": item["label"],
                        "status": "complete" if item["type"] in active_types else "missing",
                        "required": True,
                    }
                    for item in income_items
                ],
            })

            # Section 3: Asset Documentation
            asset_items = [
                {"type": "bank_statements", "label": "Bank statements (2 months)"},
                {"type": "investment_statements", "label": "Investment statements (if applicable)"},
            ]
            checklist.append({
                "section": "Asset Documentation",
                "items": [
                    {
                        "item": item["label"],
                        "status": "complete" if item["type"] in active_types else "missing",
                        "required": item["type"] == "bank_statements",
                    }
                    for item in asset_items
                ],
            })

            # Section 4: Property Documentation
            property_items = [
                {
                    "item": "Appraisal ordered",
                    "status": "complete" if loan.appraisal_ordered_date else "missing",
                    "required": True,
                },
                {
                    "item": "Appraisal received",
                    "status": "complete" if loan.appraisal_received_date else "pending",
                    "required": True,
                },
                {
                    "item": "Title ordered",
                    "status": "complete" if loan.title_ordered_date else "missing",
                    "required": True,
                },
                {
                    "item": "Title received",
                    "status": "complete" if loan.title_received_date else "pending",
                    "required": True,
                },
                {
                    "item": "Purchase contract on file",
                    "status": "complete" if "purchase_contract" in active_types else "missing",
                    "required": True,
                },
            ]
            checklist.append({"section": "Property Documentation", "items": property_items})

            # Section 5: Credit & Identity
            checklist.append({
                "section": "Credit & Identity",
                "items": [
                    {
                        "item": "Credit report on file",
                        "status": "complete" if "credit_report" in active_types else "missing",
                        "required": True,
                    },
                    {
                        "item": "Government-issued ID",
                        "status": "complete" if "drivers_license" in active_types or "passport" in active_types else "missing",
                        "required": True,
                    },
                ],
            })

            # Section 6: Compliance Checks
            today = date.today()
            compliance_items = [
                {
                    "item": "Credit docs not expired",
                    "status": "complete" if not loan.credit_docs_expire_date or loan.credit_docs_expire_date > today else "failed",
                    "required": True,
                },
                {
                    "item": "Appraisal not expired",
                    "status": "complete" if not loan.appraisal_docs_expire_date or loan.appraisal_docs_expire_date > today else "failed",
                    "required": True,
                },
            ]
            checklist.append({"section": "Compliance Checks", "items": compliance_items})

            # Calculate summary
            all_items = []
            for section in checklist:
                all_items.extend(section["items"])

            total_required = len([i for i in all_items if i.get("required")])
            complete_required = len([i for i in all_items if i.get("required") and i["status"] == "complete"])
            failed = len([i for i in all_items if i["status"] == "failed"])
            missing_required = len([i for i in all_items if i.get("required") and i["status"] == "missing"])

            is_ready = missing_required == 0 and failed == 0

            self.audit_log("generate_submission_checklist", "loan", entity_id=loan_id, details={
                "complete": complete_required,
                "missing": missing_required,
                "ready": is_ready,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "loan_type": loan.loan_type,
                    "lender": lender,
                    "checklist": checklist,
                    "summary": {
                        "total_items": len(all_items),
                        "total_required": total_required,
                        "complete": complete_required,
                        "missing": missing_required,
                        "failed": failed,
                        "completion_pct": round((complete_required / total_required) * 100, 1) if total_required > 0 else 0,
                    },
                    "is_submission_ready": is_ready,
                },
                message=f"Submission checklist: {complete_required}/{total_required} required items complete, {'READY' if is_ready else 'NOT READY'}"
            )

        except Exception as e:
            logger.exception("generate_submission_checklist failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _compare_doc_versions(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Compare new upload vs. previously rejected version."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            document_id = input_data["document_id"]
            previous_document_id = input_data["previous_document_id"]
            org_id = self.require_org_id()

            # Get both documents with tenant isolation
            current_doc = db.execute(text("""
                SELECT d.id, d.doc_type, d.doc_category, d.filename,
                       d.status, d.uploaded_at, d.source,
                       l.id as loan_id, l.loan_number
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.id = :doc_id
            """), {"doc_id": document_id, "org_id": org_id}).fetchone()

            previous_doc = db.execute(text("""
                SELECT d.id, d.doc_type, d.doc_category, d.filename,
                       d.status, d.uploaded_at, d.source,
                       l.id as loan_id, l.loan_number
                FROM documents d
                JOIN loans l ON l.id = d.loan_id AND l.organization_id = :org_id
                WHERE d.id = :doc_id
            """), {"doc_id": previous_document_id, "org_id": org_id}).fetchone()

            if not current_doc:
                return ToolResult(success=False, error=f"Current document {document_id} not found")
            if not previous_doc:
                return ToolResult(success=False, error=f"Previous document {previous_document_id} not found")

            # Compare metadata
            differences = []
            warnings = []

            # Check doc types match
            if current_doc.doc_type != previous_doc.doc_type:
                differences.append({
                    "field": "doc_type",
                    "previous": previous_doc.doc_type,
                    "current": current_doc.doc_type,
                    "note": "Document type changed — verify correct classification",
                })
                warnings.append("Document type mismatch between versions")

            # Check upload recency
            if current_doc.uploaded_at and previous_doc.uploaded_at:
                days_between = (current_doc.uploaded_at - previous_doc.uploaded_at).days
                differences.append({
                    "field": "upload_date",
                    "previous": previous_doc.uploaded_at.isoformat(),
                    "current": current_doc.uploaded_at.isoformat(),
                    "days_between": days_between,
                })

            # Check if same loan
            if current_doc.loan_id != previous_doc.loan_id:
                warnings.append("Documents are from different loans — verify correct file")

            # Check source
            if current_doc.source != previous_doc.source:
                differences.append({
                    "field": "source",
                    "previous": previous_doc.source,
                    "current": current_doc.source,
                })

            # Status comparison
            differences.append({
                "field": "status",
                "previous": previous_doc.status,
                "current": current_doc.status,
            })

            self.audit_log("compare_doc_versions", "document", entity_id=document_id, details={
                "previous_id": previous_document_id,
                "differences": len(differences),
            })

            return ToolResult(
                success=True,
                data={
                    "current": {
                        "doc_id": current_doc.id,
                        "doc_type": current_doc.doc_type,
                        "filename": current_doc.filename,
                        "status": current_doc.status,
                        "uploaded_at": current_doc.uploaded_at.isoformat() if current_doc.uploaded_at else None,
                    },
                    "previous": {
                        "doc_id": previous_doc.id,
                        "doc_type": previous_doc.doc_type,
                        "filename": previous_doc.filename,
                        "status": previous_doc.status,
                        "uploaded_at": previous_doc.uploaded_at.isoformat() if previous_doc.uploaded_at else None,
                    },
                    "differences": differences,
                    "warnings": warnings,
                    "version_improved": current_doc.status in ("active", "pending") and previous_doc.status in ("rejected", "expired"),
                },
                message=f"Version comparison: {len(differences)} differences, {len(warnings)} warnings"
            )

        except Exception as e:
            logger.exception("compare_doc_versions failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _estimate_time_to_clear(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Estimate time to clear all documents per loan."""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.require_org_id()
            loan_id = input_data.get("loan_id")
            processor_id = input_data.get("processor_id") or context.get("user_id")

            params = {"org_id": org_id}
            filters = ["l.organization_id = :org_id",
                       "l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')"]
            if loan_id:
                filters.append("l.id = :loan_id")
                params["loan_id"] = loan_id
            if processor_id:
                filters.append("l.processor_id = :processor_id")
                params["processor_id"] = processor_id

            where_sql = " AND ".join(filters)

            loans = db.execute(text(f"""
                SELECT
                    l.id, l.loan_number, l.borrower_name, l.stage,
                    l.closing_date,
                    COUNT(d.id) FILTER (WHERE d.status IN ('pending', 'uploaded')) as pending_docs,
                    COUNT(d.id) FILTER (WHERE d.status = 'active') as approved_docs,
                    COUNT(ca.id) FILTER (WHERE ca.status = 'open') as open_conditions
                FROM loans l
                LEFT JOIN documents d ON d.loan_id = l.id
                LEFT JOIN compliance_alerts ca ON ca.loan_id = l.id AND ca.status = 'open'
                WHERE {where_sql}
                GROUP BY l.id, l.loan_number, l.borrower_name, l.stage, l.closing_date
                HAVING COUNT(d.id) FILTER (WHERE d.status IN ('pending', 'uploaded')) > 0
                    OR COUNT(ca.id) FILTER (WHERE ca.status = 'open') > 0
                ORDER BY l.closing_date ASC NULLS LAST
            """), params).fetchall()

            # Time estimates per activity (in minutes)
            time_per_doc_review = 15  # minutes per document review
            time_per_condition = 30  # minutes per condition response
            time_per_data_entry = 10  # minutes per doc data entry

            estimates = []
            total_estimated_minutes = 0

            for loan in loans:
                pending = loan.pending_docs or 0
                conditions = loan.open_conditions or 0

                # Estimate review time
                doc_review_time = pending * time_per_doc_review
                condition_time = conditions * time_per_condition
                data_entry_time = pending * time_per_data_entry
                total_loan_minutes = doc_review_time + condition_time + data_entry_time

                total_estimated_minutes += total_loan_minutes

                days_to_close = (loan.closing_date - date.today()).days if loan.closing_date else None
                urgency = "critical" if days_to_close is not None and days_to_close <= 3 else \
                          "high" if days_to_close is not None and days_to_close <= 7 else \
                          "normal"

                estimates.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "stage": loan.stage,
                    "pending_docs": pending,
                    "open_conditions": conditions,
                    "estimated_minutes": total_loan_minutes,
                    "estimated_hours": round(total_loan_minutes / 60, 1),
                    "days_to_close": days_to_close,
                    "urgency": urgency,
                    "breakdown": {
                        "doc_review": doc_review_time,
                        "condition_response": condition_time,
                        "data_entry": data_entry_time,
                    },
                })

            self.audit_log("estimate_time_to_clear", details={
                "loans_estimated": len(estimates),
                "total_hours": round(total_estimated_minutes / 60, 1),
            })

            return ToolResult(
                success=True,
                data={
                    "estimates": estimates,
                    "total_loans": len(estimates),
                    "total_estimated_minutes": total_estimated_minutes,
                    "total_estimated_hours": round(total_estimated_minutes / 60, 1),
                    "total_estimated_days": round(total_estimated_minutes / 480, 1),  # 8-hour workday
                    "avg_minutes_per_loan": round(total_estimated_minutes / len(estimates), 1) if estimates else 0,
                },
                message=f"Estimated {round(total_estimated_minutes / 60, 1)} hours to clear {len(estimates)} loans"
            )

        except Exception as e:
            logger.exception("estimate_time_to_clear failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
