"""
Borrower Experience Agent

Specialized agent that optimizes the borrower's document submission journey.
Focuses on borrower-facing interactions: personalized checklists, plain-English
explanations, sentiment assessment, milestone celebrations, friction prediction,
and TCPA-compliant multi-channel communications.

15 Tools:
1.  generate_personalized_checklist - Create borrower-friendly document checklist
2.  explain_document_requirement - Explain WHY a specific document is needed
3.  suggest_document_alternatives - Suggest acceptable alternative documents
4.  draft_borrower_message - Draft personalized message for any channel
5.  handle_borrower_question - Answer common questions about document requirements
6.  assess_borrower_sentiment - Gauge borrower frustration/satisfaction from history
7.  recommend_communication_channel - Choose best channel for this borrower
8.  generate_progress_celebration - Send congratulatory message at milestones
9.  simplify_rejection_explanation - Turn technical rejection into friendly explanation
10. create_document_tutorial - Step-by-step instructions for obtaining a document
11. schedule_assistance_call - Schedule help call when borrower is struggling
12. predict_borrower_friction - Identify docs this borrower will likely struggle with
13. generate_portal_notification - Create in-app notification for borrower portal
14. localize_communication - Adapt communication for borrower's preferred language
15. measure_borrower_experience_score - Calculate NPS-style experience score
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


# ============================================================================
# CONSTANTS
# ============================================================================

# Plain-English explanations for each document type
_DOC_EXPLANATIONS = {
    "paystubs": {
        "why": "Your pay stubs show your current income so the lender can verify you earn enough to make your monthly mortgage payments.",
        "what": "Your two most recent pay stubs from your employer, showing year-to-date earnings.",
        "tip": "Most employers offer online access through payroll portals like ADP, Workday, or Gusto.",
    },
    "w2": {
        "why": "W-2s confirm your annual earnings history and help verify the income shown on your pay stubs is consistent.",
        "what": "W-2 forms from the last 2 years, from each employer you worked for.",
        "tip": "Check your email for electronic copies, or request from your HR department. The IRS can also provide wage transcripts.",
    },
    "tax_returns": {
        "why": "Tax returns give a complete picture of all income sources and are required when income varies year to year.",
        "what": "Complete federal tax returns (all pages and schedules) for the last 2 years.",
        "tip": "Your accountant or tax preparer should have copies. You can also download them from the IRS at irs.gov.",
    },
    "bank_statements": {
        "why": "Bank statements verify you have enough savings for the down payment and closing costs, and that the funds are seasoned (not borrowed).",
        "what": "Complete statements (all pages) from the last 2 months for all accounts you plan to use.",
        "tip": "Download PDFs directly from your bank's website. Lenders need every page, even blank ones.",
    },
    "drivers_license": {
        "why": "A government-issued ID confirms your identity, which is required by federal regulations to prevent fraud.",
        "what": "Clear photo of the front and back of your current, non-expired driver's license or state ID.",
        "tip": "Take a clear, well-lit photo with all four corners visible. A phone camera works fine.",
    },
    "gift_letter": {
        "why": "If someone is helping with your down payment, the lender needs to confirm it's a gift (not a loan that would add to your debt).",
        "what": "A signed letter from the gift giver stating the amount, that it's a gift, and no repayment is expected.",
        "tip": "Your loan officer can provide a template. The gift giver will also need a bank statement showing the withdrawal.",
    },
    "purchase_contract": {
        "why": "The purchase contract tells the lender the price, terms, and timeline of your home purchase so they can structure the loan correctly.",
        "what": "Fully executed (all parties signed) purchase agreement including any addenda or amendments.",
        "tip": "Your real estate agent should provide this. Make sure all pages and signatures are included.",
    },
    "appraisal": {
        "why": "The appraisal protects both you and the lender by confirming the home is worth at least what you're paying for it.",
        "what": "This is typically ordered by the lender. You usually don't need to obtain it yourself.",
        "tip": "Your loan officer will order the appraisal and coordinate access. You'll receive a copy once it's complete.",
    },
    "credit_report": {
        "why": "Your credit report shows your borrowing history and helps determine your interest rate and loan eligibility.",
        "what": "The lender pulls this directly with your authorization. You don't need to provide it.",
        "tip": "Check your free credit reports at AnnualCreditReport.com before applying so there are no surprises.",
    },
    "insurance": {
        "why": "Homeowner's insurance protects the property (the lender's collateral) and is required before closing.",
        "what": "An insurance binder or declaration page showing coverage for at least the loan amount.",
        "tip": "Contact an insurance agent early. Shopping around can save hundreds per year. Your lender needs this before closing.",
    },
    "1099": {
        "why": "1099 forms document income from freelance, contract, or investment sources that don't appear on a W-2.",
        "what": "All 1099 forms received for the past 2 years.",
        "tip": "Check your email and tax software for electronic copies, or contact each payer directly.",
    },
    "profit_loss": {
        "why": "A P&L statement shows your business's recent financial performance when you're self-employed.",
        "what": "A year-to-date profit and loss statement, ideally prepared or signed by your accountant.",
        "tip": "Many accounting tools (QuickBooks, FreshBooks) can generate this in minutes.",
    },
}

# Alternative document suggestions
_ALTERNATIVE_DOCUMENTS = {
    "paystubs": [
        "Direct deposit statement from your bank showing employer deposits",
        "Employer-issued pay summary letter on company letterhead",
        "ADP, Workday, or payroll service printout",
    ],
    "w2": [
        "IRS Wage & Income Transcript (request at irs.gov, free, takes ~5 days)",
        "Year-end paystub showing total annual earnings and taxes withheld",
    ],
    "tax_returns": [
        "IRS Tax Return Transcript (Form 4506-C request, free)",
        "Signed copy from your accountant or tax preparer",
    ],
    "bank_statements": [
        "Credit union statements (same format, all pages needed)",
        "Letter from your bank verifying account type, balance, and history",
    ],
    "drivers_license": [
        "State-issued identification card",
        "Valid US passport (photo page)",
        "Military ID (active duty or veteran)",
    ],
    "gift_letter": [
        "Wire transfer confirmation showing donor name and amount",
        "Donor's bank statement showing the withdrawal (can redact other transactions)",
    ],
    "insurance": [
        "Insurance binder from your agent",
        "Declaration page from your homeowner's policy",
        "Evidence of insurance letter from the insurer",
    ],
}

# Document tutorials — step-by-step instructions
_DOC_TUTORIALS = {
    "paystubs": [
        "Log in to your employer's payroll portal (ADP, Workday, Paychex, etc.)",
        "Navigate to 'Pay' or 'Pay History' section",
        "Select your two most recent pay periods",
        "Download or print each as a PDF",
        "Make sure year-to-date earnings are visible on each stub",
        "Upload both PDFs to your secure document portal",
    ],
    "bank_statements": [
        "Log in to your bank's online banking or mobile app",
        "Go to 'Statements' or 'Documents' section",
        "Download the last 2 monthly statements as PDFs",
        "Important: download the FULL statement (every page, even blank ones)",
        "Do this for EACH account you're using for down payment or reserves",
        "Upload all statement PDFs to your secure document portal",
    ],
    "tax_returns": [
        "Option A: Contact your accountant or tax preparer for copies",
        "Option B: Download from your tax software (TurboTax, H&R Block, etc.)",
        "Option C: Request a free IRS transcript at irs.gov/individuals/get-transcript",
        "Make sure to include ALL pages and schedules (especially Schedules C, E, K-1 if applicable)",
        "You'll need returns for the last 2 tax years",
        "Upload the complete returns to your secure document portal",
    ],
    "drivers_license": [
        "Place your ID on a flat, well-lit surface (natural light works best)",
        "Take a clear photo of the FRONT of your ID with your phone camera",
        "Make sure all four corners are visible and text is readable",
        "Flip the ID over and take a clear photo of the BACK",
        "Check that both photos are sharp and not blurry",
        "Upload both photos to your secure document portal",
    ],
}

# Common borrower questions and answers
_BORROWER_FAQ = {
    "how_long": {
        "question_patterns": ["how long", "how much time", "when will", "timeline"],
        "answer": "The typical mortgage process takes 30-45 days from application to closing. Document collection is usually the biggest factor — the faster we receive your documents, the faster we can move forward.",
    },
    "why_so_many": {
        "question_patterns": ["why so many", "too many documents", "so much paperwork", "why all this"],
        "answer": "I know it feels like a lot of paperwork. Federal regulations require lenders to verify your income, assets, and identity to protect both you and the lender. Each document serves a specific purpose, and we've streamlined the list to only what's truly needed.",
    },
    "is_it_safe": {
        "question_patterns": ["safe", "secure", "privacy", "who sees", "data protection"],
        "answer": "Absolutely. Your documents are transmitted over encrypted connections and stored in a secure, bank-grade system. Only your loan team has access, and all activity is logged for your protection. We follow strict federal privacy regulations (GLBA).",
    },
    "what_if_cant_find": {
        "question_patterns": ["can't find", "don't have", "lost", "missing", "where do i get"],
        "answer": "No worries — this happens more often than you'd think. For most documents, there are alternative versions we can accept. Let me know which document you're having trouble with, and I'll suggest alternatives.",
    },
    "why_all_pages": {
        "question_patterns": ["all pages", "blank pages", "every page", "why blank"],
        "answer": "Lenders need every page of bank statements and tax returns, including blank pages, because missing pages could indicate hidden information. It's a federal audit requirement — even the blank pages confirm the statement is complete.",
    },
    "already_sent": {
        "question_patterns": ["already sent", "already uploaded", "sent that", "gave you that"],
        "answer": "Let me check our records right away. Sometimes uploads take a moment to process, or a document may need to be re-uploaded if the image quality wasn't clear enough. I'll verify and let you know the status.",
    },
    "credit_score_impact": {
        "question_patterns": ["credit score", "hard pull", "credit check", "affect my credit"],
        "answer": "The initial credit check is a hard inquiry, but if you're rate shopping within a 45-day window, multiple mortgage inquiries count as just one. The document collection process itself has zero impact on your credit score.",
    },
}

# Friction predictors — doc types commonly difficult for borrower profiles
_FRICTION_PREDICTORS = {
    "self_employed": ["tax_returns", "profit_loss", "1099", "bank_statements"],
    "first_time_buyer": ["purchase_contract", "insurance", "gift_letter"],
    "relocating": ["drivers_license", "insurance", "bank_statements"],
    "commission_income": ["tax_returns", "1099", "paystubs"],
    "gift_funds": ["gift_letter", "bank_statements"],
    "retirement_income": ["tax_returns", "1099", "bank_statements"],
}


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class GenerateChecklistInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to generate checklist for")
    include_tips: bool = Field(default=True, description="Include helpful tips with each item")


class ExplainDocumentInput(BaseModel):
    document_type: str = Field(..., description="Document type to explain (e.g., paystubs, w2, bank_statements)")


class SuggestAlternativesInput(BaseModel):
    document_type: str = Field(..., description="Document type the borrower cannot provide")
    reason: Optional[str] = Field(None, description="Why borrower cannot provide the document")


class DraftBorrowerMessageInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for context")
    channel: str = Field(default="email", description="Channel: email, sms, portal")
    message_purpose: str = Field(..., description="Purpose: reminder, welcome, milestone, clarification, rejection_explanation")
    custom_context: Optional[str] = Field(None, description="Additional context for the message")


class HandleQuestionInput(BaseModel):
    question: str = Field(..., description="The borrower's question text")
    loan_id: Optional[int] = Field(None, description="Loan ID for context")


class AssessSentimentInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to assess borrower sentiment for")


class RecommendChannelInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to recommend communication channel for")


class GenerateCelebrationInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to check milestones for")


class SimplifyRejectionInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID with rejection")
    rejection_reason: str = Field(..., description="Technical rejection reason to simplify")
    document_type: Optional[str] = Field(None, description="Document type that was rejected")


class CreateTutorialInput(BaseModel):
    document_type: str = Field(..., description="Document type to create tutorial for")


class ScheduleAssistanceCallInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for the borrower needing help")
    reason: str = Field(..., description="Reason for the assistance call")
    preferred_time: Optional[str] = Field(None, description="Borrower's preferred time for the call")


class PredictFrictionInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to predict friction for")


class GeneratePortalNotificationInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID for the notification")
    notification_type: str = Field(..., description="Type: doc_received, doc_needed, milestone, status_update, action_required")
    details: Optional[str] = Field(None, description="Additional notification details")


class LocalizeCommunicationInput(BaseModel):
    message: str = Field(..., description="Message text to localize")
    target_language: str = Field(default="es", description="Target language code: es, zh, vi, ko, tl")


class MeasureExperienceScoreInput(BaseModel):
    loan_id: int = Field(..., description="Loan ID to calculate experience score for")


# ============================================================================
# BORROWER EXPERIENCE AGENT
# ============================================================================

@AgentRegistry.register
class BorrowerExperienceAgent(SpecializedAgent):
    """
    Specialized agent for optimizing the borrower's document submission journey.

    Focuses on borrower-facing interactions with warm, patient communication.
    All tools enforce tenant isolation via organization_id and ensure TCPA
    compliance for outbound communications.

    15 tools covering checklists, explanations, alternatives, messaging,
    FAQ handling, sentiment analysis, channel selection, milestone celebrations,
    rejection explanations, tutorials, assistance scheduling, friction
    prediction, portal notifications, localization, and experience scoring.
    """

    @property
    def name(self) -> str:
        return "BorrowerExperienceAgent"

    @property
    def description(self) -> str:
        return (
            "Optimizes the borrower document submission journey with personalized "
            "checklists, plain-English explanations, sentiment-aware communication, "
            "and milestone celebrations"
        )

    def _register_tools(self):
        """Register all borrower experience tools."""

        # Tool 1: Generate Personalized Checklist
        self.register_tool(AgentTool(
            name="generate_personalized_checklist",
            description="Create a borrower-friendly document checklist with plain-English "
                        "instructions and helpful tips tailored to their loan type and situation.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._generate_personalized_checklist,
            input_schema=GenerateChecklistInput,
        ))

        # Tool 2: Explain Document Requirement
        self.register_tool(AgentTool(
            name="explain_document_requirement",
            description="Explain WHY a specific document is needed in simple, "
                        "borrower-friendly terms without jargon.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._explain_document_requirement,
            input_schema=ExplainDocumentInput,
        ))

        # Tool 3: Suggest Document Alternatives
        self.register_tool(AgentTool(
            name="suggest_document_alternatives",
            description="When a borrower cannot provide a requested document, "
                        "suggest acceptable alternatives they can use instead.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._suggest_document_alternatives,
            input_schema=SuggestAlternativesInput,
        ))

        # Tool 4: Draft Borrower Message
        self.register_tool(AgentTool(
            name="draft_borrower_message",
            description="Draft a personalized message for any channel (email, SMS, portal) "
                        "with TCPA compliance checks for outbound communications.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._draft_borrower_message,
            input_schema=DraftBorrowerMessageInput,
        ))

        # Tool 5: Handle Borrower Question
        self.register_tool(AgentTool(
            name="handle_borrower_question",
            description="Answer common borrower questions about document requirements, "
                        "process timeline, security, and more in plain language.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._handle_borrower_question,
            input_schema=HandleQuestionInput,
        ))

        # Tool 6: Assess Borrower Sentiment
        self.register_tool(AgentTool(
            name="assess_borrower_sentiment",
            description="Analyze communication history to gauge borrower frustration "
                        "or satisfaction level and recommend tone adjustments.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._assess_borrower_sentiment,
            input_schema=AssessSentimentInput,
        ))

        # Tool 7: Recommend Communication Channel
        self.register_tool(AgentTool(
            name="recommend_communication_channel",
            description="Based on borrower response history and preferences, recommend "
                        "which channel (email, SMS, call, portal) gets the best response.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._recommend_communication_channel,
            input_schema=RecommendChannelInput,
        ))

        # Tool 8: Generate Progress Celebration
        self.register_tool(AgentTool(
            name="generate_progress_celebration",
            description="When borrower hits a document milestone (50%% docs, all income "
                        "docs, etc.), generate a congratulatory message.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_progress_celebration,
            input_schema=GenerateCelebrationInput,
        ))

        # Tool 9: Simplify Rejection Explanation
        self.register_tool(AgentTool(
            name="simplify_rejection_explanation",
            description="Turn a technical document rejection reason into a borrower-friendly "
                        "explanation with clear fix instructions.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._simplify_rejection_explanation,
            input_schema=SimplifyRejectionInput,
        ))

        # Tool 10: Create Document Tutorial
        self.register_tool(AgentTool(
            name="create_document_tutorial",
            description="Generate step-by-step instructions for obtaining a specific "
                        "document that a borrower needs to provide.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._create_document_tutorial,
            input_schema=CreateTutorialInput,
        ))

        # Tool 11: Schedule Assistance Call
        self.register_tool(AgentTool(
            name="schedule_assistance_call",
            description="When a borrower is struggling with documents, schedule a help "
                        "call with their loan officer or processor.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_assistance_call,
            input_schema=ScheduleAssistanceCallInput,
        ))

        # Tool 12: Predict Borrower Friction
        self.register_tool(AgentTool(
            name="predict_borrower_friction",
            description="Identify which remaining documents this borrower will likely "
                        "struggle with based on their profile and loan type.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._predict_borrower_friction,
            input_schema=PredictFrictionInput,
        ))

        # Tool 13: Generate Portal Notification
        self.register_tool(AgentTool(
            name="generate_portal_notification",
            description="Create an in-app notification for the borrower portal with "
                        "appropriate urgency and clear call-to-action.",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.LOW,
            handler=self._generate_portal_notification,
            input_schema=GeneratePortalNotificationInput,
        ))

        # Tool 14: Localize Communication
        self.register_tool(AgentTool(
            name="localize_communication",
            description="Adapt communication for the borrower's preferred language "
                        "with culturally appropriate tone.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._localize_communication,
            input_schema=LocalizeCommunicationInput,
        ))

        # Tool 15: Measure Borrower Experience Score
        self.register_tool(AgentTool(
            name="measure_borrower_experience_score",
            description="Calculate an NPS-style experience score based on response times, "
                        "document completion rate, and communication frequency.",
            category=ToolCategory.ANALYSIS,
            risk_level=RiskLevel.LOW,
            handler=self._measure_borrower_experience_score,
            input_schema=MeasureExperienceScoreInput,
        ))

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _check_tcpa_consent(self, db: Any, loan_id: int, channel: str) -> Dict[str, Any]:
        """Check TCPA consent for outbound communication on the given channel.

        Returns dict with 'allowed' bool and 'reason' string.
        For email: consent is implied during an active loan application.
        For SMS/call: requires explicit opt-in via borrower profile or lead record.
        Portal notifications do not require TCPA consent.
        """
        if channel == "portal":
            return {"allowed": True, "reason": "Portal notifications exempt from TCPA"}

        if channel == "email":
            # Email during active loan process is permissible (existing business relationship)
            return {"allowed": True, "reason": "Active loan application — existing business relationship"}

        # SMS and call require explicit consent
        org_id = self.require_org_id()

        consent_row = db.execute(
            text("""
                SELECT bp.sms_consent, bp.call_consent
                FROM borrower_profiles bp
                JOIN loans l ON LOWER(l.borrower_email) = LOWER(bp.email)
                WHERE l.id = :loan_id AND l.organization_id = :org_id
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()

        if not consent_row:
            return {"allowed": False, "reason": "No borrower profile found — cannot verify consent"}

        if channel == "sms":
            has_consent = bool(consent_row.sms_consent)
            return {
                "allowed": has_consent,
                "reason": "SMS consent on file" if has_consent else "No SMS consent — TCPA prohibits outbound SMS",
            }

        if channel == "call":
            has_consent = bool(consent_row.call_consent)
            return {
                "allowed": has_consent,
                "reason": "Call consent on file" if has_consent else "No call consent — TCPA prohibits outbound calls",
            }

        return {"allowed": False, "reason": f"Unknown channel: {channel}"}

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _generate_personalized_checklist(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate a personalized, borrower-friendly document checklist."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        include_tips = input_data.get("include_tips", True)
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.borrower_name, l.loan_type,
                           l.loan_purpose, l.stage
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get documents already on file
            existing = db.execute(
                text("SELECT doc_type, status FROM documents WHERE loan_id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchall()
            received_types = {d.doc_type for d in existing if d.status == "active"}

            # Build checklist based on loan type
            required_docs = ["paystubs", "w2", "bank_statements", "drivers_license", "credit_report"]
            if loan.loan_type in ("fha", "va", "usda"):
                required_docs.append("tax_returns")
            if loan.loan_purpose == "purchase":
                required_docs.extend(["purchase_contract", "insurance"])

            checklist = []
            for doc_type in required_docs:
                status = "received" if doc_type in received_types else "needed"
                item = {
                    "document": doc_type,
                    "friendly_name": doc_type.replace("_", " ").title(),
                    "status": status,
                }
                if include_tips and doc_type in _DOC_EXPLANATIONS:
                    item["why_needed"] = _DOC_EXPLANATIONS[doc_type]["why"]
                    item["tip"] = _DOC_EXPLANATIONS[doc_type]["tip"]
                checklist.append(item)

            received_count = len([c for c in checklist if c["status"] == "received"])
            total_count = len(checklist)
            pct = round((received_count / total_count) * 100) if total_count > 0 else 0

            first_name = (loan.borrower_name or "").split()[0] if loan.borrower_name else "there"

            self.audit_log("generate_checklist", "loan", str(loan_id), {
                "received": received_count, "total": total_count,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_name": first_name,
                    "loan_type": loan.loan_type,
                    "checklist": checklist,
                    "progress": {
                        "received": received_count,
                        "total": total_count,
                        "percentage": pct,
                    },
                },
                message=f"Checklist for {first_name}: {received_count}/{total_count} documents ({pct}% complete)",
            )
        except Exception as e:
            logger.exception("generate_personalized_checklist failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _explain_document_requirement(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Explain why a specific document is needed in plain English."""
        doc_type = input_data["document_type"].lower().strip()

        explanation = _DOC_EXPLANATIONS.get(doc_type)
        if not explanation:
            return ToolResult(
                success=True,
                data={
                    "document_type": doc_type,
                    "explanation": f"This document helps verify important details about your loan application. Your loan officer can provide more specific guidance.",
                },
                message=f"General explanation provided for {doc_type}",
            )

        return ToolResult(
            success=True,
            data={
                "document_type": doc_type,
                "friendly_name": doc_type.replace("_", " ").title(),
                "why_needed": explanation["why"],
                "what_to_provide": explanation["what"],
                "helpful_tip": explanation["tip"],
            },
            message=f"Explanation for {doc_type.replace('_', ' ')}",
        )

    async def _suggest_document_alternatives(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Suggest acceptable alternative documents."""
        doc_type = input_data["document_type"].lower().strip()
        reason = input_data.get("reason", "")

        alternatives = _ALTERNATIVE_DOCUMENTS.get(doc_type, [])

        if not alternatives:
            return ToolResult(
                success=True,
                data={
                    "document_type": doc_type,
                    "alternatives": [],
                    "recommendation": "Please contact your loan officer to discuss options for this document.",
                },
                message=f"No standard alternatives for {doc_type} — loan officer review recommended",
            )

        return ToolResult(
            success=True,
            data={
                "document_type": doc_type,
                "original_reason": reason,
                "alternatives": alternatives,
                "note": "Any ONE of these alternatives is acceptable. Check with your loan officer if unsure.",
            },
            message=f"{len(alternatives)} alternative(s) available for {doc_type.replace('_', ' ')}",
        )

    async def _draft_borrower_message(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Draft a personalized message with TCPA compliance check."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        channel = input_data.get("channel", "email")
        purpose = input_data["message_purpose"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            # TCPA consent check
            consent = self._check_tcpa_consent(db, loan_id, channel)
            if not consent["allowed"]:
                return ToolResult(
                    success=False,
                    error=f"TCPA compliance block: {consent['reason']}",
                    message=consent["reason"],
                )

            loan = db.execute(
                text("""
                    SELECT l.borrower_name, l.borrower_email, l.loan_number, l.stage,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            first_name = (loan.borrower_name or "").split()[0] if loan.borrower_name else "there"
            lo_name = loan.lo_name or "your loan officer"

            # Build message based on purpose and channel
            if purpose == "welcome":
                subject = f"Welcome, {first_name} — Let's Get Started"
                body = (
                    f"Hi {first_name},\n\n"
                    f"Welcome to your mortgage journey! I'm {lo_name}, and I'll be guiding you "
                    f"through the process.\n\n"
                    f"To get things moving, I've prepared a personalized document checklist for you. "
                    f"Each item includes a simple explanation of why we need it.\n\n"
                    f"You can upload documents anytime through your secure portal. "
                    f"If you have questions about any document, just reply to this message.\n\n"
                    f"Let's make this as smooth as possible!\n\n"
                    f"Best,\n{lo_name}"
                )
            elif purpose == "reminder":
                subject = f"{first_name}, a few documents are still needed"
                body = (
                    f"Hi {first_name},\n\n"
                    f"Just checking in on your document submissions. We still need a few items "
                    f"to keep your loan moving forward.\n\n"
                    f"Log in to your portal to see what's remaining. "
                    f"If you're having trouble with any document, I'm happy to help — "
                    f"there are often alternatives we can accept.\n\n"
                    f"Best,\n{lo_name}"
                )
            elif purpose == "milestone":
                subject = f"Great progress, {first_name}!"
                body = (
                    f"Hi {first_name},\n\n"
                    f"Great news — you're making excellent progress on your document submissions! "
                    f"We're getting closer to moving your loan forward.\n\n"
                    f"Keep it up!\n\n"
                    f"Best,\n{lo_name}"
                )
            else:
                subject = f"Update on your loan, {first_name}"
                body = (
                    f"Hi {first_name},\n\n"
                    f"I have an update regarding your loan application. "
                    f"Please log in to your portal for details, or reply to this message "
                    f"if you have any questions.\n\n"
                    f"Best,\n{lo_name}"
                )

            # Trim for SMS
            if channel == "sms":
                sms_templates = {
                    "welcome": f"Hi {first_name}, welcome! Your document checklist is ready in your portal. Upload anytime — reply HELP if you need assistance. -{lo_name}",
                    "reminder": f"Hi {first_name}, a few documents are still needed for your loan. Check your portal for details. Reply HELP for assistance. -{lo_name}",
                    "milestone": f"Great progress {first_name}! Your document submissions are looking good. Check your portal for what's next. -{lo_name}",
                }
                body = sms_templates.get(purpose, f"Hi {first_name}, you have an update on your loan. Check your portal for details. -{lo_name}")
                subject = None

            self.audit_log("draft_borrower_message", "loan", str(loan_id), {
                "channel": channel, "purpose": purpose,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "channel": channel,
                    "subject": subject,
                    "body": body,
                    "recipient": loan.borrower_email if channel == "email" else first_name,
                    "tcpa_consent": consent,
                    "requires_review": True,
                },
                message=f"Draft {channel} message ({purpose}) ready for review",
            )
        except Exception as e:
            logger.exception("draft_borrower_message failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _handle_borrower_question(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Answer a common borrower question in plain language."""
        question = input_data["question"].lower()

        best_match = None
        best_score = 0
        for faq_key, faq in _BORROWER_FAQ.items():
            matches = sum(1 for p in faq["question_patterns"] if p in question)
            if matches > best_score:
                best_score = matches
                best_match = faq

        if best_match and best_score > 0:
            return ToolResult(
                success=True,
                data={
                    "question": input_data["question"],
                    "answer": best_match["answer"],
                    "confidence": "high" if best_score >= 2 else "medium",
                },
                message=best_match["answer"],
            )

        return ToolResult(
            success=True,
            data={
                "question": input_data["question"],
                "answer": "That's a great question. Let me connect you with your loan officer who can give you the most accurate answer for your specific situation.",
                "confidence": "low",
                "escalate": True,
            },
            message="Question routed to loan officer for a personalized answer",
        )

    async def _assess_borrower_sentiment(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Assess borrower sentiment from communication history."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            # Analyze activities for sentiment signals
            activities = db.execute(
                text("""
                    SELECT a.type, a.sentiment, a.content, a.created_at
                    FROM activities a
                    JOIN leads ld ON ld.id = a.lead_id
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                    ORDER BY a.created_at DESC
                    LIMIT 20
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchall()

            # Count sentiment indicators
            positive_signals = 0
            negative_signals = 0
            neutral_count = 0
            response_times = []

            for act in activities:
                sentiment = (act.sentiment or "").lower()
                if sentiment in ("positive", "happy", "satisfied"):
                    positive_signals += 1
                elif sentiment in ("negative", "frustrated", "angry", "upset"):
                    negative_signals += 1
                else:
                    neutral_count += 1

            total = len(activities)
            if total == 0:
                return ToolResult(
                    success=True,
                    data={
                        "loan_id": loan_id,
                        "sentiment_score": 50,
                        "sentiment_label": "neutral",
                        "recommendation": "No communication history yet. Start with a warm welcome message.",
                        "activity_count": 0,
                    },
                    message="No activity history — recommend warm welcome outreach",
                )

            # Calculate sentiment score (0-100, higher = happier)
            sentiment_score = 50  # baseline
            if total > 0:
                sentiment_score = int(50 + (positive_signals - negative_signals) / total * 50)
                sentiment_score = max(0, min(100, sentiment_score))

            if sentiment_score >= 70:
                label = "positive"
                recommendation = "Borrower is engaged and responsive. Maintain current communication cadence."
            elif sentiment_score >= 40:
                label = "neutral"
                recommendation = "Borrower is cooperative but not enthusiastic. Consider adding encouragement and celebrating small wins."
            else:
                label = "frustrated"
                recommendation = (
                    "Borrower may be frustrated. Use extra patience, acknowledge the paperwork burden, "
                    "offer a help call, and simplify remaining requests."
                )

            self.audit_log("assess_sentiment", "loan", str(loan_id), {
                "score": sentiment_score, "label": label,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "sentiment_score": sentiment_score,
                    "sentiment_label": label,
                    "signals": {
                        "positive": positive_signals,
                        "negative": negative_signals,
                        "neutral": neutral_count,
                    },
                    "activity_count": total,
                    "recommendation": recommendation,
                },
                message=f"Sentiment: {label} (score: {sentiment_score}/100)",
            )
        except Exception as e:
            logger.exception("assess_borrower_sentiment failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _recommend_communication_channel(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Recommend best communication channel based on borrower history."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            self.verify_loan_tenant(db, loan_id)

            # Check borrower's stated preference
            pref_row = db.execute(
                text("""
                    SELECT ld.preferred_communication
                    FROM leads ld
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            # Check response history by channel
            channel_stats = db.execute(
                text("""
                    SELECT a.type, COUNT(*) as cnt
                    FROM activities a
                    JOIN leads ld ON ld.id = a.lead_id
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                        AND a.type IN ('Email', 'SMS', 'Call')
                    GROUP BY a.type
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchall()

            channel_counts = {row.type: row.cnt for row in channel_stats}
            stated_preference = pref_row.preferred_communication if pref_row else None

            # TCPA consent check for SMS and call
            sms_consent = self._check_tcpa_consent(db, loan_id, "sms")
            call_consent = self._check_tcpa_consent(db, loan_id, "call")

            # Determine recommendation
            if stated_preference and stated_preference.lower() in ("email", "sms", "call", "phone"):
                recommended = stated_preference.lower()
                if recommended == "phone":
                    recommended = "call"
                reason = f"Borrower's stated preference is {recommended}"
            elif channel_counts:
                # Recommend channel with most activity (likely most responsive)
                recommended = max(channel_counts, key=channel_counts.get).lower()
                reason = f"Borrower responds most on {recommended} ({channel_counts.get(recommended.title(), 0)} interactions)"
            else:
                recommended = "email"
                reason = "No interaction history — defaulting to email (lowest friction)"

            # Override if consent missing
            if recommended == "sms" and not sms_consent["allowed"]:
                recommended = "email"
                reason = f"SMS preferred but no consent on file. Falling back to email."
            elif recommended == "call" and not call_consent["allowed"]:
                recommended = "email"
                reason = f"Call preferred but no consent on file. Falling back to email."

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "recommended_channel": recommended,
                    "reason": reason,
                    "stated_preference": stated_preference,
                    "channel_history": channel_counts,
                    "consent_status": {
                        "sms": sms_consent,
                        "call": call_consent,
                        "email": {"allowed": True, "reason": "Active business relationship"},
                        "portal": {"allowed": True, "reason": "In-app, no consent needed"},
                    },
                },
                message=f"Recommended channel: {recommended} — {reason}",
            )
        except Exception as e:
            logger.exception("recommend_communication_channel failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_progress_celebration(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate celebration message when borrower hits document milestones."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.borrower_name, l.loan_type
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            existing = db.execute(
                text("SELECT doc_type, doc_category FROM documents WHERE loan_id = :loan_id AND status = 'active'"),
                {"loan_id": loan_id},
            ).fetchall()

            received_types = {d.doc_type for d in existing}
            received_categories = {d.doc_category for d in existing}

            # Determine required docs (simplified)
            required = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
            received_required = received_types & required
            pct = round(len(received_required) / len(required) * 100) if required else 0

            first_name = (loan.borrower_name or "").split()[0] if loan.borrower_name else "there"

            # Check specific milestones
            milestones_hit = []
            if "income" in received_categories:
                milestones_hit.append("all_income_docs")
            if "assets" in received_categories:
                milestones_hit.append("all_asset_docs")
            if pct >= 100:
                milestones_hit.append("all_docs_complete")
            elif pct >= 75:
                milestones_hit.append("75_percent")
            elif pct >= 50:
                milestones_hit.append("50_percent")
            elif pct >= 25:
                milestones_hit.append("25_percent")

            celebrations = {
                "all_docs_complete": f"Incredible, {first_name}! You've submitted every document we need. Your file is now complete and ready for the next step. Thank you for being so on top of this!",
                "75_percent": f"Almost there, {first_name}! You've completed 75% of your documents. Just a few more items and your file will be complete!",
                "50_percent": f"Halfway there, {first_name}! You've knocked out half of your document checklist. Great momentum — keep it going!",
                "25_percent": f"Great start, {first_name}! You've completed your first few documents. You're building momentum!",
                "all_income_docs": f"All income documents are in, {first_name}! That's one of the most important categories checked off.",
                "all_asset_docs": f"All asset documents received, {first_name}! Your financial picture is coming together nicely.",
            }

            if not milestones_hit:
                return ToolResult(
                    success=True,
                    data={"loan_id": loan_id, "milestone": None, "percentage": pct},
                    message="No new milestone reached yet",
                )

            primary_milestone = milestones_hit[0]
            message = celebrations.get(primary_milestone, f"Great progress, {first_name}!")

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_name": first_name,
                    "milestone": primary_milestone,
                    "milestones_hit": milestones_hit,
                    "percentage": pct,
                    "celebration_message": message,
                },
                message=message,
            )
        except Exception as e:
            logger.exception("generate_progress_celebration failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _simplify_rejection_explanation(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Turn a technical rejection reason into borrower-friendly language."""
        rejection_reason = input_data["rejection_reason"]
        doc_type = input_data.get("document_type", "")

        # Map common technical rejections to friendly explanations
        rejection_mappings = {
            "illegible": {
                "explanation": "The document was a bit hard to read. This can happen with photos taken in low light or at an angle.",
                "fix": "Try retaking the photo in good lighting, making sure all text is clear and all four corners are visible. A flatbed scanner works great too.",
            },
            "expired": {
                "explanation": "The document has passed its valid date. We need a current version to accurately verify your information.",
                "fix": "Please obtain an updated version. For IDs, visit your local DMV. For financial documents, download the most recent version from your provider.",
            },
            "incomplete": {
                "explanation": "We received part of the document but some pages appear to be missing.",
                "fix": "Please upload the complete document with all pages, including any blank pages. Bank statements, for example, need every page even if some are blank.",
            },
            "wrong_document": {
                "explanation": "The file you uploaded doesn't appear to match what was requested.",
                "fix": "Please double-check the document type and upload the correct file. If you're unsure what's needed, I'm happy to explain.",
            },
            "too_old": {
                "explanation": "The document is from too long ago. We need more recent information to verify your current financial situation.",
                "fix": "Please provide a version dated within the last 60-90 days. You can usually download current statements from your bank's website.",
            },
            "name_mismatch": {
                "explanation": "The name on the document doesn't exactly match the name on your application.",
                "fix": "If you've changed your name, we may need supporting documentation (like a marriage certificate). Otherwise, please provide a version with your current legal name.",
            },
            "unsigned": {
                "explanation": "The document needs a signature to be accepted.",
                "fix": "Please sign the document and re-upload. If it requires a specific person's signature (like a gift letter), please have them sign it as well.",
            },
        }

        # Find best matching rejection
        reason_lower = rejection_reason.lower()
        matched = None
        for key, mapping in rejection_mappings.items():
            if key in reason_lower:
                matched = mapping
                break

        if not matched:
            matched = {
                "explanation": "There was an issue with the document you submitted, and we need an updated version.",
                "fix": f"Please review the document and re-upload. If you have questions, your loan officer can explain exactly what's needed. Original note: {rejection_reason}",
            }

        return ToolResult(
            success=True,
            data={
                "original_reason": rejection_reason,
                "document_type": doc_type,
                "friendly_explanation": matched["explanation"],
                "how_to_fix": matched["fix"],
                "alternatives": _ALTERNATIVE_DOCUMENTS.get(doc_type, []),
            },
            message=f"Simplified: {matched['explanation']}",
        )

    async def _create_document_tutorial(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate step-by-step instructions for obtaining a document."""
        doc_type = input_data["document_type"].lower().strip()

        steps = _DOC_TUTORIALS.get(doc_type)

        if not steps:
            # Provide generic guidance
            return ToolResult(
                success=True,
                data={
                    "document_type": doc_type,
                    "steps": [
                        f"Locate your {doc_type.replace('_', ' ')} from your records or provider",
                        "Ensure the document is current and complete (all pages included)",
                        "Scan or photograph it clearly with all text readable",
                        "Upload to your secure document portal",
                    ],
                    "generic": True,
                },
                message=f"Generic tutorial for {doc_type.replace('_', ' ')}",
            )

        explanation = _DOC_EXPLANATIONS.get(doc_type, {})

        return ToolResult(
            success=True,
            data={
                "document_type": doc_type,
                "friendly_name": doc_type.replace("_", " ").title(),
                "why_needed": explanation.get("why", "Required for your loan application."),
                "steps": [{"step_number": i + 1, "instruction": step} for i, step in enumerate(steps)],
                "total_steps": len(steps),
                "estimated_time": "5-10 minutes",
            },
            message=f"Tutorial: {len(steps)} steps to get your {doc_type.replace('_', ' ')}",
        )

    async def _schedule_assistance_call(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Schedule a help call when borrower is struggling with documents."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        reason = input_data["reason"]
        preferred_time = input_data.get("preferred_time")
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.borrower_name, l.borrower_phone, l.loan_officer_id,
                           CONCAT(u.first_name, ' ', u.last_name) as lo_name
                    FROM loans l
                    LEFT JOIN users u ON u.id = l.loan_officer_id
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # TCPA check for outbound call
            consent = self._check_tcpa_consent(db, loan_id, "call")

            # Create a task for the LO
            task_result = db.execute(
                text("""
                    INSERT INTO tasks (
                        title, description, task_type, entity_type, entity_id,
                        due_date, assigned_to, status, created_at
                    )
                    VALUES (
                        :title, :description, 'callback', 'loan', :loan_id,
                        :due_date, :assigned_to, 'pending', CURRENT_TIMESTAMP
                    )
                    RETURNING id
                """),
                {
                    "title": f"Document Assistance Call — {loan.borrower_name}",
                    "description": f"Borrower needs help with documents. Reason: {reason}",
                    "loan_id": loan_id,
                    "due_date": preferred_time,
                    "assigned_to": loan.loan_officer_id,
                },
            ).fetchone()
            db.commit()

            self.audit_log("schedule_assistance_call", "loan", str(loan_id), {
                "reason": reason, "task_id": task_result.id if task_result else None,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "task_id": task_result.id if task_result else None,
                    "borrower": loan.borrower_name,
                    "lo_name": loan.lo_name,
                    "reason": reason,
                    "preferred_time": preferred_time,
                    "tcpa_consent": consent,
                    "call_allowed": consent["allowed"],
                },
                message=f"Assistance call scheduled for {loan.borrower_name} with {loan.lo_name}",
            )
        except Exception as e:
            db.rollback()
            logger.exception("schedule_assistance_call failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _predict_borrower_friction(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Predict which remaining documents will cause friction for this borrower."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.loan_type, l.loan_purpose, l.borrower_name
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Get lead profile for employment type hints
            lead = db.execute(
                text("""
                    SELECT ld.employment_type, ld.loan_purpose, ld.property_type
                    FROM leads ld
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            # Get documents already received
            existing = db.execute(
                text("SELECT doc_type FROM documents WHERE loan_id = :loan_id AND status = 'active'"),
                {"loan_id": loan_id},
            ).fetchall()
            received_types = {d.doc_type for d in existing}

            # Determine borrower profile for friction prediction
            profiles_matched = []
            employment = (lead.employment_type or "").lower() if lead else ""

            if "self" in employment or "1099" in employment or "business" in employment:
                profiles_matched.append("self_employed")
            if "commission" in employment:
                profiles_matched.append("commission_income")
            if loan.loan_purpose and "purchase" in (loan.loan_purpose or "").lower():
                profiles_matched.append("first_time_buyer")

            # Predict friction documents
            friction_docs = []
            seen = set()
            for profile in profiles_matched:
                for doc_type in _FRICTION_PREDICTORS.get(profile, []):
                    if doc_type not in received_types and doc_type not in seen:
                        seen.add(doc_type)
                        explanation = _DOC_EXPLANATIONS.get(doc_type, {})
                        friction_docs.append({
                            "document_type": doc_type,
                            "friction_profile": profile,
                            "reason": f"Commonly difficult for {profile.replace('_', ' ')} borrowers",
                            "tip": explanation.get("tip", "Contact your loan officer for guidance."),
                            "alternatives_available": len(_ALTERNATIVE_DOCUMENTS.get(doc_type, [])),
                        })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_profiles": profiles_matched,
                    "predicted_friction_docs": friction_docs,
                    "friction_count": len(friction_docs),
                    "recommendation": (
                        "Proactively provide tutorials and alternatives for these documents "
                        "to reduce borrower frustration and speed up collection."
                        if friction_docs else
                        "No high-friction documents predicted for this borrower profile."
                    ),
                },
                message=f"{len(friction_docs)} documents predicted to cause friction",
            )
        except Exception as e:
            logger.exception("predict_borrower_friction failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _generate_portal_notification(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Generate an in-app notification for the borrower portal."""
        loan_id = input_data["loan_id"]
        notification_type = input_data["notification_type"]
        details = input_data.get("details", "")
        org_id = self.require_org_id()

        notification_templates = {
            "doc_received": {
                "title": "Document Received",
                "body": f"We've received your document. Thank you! {details}".strip(),
                "urgency": "info",
                "icon": "check_circle",
            },
            "doc_needed": {
                "title": "Document Needed",
                "body": f"We still need a few documents to move forward. {details}".strip(),
                "urgency": "action_required",
                "icon": "upload_file",
            },
            "milestone": {
                "title": "Great Progress!",
                "body": f"You've hit a document milestone. {details}".strip(),
                "urgency": "info",
                "icon": "celebration",
            },
            "status_update": {
                "title": "Loan Status Update",
                "body": f"Your loan status has been updated. {details}".strip(),
                "urgency": "info",
                "icon": "info",
            },
            "action_required": {
                "title": "Action Needed",
                "body": f"Please review and take action on a pending item. {details}".strip(),
                "urgency": "high",
                "icon": "priority_high",
            },
        }

        template = notification_templates.get(
            notification_type,
            {"title": "Update", "body": details or "You have a new update.", "urgency": "info", "icon": "info"},
        )

        self.audit_log("portal_notification", "loan", str(loan_id), {
            "type": notification_type,
        })

        return ToolResult(
            success=True,
            data={
                "loan_id": loan_id,
                "notification": {
                    "type": notification_type,
                    "title": template["title"],
                    "body": template["body"],
                    "urgency": template["urgency"],
                    "icon": template["icon"],
                    "created_at": datetime.utcnow().isoformat(),
                },
            },
            message=f"Portal notification: {template['title']}",
        )

    async def _localize_communication(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Provide localization guidance for borrower communication.

        Note: actual translation requires an external translation service.
        This tool provides templates and cultural guidance for common languages.
        """
        message = input_data["message"]
        target_lang = input_data.get("target_language", "es")

        language_info = {
            "es": {
                "language_name": "Spanish",
                "greeting": "Hola",
                "cultural_notes": "Use formal 'usted' form. Include both English and Spanish versions.",
                "common_terms": {
                    "pay stubs": "talones de pago",
                    "bank statements": "estados de cuenta bancarios",
                    "tax returns": "declaraciones de impuestos",
                    "driver's license": "licencia de conducir",
                    "loan": "prestamo",
                    "mortgage": "hipoteca",
                    "closing": "cierre",
                },
            },
            "zh": {
                "language_name": "Chinese (Simplified)",
                "greeting": "您好",
                "cultural_notes": "Use formal, respectful tone. Include both English and Chinese versions.",
                "common_terms": {},
            },
            "vi": {
                "language_name": "Vietnamese",
                "greeting": "Xin chao",
                "cultural_notes": "Use formal pronouns. Include both English and Vietnamese versions.",
                "common_terms": {},
            },
            "ko": {
                "language_name": "Korean",
                "greeting": "안녕하세요",
                "cultural_notes": "Use formal/polite speech level (합쇼체). Include both English and Korean versions.",
                "common_terms": {},
            },
            "tl": {
                "language_name": "Tagalog",
                "greeting": "Kumusta",
                "cultural_notes": "Use polite 'po' and 'opo'. Include both English and Tagalog versions.",
                "common_terms": {},
            },
        }

        lang_data = language_info.get(target_lang, {
            "language_name": target_lang,
            "greeting": "",
            "cultural_notes": "Include both English and translated versions for clarity.",
            "common_terms": {},
        })

        return ToolResult(
            success=True,
            data={
                "original_message": message,
                "target_language": target_lang,
                "language_name": lang_data["language_name"],
                "greeting": lang_data["greeting"],
                "cultural_notes": lang_data["cultural_notes"],
                "common_mortgage_terms": lang_data.get("common_terms", {}),
                "recommendation": (
                    f"For {lang_data['language_name']} speakers, send a bilingual message "
                    f"with the {lang_data['language_name']} version first, followed by English. "
                    f"Use a professional translation service for accuracy."
                ),
                "needs_professional_translation": True,
            },
            message=f"Localization guidance for {lang_data['language_name']}",
        )

    async def _measure_borrower_experience_score(
        self, input_data: Dict[str, Any], context: AgentContext
    ) -> ToolResult:
        """Calculate an NPS-style borrower experience score."""
        from database import SessionLocal

        loan_id = input_data["loan_id"]
        org_id = self.require_org_id()

        db = SessionLocal()
        try:
            loan = db.execute(
                text("""
                    SELECT l.id, l.borrower_name, l.stage, l.application_date,
                           l.stage_changed_at, l.created_at
                    FROM loans l
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not loan:
                return ToolResult(success=False, error=f"Loan {loan_id} not found")

            # Factor 1: Document completion rate (0-30 points)
            docs = db.execute(
                text("SELECT COUNT(*) as cnt FROM documents WHERE loan_id = :loan_id AND status = 'active'"),
                {"loan_id": loan_id},
            ).fetchone()
            doc_count = docs.cnt if docs else 0
            # Assume ~8 required docs; cap at 30 points
            doc_score = min(30, int((doc_count / 8) * 30))

            # Factor 2: Communication responsiveness (0-25 points)
            activity_stats = db.execute(
                text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN sentiment IN ('positive', 'happy') THEN 1 END) as positive
                    FROM activities a
                    JOIN leads ld ON ld.id = a.lead_id
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id AND l.organization_id = :org_id
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            total_activities = activity_stats.total if activity_stats else 0
            positive_activities = activity_stats.positive if activity_stats else 0

            if total_activities > 0:
                comm_score = min(25, int((positive_activities / total_activities) * 25) + 10)
            else:
                comm_score = 10  # neutral baseline

            # Factor 3: Stage progression velocity (0-25 points)
            if loan.application_date and loan.stage_changed_at:
                days_elapsed = (datetime.utcnow() - loan.application_date).days if isinstance(loan.application_date, datetime) else 30
                # Faster progression = higher score
                if days_elapsed <= 15:
                    velocity_score = 25
                elif days_elapsed <= 30:
                    velocity_score = 20
                elif days_elapsed <= 45:
                    velocity_score = 15
                else:
                    velocity_score = 5
            else:
                velocity_score = 15  # neutral

            # Factor 4: Absence of escalations (0-20 points)
            escalations = db.execute(
                text("""
                    SELECT COUNT(*) as cnt
                    FROM compliance_alerts
                    WHERE loan_id = :loan_id AND severity IN ('high', 'critical')
                """),
                {"loan_id": loan_id},
            ).fetchone()
            escalation_count = escalations.cnt if escalations else 0
            escalation_score = max(0, 20 - (escalation_count * 5))

            total_score = doc_score + comm_score + velocity_score + escalation_score

            # NPS-style categorization
            if total_score >= 80:
                category = "promoter"
                label = "Excellent experience"
            elif total_score >= 50:
                category = "passive"
                label = "Satisfactory experience"
            else:
                category = "detractor"
                label = "Needs improvement"

            self.audit_log("experience_score", "loan", str(loan_id), {
                "score": total_score, "category": category,
            })

            return ToolResult(
                success=True,
                data={
                    "loan_id": loan_id,
                    "borrower_name": loan.borrower_name,
                    "experience_score": total_score,
                    "max_score": 100,
                    "category": category,
                    "label": label,
                    "breakdown": {
                        "document_completion": {"score": doc_score, "max": 30},
                        "communication_quality": {"score": comm_score, "max": 25},
                        "progression_velocity": {"score": velocity_score, "max": 25},
                        "escalation_absence": {"score": escalation_score, "max": 20},
                    },
                    "improvement_areas": [
                        area for area, score, threshold in [
                            ("Document collection", doc_score, 15),
                            ("Communication responsiveness", comm_score, 12),
                            ("Loan progression speed", velocity_score, 12),
                            ("Issue resolution", escalation_score, 10),
                        ] if score < threshold
                    ],
                },
                message=f"Experience score: {total_score}/100 ({category}) — {label}",
            )
        except Exception as e:
            logger.exception("measure_borrower_experience_score failed")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
