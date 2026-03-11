"""
Document Follow-Up Agent

AI agent specialized in managing document follow-up campaigns for mortgage
lending. Orchestrates multi-channel outreach (email, SMS, call, portal) to
collect outstanding documents from borrowers, with intelligent timing,
channel selection, urgency assessment, and escalation logic.

Integrates with the FollowupAutomationService for campaign management and
the Smart Docs service layer for document status tracking.

15 Tools:
1.  assess_followup_urgency - Determine urgency based on loan stage, closing date, missing docs
2.  select_followup_channel - Choose best channel based on borrower preferences and history
3.  draft_followup_message - Generate personalized follow-up message for missing documents
4.  schedule_followup_sequence - Plan multi-step follow-up campaign timing
5.  evaluate_borrower_responsiveness - Analyze past response patterns to optimize timing
6.  escalate_to_loan_officer - Determine when to escalate to LO for personal outreach
7.  schedule_document_appointment - Book appointment for complex document issues
8.  generate_reminder_summary - Create summary of all outstanding document needs for a loan
9.  optimize_contact_timing - Determine best day/time to contact based on response history
10. track_campaign_effectiveness - Measure follow-up campaign success rates
11. pause_followup_on_receipt - Auto-pause campaign when requested document is received
12. suggest_alternative_documents - Suggest alternative acceptable documents
13. create_borrower_portal_notification - Generate portal notification for the borrower
14. batch_process_overdue_followups - Process all overdue follow-ups across pipeline
15. generate_followup_report - Create follow-up status report for the LO
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta, timezone
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
# ALTERNATIVE DOCUMENT MAPPINGS
# ============================================================================

_ALTERNATIVE_DOCUMENTS = {
    "paystubs": [
        "Direct deposit statement from bank",
        "Employer-issued pay summary letter",
        "ADP or payroll service printout",
    ],
    "w2": [
        "Wage and Tax Statement from employer",
        "IRS Form 4506-C transcript",
        "Year-end paystub showing total earnings",
    ],
    "tax_returns": [
        "IRS Tax Return Transcript (Form 4506-C)",
        "Accountant-prepared tax return copy",
    ],
    "bank_statements": [
        "Credit union statements",
        "Online bank PDF export with institution letterhead",
        "Letter from bank verifying account and balances",
    ],
    "gift_letter": [
        "Gift donor bank statement showing withdrawal",
        "Wire transfer confirmation with donor info",
    ],
    "purchase_contract": [
        "Fully executed sales agreement",
        "Builder contract with addenda",
    ],
    "appraisal": [
        "Desktop appraisal (if eligible per program)",
        "Appraisal waiver documentation (if eligible)",
    ],
    "drivers_license": [
        "State-issued ID card",
        "US Passport",
        "Military ID",
    ],
    "insurance": [
        "Homeowner's insurance binder",
        "Insurance declaration page",
        "Agent-issued evidence of insurance letter",
    ],
    "1099": [
        "Year-end broker statement",
        "IRS income transcript",
    ],
    "profit_loss": [
        "Accountant-prepared P&L statement",
        "QuickBooks / accounting software export (signed)",
    ],
    "hoa": [
        "HOA questionnaire completed by management company",
        "HOA budget and meeting minutes",
    ],
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class AssessFollowupUrgencyInput(BaseModel):
    """Input schema for assess_followup_urgency tool"""
    loan_id: int = Field(..., description="Loan ID to assess follow-up urgency for")


class SelectFollowupChannelInput(BaseModel):
    """Input schema for select_followup_channel tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")


class DraftFollowupMessageInput(BaseModel):
    """Input schema for draft_followup_message tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")
    channel: str = Field(
        "email",
        description="Channel for the message: email, sms, or call_script",
    )
    urgency: str = Field(
        "normal",
        description="Urgency level: low, normal, high, critical",
    )


class ScheduleFollowupSequenceInput(BaseModel):
    """Input schema for schedule_followup_sequence tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")
    campaign_type: str = Field(
        "initial_request",
        description="Campaign type: initial_request, gentle_reminder, urgent_reminder, "
                    "document_rejected, document_expired",
    )
    request_ids: str = Field(
        ..., description="Comma-separated document request IDs to follow up on",
    )


class EvaluateBorrowerResponsivenessInput(BaseModel):
    """Input schema for evaluate_borrower_responsiveness tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")


class EscalateToLoanOfficerInput(BaseModel):
    """Input schema for escalate_to_loan_officer tool"""
    loan_id: int = Field(..., description="Loan ID")
    campaign_id: int = Field(..., description="Campaign ID to escalate")
    reason: str = Field(
        "",
        description="Optional reason for escalation (auto-determined if empty)",
    )


class ScheduleDocumentAppointmentInput(BaseModel):
    """Input schema for schedule_document_appointment tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")
    appointment_type: str = Field(
        "document_collection",
        description="Appointment type: document_collection, tax_return_review, "
                    "general_consultation",
    )
    preferred_date: str = Field(
        "",
        description="Preferred date in YYYY-MM-DD format (defaults to next business day)",
    )
    duration_minutes: int = Field(
        30, description="Appointment duration in minutes",
    )


class GenerateReminderSummaryInput(BaseModel):
    """Input schema for generate_reminder_summary tool"""
    loan_id: int = Field(..., description="Loan ID to summarize outstanding documents for")


