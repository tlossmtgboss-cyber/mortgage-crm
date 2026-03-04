"""
AI Receptionist Agent

Specialized agent for voice/chat receptionist with 8 tools:
1. greet_caller - Welcome and identify caller
2. lookup_caller - Find caller in CRM
3. route_call - Route to appropriate person/queue
4. capture_lead_info - Capture new lead information
5. schedule_callback - Schedule a callback
6. provide_loan_status - Give loan status update
7. answer_faq - Answer common questions
8. escalate_to_human - Transfer to human agent
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field

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

class GreetCallerInput(BaseModel):
    """Input for greeting a caller"""
    caller_phone: Optional[str] = Field(None, description="Caller's phone number")
    channel: str = Field(default="phone", description="Communication channel: phone, chat, voice")
    time_of_day: Optional[str] = Field(None, description="Time context: morning, afternoon, evening")


class LookupCallerInput(BaseModel):
    """Input for looking up caller in CRM"""
    phone: Optional[str] = Field(None, description="Phone number to lookup")
    email: Optional[str] = Field(None, description="Email to lookup")
    name: Optional[str] = Field(None, description="Name to search")


class RouteCallInput(BaseModel):
    """Input for routing a call"""
    caller_id: Optional[int] = Field(None, description="Lead/Contact ID if known")
    intent: str = Field(..., description="Caller intent: new_loan, status_check, payment, support, other")
    urgency: str = Field(default="normal", description="Urgency: low, normal, high, urgent")


class CaptureLeadInput(BaseModel):
    """Input for capturing lead information"""
    first_name: str = Field(..., description="Lead's first name")
    last_name: str = Field(..., description="Lead's last name")
    phone: str = Field(..., description="Phone number")
    email: Optional[str] = Field(None, description="Email address")
    loan_purpose: Optional[str] = Field(None, description="Loan purpose: purchase, refinance, cash_out")
    notes: Optional[str] = Field(None, description="Additional notes from conversation")


class ScheduleCallbackInput(BaseModel):
    """Input for scheduling a callback"""
    contact_id: Optional[int] = Field(None, description="Contact ID if known")
    phone: str = Field(..., description="Phone number for callback")
    preferred_time: Optional[str] = Field(None, description="Preferred callback time")
    reason: str = Field(..., description="Reason for callback")
    assign_to: Optional[int] = Field(None, description="User ID to assign callback to")


class LoanStatusInput(BaseModel):
    """Input for providing loan status"""
    loan_id: Optional[int] = Field(None, description="Loan ID if known")
    borrower_phone: Optional[str] = Field(None, description="Borrower's phone number")
    last_four_ssn: Optional[str] = Field(None, description="Last 4 digits of SSN for verification")


class FAQInput(BaseModel):
    """Input for answering FAQs"""
    question: str = Field(..., description="The question asked")
    category: Optional[str] = Field(None, description="Category: rates, process, requirements, timeline")


class EscalateInput(BaseModel):
    """Input for escalating to human"""
    reason: str = Field(..., description="Reason for escalation")
    caller_info: Optional[Dict] = Field(None, description="Caller information collected")
    urgency: str = Field(default="normal", description="Urgency level")
    preferred_department: Optional[str] = Field(None, description="Department: sales, processing, support")


# ============================================================================
# RECEPTIONIST AGENT
# ============================================================================

@AgentRegistry.register
class ReceptionistAgent(SpecializedAgent):
    """
    AI Receptionist for handling inbound calls and chats.

    Provides intelligent call routing, lead capture, and first-line support
    with 8 specialized tools.
    """

    @property
    def name(self) -> str:
        return "ReceptionistAgent"

    @property
    def description(self) -> str:
        return "AI receptionist for inbound calls, lead capture, call routing, and first-line support"

    def _register_tools(self):
        """Register all receptionist tools"""

        self.register_tool(AgentTool(
            name="greet_caller",
            description="Generate appropriate greeting for incoming caller based on time and channel",
            category=ToolCategory.COMMUNICATION,
            risk_level=RiskLevel.LOW,
            handler=self._greet_caller,
            input_schema=GreetCallerInput
        ))

        self.register_tool(AgentTool(
            name="lookup_caller",
            description="Look up caller in CRM by phone, email, or name to identify existing leads/clients",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._lookup_caller,
            input_schema=LookupCallerInput
        ))

        self.register_tool(AgentTool(
            name="route_call",
            description="Route call to appropriate person or department based on intent and urgency",
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.MEDIUM,
            handler=self._route_call,
            input_schema=RouteCallInput
        ))

        self.register_tool(AgentTool(
            name="capture_lead_info",
            description="Capture new lead information from caller and create lead record",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._capture_lead_info,
            input_schema=CaptureLeadInput
        ))

        self.register_tool(AgentTool(
            name="schedule_callback",
            description="Schedule a callback for the caller at their preferred time",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._schedule_callback,
            input_schema=ScheduleCallbackInput
        ))

        self.register_tool(AgentTool(
            name="provide_loan_status",
            description="Provide loan status update to verified caller",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.MEDIUM,
            handler=self._provide_loan_status,
            input_schema=LoanStatusInput
        ))

        self.register_tool(AgentTool(
            name="answer_faq",
            description="Answer common questions about rates, process, requirements, and timelines",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._answer_faq,
            input_schema=FAQInput
        ))

        self.register_tool(AgentTool(
            name="escalate_to_human",
            description="Transfer call to human agent when needed",
            category=ToolCategory.WORKFLOW,
            risk_level=RiskLevel.LOW,
            handler=self._escalate_to_human,
            input_schema=EscalateInput
        ))

    async def _greet_caller(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Generate greeting for caller"""
        time_of_day = input_data.get("time_of_day", "day")
        channel = input_data.get("channel", "phone")

        greetings = {
            "morning": "Good morning",
            "afternoon": "Good afternoon",
            "evening": "Good evening",
            "day": "Hello"
        }

        greeting = greetings.get(time_of_day, "Hello")

        if channel == "chat":
            message = f"{greeting}! Welcome to Perennia. How can I assist you today?"
        else:
            message = f"{greeting}, thank you for calling Perennia. How may I help you?"

        return ToolResult(
            success=True,
            data={"greeting": message, "channel": channel},
            message=message
        )

    async def _lookup_caller(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Look up caller in CRM with tenant isolation"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            search_conditions = []
            params: dict = {}

            if input_data.get("phone"):
                search_conditions.append("(phone LIKE :phone)")
                params["phone"] = f"%{input_data['phone'][-10:]}%"

            if input_data.get("email"):
                search_conditions.append("(email ILIKE :email)")
                params["email"] = input_data["email"]

            if input_data.get("name"):
                search_conditions.append("(first_name ILIKE :name OR last_name ILIKE :name)")
                params["name"] = f"%{input_data['name']}%"

            if not search_conditions:
                return ToolResult(success=False, error="No search criteria provided")

            # Tenant isolation
            org_id = self.context.get("organization_id")
            org_clause = ""
            if org_id:
                org_clause = "AND organization_id = :org_id"
                params["org_id"] = org_id

            query = text(f"""
                SELECT id, first_name, last_name, email, phone, stage, owner_id
                FROM leads
                WHERE ({' OR '.join(search_conditions)}) {org_clause}
                LIMIT 5
            """)

            results = db.execute(query, params).fetchall()

            matches = []
            for r in results:
                name = f"{r.first_name or ''} {r.last_name or ''}".strip()
                matches.append({
                    "id": r.id,
                    "name": name,
                    "email": r.email,
                    "phone": r.phone,
                    "stage": r.stage,
                    "type": "lead"
                })

            self.audit_log("caller_lookup", details={"matches": len(matches)})

            return ToolResult(
                success=True,
                data={"matches": matches, "count": len(matches)},
                message=f"Found {len(matches)} matching records"
            )

        except Exception as e:
            logger.exception("Error in lookup_caller")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _route_call(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Route call to appropriate destination"""
        intent = input_data["intent"]
        urgency = input_data.get("urgency", "normal")

        routing_map = {
            "new_loan": {"department": "Sales", "queue": "new_applications"},
            "status_check": {"department": "Processing", "queue": "status_inquiries"},
            "payment": {"department": "Servicing", "queue": "payments"},
            "support": {"department": "Support", "queue": "general"},
            "other": {"department": "Support", "queue": "general"}
        }

        route = routing_map.get(intent, routing_map["other"])

        if urgency == "urgent":
            route["priority"] = "high"

        return ToolResult(
            success=True,
            data={"route": route, "intent": intent, "urgency": urgency},
            message=f"Routing to {route['department']} - {route['queue']}"
        )

    async def _capture_lead_info(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Capture new lead information with tenant isolation"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")

            query = text("""
                INSERT INTO leads (
                    first_name, last_name, phone, email, loan_purpose,
                    notes, source, stage, organization_id, created_at
                )
                VALUES (
                    :first_name, :last_name, :phone, :email, :loan_purpose,
                    :notes, 'inbound_call', 'New', :org_id, CURRENT_TIMESTAMP
                )
                RETURNING id
            """)

            result = db.execute(query, {
                "first_name": input_data["first_name"],
                "last_name": input_data["last_name"],
                "phone": input_data["phone"],
                "email": input_data.get("email"),
                "loan_purpose": input_data.get("loan_purpose"),
                "notes": input_data.get("notes"),
                "org_id": org_id
            }).fetchone()

            db.commit()

            self.audit_log(
                "lead_captured",
                entity_type="lead",
                entity_id=str(result.id),
                details={"source": "inbound_call"}
            )

            return ToolResult(
                success=True,
                data={"lead_id": result.id, "name": f"{input_data['first_name']} {input_data['last_name']}"},
                message=f"Created new lead: {input_data['first_name']} {input_data['last_name']}"
            )

        except Exception as e:
            db.rollback()
            logger.exception("Error in capture_lead_info")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _schedule_callback(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Schedule a callback"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            query = text("""
                INSERT INTO tasks (title, description, task_type, entity_type, entity_id, due_date, assigned_to, status, created_at)
                VALUES (:title, :description, 'callback', 'lead', :contact_id, :due_date, :assign_to, 'pending', CURRENT_TIMESTAMP)
                RETURNING id
            """)

            result = db.execute(query, {
                "title": f"Callback: {input_data['phone']}",
                "description": f"Reason: {input_data['reason']}",
                "contact_id": input_data.get("contact_id"),
                "due_date": input_data.get("preferred_time"),
                "assign_to": input_data.get("assign_to")
            }).fetchone()

            db.commit()

            return ToolResult(
                success=True,
                data={"task_id": result.id, "phone": input_data["phone"]},
                message=f"Callback scheduled for {input_data['phone']}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _provide_loan_status(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Provide loan status to verified caller.

        SECURITY: Requires last_four_ssn for identity verification before
        disclosing ANY loan information (PII protection / GLBA compliance).
        """
        from database import SessionLocal
        from sqlalchemy import text

        # --- Identity verification gate ---
        last_four_ssn = input_data.get("last_four_ssn")
        if not last_four_ssn or len(str(last_four_ssn)) != 4:
            self.audit_log("loan_status_denied", details={"reason": "missing_identity_verification"})
            return ToolResult(
                success=False,
                error="identity_verification_required",
                message="For your security, I need the last 4 digits of the borrower's SSN to look up loan status."
            )

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            conditions = []
            params: dict = {}

            if org_id:
                conditions.append("l.organization_id = :org_id")
                params["org_id"] = org_id

            if input_data.get("loan_id"):
                conditions.append("l.id = :loan_id")
                params["loan_id"] = input_data["loan_id"]
            elif input_data.get("borrower_phone"):
                conditions.append("l.borrower_phone LIKE :phone")
                params["phone"] = f"%{input_data['borrower_phone'][-10:]}%"
            else:
                return ToolResult(success=False, error="No loan identifier provided")

            # Verify SSN match (last 4 stored on borrower profile or loan)
            conditions.append("RIGHT(COALESCE(l.borrower_ssn, ''), 4) = :ssn_last4")
            params["ssn_last4"] = str(last_four_ssn)

            where_sql = " AND ".join(conditions)

            query = text(f"""
                SELECT l.id, l.loan_number, l.stage, l.borrower_name, l.loan_amount, l.closing_date
                FROM loans l
                WHERE {where_sql}
                LIMIT 1
            """)

            result = db.execute(query, params).fetchone()

            if not result:
                self.audit_log("loan_status_denied", details={"reason": "no_match_or_ssn_mismatch"})
                return ToolResult(
                    success=False,
                    error="Unable to verify identity. Please check the information and try again."
                )

            status_messages = {
                "PROCESSING": "Your loan is currently being processed",
                "UNDERWRITING": "Your loan is in underwriting review",
                "APPROVED": "Great news! Your loan has been approved",
                "CLEAR_TO_CLOSE": "Your loan is cleared to close",
                "CTC": "Your loan is cleared to close",
                "FUNDED": "Your loan has been funded"
            }

            message = status_messages.get(result.stage, f"Your loan status is: {result.stage}")

            self.audit_log(
                "loan_status_provided",
                entity_type="loan",
                entity_id=str(result.id),
                details={"verified": True}
            )

            return ToolResult(
                success=True,
                data={
                    "loan_number": result.loan_number,
                    "status": result.stage,
                    "borrower": result.borrower_name,
                    "expected_close": result.closing_date.isoformat() if result.closing_date else None
                },
                message=message
            )

        except Exception as e:
            logger.exception("Error in provide_loan_status")
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _answer_faq(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Answer frequently asked questions"""
        question = input_data["question"].lower()

        faqs = {
            "rates": "Current rates vary based on loan type, credit score, and down payment. I can connect you with a loan officer for a personalized quote.",
            "process": "Our mortgage process typically takes 30-45 days from application to closing. We'll guide you through each step.",
            "requirements": "Basic requirements include proof of income, assets, employment verification, and credit check. Specific requirements depend on loan type.",
            "timeline": "After application, you'll receive your Loan Estimate within 3 days. We aim to close within 30-45 days.",
            "down_payment": "Down payment requirements vary: Conventional loans typically require 3-20%, FHA requires 3.5%, and VA/USDA may require 0% down.",
            "credit_score": "Minimum credit scores vary by loan type: Conventional typically 620+, FHA 580+, VA has no minimum but lenders typically require 620+"
        }

        for keyword, answer in faqs.items():
            if keyword in question:
                return ToolResult(
                    success=True,
                    data={"category": keyword, "answer": answer},
                    message=answer
                )

        return ToolResult(
            success=True,
            data={"answer": "I'd be happy to connect you with a loan officer who can answer that question in detail."},
            message="Let me connect you with a specialist who can help with that question."
        )

    async def _escalate_to_human(self, input_data: Dict[str, Any], context: AgentContext) -> ToolResult:
        """Escalate call to human agent"""
        department = input_data.get("preferred_department", "support")
        urgency = input_data.get("urgency", "normal")

        return ToolResult(
            success=True,
            data={
                "escalated": True,
                "department": department,
                "urgency": urgency,
                "reason": input_data["reason"],
                "caller_info": input_data.get("caller_info")
            },
            message=f"Transferring to {department} team"
        )
