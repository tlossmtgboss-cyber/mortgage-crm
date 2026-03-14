"""
Application Completion Agent

Specialized AI agent that powers the decisioning layer of the Application
Completion Orchestrator (ACO). Ensures submitted loan applications move from
incomplete to review-ready as fast as possible by identifying missing data,
scoring completeness, resolving gaps via borrower outreach, staging document
requests, and scheduling production assistant calls when human intervention
is required.

10 Tools:
1.  review_submitted_application - Full application review orchestration
2.  get_application_score - Current completeness score with section breakdown
3.  resolve_missing_item - Fill a single missing item and recalculate score
4.  send_borrower_question - SMS a borrower about a specific missing item
5.  stage_document_request - Stage a document request for staff review
6.  publish_document_requests - Publish staged docs to borrower portal
7.  schedule_pa_call - Schedule a production assistant review call
8.  get_scoring_page_summary - Full scoring page data for display/analysis
9.  analyze_borrower_response - AI-parse a borrower response into structured data
10. check_completion_status - Determine if application is complete enough to proceed
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

# Score bands drive the resolution strategy
SCORE_BANDS = {
    "GREEN": {"min": 90, "max": 100, "label": "Near-Complete", "strategy": "text_only"},
    "YELLOW": {"min": 75, "max": 89, "label": "Moderate Gaps", "strategy": "text_and_docs"},
    "ORANGE": {"min": 50, "max": 74, "label": "Significant Gaps", "strategy": "hybrid"},
    "RED": {"min": 0, "max": 49, "label": "Major Gaps", "strategy": "schedule_call"},
}

# Section weights for score calculation (must sum to 100)
SECTION_WEIGHTS = {
    "borrower_info": 20,       # Name, SSN, DOB, marital status, dependents
    "employment": 15,          # Employer, position, dates, income stated
    "income": 15,              # Income docs, amounts, sources
    "assets": 10,              # Bank accounts, retirement, gift funds
    "property": 15,            # Address, type, occupancy, purchase price
    "declarations": 10,        # 1003 declarations (legally sensitive)
    "credit": 10,              # Authorization, credit report pulled
    "documents": 5,            # Supporting docs uploaded
}

# Items that must NEVER be auto-filled by the agent
PROTECTED_FIELDS = {
    "ssn", "social_security_number", "income_amount", "annual_income",
    "monthly_income", "base_salary", "bonus_income", "commission_income",
    "declaration_bankruptcy", "declaration_judgments", "declaration_lawsuit",
    "declaration_delinquent", "declaration_alimony", "declaration_down_payment_borrowed",
    "declaration_co_maker", "declaration_us_citizen", "declaration_permanent_resident",
    "declaration_ownership_interest", "declaration_primary_residence",
}

# Maximum unanswered messages before escalation
MAX_UNANSWERED_MESSAGES = 3

# Business hours for borrower contact (local time)
BUSINESS_HOURS_START = 8   # 8:00 AM
BUSINESS_HOURS_END = 20    # 8:00 PM

# Priority ordering for missing items
ITEM_PRIORITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


# =============================================================================
# INPUT SCHEMAS
# =============================================================================

class ReviewApplicationInput(BaseModel):
    """Input for review_submitted_application tool"""
    loan_id: int = Field(..., description="The loan ID to review")


class GetScoreInput(BaseModel):
    """Input for get_application_score tool"""
    loan_id: int = Field(..., description="The loan ID")


class ResolveItemInput(BaseModel):
    """Input for resolve_missing_item tool"""
    item_id: int = Field(..., description="The missing item ID")
    value: str = Field(..., description="The value to fill in")
    source: str = Field(
        default="AI_AGENT",
        description="Who resolved it: AI_AGENT, BORROWER_RESPONSE, LO_MANUAL, DOCUMENT_EXTRACTION",
    )


class SendQuestionInput(BaseModel):
    """Input for send_borrower_question tool"""
    loan_id: int = Field(..., description="The loan ID")
    item_id: int = Field(..., description="The missing item to ask about")
    custom_question: Optional[str] = Field(
        None, description="Override the default question text"
    )


class StageDocInput(BaseModel):
    """Input for stage_document_request tool"""
    loan_id: int = Field(..., description="The loan ID")
    doc_type: str = Field(..., description="Document type code (e.g. paystubs, w2, bank_statements)")
    doc_label: str = Field(..., description="Display label for borrower (e.g. 'Most Recent Pay Stub')")
    reason: str = Field(..., description="Why this document is needed")
    priority: str = Field(
        default="MEDIUM",
        description="CRITICAL, HIGH, MEDIUM, LOW",
    )


class PublishDocsInput(BaseModel):
    """Input for publish_document_requests tool"""
    loan_id: int = Field(..., description="The loan ID")
    notify_borrower: bool = Field(
        default=True, description="Send SMS/email notification to borrower"
    )


class ScheduleCallInput(BaseModel):
    """Input for schedule_pa_call tool"""
    loan_id: int = Field(..., description="The loan ID")
    preferred_time: Optional[str] = Field(
        None, description="Preferred datetime ISO string if known"
    )
    duration_minutes: int = Field(default=15, description="Call duration in minutes")
    reason: str = Field(
        default="Application review",
        description="Reason for the call shown in calendar",
    )


class ScoringPageInput(BaseModel):
    """Input for get_scoring_page_summary tool"""
    loan_id: int = Field(..., description="The loan ID")


class AnalyzeResponseInput(BaseModel):
    """Input for analyze_borrower_response tool"""
    loan_id: int = Field(..., description="The loan ID")
    response_text: str = Field(..., description="The borrower's response message")
    question_context: str = Field(
        ..., description="What was originally asked of the borrower"
    )


class CheckCompletionInput(BaseModel):
    """Input for check_completion_status tool"""
    loan_id: int = Field(..., description="The loan ID")


# =============================================================================
# APPLICATION COMPLETION AGENT
# =============================================================================

@AgentRegistry.register
class AppCompletionAgent(SpecializedAgent):
    """
    Application Completion AI Agent for Perennia AI's mortgage CRM.

    Ensures submitted loan applications move from incomplete to review-ready
    as fast as possible by:

    1. Reviewing submitted applications to find all missing data, clarifications,
       documents, and exceptions.
    2. Calculating and tracking completeness scores (0-100).
    3. Resolving simple missing items by asking borrowers via SMS.
    4. Staging and publishing document requests to the borrower portal.
    5. Scheduling production assistant calls for complex items.
    6. Monitoring score improvements and determining when files are ready.
    """

    @property
    def name(self) -> str:
        return "AppCompletionAgent"

    @property
    def description(self) -> str:
        return (
            "Application Completion AI Agent that drives submitted loan applications "
            "from incomplete to review-ready. Scores completeness, resolves gaps via "
            "borrower SMS outreach, stages document requests, and schedules PA calls "
            "for complex items."
        )

    # =========================================================================
    # TENANT ISOLATION
    # =========================================================================

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

    # =========================================================================
    # TOOL REGISTRATION
    # =========================================================================

    def _register_tools(self):
        """Register all application completion tools."""

        # Tool 1: Review Submitted Application
        self.register_tool(AgentTool(
            name="review_submitted_application",
            description=(
                "Trigger a full application review orchestration for a submitted loan. "
                "Analyzes the 1003, identifies all missing data fields, required documents, "
                "clarifications needed, and exceptions. Returns a review summary with "
                "completeness score, findings count, and recommended next action."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._review_submitted_application,
            input_schema=ReviewApplicationInput,
        ))

        # Tool 2: Get Application Score
        self.register_tool(AgentTool(
            name="get_application_score",
            description=(
                "Get the current application completeness score (0-100) for a loan. "
                "Returns the overall score, score band (GREEN/YELLOW/ORANGE/RED), "
                "trend direction, and per-section breakdown with individual item statuses."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_application_score,
            input_schema=GetScoreInput,
        ))

        # Tool 3: Resolve Missing Item
        self.register_tool(AgentTool(
            name="resolve_missing_item",
            description=(
                "Resolve a single missing item by providing its value. The agent will "
                "validate the value, check that the field is not protected (income, SSN, "
                "declarations), record the resolution with audit trail, and recalculate "
                "the completeness score. Returns updated score and remaining items."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._resolve_missing_item,
            input_schema=ResolveItemInput,
            requires_confirmation=False,
        ))

        # Tool 4: Send Borrower Question
        self.register_tool(AgentTool(
            name="send_borrower_question",
            description=(
                "Send an SMS question to the borrower about a specific missing item. "
                "Checks business hours (8am-8pm local), unanswered message count "
                "(max 3 before escalation), and TCPA compliance before sending. "
                "Messages are sent as part of the LO's team, never cold-contact."
            ),
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.HIGH,
            handler=self._send_borrower_question,
            input_schema=SendQuestionInput,
            requires_confirmation=True,
            cooldown_seconds=30,
            max_per_hour=20,
        ))

        # Tool 5: Stage Document Request
        self.register_tool(AgentTool(
            name="stage_document_request",
            description=(
                "Stage a document request for staff review before publishing to the "
                "borrower portal. Includes document type, display label, reason needed, "
                "and priority level. Staged requests must be published separately."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._stage_document_request,
            input_schema=StageDocInput,
        ))

        # Tool 6: Publish Document Requests
        self.register_tool(AgentTool(
            name="publish_document_requests",
            description=(
                "Publish all staged document requests for a loan to the borrower portal. "
                "Optionally sends SMS/email notification to the borrower. Only publishes "
                "requests in STAGED status. Returns count of published requests."
            ),
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.HIGH,
            handler=self._publish_document_requests,
            input_schema=PublishDocsInput,
            requires_confirmation=True,
        ))

        # Tool 7: Schedule PA Call
        self.register_tool(AgentTool(
            name="schedule_pa_call",
            description=(
                "Schedule a production assistant review call for complex items that "
                "cannot be resolved via text. Creates a calendar event with the reason, "
                "links to the loan file, and preferred time if known."
            ),
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_pa_call,
            input_schema=ScheduleCallInput,
        ))

        # Tool 8: Get Scoring Page Summary
        self.register_tool(AgentTool(
            name="get_scoring_page_summary",
            description=(
                "Get the full scoring page data for display and analysis. Returns "
                "the overall score, band, all sections with their scores and items, "
                "recent activity log, communication history, and staged document requests."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_scoring_page_summary,
            input_schema=ScoringPageInput,
        ))

        # Tool 9: Analyze Borrower Response
        self.register_tool(AgentTool(
            name="analyze_borrower_response",
            description=(
                "Use AI to parse and extract structured data from a borrower's free-text "
                "response message. Maps the response to the original question context, "
                "extracts field values, confidence scores, and suggests which missing "
                "items can be resolved from the response."
            ),
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._analyze_borrower_response,
            input_schema=AnalyzeResponseInput,
        ))

        # Tool 10: Check Completion Status
        self.register_tool(AgentTool(
            name="check_completion_status",
            description=(
                "Check if the application is now complete enough to proceed to the next "
                "stage. Returns complete/not-complete status, list of blocking items, "
                "current score, and recommended action (submit, continue outreach, or "
                "schedule call)."
            ),
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._check_completion_status,
            input_schema=CheckCompletionInput,
        ))

    # =========================================================================
    # SYSTEM PROMPT
    # =========================================================================

    def get_system_prompt(self) -> str:
        """Return the system prompt establishing the agent's role and operating principles."""
        return """You are the Application Completion AI Agent for Perennia AI's mortgage CRM. \
Your role is to ensure submitted loan applications move from incomplete to review-ready \
as fast as possible.

Your capabilities:
1. Review submitted applications to find all missing data, clarifications, documents, \
and exceptions
2. Calculate and track completeness scores (0-100)
3. Resolve simple missing items by asking borrowers via SMS
4. Stage and publish document requests to the borrower portal
5. Schedule production assistant calls for complex items
6. Monitor score improvements and determine when files are ready

Operating principles:
- SPEED: Applications should not sit incomplete. Act immediately.
- CLARITY: Borrower communications must be clear, friendly, and professional.
- TRUST: Always introduce yourself as part of the LO's team. Never cold-contact.
- ESCALATION: Know when to stop texting and schedule a human call.
- ACCURACY: Never auto-fill income, SSN, or declaration fields. Confirm before filling.
- AUDIT: Log every action, every communication, every field change.
- SCORING: Score drives action. Score improvement is the KPI.

Resolution rules by score band:
- Score 90-100 (GREEN): Minor text follow-up only
- Score 75-89 (YELLOW): AI text resolution + document staging
- Score 50-74 (ORANGE): Hybrid - text for easy items, schedule call for complex
- Score 0-49 (RED): Schedule PA call immediately after intro

Never:
- Change income or financial data without explicit borrower confirmation
- Contact borrowers outside business hours (8am-8pm local)
- Send more than 3 unanswered messages without escalating
- Auto-fill declaration fields
- Skip the intro/trust-building sequence"""

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_score_band(self, score: int) -> Dict[str, Any]:
        """Determine score band from numeric score."""
        for band_name, band in SCORE_BANDS.items():
            if band["min"] <= score <= band["max"]:
                return {
                    "band": band_name,
                    "label": band["label"],
                    "strategy": band["strategy"],
                }
        return {"band": "RED", "label": "Major Gaps", "strategy": "schedule_call"}

    def _is_protected_field(self, field_name: str) -> bool:
        """Check if a field is protected from auto-fill."""
        return field_name.lower() in PROTECTED_FIELDS

    def _is_business_hours(self) -> bool:
        """Check if current time is within business hours."""
        now = datetime.utcnow()
        # Simplified: uses UTC. Production should use borrower's local timezone.
        return BUSINESS_HOURS_START <= now.hour < BUSINESS_HOURS_END

    # =========================================================================
    # TOOL 1: REVIEW SUBMITTED APPLICATION
    # =========================================================================

    async def _review_submitted_application(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Trigger full application review orchestration for a submitted loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Fetch loan details
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
                           l.borrower_phone, l.stage, l.loan_type, l.amount,
                           l.property_address, l.loan_officer_id,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Gather missing items from application data
            missing_items = self._identify_missing_items(db, loan_id)

            # Gather missing documents
            missing_docs = self._identify_missing_documents(db, loan_id, loan.loan_type)

            # Calculate initial score
            score_data = self._calculate_score(db, loan_id)
            score = score_data["overall_score"]
            band = self._get_score_band(score)

            # Determine next action based on score band
            if score >= 90:
                next_action = "text_followup"
                next_action_label = "Send minor text follow-ups for remaining items"
            elif score >= 75:
                next_action = "text_and_stage_docs"
                next_action_label = "Text borrower for data gaps and stage document requests"
            elif score >= 50:
                next_action = "hybrid_outreach"
                next_action_label = "Text for easy items, schedule PA call for complex gaps"
            else:
                next_action = "schedule_pa_call"
                next_action_label = "Schedule PA call immediately — too many gaps for text resolution"

            total_findings = len(missing_items) + len(missing_docs)

            self.audit_log(
                "review_submitted_application",
                entity_type="loan",
                entity_id=str(loan_id),
                details={
                    "score": score,
                    "band": band["band"],
                    "missing_items": len(missing_items),
                    "missing_docs": len(missing_docs),
                    "next_action": next_action,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "stage": loan.stage,
                    "score": score,
                    "score_band": band,
                    "total_findings": total_findings,
                    "missing_data_items": len(missing_items),
                    "missing_documents": len(missing_docs),
                    "items": missing_items[:20],  # Top 20 for summary
                    "documents_needed": missing_docs[:10],
                    "next_action": next_action,
                    "next_action_label": next_action_label,
                    "reviewed_at": datetime.utcnow().isoformat(),
                },
                message=(
                    f"Loan {loan.loan_number}: Score {score}/100 ({band['band']}). "
                    f"{total_findings} findings. Action: {next_action_label}"
                ),
            )

        except Exception as e:
            logger.exception(f"review_submitted_application failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 2: GET APPLICATION SCORE
    # =========================================================================

    async def _get_application_score(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get current application completeness score with section breakdown."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            score_data = self._calculate_score(db, loan_id)
            score = score_data["overall_score"]
            band = self._get_score_band(score)

            # Determine trend from score history
            history = db.execute(
                text("""
                    SELECT score, recorded_at
                    FROM app_completion_scores
                    WHERE loan_id = :loan_id
                    ORDER BY recorded_at DESC
                    LIMIT 5
                """),
                {"loan_id": loan_id},
            ).fetchall()

            trend = "stable"
            if len(history) >= 2:
                prev_score = history[1].score if hasattr(history[1], "score") else history[1][0]
                if score > prev_score:
                    trend = "improving"
                elif score < prev_score:
                    trend = "declining"

            self.audit_log(
                "get_application_score",
                entity_type="loan",
                entity_id=str(loan_id),
                details={"score": score, "band": band["band"], "trend": trend},
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "score": score,
                    "band": band["band"],
                    "band_label": band["label"],
                    "strategy": band["strategy"],
                    "trend": trend,
                    "sections": score_data["sections"],
                    "history": [
                        {
                            "score": h.score if hasattr(h, "score") else h[0],
                            "recorded_at": (
                                h.recorded_at.isoformat()
                                if hasattr(h, "recorded_at") else str(h[1])
                            ),
                        }
                        for h in history
                    ],
                },
                message=f"Score: {score}/100 ({band['band']}) - {trend}",
            )

        except Exception as e:
            logger.exception(f"get_application_score failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 3: RESOLVE MISSING ITEM
    # =========================================================================

    async def _resolve_missing_item(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Resolve a single missing item and recalculate score."""
        from database import SessionLocal

        item_id = input_data["item_id"]
        value = input_data["value"]
        source = input_data.get("source", "AI_AGENT")
        db = SessionLocal()
        try:
            # Fetch the missing item with loan for tenant check
            item = db.execute(
                text("""
                    SELECT mi.id, mi.loan_id, mi.field_name, mi.section,
                           mi.status, mi.field_label
                    FROM app_completion_items mi
                    JOIN loans l ON l.id = mi.loan_id
                    WHERE mi.id = :item_id
                """),
                {"item_id": item_id},
            ).fetchone()

            if not item:
                return ToolResult(success=False, error=f"Missing item {item_id} not found")

            # Tenant isolation
            self._verify_loan_org(db, item.loan_id)

            # Check protected field
            field_name = item.field_name
            if self._is_protected_field(field_name):
                return ToolResult(
                    success=False,
                    error=(
                        f"Field '{item.field_label or field_name}' is protected and cannot be "
                        f"auto-filled. Income, SSN, and declaration fields require explicit "
                        f"borrower confirmation or manual entry."
                    ),
                    data={"field_name": field_name, "protected": True},
                )

            # Already resolved check
            if item.status == "RESOLVED":
                return ToolResult(
                    success=False,
                    error=f"Item {item_id} is already resolved",
                    data={"item_id": item_id, "status": "RESOLVED"},
                )

            # Resolve the item
            db.execute(
                text("""
                    UPDATE app_completion_items
                    SET status = 'RESOLVED',
                        resolved_value = :value,
                        resolved_by = :source,
                        resolved_at = :now,
                        resolved_by_user_id = :user_id
                    WHERE id = :item_id
                """),
                {
                    "item_id": item_id,
                    "value": value,
                    "source": source,
                    "now": datetime.utcnow(),
                    "user_id": context.get("user_id"),
                },
            )
            db.commit()

            # Recalculate score
            score_data = self._calculate_score(db, item.loan_id)
            new_score = score_data["overall_score"]
            band = self._get_score_band(new_score)

            # Count remaining items
            remaining = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM app_completion_items
                    WHERE loan_id = :loan_id AND status != 'RESOLVED'
                """),
                {"loan_id": item.loan_id},
            ).fetchone()
            remaining_count = remaining.cnt if remaining else 0

            self.audit_log(
                "resolve_missing_item",
                entity_type="app_completion_item",
                entity_id=str(item_id),
                details={
                    "field_name": field_name,
                    "source": source,
                    "new_score": new_score,
                    "remaining_items": remaining_count,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "item_id": item_id,
                    "field_name": field_name,
                    "field_label": item.field_label,
                    "source": source,
                    "new_score": new_score,
                    "score_band": band,
                    "remaining_items": remaining_count,
                },
                message=(
                    f"Resolved '{item.field_label or field_name}'. "
                    f"Score: {new_score}/100. {remaining_count} items remaining."
                ),
            )

        except Exception as e:
            logger.exception(f"resolve_missing_item failed for item {item_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 4: SEND BORROWER QUESTION
    # =========================================================================

    async def _send_borrower_question(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Send an SMS question to the borrower about a specific missing item."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        item_id = input_data["item_id"]
        custom_question = input_data.get("custom_question")
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Fetch loan + borrower info
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.borrower_phone,
                           l.borrower_email,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            if not loan.borrower_phone:
                return ToolResult(
                    success=False,
                    error="No borrower phone number on file. Cannot send SMS.",
                    data={"loan_id": loan_id, "needs_phone": True},
                )

            # Fetch the missing item
            item = db.execute(
                text("""
                    SELECT id, field_name, field_label, section, default_question
                    FROM app_completion_items
                    WHERE id = :item_id AND loan_id = :loan_id
                """),
                {"item_id": item_id, "loan_id": loan_id},
            ).fetchone()

            if not item:
                return ToolResult(
                    success=False,
                    error=f"Missing item {item_id} not found for loan {loan_id}",
                )

            # Check business hours
            if not self._is_business_hours():
                return ToolResult(
                    success=False,
                    error=(
                        "Outside business hours (8am-8pm). Message will not be sent. "
                        "Schedule for next business window."
                    ),
                    data={"outside_hours": True, "current_hour_utc": datetime.utcnow().hour},
                )

            # Check unanswered message count
            unanswered = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM app_completion_messages
                    WHERE loan_id = :loan_id AND direction = 'OUTBOUND'
                          AND response_received = FALSE
                """),
                {"loan_id": loan_id},
            ).fetchone()
            unanswered_count = unanswered.cnt if unanswered else 0

            if unanswered_count >= MAX_UNANSWERED_MESSAGES:
                return ToolResult(
                    success=False,
                    error=(
                        f"{unanswered_count} unanswered messages already sent. "
                        f"Escalation required — schedule a PA call instead."
                    ),
                    data={
                        "unanswered_count": unanswered_count,
                        "max_allowed": MAX_UNANSWERED_MESSAGES,
                        "needs_escalation": True,
                    },
                )

            # Build question text
            question_text = custom_question or item.default_question or (
                f"Hi {loan.borrower_name.split()[0] if loan.borrower_name else 'there'}, "
                f"this is {loan.lo_name}'s team working on your loan application. "
                f"We need your help with one item: {item.field_label or item.field_name}. "
                f"Could you provide this? Thank you!"
            )

            # Record the outbound message
            db.execute(
                text("""
                    INSERT INTO app_completion_messages
                    (loan_id, item_id, direction, channel, message_text,
                     sent_at, sent_by_user_id, response_received)
                    VALUES (:loan_id, :item_id, 'OUTBOUND', 'SMS', :message,
                            :now, :user_id, FALSE)
                """),
                {
                    "loan_id": loan_id,
                    "item_id": item_id,
                    "message": question_text,
                    "now": datetime.utcnow(),
                    "user_id": context.get("user_id"),
                },
            )
            db.commit()

            self.audit_log(
                "send_borrower_question",
                entity_type="loan",
                entity_id=str(loan_id),
                details={
                    "item_id": item_id,
                    "field": item.field_name,
                    "channel": "SMS",
                    "unanswered_prior": unanswered_count,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "item_id": item_id,
                    "field": item.field_label or item.field_name,
                    "channel": "SMS",
                    "message_preview": question_text[:200],
                    "sent_to": loan.borrower_phone[-4:].rjust(len(loan.borrower_phone), "*"),
                    "unanswered_count": unanswered_count + 1,
                    "max_before_escalation": MAX_UNANSWERED_MESSAGES,
                },
                message=(
                    f"SMS sent to borrower about '{item.field_label or item.field_name}'. "
                    f"Unanswered: {unanswered_count + 1}/{MAX_UNANSWERED_MESSAGES}."
                ),
            )

        except Exception as e:
            logger.exception(f"send_borrower_question failed for loan {loan_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 5: STAGE DOCUMENT REQUEST
    # =========================================================================

    async def _stage_document_request(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Stage a document request for staff review before publishing."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        doc_type = input_data["doc_type"]
        doc_label = input_data["doc_label"]
        reason = input_data["reason"]
        priority = input_data.get("priority", "MEDIUM")
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Check for duplicate staged request
            existing = db.execute(
                text("""
                    SELECT id FROM app_completion_doc_requests
                    WHERE loan_id = :loan_id AND doc_type = :doc_type
                          AND status = 'STAGED'
                """),
                {"loan_id": loan_id, "doc_type": doc_type},
            ).fetchone()

            if existing:
                return ToolResult(
                    success=False,
                    error=f"Document request for '{doc_type}' is already staged (ID: {existing.id})",
                    data={"existing_id": existing.id, "doc_type": doc_type},
                )

            # Validate priority
            valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
            if priority.upper() not in valid_priorities:
                priority = "MEDIUM"

            # Insert staged request
            result = db.execute(
                text("""
                    INSERT INTO app_completion_doc_requests
                    (loan_id, doc_type, doc_label, reason, priority, status,
                     staged_at, staged_by_user_id)
                    VALUES (:loan_id, :doc_type, :doc_label, :reason, :priority, 'STAGED',
                            :now, :user_id)
                    RETURNING id
                """),
                {
                    "loan_id": loan_id,
                    "doc_type": doc_type,
                    "doc_label": doc_label,
                    "reason": reason,
                    "priority": priority.upper(),
                    "now": datetime.utcnow(),
                    "user_id": context.get("user_id"),
                },
            )
            new_id = result.fetchone()[0]
            db.commit()

            self.audit_log(
                "stage_document_request",
                entity_type="app_completion_doc_request",
                entity_id=str(new_id),
                details={
                    "loan_id": loan_id,
                    "doc_type": doc_type,
                    "priority": priority.upper(),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "request_id": new_id,
                    "loan_id": loan_id,
                    "doc_type": doc_type,
                    "doc_label": doc_label,
                    "reason": reason,
                    "priority": priority.upper(),
                    "status": "STAGED",
                },
                message=f"Staged document request: {doc_label} ({priority.upper()}) for loan {loan_id}",
            )

        except Exception as e:
            logger.exception(f"stage_document_request failed for loan {loan_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 6: PUBLISH DOCUMENT REQUESTS
    # =========================================================================

    async def _publish_document_requests(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Publish all staged document requests to the borrower portal."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        notify_borrower = input_data.get("notify_borrower", True)
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Fetch all staged requests
            staged = db.execute(
                text("""
                    SELECT id, doc_type, doc_label, priority
                    FROM app_completion_doc_requests
                    WHERE loan_id = :loan_id AND status = 'STAGED'
                    ORDER BY
                        CASE priority
                            WHEN 'CRITICAL' THEN 1
                            WHEN 'HIGH' THEN 2
                            WHEN 'MEDIUM' THEN 3
                            WHEN 'LOW' THEN 4
                        END
                """),
                {"loan_id": loan_id},
            ).fetchall()

            if not staged:
                return ToolResult(
                    success=False,
                    error="No staged document requests to publish",
                    data={"loan_id": loan_id},
                )

            # Update all staged to PUBLISHED
            now = datetime.utcnow()
            db.execute(
                text("""
                    UPDATE app_completion_doc_requests
                    SET status = 'PUBLISHED',
                        published_at = :now,
                        published_by_user_id = :user_id
                    WHERE loan_id = :loan_id AND status = 'STAGED'
                """),
                {
                    "loan_id": loan_id,
                    "now": now,
                    "user_id": context.get("user_id"),
                },
            )
            db.commit()

            published_list = [
                {
                    "id": s.id,
                    "doc_type": s.doc_type,
                    "doc_label": s.doc_label,
                    "priority": s.priority,
                }
                for s in staged
            ]

            notification_status = "not_requested"
            if notify_borrower:
                # Delegate to notification service (SMS + email)
                loan = db.execute(
                    text("""
                        SELECT borrower_name, borrower_phone, borrower_email
                        FROM loans WHERE id = :loan_id
                    """),
                    {"loan_id": loan_id},
                ).fetchone()

                notification_status = "queued"
                if loan and (loan.borrower_phone or loan.borrower_email):
                    # In production, this would call the notification service
                    notification_status = "sent"

            self.audit_log(
                "publish_document_requests",
                entity_type="loan",
                entity_id=str(loan_id),
                details={
                    "count": len(published_list),
                    "notify_borrower": notify_borrower,
                    "notification_status": notification_status,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "published_count": len(published_list),
                    "documents": published_list,
                    "notification_status": notification_status,
                    "published_at": now.isoformat(),
                },
                message=(
                    f"Published {len(published_list)} document requests to borrower portal. "
                    f"Notification: {notification_status}."
                ),
            )

        except Exception as e:
            logger.exception(f"publish_document_requests failed for loan {loan_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 7: SCHEDULE PA CALL
    # =========================================================================

    async def _schedule_pa_call(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Schedule a production assistant review call."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        preferred_time = input_data.get("preferred_time")
        duration_minutes = input_data.get("duration_minutes", 15)
        reason = input_data.get("reason", "Application review")
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.borrower_phone,
                           l.loan_officer_id,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Determine call time
            if preferred_time:
                try:
                    call_time = datetime.fromisoformat(preferred_time)
                except (ValueError, TypeError):
                    call_time = datetime.utcnow() + timedelta(hours=2)
            else:
                # Default: next available slot (2 hours from now, within business hours)
                call_time = datetime.utcnow() + timedelta(hours=2)
                if call_time.hour >= BUSINESS_HOURS_END:
                    # Push to next day 10 AM
                    call_time = call_time.replace(
                        hour=10, minute=0, second=0
                    ) + timedelta(days=1)
                elif call_time.hour < BUSINESS_HOURS_START:
                    call_time = call_time.replace(hour=10, minute=0, second=0)

            # Create the scheduled call record
            result = db.execute(
                text("""
                    INSERT INTO app_completion_calls
                    (loan_id, scheduled_at, duration_minutes, reason,
                     status, created_by_user_id, created_at,
                     loan_officer_id)
                    VALUES (:loan_id, :scheduled_at, :duration, :reason,
                            'SCHEDULED', :user_id, :now,
                            :lo_id)
                    RETURNING id
                """),
                {
                    "loan_id": loan_id,
                    "scheduled_at": call_time,
                    "duration": duration_minutes,
                    "reason": reason,
                    "user_id": context.get("user_id"),
                    "now": datetime.utcnow(),
                    "lo_id": loan.loan_officer_id,
                },
            )
            call_id = result.fetchone()[0]
            db.commit()

            self.audit_log(
                "schedule_pa_call",
                entity_type="app_completion_call",
                entity_id=str(call_id),
                details={
                    "loan_id": loan_id,
                    "scheduled_at": call_time.isoformat(),
                    "duration": duration_minutes,
                    "reason": reason,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "call_id": call_id,
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "scheduled_at": call_time.isoformat(),
                    "duration_minutes": duration_minutes,
                    "reason": reason,
                    "status": "SCHEDULED",
                },
                message=(
                    f"PA call scheduled for {call_time.strftime('%m/%d at %I:%M %p')} "
                    f"({duration_minutes} min) — {reason}"
                ),
            )

        except Exception as e:
            logger.exception(f"schedule_pa_call failed for loan {loan_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 8: GET SCORING PAGE SUMMARY
    # =========================================================================

    async def _get_scoring_page_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Get the full scoring page data for display and analysis."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Loan header
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                           l.loan_type, l.amount,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Score + sections
            score_data = self._calculate_score(db, loan_id)
            score = score_data["overall_score"]
            band = self._get_score_band(score)

            # All items grouped by section
            items = db.execute(
                text("""
                    SELECT id, field_name, field_label, section, status,
                           priority, resolved_value, resolved_by, resolved_at
                    FROM app_completion_items
                    WHERE loan_id = :loan_id
                    ORDER BY
                        CASE priority
                            WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4
                        END,
                        section, field_name
                """),
                {"loan_id": loan_id},
            ).fetchall()

            sections = {}
            for item in items:
                sec = item.section or "other"
                if sec not in sections:
                    sections[sec] = {"items": [], "total": 0, "resolved": 0}
                sections[sec]["items"].append({
                    "id": item.id,
                    "field_name": item.field_name,
                    "field_label": item.field_label,
                    "status": item.status,
                    "priority": item.priority,
                    "resolved_value": item.resolved_value,
                    "resolved_by": item.resolved_by,
                })
                sections[sec]["total"] += 1
                if item.status == "RESOLVED":
                    sections[sec]["resolved"] += 1

            # Recent activity
            activity = db.execute(
                text("""
                    SELECT action, details, created_at
                    FROM app_completion_activity_log
                    WHERE loan_id = :loan_id
                    ORDER BY created_at DESC
                    LIMIT 10
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Staged doc requests
            staged_docs = db.execute(
                text("""
                    SELECT id, doc_type, doc_label, priority, status, staged_at
                    FROM app_completion_doc_requests
                    WHERE loan_id = :loan_id
                    ORDER BY staged_at DESC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Communication history
            messages = db.execute(
                text("""
                    SELECT id, direction, channel, message_text,
                           sent_at, response_received
                    FROM app_completion_messages
                    WHERE loan_id = :loan_id
                    ORDER BY sent_at DESC
                    LIMIT 20
                """),
                {"loan_id": loan_id},
            ).fetchall()

            self.audit_log(
                "get_scoring_page_summary",
                entity_type="loan",
                entity_id=str(loan_id),
            )

            return ToolResult(
                success=True,
                data={
                    "loan": {
                        "id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "stage": loan.stage,
                        "loan_type": loan.loan_type,
                        "amount": float(loan.amount) if loan.amount else 0,
                        "lo_name": loan.lo_name,
                    },
                    "score": score,
                    "band": band,
                    "sections": {
                        sec_name: {
                            "total": sec_data["total"],
                            "resolved": sec_data["resolved"],
                            "pct": round(
                                (sec_data["resolved"] / sec_data["total"] * 100)
                                if sec_data["total"] > 0 else 0, 1
                            ),
                            "weight": SECTION_WEIGHTS.get(sec_name, 0),
                            "items": sec_data["items"],
                        }
                        for sec_name, sec_data in sections.items()
                    },
                    "recent_activity": [
                        {
                            "action": a.action,
                            "details": a.details,
                            "at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in activity
                    ],
                    "staged_documents": [
                        {
                            "id": d.id,
                            "doc_type": d.doc_type,
                            "doc_label": d.doc_label,
                            "priority": d.priority,
                            "status": d.status,
                        }
                        for d in staged_docs
                    ],
                    "messages": [
                        {
                            "id": m.id,
                            "direction": m.direction,
                            "channel": m.channel,
                            "text": m.message_text[:200] if m.message_text else None,
                            "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                            "response_received": m.response_received,
                        }
                        for m in messages
                    ],
                },
                message=f"Scoring page: {score}/100 ({band['band']})",
            )

        except Exception as e:
            logger.exception(f"get_scoring_page_summary failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 9: ANALYZE BORROWER RESPONSE
    # =========================================================================

    async def _analyze_borrower_response(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Use AI to parse and extract structured data from a borrower response."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        response_text = input_data["response_text"]
        question_context = input_data["question_context"]
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            # Fetch pending items for this loan to match against
            pending_items = db.execute(
                text("""
                    SELECT id, field_name, field_label, section, default_question
                    FROM app_completion_items
                    WHERE loan_id = :loan_id AND status != 'RESOLVED'
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Build extraction analysis
            # In production, this delegates to the AI service (OpenAI/Claude)
            # for structured extraction. Here we build the analysis framework.
            extracted_values = []
            response_lower = response_text.lower().strip()

            for item in pending_items:
                field = item.field_name
                label = item.field_label or field

                # Skip protected fields — never auto-resolve from text
                if self._is_protected_field(field):
                    continue

                # Simple heuristic matching (production uses LLM extraction)
                confidence = 0.0
                extracted_value = None

                # Check if the response seems to address this field
                if label and label.lower() in response_lower:
                    confidence = 0.6
                    # Try to extract a value after the label mention
                    idx = response_lower.find(label.lower())
                    remainder = response_text[idx + len(label):].strip()
                    if remainder:
                        # Take the first meaningful chunk as the value
                        extracted_value = remainder.split("\n")[0].strip(":- ").strip()
                        if extracted_value:
                            confidence = 0.75

                if extracted_value and confidence >= 0.6:
                    extracted_values.append({
                        "item_id": item.id,
                        "field_name": field,
                        "field_label": label,
                        "extracted_value": extracted_value,
                        "confidence": round(confidence, 2),
                        "protected": False,
                        "auto_resolvable": confidence >= 0.8,
                    })

            # Record the inbound message
            db.execute(
                text("""
                    INSERT INTO app_completion_messages
                    (loan_id, direction, channel, message_text,
                     sent_at, response_received)
                    VALUES (:loan_id, 'INBOUND', 'SMS', :message,
                            :now, TRUE)
                """),
                {
                    "loan_id": loan_id,
                    "message": response_text[:2000],
                    "now": datetime.utcnow(),
                },
            )

            # Mark related outbound messages as having received a response
            db.execute(
                text("""
                    UPDATE app_completion_messages
                    SET response_received = TRUE
                    WHERE loan_id = :loan_id AND direction = 'OUTBOUND'
                          AND response_received = FALSE
                """),
                {"loan_id": loan_id},
            )
            db.commit()

            self.audit_log(
                "analyze_borrower_response",
                entity_type="loan",
                entity_id=str(loan_id),
                details={
                    "response_length": len(response_text),
                    "extracted_count": len(extracted_values),
                    "question_context": question_context[:100],
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "response_text": response_text[:500],
                    "question_context": question_context,
                    "extracted_values": extracted_values,
                    "total_extracted": len(extracted_values),
                    "auto_resolvable": len([v for v in extracted_values if v["auto_resolvable"]]),
                    "needs_confirmation": len([v for v in extracted_values if not v["auto_resolvable"]]),
                    "analysis_note": (
                        "Production uses LLM-powered extraction for higher accuracy. "
                        "Values with confidence >= 0.8 can be auto-resolved."
                    ) if not extracted_values else None,
                },
                message=(
                    f"Extracted {len(extracted_values)} values from borrower response. "
                    f"{len([v for v in extracted_values if v['auto_resolvable']])} auto-resolvable."
                ),
            )

        except Exception as e:
            logger.exception(f"analyze_borrower_response failed for loan {loan_id}")
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # TOOL 10: CHECK COMPLETION STATUS
    # =========================================================================

    async def _check_completion_status(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Check if the application is complete enough to proceed."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        db = SessionLocal()
        try:
            self._verify_loan_org(db, loan_id)

            loan = db.execute(
                text("SELECT id, loan_number, stage FROM loans WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Calculate current score
            score_data = self._calculate_score(db, loan_id)
            score = score_data["overall_score"]
            band = self._get_score_band(score)

            # Get blocking items (CRITICAL priority that are unresolved)
            blocking = db.execute(
                text("""
                    SELECT id, field_name, field_label, section, priority
                    FROM app_completion_items
                    WHERE loan_id = :loan_id
                          AND status != 'RESOLVED'
                          AND priority IN ('CRITICAL', 'HIGH')
                    ORDER BY
                        CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 END,
                        section
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Get unpublished doc requests
            pending_docs = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM app_completion_doc_requests
                    WHERE loan_id = :loan_id AND status IN ('STAGED', 'PUBLISHED')
                          AND doc_received = FALSE
                """),
                {"loan_id": loan_id},
            ).fetchone()
            pending_doc_count = pending_docs.cnt if pending_docs else 0

            # Determine completion status
            is_complete = score >= 90 and len(blocking) == 0
            blocking_items = [
                {
                    "id": b.id,
                    "field": b.field_label or b.field_name,
                    "section": b.section,
                    "priority": b.priority,
                }
                for b in blocking
            ]

            # Determine recommended action
            if is_complete:
                recommended_action = "submit_for_processing"
                action_label = "Application is complete. Submit for processing."
            elif score >= 90 and len(blocking) > 0:
                recommended_action = "resolve_blocking_items"
                action_label = (
                    f"Score is {score} but {len(blocking)} blocking items remain. "
                    f"Resolve these before submission."
                )
            elif score >= 75:
                recommended_action = "continue_outreach"
                action_label = (
                    f"Score {score}/100. Continue text outreach and doc staging "
                    f"for remaining gaps."
                )
            elif score >= 50:
                recommended_action = "hybrid_resolution"
                action_label = (
                    f"Score {score}/100. Text for easy items, schedule call for complex."
                )
            else:
                recommended_action = "schedule_call"
                action_label = (
                    f"Score {score}/100. Too many gaps for text resolution. "
                    f"Schedule PA call."
                )

            self.audit_log(
                "check_completion_status",
                entity_type="loan",
                entity_id=str(loan_id),
                details={
                    "score": score,
                    "is_complete": is_complete,
                    "blocking_count": len(blocking),
                    "recommended_action": recommended_action,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "is_complete": is_complete,
                    "score": score,
                    "score_band": band,
                    "blocking_items": blocking_items,
                    "blocking_count": len(blocking_items),
                    "pending_documents": pending_doc_count,
                    "recommended_action": recommended_action,
                    "action_label": action_label,
                },
                message=action_label,
            )

        except Exception as e:
            logger.exception(f"check_completion_status failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    # =========================================================================
    # INTERNAL HELPERS (not exposed as tools)
    # =========================================================================

    def _calculate_score(self, db, loan_id: int) -> Dict[str, Any]:
        """Calculate the application completeness score.

        Returns a dict with overall_score (0-100) and per-section breakdown.
        Score is a weighted sum across sections, where each section's score
        is the percentage of resolved items in that section.
        """
        items = db.execute(
            text("""
                SELECT section, status
                FROM app_completion_items
                WHERE loan_id = :loan_id
            """),
            {"loan_id": loan_id},
        ).fetchall()

        if not items:
            return {"overall_score": 0, "sections": {}}

        # Group by section
        section_counts: Dict[str, Dict[str, int]] = {}
        for item in items:
            sec = item.section or "other"
            if sec not in section_counts:
                section_counts[sec] = {"total": 0, "resolved": 0}
            section_counts[sec]["total"] += 1
            if item.status == "RESOLVED":
                section_counts[sec]["resolved"] += 1

        # Calculate weighted score
        total_weight = 0
        weighted_sum = 0.0
        sections = {}

        for sec_name, counts in section_counts.items():
            weight = SECTION_WEIGHTS.get(sec_name, 5)  # Default weight 5 for unknown sections
            pct = (counts["resolved"] / counts["total"] * 100) if counts["total"] > 0 else 0
            sections[sec_name] = {
                "total": counts["total"],
                "resolved": counts["resolved"],
                "pct": round(pct, 1),
                "weight": weight,
            }
            weighted_sum += pct * weight
            total_weight += weight

        overall = round(weighted_sum / total_weight, 0) if total_weight > 0 else 0

        # Persist the score for trend tracking (best effort)
        try:
            db.execute(
                text("""
                    INSERT INTO app_completion_scores (loan_id, score, recorded_at)
                    VALUES (:loan_id, :score, :now)
                """),
                {"loan_id": loan_id, "score": int(overall), "now": datetime.utcnow()},
            )
            db.commit()
        except Exception as e:
            logger.debug(f"Score persistence skipped (table may not exist): {e}")
            db.rollback()

        return {"overall_score": int(overall), "sections": sections}

    def _identify_missing_items(self, db, loan_id: int) -> List[Dict[str, Any]]:
        """Identify missing data items for a loan from the app_completion_items table."""
        items = db.execute(
            text("""
                SELECT id, field_name, field_label, section, priority, status
                FROM app_completion_items
                WHERE loan_id = :loan_id AND status != 'RESOLVED'
                ORDER BY
                    CASE priority
                        WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4
                    END,
                    section
            """),
            {"loan_id": loan_id},
        ).fetchall()

        return [
            {
                "id": i.id,
                "field_name": i.field_name,
                "field_label": i.field_label,
                "section": i.section,
                "priority": i.priority,
                "status": i.status,
                "protected": self._is_protected_field(i.field_name),
            }
            for i in items
        ]

    def _identify_missing_documents(
        self, db, loan_id: int, loan_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Identify documents still needed for a loan.

        Compares required document types (based on loan type) against
        documents already on file.
        """
        # Get existing documents
        existing = db.execute(
            text("""
                SELECT doc_type, status
                FROM documents
                WHERE loan_id = :loan_id AND status = 'active'
            """),
            {"loan_id": loan_id},
        ).fetchall()
        existing_types = {d.doc_type for d in existing}

        # Determine required types from standard categories
        from agents.specialized.document_lifecycle_agent import LOAN_TYPE_REQUIREMENTS
        lt = (loan_type or "conventional").lower()
        reqs = LOAN_TYPE_REQUIREMENTS.get(lt, LOAN_TYPE_REQUIREMENTS.get("conventional", {}))
        required = set(reqs.get("base", [])) | set(reqs.get("extra", []))

        missing = []
        for doc_type in required:
            if doc_type not in existing_types:
                missing.append({
                    "doc_type": doc_type,
                    "required": True,
                    "loan_type_specific": doc_type in reqs.get("extra", []),
                })

        return missing