class OptimizeContactTimingInput(BaseModel):
    """Input schema for optimize_contact_timing tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")


class TrackCampaignEffectivenessInput(BaseModel):
    """Input schema for track_campaign_effectiveness tool"""
    days: int = Field(30, description="Lookback window in days (default 30)")


class PauseFollowupOnReceiptInput(BaseModel):
    """Input schema for pause_followup_on_receipt tool"""
    loan_id: int = Field(..., description="Loan ID")
    request_id: int = Field(
        ..., description="Document request ID that was fulfilled",
    )


class SuggestAlternativeDocumentsInput(BaseModel):
    """Input schema for suggest_alternative_documents tool"""
    doc_type: str = Field(
        ..., description="Document type to suggest alternatives for "
                         "(e.g. paystubs, w2, bank_statements, tax_returns)",
    )
    loan_id: int = Field(
        0, description="Optional loan ID for loan-specific context",
    )


class CreateBorrowerPortalNotificationInput(BaseModel):
    """Input schema for create_borrower_portal_notification tool"""
    loan_id: int = Field(..., description="Loan ID")
    borrower_id: int = Field(..., description="Borrower (lead) ID")
    notification_type: str = Field(
        "document_reminder",
        description="Notification type: document_reminder, document_rejected, "
                    "document_expired, appointment_reminder",
    )
    message: str = Field(
        "",
        description="Custom message (auto-generated if empty)",
    )


class BatchProcessOverdueFollowupsInput(BaseModel):
    """Input schema for batch_process_overdue_followups tool"""
    max_campaigns: int = Field(
        50, description="Maximum number of overdue campaigns to process",
    )


class GenerateFollowupReportInput(BaseModel):
    """Input schema for generate_followup_report tool"""
    loan_id: int = Field(
        0, description="Specific loan ID, or 0 for org-wide report",
    )
    days: int = Field(30, description="Lookback window in days")


# ============================================================================
# DOCUMENT FOLLOW-UP AGENT
# ============================================================================

@AgentRegistry.register
class DocumentFollowUpAgent(SpecializedAgent):
    """
    Document Follow-Up AI Agent for mortgage document collection.

    I am the specialized agent for managing all aspects of document follow-up
    outreach. I coordinate multi-channel campaigns to collect outstanding
    documents from borrowers, with intelligent urgency assessment, channel
    selection, timing optimization, and escalation logic.

    1. ASSESS URGENCY: I analyze the loan stage, closing date proximity,
       SLA deadlines, and number of missing documents to determine how
       urgently follow-up is needed.

    2. SELECT CHANNELS: Based on borrower communication preferences, past
       response patterns, and campaign history, I recommend the best channel
       (email, SMS, phone call, portal notification) for each outreach.

    3. DRAFT MESSAGES: I generate personalized follow-up messages tailored
       to the borrower, the specific documents needed, the urgency level,
       and the communication channel.

    4. SCHEDULE CAMPAIGNS: I create and manage multi-step follow-up sequences
       that automatically progress through channels and escalate when needed.

    5. EVALUATE RESPONSIVENESS: I analyze borrower response history to predict
       likelihood of response and optimize outreach strategy accordingly.

    6. ESCALATE INTELLIGENTLY: When automated follow-up is insufficient, I
       determine the right time to escalate to the loan officer with a full
       summary of all attempts made.

    7. BOOK APPOINTMENTS: For complex document situations (tax returns,
       self-employment docs), I schedule document collection appointments.

    8. TRACK EFFECTIVENESS: I measure campaign success rates, channel
       performance, and response times to continuously improve follow-up
       strategies.
    """

    @property
    def name(self) -> str:
        return "DocumentFollowUpAgent"

    @property
    def description(self) -> str:
        return (
            "AI-powered document follow-up agent for mortgage lending. "
            "Manages multi-channel outreach campaigns, urgency assessment, "
            "channel selection, timing optimization, borrower responsiveness "
            "analysis, LO escalation, appointment scheduling, and campaign "
            "effectiveness tracking for outstanding document collection."
        )

    def _register_tools(self):
        """Register all document follow-up tools"""

        # Tool 1: Assess Follow-Up Urgency
        self.register_tool(AgentTool(
            name="assess_followup_urgency",
            description="Determine follow-up urgency based on loan stage, closing date "
                       "proximity, SLA deadlines, and count of missing documents. Returns "
                       "urgency level (low/normal/high/critical) with recommended action.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_followup_urgency,
            input_schema=AssessFollowupUrgencyInput,
        ))

        # Tool 2: Select Follow-Up Channel
        self.register_tool(AgentTool(
            name="select_followup_channel",
            description="Choose the best outreach channel (email, SMS, call, portal) "
                       "based on borrower communication preferences, past response "
                       "patterns, and campaign history.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._select_followup_channel,
            input_schema=SelectFollowupChannelInput,
        ))

        # Tool 3: Draft Follow-Up Message
        self.register_tool(AgentTool(
            name="draft_followup_message",
            description="Generate a personalized follow-up message for missing documents "
                       "tailored to the borrower, documents needed, urgency level, and "
                       "communication channel.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._draft_followup_message,
            input_schema=DraftFollowupMessageInput,
        ))

        # Tool 4: Schedule Follow-Up Sequence
        self.register_tool(AgentTool(
            name="schedule_followup_sequence",
            description="Create a multi-step follow-up campaign with automated progression "
                       "through email, SMS, call, appointment, and escalation steps. "
                       "Uses the FollowupAutomationService for campaign management.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_followup_sequence,
            input_schema=ScheduleFollowupSequenceInput,
        ))

        # Tool 5: Evaluate Borrower Responsiveness
        self.register_tool(AgentTool(
            name="evaluate_borrower_responsiveness",
            description="Analyze a borrower's past response patterns across follow-up "
                       "campaigns. Returns responsiveness score, average response time, "
                       "preferred response channel, and prediction for future outreach.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._evaluate_borrower_responsiveness,
            input_schema=EvaluateBorrowerResponsivenessInput,
        ))

        # Tool 6: Escalate to Loan Officer
        self.register_tool(AgentTool(
            name="escalate_to_loan_officer",
            description="Escalate an unresponsive borrower situation to the loan officer. "
                       "Creates a high-priority task with full campaign history summary, "
                       "outstanding documents, and all follow-up attempts made.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._escalate_to_loan_officer,
            input_schema=EscalateToLoanOfficerInput,
        ))

        # Tool 7: Schedule Document Appointment
        self.register_tool(AgentTool(
            name="schedule_document_appointment",
            description="Book an appointment for complex document issues such as tax "
                       "return review, self-employment documentation, or general "
                       "document collection assistance.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_document_appointment,
            input_schema=ScheduleDocumentAppointmentInput,
        ))

        # Tool 8: Generate Reminder Summary
        self.register_tool(AgentTool(
            name="generate_reminder_summary",
            description="Create a comprehensive summary of all outstanding document "
                       "needs for a loan, including missing documents, active campaigns, "
                       "last contact dates, and recommended next actions.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._generate_reminder_summary,
            input_schema=GenerateReminderSummaryInput,
        ))

        # Tool 9: Optimize Contact Timing
        self.register_tool(AgentTool(
            name="optimize_contact_timing",
            description="Determine the best day and time to contact a borrower based "
                       "on their past response history and follow-up event patterns.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._optimize_contact_timing,
            input_schema=OptimizeContactTimingInput,
        ))

        # Tool 10: Track Campaign Effectiveness
        self.register_tool(AgentTool(
            name="track_campaign_effectiveness",
            description="Measure follow-up campaign success rates, channel performance, "
                       "response times, and document collection rates. Returns org-wide "
                       "effectiveness metrics.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._track_campaign_effectiveness,
            input_schema=TrackCampaignEffectivenessInput,
        ))

        # Tool 11: Pause Follow-Up on Receipt
        self.register_tool(AgentTool(
            name="pause_followup_on_receipt",
            description="Auto-pause or complete active follow-up campaigns when a "
                       "requested document is received. Checks if all linked documents "
                       "are fulfilled and completes the campaign if so.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._pause_followup_on_receipt,
            input_schema=PauseFollowupOnReceiptInput,
        ))

        # Tool 12: Suggest Alternative Documents
        self.register_tool(AgentTool(
            name="suggest_alternative_documents",
            description="Suggest alternative acceptable documents when the borrower "
                       "cannot provide the originally requested document. Returns "
                       "alternatives with acceptance notes.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._suggest_alternative_documents,
            input_schema=SuggestAlternativeDocumentsInput,
        ))

        # Tool 13: Create Borrower Portal Notification
        self.register_tool(AgentTool(
            name="create_borrower_portal_notification",
            description="Generate an in-portal notification for the borrower about "
                       "outstanding documents, rejected documents, or upcoming "
                       "appointments.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_borrower_portal_notification,
            input_schema=CreateBorrowerPortalNotificationInput,
        ))

        # Tool 14: Batch Process Overdue Follow-Ups
        self.register_tool(AgentTool(
            name="batch_process_overdue_followups",
            description="Process all overdue follow-up campaign steps across the "
                       "entire pipeline. Executes pending actions for campaigns that "
                       "are past their next_action_at time.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._batch_process_overdue_followups,
            input_schema=BatchProcessOverdueFollowupsInput,
        ))

        # Tool 15: Generate Follow-Up Report
        self.register_tool(AgentTool(
            name="generate_followup_report",
            description="Create a follow-up status report for the loan officer showing "
                       "campaign statuses, response rates, outstanding items, and "
                       "recommended actions. Can be loan-specific or org-wide.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._generate_followup_report,
            input_schema=GenerateFollowupReportInput,
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _assess_followup_urgency(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Determine follow-up urgency based on loan stage, closing date, and missing docs."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                           l.closing_date, l.lock_expiration_date,
                           l.stage_changed_at
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Count missing documents
            missing_stats = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total_missing,
                        COUNT(CASE WHEN priority = 'CRITICAL' THEN 1 END) as critical_missing,
                        COUNT(CASE WHEN priority = 'HIGH' THEN 1 END) as high_missing
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id AND status IN ('OPEN', 'REJECTED')
                """),
                {"loan_id": loan_id},
            ).fetchone()

            total_missing = missing_stats.total_missing if missing_stats else 0
            critical_missing = missing_stats.critical_missing if missing_stats else 0
            high_missing = missing_stats.high_missing if missing_stats else 0

            # Calculate urgency score (0-100)
            urgency_score = 0
            urgency_factors = []

            # Factor 1: Loan stage progression
            late_stages = (
                "SUBMITTED", "UNDERWRITING", "UW_RECEIVED",
                "CONDITIONAL_APPROVAL", "APPROVED", "CTC",
                "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
            )
            if loan.stage in late_stages:
                urgency_score += 25
                urgency_factors.append(
                    f"Loan in late stage: {loan.stage}"
                )

            # Factor 2: Closing date proximity
            if loan.closing_date:
                closing_dt = loan.closing_date
                if isinstance(closing_dt, datetime):
                    closing_dt = closing_dt.date()
                days_to_close = (closing_dt - date.today()).days
                if days_to_close <= 7:
                    urgency_score += 30
                    urgency_factors.append(
                        f"Closing in {days_to_close} days"
                    )
                elif days_to_close <= 14:
                    urgency_score += 20
                    urgency_factors.append(
                        f"Closing in {days_to_close} days"
                    )
                elif days_to_close <= 30:
                    urgency_score += 10
                    urgency_factors.append(
                        f"Closing in {days_to_close} days"
                    )

            # Factor 3: Lock expiration
            if loan.lock_expiration_date:
                lock_dt = loan.lock_expiration_date
                if isinstance(lock_dt, datetime):
                    lock_dt = lock_dt.date()
                days_to_lock = (lock_dt - date.today()).days
                if days_to_lock <= 7:
                    urgency_score += 20
                    urgency_factors.append(
                        f"Rate lock expires in {days_to_lock} days"
                    )

            # Factor 4: Critical/high missing documents
            if critical_missing > 0:
                urgency_score += 15
                urgency_factors.append(
                    f"{critical_missing} critical document(s) missing"
                )
            if high_missing > 0:
                urgency_score += 10
                urgency_factors.append(
                    f"{high_missing} high-priority document(s) missing"
                )

            # Factor 5: Time in current stage
            if loan.stage_changed_at:
                days_in_stage = (
                    datetime.now(timezone.utc) - loan.stage_changed_at
                ).days if loan.stage_changed_at.tzinfo else (
                    datetime.now() - loan.stage_changed_at
                ).days
                if days_in_stage > 14:
                    urgency_score += 10
                    urgency_factors.append(
                        f"Loan stagnant: {days_in_stage} days in {loan.stage}"
                    )

            # Cap at 100
            urgency_score = min(urgency_score, 100)

            # Determine urgency level
            if urgency_score >= 75:
                urgency_level = "critical"
                recommended_action = "Immediate multi-channel outreach + LO escalation"
                recommended_campaign = "urgent_reminder"
            elif urgency_score >= 50:
                urgency_level = "high"
                recommended_action = "Urgent email + SMS within 24 hours"
                recommended_campaign = "urgent_reminder"
            elif urgency_score >= 25:
                urgency_level = "normal"
                recommended_action = "Standard follow-up sequence"
                recommended_campaign = "gentle_reminder"
            else:
                urgency_level = "low"
                recommended_action = "Gentle reminder when convenient"
                recommended_campaign = "gentle_reminder"

            self.audit_log(
                "assess_followup_urgency", "loan",
                entity_id=str(loan_id),
                details={
                    "urgency_score": urgency_score,
                    "urgency_level": urgency_level,
                    "total_missing": total_missing,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "loan_stage": loan.stage,
                    "urgency_score": urgency_score,
                    "urgency_level": urgency_level,
                    "missing_documents": {
                        "total": total_missing,
                        "critical": critical_missing,
                        "high": high_missing,
                    },
                    "factors": urgency_factors,
                    "recommended_action": recommended_action,
                    "recommended_campaign_type": recommended_campaign,
                    "closing_date": (
                        loan.closing_date.isoformat() if loan.closing_date else None
                    ),
                    "lock_expiration": (
                        loan.lock_expiration_date.isoformat()
                        if loan.lock_expiration_date else None
                    ),
                },
                message=(
                    f"Urgency: {urgency_level} (score {urgency_score}/100) - "
                    f"{total_missing} docs missing"
                ),
            )

        except Exception as e:
            logger.exception(f"assess_followup_urgency failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _select_followup_channel(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Choose best outreach channel based on borrower preferences and history."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Get borrower preferences
            borrower = db.execute(
                text("""
                    SELECT id, first_name, email, phone,
                           preferred_communication
                    FROM leads
                    WHERE id = :borrower_id
                """),
                {"borrower_id": borrower_id},
            ).fetchone()

            if not borrower:
                return ToolResult(success=False, error=f"Borrower {borrower_id} not found")

            # Analyze past follow-up event response patterns
            channel_response = db.execute(
                text("""
                    SELECT
                        fe.channel,
                        COUNT(*) as total_sent,
                        COUNT(CASE WHEN fe.delivery_status IN ('opened', 'clicked') THEN 1 END) as engaged,
                        COUNT(CASE WHEN fe.delivery_status = 'failed' THEN 1 END) as failed
                    FROM followup_events fe
                    JOIN followup_campaigns fc ON fc.id = fe.campaign_id
                    WHERE fc.borrower_id = :borrower_id
                        AND fe.event_type NOT IN ('borrower_responded', 'document_uploaded')
                    GROUP BY fe.channel
                """),
                {"borrower_id": borrower_id},
            ).fetchall()

            # Build channel scores
            channel_scores = {
                "email": 50,  # default baseline
                "sms": 40,
                "call": 30,
                "portal": 20,
            }

            # Boost based on borrower preference
            if borrower.preferred_communication:
                pref = borrower.preferred_communication.lower()
                if pref in channel_scores:
                    channel_scores[pref] += 20

            # Boost based on past engagement
            for row in channel_response:
                ch = row.channel
                if ch not in channel_scores:
                    continue
                if row.total_sent > 0:
                    engagement_rate = (row.engaged or 0) / row.total_sent
                    channel_scores[ch] += int(engagement_rate * 30)
                    # Penalize channels with high failure rate
                    failure_rate = (row.failed or 0) / row.total_sent
                    channel_scores[ch] -= int(failure_rate * 20)

            # Check channel availability
            has_email = bool(borrower.email)
            has_phone = bool(borrower.phone)

            if not has_email:
                channel_scores["email"] = 0
            if not has_phone:
                channel_scores["sms"] = 0
                channel_scores["call"] = 0

            # Rank channels
            ranked = sorted(
                channel_scores.items(), key=lambda x: x[1], reverse=True
            )
            recommended = ranked[0][0] if ranked else "email"

            self.audit_log(
                "select_followup_channel", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "recommended": recommended,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                    "borrower_name": borrower.first_name,
                    "recommended_channel": recommended,
                    "channel_scores": dict(ranked),
                    "borrower_preference": borrower.preferred_communication,
                    "has_email": has_email,
                    "has_phone": has_phone,
                    "past_engagement": [
                        {
                            "channel": row.channel,
                            "total_sent": row.total_sent,
                            "engaged": row.engaged or 0,
                            "failed": row.failed or 0,
                        }
                        for row in channel_response
                    ],
                },
                message=f"Recommended channel: {recommended} (score {ranked[0][1]})",
            )

        except Exception as e:
            logger.exception(f"select_followup_channel failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _draft_followup_message(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate personalized follow-up message for missing documents."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        channel = input_data.get("channel", "email")
        urgency = input_data.get("urgency", "normal")
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Get borrower info
            borrower = db.execute(
                text("""
                    SELECT first_name, last_name, email, phone
                    FROM leads WHERE id = :borrower_id
                """),
                {"borrower_id": borrower_id},
            ).fetchone()

            if not borrower:
                return ToolResult(
                    success=False, error=f"Borrower {borrower_id} not found"
                )

            # Get LO info
            lo_info = db.execute(
                text("""
                    SELECT CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            lo_name = lo_info.lo_name if lo_info else "Your Loan Officer"

            # Get missing documents
            missing_docs = db.execute(
                text("""
                    SELECT doc_type, title, priority
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

            borrower_name = (
                f"{borrower.first_name or ''} {borrower.last_name or ''}".strip()
                or "there"
            )
            doc_list = "\n".join(
                f"  - {d.title or d.doc_type}" for d in missing_docs
            ) if missing_docs else "  (documents list pending)"
            doc_count = len(missing_docs)
            portal_link = f"https://app.perenniaai.com/portal/documents/{loan_id}"

            # Generate message based on channel and urgency
            if channel == "sms":
                if urgency in ("high", "critical"):
                    body = (
                        f"URGENT: {borrower_name}, we need {doc_count} document(s) "
                        f"to proceed with your loan. Please upload ASAP at "
                        f"{portal_link} or call us."
                    )
                else:
                    body = (
                        f"Hi {borrower_name}, just a reminder - we still need "
                        f"{doc_count} document(s) for your loan. Upload anytime "
                        f"at {portal_link}"
                    )
                draft = {
                    "channel": "sms",
                    "body": body,
                    "to": borrower.phone,
                }
            elif channel == "call_script":
                draft = {
                    "channel": "call_script",
                    "body": (
                        f"Hi {borrower_name}, this is {lo_name} calling about "
                        f"your mortgage application. I wanted to check in because "
                        f"we still need {doc_count} document(s) to keep things "
                        f"moving forward. Specifically, we need:\n\n{doc_list}\n\n"
                        f"Would you have time to gather those this week? I can "
                        f"also schedule a quick call to walk through anything "
                        f"that's confusing."
                    ),
                }
            else:
                # Email
                if urgency in ("high", "critical"):
                    subject = "URGENT: Documents needed to proceed with your loan"
                    body = (
                        f"Hi {borrower_name},\n\n"
                        f"We urgently need the following documents to keep your "
                        f"loan on track:\n\n{doc_list}\n\n"
                        f"Without these documents, we may not be able to meet "
                        f"your closing timeline. Please upload as soon as "
                        f"possible: {portal_link}\n\n"
                        f"If you need help, reply to this email or call us.\n\n"
                        f"{lo_name}"
                    )
                else:
                    subject = "Friendly reminder: Documents still needed"
                    body = (
                        f"Hi {borrower_name},\n\n"
                        f"Just a friendly reminder that we're still waiting on "
                        f"a few documents to continue processing your loan:\n\n"
                        f"{doc_list}\n\n"
                        f"Upload here: {portal_link}\n\n"
                        f"Thanks,\n{lo_name}"
                    )
                draft = {
                    "channel": "email",
                    "subject": subject,
                    "body": body,
                    "to": borrower.email,
                }

            self.audit_log(
                "draft_followup_message", "loan",
                entity_id=str(loan_id),
                details={
                    "channel": channel,
                    "urgency": urgency,
                    "doc_count": doc_count,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                    "borrower_name": borrower_name,
                    "draft": draft,
                    "documents_referenced": doc_count,
                    "urgency": urgency,
                    "requires_review": True,
                },
                message=(
                    f"Draft {channel} message created for {borrower_name} "
                    f"({doc_count} docs, {urgency} urgency)"
                ),
            )

        except Exception as e:
            logger.exception(f"draft_followup_message failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _schedule_followup_sequence(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create a multi-step follow-up campaign."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        campaign_type = input_data.get("campaign_type", "initial_request")
        request_ids_str = input_data["request_ids"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Parse request IDs
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
                return ToolResult(success=False, error="No request IDs provided")

            # Verify loan ownership
            loan = db.execute(
                text("SELECT id, loan_number FROM loans "
                     "WHERE id = :loan_id AND organization_id = :org_id"),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Check for existing active campaigns for same requests
            existing = db.execute(
                text("""
                    SELECT id, campaign_type, status, current_step, total_steps
                    FROM followup_campaigns
                    WHERE loan_id = :loan_id
                        AND status IN ('active', 'paused')
                    ORDER BY created_at DESC
                    LIMIT 5
                """),
                {"loan_id": loan_id},
            ).fetchall()

            existing_campaigns = [
                {
                    "id": c.id,
                    "type": c.campaign_type,
                    "status": c.status,
                    "progress": f"{c.current_step}/{c.total_steps}",
                }
                for c in existing
            ]

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)

            user_id = context.get("user_id")
            result = service.create_campaign(
                loan_id=loan_id,
                borrower_id=borrower_id,
                organization_id=int(org_id) if org_id else 0,
                campaign_type=campaign_type,
                request_ids=request_ids,
                created_by_user_id=int(user_id) if user_id else None,
            )

            db.commit()

            self.audit_log(
                "schedule_followup_sequence", "loan",
                entity_id=str(loan_id),
                details={
                    "campaign_type": campaign_type,
                    "campaign_id": result.get("campaign_id"),
                    "request_ids": request_ids,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "campaign_id": result.get("campaign_id"),
                    "campaign_type": campaign_type,
                    "total_steps": result.get("total_steps"),
                    "next_action_at": result.get("next_action_at"),
                    "request_ids": request_ids,
                    "existing_campaigns": existing_campaigns,
                },
                message=(
                    f"Follow-up campaign created: {campaign_type} with "
                    f"{result.get('total_steps', 0)} steps for "
                    f"{len(request_ids)} document request(s)"
                ),
            )

        except Exception as e:
            logger.exception(f"schedule_followup_sequence failed for loan {loan_id}")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _evaluate_borrower_responsiveness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Analyze past response patterns to optimize timing."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Get all campaigns for this borrower
            campaigns = db.execute(
                text("""
                    SELECT
                        id, campaign_type, status, started_at,
                        borrower_responded, response_date,
                        reminders_sent, completed_at
                    FROM followup_campaigns
                    WHERE borrower_id = :borrower_id
                    ORDER BY created_at DESC
                """),
                {"borrower_id": borrower_id},
            ).fetchall()

            total_campaigns = len(campaigns)
            responded_count = sum(
                1 for c in campaigns if c.borrower_responded
            )
            completed_count = sum(
                1 for c in campaigns if c.status == "completed"
            )

            # Calculate average response time
            response_times_hours = []
            for c in campaigns:
                if c.borrower_responded and c.response_date and c.started_at:
                    delta = c.response_date - c.started_at
                    response_times_hours.append(delta.total_seconds() / 3600.0)

            avg_response_hours = (
                round(sum(response_times_hours) / len(response_times_hours), 1)
                if response_times_hours else None
            )

            # Analyze channel effectiveness from events
            channel_stats = db.execute(
                text("""
                    SELECT
                        fe.channel,
                        COUNT(*) as sent,
                        COUNT(CASE WHEN fe.delivery_status IN ('opened', 'clicked')
                              THEN 1 END) as engaged
                    FROM followup_events fe
                    JOIN followup_campaigns fc ON fc.id = fe.campaign_id
                    WHERE fc.borrower_id = :borrower_id
                        AND fe.event_type NOT IN (
                            'borrower_responded', 'document_uploaded'
                        )
                    GROUP BY fe.channel
                """),
                {"borrower_id": borrower_id},
            ).fetchall()

            # Determine preferred response channel
            best_channel = None
            best_engagement = 0
            channels = []
            for row in channel_stats:
                rate = (row.engaged / row.sent * 100) if row.sent > 0 else 0
                channels.append({
                    "channel": row.channel,
                    "sent": row.sent,
                    "engaged": row.engaged,
                    "engagement_rate": round(rate, 1),
                })
                if row.engaged > best_engagement:
                    best_engagement = row.engaged
                    best_channel = row.channel

            # Calculate responsiveness score (0-100)
            if total_campaigns == 0:
                responsiveness_score = 50  # neutral for new borrowers
                responsiveness_label = "unknown"
            else:
                response_rate = (responded_count / total_campaigns) * 100
                responsiveness_score = min(int(response_rate), 100)

                if responsiveness_score >= 80:
                    responsiveness_label = "highly_responsive"
                elif responsiveness_score >= 50:
                    responsiveness_label = "moderately_responsive"
                elif responsiveness_score >= 20:
                    responsiveness_label = "low_responsiveness"
                else:
                    responsiveness_label = "unresponsive"

            # Average reminders before response
            reminders_before_response = []
            for c in campaigns:
                if c.borrower_responded:
                    reminders_before_response.append(c.reminders_sent or 0)
            avg_reminders = (
                round(
                    sum(reminders_before_response)
                    / len(reminders_before_response), 1
                )
                if reminders_before_response else None
            )

            self.audit_log(
                "evaluate_borrower_responsiveness", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "score": responsiveness_score,
                    "label": responsiveness_label,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                    "responsiveness_score": responsiveness_score,
                    "responsiveness_label": responsiveness_label,
                    "total_campaigns": total_campaigns,
                    "responded_count": responded_count,
                    "completed_count": completed_count,
                    "avg_response_time_hours": avg_response_hours,
                    "avg_reminders_before_response": avg_reminders,
                    "preferred_response_channel": best_channel,
                    "channel_engagement": channels,
                    "recommendation": (
                        f"Use {best_channel or 'email'} as primary channel. "
                        f"Expect ~{avg_response_hours or 48}h response time."
                        if responsiveness_label != "unresponsive"
                        else "Consider LO escalation - borrower has been unresponsive."
                    ),
                },
                message=(
                    f"Responsiveness: {responsiveness_label} "
                    f"(score {responsiveness_score}/100, "
                    f"{responded_count}/{total_campaigns} campaigns responded)"
                ),
            )

        except Exception as e:
            logger.exception(
                f"evaluate_borrower_responsiveness failed for borrower {borrower_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _escalate_to_loan_officer(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Escalate unresponsive borrower to loan officer."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        campaign_id = input_data["campaign_id"]
        reason = input_data.get("reason", "")
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

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)

            # Get campaign info
            campaign = db.execute(
                text("""
                    SELECT id, borrower_id, reminders_sent, started_at,
                           borrower_responded, status
                    FROM followup_campaigns
                    WHERE id = :campaign_id
                """),
                {"campaign_id": campaign_id},
            ).fetchone()

            if not campaign:
                return ToolResult(
                    success=False, error=f"Campaign {campaign_id} not found"
                )

            if not reason:
                reason = (
                    f"Borrower unresponsive after {campaign.reminders_sent or 0} "
                    f"follow-up attempts over "
                    f"{(datetime.now(timezone.utc) - campaign.started_at).days if campaign.started_at else '?'} days"
                )

            # Use the service's escalation
            result = service._escalate_to_lo(
                campaign_id=campaign_id,
                loan_id=loan_id,
            )

            # Cancel the campaign after escalation
            service.cancel_campaign(
                campaign_id,
                reason=f"Escalated to LO: {reason}",
            )

            db.commit()

            self.audit_log(
                "escalate_to_loan_officer", "loan",
                entity_id=str(loan_id),
                details={
                    "campaign_id": campaign_id,
                    "reason": reason,
                    "task_id": result.get("task_id"),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "campaign_id": campaign_id,
                    "escalation_reason": reason,
                    "task_id": result.get("task_id"),
                    "lo_user_id": result.get("lo_user_id"),
                    "lo_email": result.get("lo_email"),
                    "outstanding_docs": result.get("outstanding_document_count", 0),
                },
                message=(
                    f"Escalated to LO (task #{result.get('task_id')}): {reason}"
                ),
            )

        except Exception as e:
            logger.exception(
                f"escalate_to_loan_officer failed for campaign {campaign_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _schedule_document_appointment(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Book appointment for complex document issues."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        appointment_type = input_data.get("appointment_type", "document_collection")
        preferred_date_str = input_data.get("preferred_date", "")
        duration_minutes = input_data.get("duration_minutes", 30)
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

            # Parse preferred date or default to next business day
            if preferred_date_str:
                try:
                    preferred_date = datetime.strptime(
                        preferred_date_str, "%Y-%m-%d"
                    )
                except ValueError:
                    return ToolResult(
                        success=False,
                        error="Invalid date format. Use YYYY-MM-DD.",
                    )
            else:
                # Next business day at 10 AM ET (~15:00 UTC)
                now = datetime.now(timezone.utc)
                preferred_date = now + timedelta(days=1)
                while preferred_date.weekday() >= 5:
                    preferred_date += timedelta(days=1)

            scheduled_time = preferred_date.replace(
                hour=15, minute=0, second=0, microsecond=0
            )
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

            # Get outstanding documents for context
            outstanding = db.execute(
                text("""
                    SELECT id, doc_type, title
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id AND status IN ('OPEN', 'REJECTED')
                """),
                {"loan_id": loan_id},
            ).fetchall()

            doc_ids = [d.id for d in outstanding]

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)

            title_map = {
                "document_collection": "Document Collection Assistance",
                "tax_return_review": "Tax Return Review Session",
                "general_consultation": "Loan Document Consultation",
            }
            title = title_map.get(appointment_type, "Document Assistance")

            result = service.create_appointment(
                loan_id=loan_id,
                borrower_id=borrower_id,
                organization_id=int(org_id) if org_id else 0,
                appointment_type=appointment_type,
                title=title,
                scheduled_time=scheduled_time,
                duration_minutes=duration_minutes,
                documents_to_discuss=doc_ids if doc_ids else None,
            )

            db.commit()

            self.audit_log(
                "schedule_document_appointment", "loan",
                entity_id=str(loan_id),
                details={
                    "appointment_id": result.get("appointment_id"),
                    "type": appointment_type,
                    "scheduled": scheduled_time.isoformat(),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "appointment_id": result.get("appointment_id"),
                    "appointment_type": appointment_type,
                    "title": title,
                    "scheduled_time": scheduled_time.isoformat(),
                    "duration_minutes": duration_minutes,
                    "documents_to_discuss": [
                        {"id": d.id, "title": d.title, "type": d.doc_type}
                        for d in outstanding
                    ],
                    "assigned_to_user_id": result.get("assigned_to_user_id"),
                    "attendee_name": result.get("attendee_name"),
                    "attendee_email": result.get("attendee_email"),
                },
                message=(
                    f"Appointment scheduled: {title} on "
                    f"{scheduled_time.strftime('%m/%d/%Y at %I:%M %p')} UTC"
                ),
            )

        except Exception as e:
            logger.exception(
                f"schedule_document_appointment failed for loan {loan_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_reminder_summary(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create summary of all outstanding document needs for a loan."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                           l.closing_date,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get all missing documents grouped by category
            missing = db.execute(
                text("""
                    SELECT doc_type, title, priority, category, status, sla_due_at
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

            # Get active campaigns
            campaigns = db.execute(
                text("""
                    SELECT id, campaign_type, status, current_step, total_steps,
                           reminders_sent, next_action_at, borrower_responded
                    FROM followup_campaigns
                    WHERE loan_id = :loan_id
                        AND status IN ('active', 'paused')
                    ORDER BY created_at DESC
                """),
                {"loan_id": loan_id},
            ).fetchall()

            # Get completeness
            completeness = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN status IN ('ACCEPTED', 'WAIVED') THEN 1 END) as completed
                    FROM smart_document_requests
                    WHERE loan_id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            total_req = completeness.total if completeness else 0
            completed_req = completeness.completed if completeness else 0
            pct = round(
                (completed_req / total_req) * 100, 1
            ) if total_req > 0 else 0

            # Group missing by category
            by_category = {}
            for doc in missing:
                cat = doc.category or "other"
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append({
                    "doc_type": doc.doc_type,
                    "title": doc.title,
                    "priority": doc.priority,
                    "status": doc.status,
                    "sla_due": (
                        doc.sla_due_at.isoformat() if doc.sla_due_at else None
                    ),
                })

            # Build recommended actions
            recommendations = []
            if len(missing) > 0 and not campaigns:
                recommendations.append(
                    "No active follow-up campaign. Consider starting one."
                )

            critical_count = sum(
                1 for d in missing if d.priority == "CRITICAL"
            )
            if critical_count > 0:
                recommendations.append(
                    f"{critical_count} critical document(s) missing - urgent follow-up needed."
                )

            for c in campaigns:
                if c.reminders_sent and c.reminders_sent >= 3 and not c.borrower_responded:
                    recommendations.append(
                        f"Campaign #{c.id}: {c.reminders_sent} attempts with no response - "
                        f"consider LO escalation."
                    )

            self.audit_log(
                "generate_reminder_summary", "loan",
                entity_id=str(loan_id),
                details={
                    "missing_count": len(missing),
                    "completeness_pct": pct,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "loan_stage": loan.stage,
                    "closing_date": (
                        loan.closing_date.isoformat()
                        if loan.closing_date else None
                    ),
                    "completeness": {
                        "total_required": total_req,
                        "completed": completed_req,
                        "missing": len(missing),
                        "pct": pct,
                    },
                    "missing_by_category": by_category,
                    "active_campaigns": [
                        {
                            "campaign_id": c.id,
                            "type": c.campaign_type,
                            "status": c.status,
                            "progress": f"{c.current_step}/{c.total_steps}",
                            "reminders_sent": c.reminders_sent,
                            "borrower_responded": c.borrower_responded,
                            "next_action": (
                                c.next_action_at.isoformat()
                                if c.next_action_at else None
                            ),
                        }
                        for c in campaigns
                    ],
                    "recommendations": recommendations,
                },
                message=(
                    f"Summary: {pct}% complete, {len(missing)} missing, "
                    f"{len(campaigns)} active campaign(s)"
                ),
            )

        except Exception as e:
            logger.exception(
                f"generate_reminder_summary failed for loan {loan_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _optimize_contact_timing(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Determine best day/time to contact based on response history."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Get timestamps when borrower responded or uploaded docs
            responses = db.execute(
                text("""
                    SELECT
                        fe.created_at,
                        EXTRACT(DOW FROM fe.created_at) as day_of_week,
                        EXTRACT(HOUR FROM fe.created_at) as hour_of_day
                    FROM followup_events fe
                    JOIN followup_campaigns fc ON fc.id = fe.campaign_id
                    WHERE fc.borrower_id = :borrower_id
                        AND fe.event_type IN (
                            'borrower_responded', 'document_uploaded'
                        )
                    ORDER BY fe.created_at DESC
                """),
                {"borrower_id": borrower_id},
            ).fetchall()

            # Also look at email open/click times
            engagement_times = db.execute(
                text("""
                    SELECT
                        COALESCE(fe.opened_at, fe.clicked_at) as engaged_at,
                        EXTRACT(DOW FROM COALESCE(fe.opened_at, fe.clicked_at))
                            as day_of_week,
                        EXTRACT(HOUR FROM COALESCE(fe.opened_at, fe.clicked_at))
                            as hour_of_day
                    FROM followup_events fe
                    JOIN followup_campaigns fc ON fc.id = fe.campaign_id
                    WHERE fc.borrower_id = :borrower_id
                        AND (fe.opened_at IS NOT NULL OR fe.clicked_at IS NOT NULL)
                """),
                {"borrower_id": borrower_id},
            ).fetchall()

            all_events = list(responses) + list(engagement_times)

            day_names = [
                "Sunday", "Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday",
            ]

            if all_events:
                # Analyze day of week patterns
                day_counts = {}
                hour_counts = {}
                for ev in all_events:
                    dow = int(ev.day_of_week)
                    hour = int(ev.hour_of_day)
                    day_counts[dow] = day_counts.get(dow, 0) + 1
                    hour_counts[hour] = hour_counts.get(hour, 0) + 1

                # Best day
                best_day = max(day_counts, key=day_counts.get)
                # Best hour
                best_hour = max(hour_counts, key=hour_counts.get)

                # Top 3 days
                sorted_days = sorted(
                    day_counts.items(), key=lambda x: x[1], reverse=True
                )
                top_days = [day_names[d[0]] for d in sorted_days[:3]]

                # Peak hours (top 3)
                sorted_hours = sorted(
                    hour_counts.items(), key=lambda x: x[1], reverse=True
                )
                peak_hours = [
                    f"{h[0]:02d}:00 UTC" for h in sorted_hours[:3]
                ]

                confidence = "high" if len(all_events) >= 5 else "medium"
            else:
                # Defaults: Tuesday-Thursday, 9-11 AM ET (14-16 UTC)
                best_day = 2  # Tuesday
                best_hour = 15  # 3 PM UTC ~ 10 AM ET
                top_days = ["Tuesday", "Wednesday", "Thursday"]
                peak_hours = ["15:00 UTC", "14:00 UTC", "16:00 UTC"]
                confidence = "low"

            self.audit_log(
                "optimize_contact_timing", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "data_points": len(all_events),
                    "best_day": day_names[best_day],
                    "best_hour": best_hour,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                    "best_day": day_names[best_day],
                    "best_hour_utc": f"{best_hour:02d}:00",
                    "top_days": top_days,
                    "peak_hours": peak_hours,
                    "data_points": len(all_events),
                    "confidence": confidence,
                    "recommendation": (
                        f"Contact on {day_names[best_day]} around "
                        f"{best_hour:02d}:00 UTC ({confidence} confidence, "
                        f"based on {len(all_events)} data points)"
                    ),
                },
                message=(
                    f"Best time: {day_names[best_day]} at {best_hour:02d}:00 UTC "
                    f"({confidence} confidence)"
                ),
            )

        except Exception as e:
            logger.exception(
                f"optimize_contact_timing failed for borrower {borrower_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _track_campaign_effectiveness(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Measure follow-up campaign success rates."""
        from database import SessionLocal

        days = input_data.get("days", 30)
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)
            stats = service.get_followup_stats(
                organization_id=int(org_id) if org_id else 0,
                days=days,
            )

            # Supplement with per-campaign-type breakdown
            type_breakdown = db.execute(
                text("""
                    SELECT
                        campaign_type,
                        COUNT(*) as total,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                        COUNT(CASE WHEN borrower_responded = true THEN 1 END) as responded
                    FROM followup_campaigns
                    WHERE organization_id = :org_id
                        AND created_at >= CURRENT_TIMESTAMP - :days * INTERVAL '1 day'
                    GROUP BY campaign_type
                """),
                {"org_id": org_id, "days": days},
            ).fetchall()

            by_type = [
                {
                    "campaign_type": row.campaign_type,
                    "total": row.total,
                    "completed": row.completed,
                    "responded": row.responded,
                    "completion_rate": round(
                        (row.completed / row.total) * 100, 1
                    ) if row.total > 0 else 0,
                    "response_rate": round(
                        (row.responded / row.total) * 100, 1
                    ) if row.total > 0 else 0,
                }
                for row in type_breakdown
            ]

            self.audit_log(
                "track_campaign_effectiveness", "organization",
                entity_id=str(org_id),
                details={
                    "period_days": days,
                    "total_campaigns": stats.get("total_campaigns", 0),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "period_days": days,
                    "overall": stats,
                    "by_campaign_type": by_type,
                },
                message=(
                    f"Effectiveness: {stats.get('collection_rate', 0)}% collection rate, "
                    f"{stats.get('response_rate', 0)}% response rate over {days} days"
                ),
            )

        except Exception as e:
            logger.exception("track_campaign_effectiveness failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _pause_followup_on_receipt(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Auto-pause campaign when requested document is received."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        request_id = input_data["request_id"]
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

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)

            # Let the service handle document upload logic
            service.handle_document_uploaded(
                loan_id=loan_id,
                request_id=request_id,
            )

            db.commit()

            # Check which campaigns were affected
            affected = db.execute(
                text("""
                    SELECT id, status, linked_request_ids
                    FROM followup_campaigns
                    WHERE loan_id = :loan_id
                        AND status IN ('active', 'paused', 'completed')
                    ORDER BY updated_at DESC
                    LIMIT 10
                """),
                {"loan_id": loan_id},
            ).fetchall()

            affected_campaigns = []
            for c in affected:
                linked = c.linked_request_ids or []
                if request_id in linked:
                    affected_campaigns.append({
                        "campaign_id": c.id,
                        "status": c.status,
                    })

            self.audit_log(
                "pause_followup_on_receipt", "loan",
                entity_id=str(loan_id),
                details={
                    "request_id": request_id,
                    "affected_campaigns": len(affected_campaigns),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "request_id": request_id,
                    "affected_campaigns": affected_campaigns,
                    "campaigns_completed": sum(
                        1 for c in affected_campaigns if c["status"] == "completed"
                    ),
                },
                message=(
                    f"Document receipt processed for request #{request_id}. "
                    f"{len(affected_campaigns)} campaign(s) affected."
                ),
            )

        except Exception as e:
            logger.exception(
                f"pause_followup_on_receipt failed for loan {loan_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _suggest_alternative_documents(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Suggest alternative acceptable documents."""
        doc_type = input_data["doc_type"]
        loan_id = input_data.get("loan_id", 0)

        # Normalize doc_type
        doc_type_lower = doc_type.lower().replace(" ", "_").replace("-", "_")

        alternatives = _ALTERNATIVE_DOCUMENTS.get(doc_type_lower, [])

        # If no exact match, try partial match
        if not alternatives:
            for key, alts in _ALTERNATIVE_DOCUMENTS.items():
                if doc_type_lower in key or key in doc_type_lower:
                    alternatives = alts
                    doc_type_lower = key
                    break

        if not alternatives:
            return ToolResult(
                success=True,
                data={
                    "doc_type": doc_type,
                    "alternatives": [],
                    "message": (
                        f"No standard alternatives found for '{doc_type}'. "
                        "Consult with underwriting for acceptable substitutes."
                    ),
                },
                message=f"No alternatives found for {doc_type}",
            )

        # Get loan-specific context if loan_id provided
        loan_context = None
        if loan_id:
            from database import SessionLocal
            org_id = self.require_org_id()
            db = SessionLocal()
            try:
                loan = db.execute(
                    text("""
                        SELECT loan_type, stage
                        FROM loans
                        WHERE id = :loan_id AND organization_id = :org_id
                    """),
                    {"loan_id": loan_id, "org_id": org_id},
                ).fetchone()
                if loan:
                    loan_context = {
                        "loan_type": loan.loan_type,
                        "stage": loan.stage,
                    }
            except Exception as e:
                logger.warning(
                    f"Could not fetch loan context for alternatives: {e}"
                )
            finally:
                db.close()

        self.audit_log(
            "suggest_alternative_documents", "document",
            details={
                "doc_type": doc_type,
                "alternatives_count": len(alternatives),
            },
        )

        return ToolResult(
            success=True,
            data={
                "doc_type": doc_type,
                "normalized_type": doc_type_lower,
                "alternatives": [
                    {"description": alt, "index": i + 1}
                    for i, alt in enumerate(alternatives)
                ],
                "loan_context": loan_context,
                "note": (
                    "Alternative documents may require underwriter approval. "
                    "Verify acceptability with your investor guidelines."
                ),
            },
            message=(
                f"{len(alternatives)} alternative(s) for {doc_type}"
            ),
        )

    async def _create_borrower_portal_notification(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Generate portal notification for the borrower."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        borrower_id = input_data["borrower_id"]
        notification_type = input_data.get(
            "notification_type", "document_reminder"
        )
        custom_message = input_data.get("message", "")
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

            borrower_name = loan.borrower_name or "Borrower"

            # Auto-generate message if not provided
            if not custom_message:
                if notification_type == "document_reminder":
                    # Get missing doc count
                    missing = db.execute(
                        text("""
                            SELECT COUNT(*) as cnt
                            FROM smart_document_requests
                            WHERE loan_id = :loan_id
                                AND status IN ('OPEN', 'REJECTED')
                        """),
                        {"loan_id": loan_id},
                    ).fetchone()
                    doc_count = missing.cnt if missing else 0
                    custom_message = (
                        f"You have {doc_count} outstanding document(s) "
                        f"needed for your loan application. Please upload "
                        f"them at your earliest convenience."
                    )
                elif notification_type == "document_rejected":
                    custom_message = (
                        "A document you submitted requires re-upload. "
                        "Please check the documents section for details "
                        "and upload a corrected version."
                    )
                elif notification_type == "document_expired":
                    custom_message = (
                        "A document on file has expired and we need "
                        "an updated version. Please check the documents "
                        "section for details."
                    )
                elif notification_type == "appointment_reminder":
                    custom_message = (
                        "You have an upcoming document review appointment. "
                        "Please have your outstanding documents ready."
                    )

            # Record the notification event
            from database.models.document_followup import (
                FollowupEvent,
                FollowupEventType,
                DeliveryStatus,
            )

            # Find active campaign for this loan (if any)
            campaign = db.execute(
                text("""
                    SELECT id FROM followup_campaigns
                    WHERE loan_id = :loan_id AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"loan_id": loan_id},
            ).fetchone()

            campaign_id = campaign.id if campaign else None

            if campaign_id:
                event = FollowupEvent(
                    campaign_id=campaign_id,
                    event_type=FollowupEventType.PORTAL_NOTIFICATION,
                    channel="portal",
                    message_preview=custom_message[:500],
                    delivery_status=DeliveryStatus.SENT,
                    metadata={
                        "notification_type": notification_type,
                        "borrower_id": borrower_id,
                    },
                )
                db.add(event)

            # Create notification record
            now = datetime.now(timezone.utc)
            db.execute(
                text("""
                    INSERT INTO notifications (
                        user_id, title, message, type, read,
                        created_at, organization_id
                    ) VALUES (
                        :borrower_id, :title, :message, :type, false,
                        :created_at, :org_id
                    )
                """),
                {
                    "borrower_id": borrower_id,
                    "title": f"Document Update - Loan {loan.loan_number}",
                    "message": custom_message,
                    "type": notification_type,
                    "created_at": now,
                    "org_id": org_id,
                },
            )

            db.commit()

            self.audit_log(
                "create_borrower_portal_notification", "loan",
                entity_id=str(loan_id),
                details={
                    "borrower_id": borrower_id,
                    "notification_type": notification_type,
                },
            )

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower_id": borrower_id,
                    "notification_type": notification_type,
                    "message": custom_message,
                    "campaign_id": campaign_id,
                    "sent_at": now.isoformat(),
                },
                message=(
                    f"Portal notification created for {borrower_name}: "
                    f"{notification_type}"
                ),
            )

        except Exception as e:
            logger.exception(
                f"create_borrower_portal_notification failed for loan {loan_id}"
            )
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _batch_process_overdue_followups(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Process all overdue follow-up campaign steps across pipeline."""
        from database import SessionLocal

        max_campaigns = input_data.get("max_campaigns", 50)
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            # Count overdue before processing
            overdue_count = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM followup_campaigns
                    WHERE organization_id = :org_id
                        AND status = 'active'
                        AND next_action_at <= CURRENT_TIMESTAMP
                """),
                {"org_id": org_id},
            ).fetchone()

            total_overdue = overdue_count.cnt if overdue_count else 0

            from services.smart_docs.followup_automation_service import (
                get_followup_automation_service,
            )
            service = get_followup_automation_service(db)
            results = service.process_pending_actions()

            db.commit()

            self.audit_log(
                "batch_process_overdue_followups", "organization",
                entity_id=str(org_id),
                details={
                    "total_overdue": total_overdue,
                    "processed": results.get("processed", 0),
                    "succeeded": results.get("succeeded", 0),
                    "failed": results.get("failed", 0),
                },
            )

            return ToolResult(
                success=True,
                data={
                    "total_overdue_found": total_overdue,
                    "processed": results.get("processed", 0),
                    "succeeded": results.get("succeeded", 0),
                    "failed": results.get("failed", 0),
                    "completed_campaigns": results.get("completed_campaigns", 0),
                    "details": results.get("details", [])[:max_campaigns],
                },
                message=(
                    f"Batch processed {results.get('processed', 0)} overdue "
                    f"campaigns: {results.get('succeeded', 0)} succeeded, "
                    f"{results.get('failed', 0)} failed"
                ),
            )

        except Exception as e:
            logger.exception("batch_process_overdue_followups failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_followup_report(
        self,
        input_data: Dict[str, Any],
        context: AgentContext,
    ) -> ToolResult:
        """Create follow-up status report for the LO."""
        from database import SessionLocal

        loan_id = input_data.get("loan_id", 0)
        days = input_data.get("days", 30)
        org_id = self.require_org_id()
        db = SessionLocal()
        try:
            if loan_id:
                # Loan-specific report
                loan = db.execute(
                    text("""
                        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                               l.closing_date,
                               CONCAT(u.first_name, ' ', u.last_name) as lo_name
                        FROM loans l
                        LEFT JOIN users u ON u.id = l.loan_officer_id
                        WHERE l.id = :loan_id AND l.organization_id = :org_id
                    """),
                    {"loan_id": loan_id, "org_id": org_id},
                ).fetchone()

                if not loan:
                    return ToolResult(
                        success=False, error=f"Loan {loan_id} not found"
                    )

                # Campaign history for this loan
                campaigns = db.execute(
                    text("""
                        SELECT
                            id, campaign_type, status, current_step,
                            total_steps, reminders_sent,
                            borrower_responded, response_date,
                            started_at, completed_at, cancelled_at,
                            cancel_reason
                        FROM followup_campaigns
                        WHERE loan_id = :loan_id
                        ORDER BY created_at DESC
                    """),
                    {"loan_id": loan_id},
                ).fetchall()

                # Document status
                doc_stats = db.execute(
                    text("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(CASE WHEN status = 'OPEN' THEN 1 END) as open,
                            COUNT(CASE WHEN status = 'ACCEPTED' THEN 1 END) as accepted,
                            COUNT(CASE WHEN status = 'REJECTED' THEN 1 END) as rejected
                        FROM smart_document_requests
                        WHERE loan_id = :loan_id
                    """),
                    {"loan_id": loan_id},
                ).fetchone()

                report = {
                    "report_type": "loan_specific",
                    "loan_id": loan_id,
                    "loan_number": loan.loan_number,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "loan_stage": loan.stage,
                    "closing_date": (
                        loan.closing_date.isoformat()
                        if loan.closing_date else None
                    ),
                    "document_status": {
                        "total": doc_stats.total if doc_stats else 0,
                        "open": doc_stats.open if doc_stats else 0,
                        "accepted": doc_stats.accepted if doc_stats else 0,
                        "rejected": doc_stats.rejected if doc_stats else 0,
                    },
                    "campaign_history": [
                        {
                            "campaign_id": c.id,
                            "type": c.campaign_type,
                            "status": c.status,
                            "progress": f"{c.current_step}/{c.total_steps}",
                            "reminders_sent": c.reminders_sent,
                            "borrower_responded": c.borrower_responded,
                            "response_date": (
                                c.response_date.isoformat()
                                if c.response_date else None
                            ),
                            "started": (
                                c.started_at.isoformat()
                                if c.started_at else None
                            ),
                            "completed": (
                                c.completed_at.isoformat()
                                if c.completed_at else None
                            ),
                            "cancel_reason": c.cancel_reason,
                        }
                        for c in campaigns
                    ],
                    "total_campaigns": len(campaigns),
                    "active_campaigns": sum(
                        1 for c in campaigns if c.status == "active"
                    ),
                }
            else:
                # Org-wide report
                from services.smart_docs.followup_automation_service import (
                    get_followup_automation_service,
                )
                service = get_followup_automation_service(db)
                stats = service.get_followup_stats(
                    organization_id=int(org_id) if org_id else 0,
                    days=days,
                )

                # Top unresponsive borrowers
                unresponsive = db.execute(
                    text("""
                        SELECT
                            fc.loan_id,
                            l.loan_number,
                            l.borrower_name,
                            COUNT(*) as campaign_count,
                            SUM(fc.reminders_sent) as total_reminders,
                            MAX(fc.updated_at) as last_attempt
                        FROM followup_campaigns fc
                        JOIN loans l ON l.id = fc.loan_id
                        WHERE fc.organization_id = :org_id
                            AND fc.status = 'active'
                            AND fc.borrower_responded = false
                            AND fc.reminders_sent >= 3
                        GROUP BY fc.loan_id, l.loan_number, l.borrower_name
                        ORDER BY total_reminders DESC
                        LIMIT 10
                    """),
                    {"org_id": org_id},
                ).fetchall()

                report = {
                    "report_type": "organization",
                    "period_days": days,
                    "summary": stats,
                    "needs_attention": [
                        {
                            "loan_id": row.loan_id,
                            "loan_number": row.loan_number,
                            "borrower": row.borrower_name,
                            "campaigns": row.campaign_count,
                            "total_reminders": row.total_reminders,
                            "last_attempt": (
                                row.last_attempt.isoformat()
                                if row.last_attempt else None
                            ),
                        }
                        for row in unresponsive
                    ],
                    "needs_attention_count": len(unresponsive),
                }

            self.audit_log(
                "generate_followup_report", "organization",
                entity_id=str(org_id),
                details={
                    "report_type": report.get("report_type"),
                    "loan_id": loan_id or "org_wide",
                },
            )

            return ToolResult(
                success=True,
                data=report,
                message=(
                    f"Follow-up report generated: "
                    f"{report.get('report_type', 'unknown')} "
                    f"({days} day window)"
                ),
            )

        except Exception as e:
            logger.exception("generate_followup_report failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
