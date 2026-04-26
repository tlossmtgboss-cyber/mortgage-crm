"""
================================================================================
PERENNIA AI - TOOL EXECUTOR
================================================================================
Connects the AI Receptionist to the 160+ Perennia AI tools.

Maps receptionist actions to CRM operations:
- Customer lookup
- Appointment scheduling
- Loan status queries
- Lead qualification
- Callback requests

================================================================================
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL RESULT WRAPPER
# =============================================================================

@dataclass
class ToolExecutionResult:
    """Standardized result from tool execution."""

    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: Optional[str] = None
    tool_name: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "tool_name": self.tool_name,
        }

    @classmethod
    def ok(cls, data: Dict[str, Any], message: str = "") -> "ToolExecutionResult":
        return cls(success=True, data=data, message=message)

    @classmethod
    def fail(cls, error: str, message: str = "") -> "ToolExecutionResult":
        return cls(success=False, error=error, message=message or error)


# =============================================================================
# TOOL EXECUTOR
# =============================================================================

class ReceptionistToolExecutor:
    """
    Executes tools on behalf of the AI receptionist.

    Maps receptionist actions to our 160 Perennia tools.

    Usage:
        executor = ReceptionistToolExecutor(tool_registry=registry)

        # Execute a tool
        result = await executor.execute("lookup_caller", phone_number="+15551234567")

        # Get available tools
        tools = executor.get_available_tools()
    """

    # Tool definitions for LLM function calling
    TOOL_DEFINITIONS = [
        {
            "name": "lookup_caller",
            "description": "Look up caller information in the CRM by phone number",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Caller's phone number in E.164 format",
                    },
                },
                "required": ["phone_number"],
            },
        },
        {
            "name": "get_lo_availability",
            "description": "Get a loan officer's available appointment slots",
            "parameters": {
                "type": "object",
                "properties": {
                    "lo_id": {
                        "type": "string",
                        "description": "Loan officer ID (optional)",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date to check (YYYY-MM-DD format)",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "book_appointment",
            "description": "Book an appointment with a loan officer",
            "parameters": {
                "type": "object",
                "properties": {
                    "lo_id": {
                        "type": "string",
                        "description": "Loan officer ID",
                    },
                    "caller_name": {
                        "type": "string",
                        "description": "Caller's full name",
                    },
                    "caller_phone": {
                        "type": "string",
                        "description": "Caller's phone number",
                    },
                    "datetime_str": {
                        "type": "string",
                        "description": "Appointment date/time (ISO format)",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Purpose of the appointment",
                    },
                    "caller_email": {
                        "type": "string",
                        "description": "Caller's email (optional)",
                    },
                },
                "required": ["lo_id", "caller_name", "caller_phone", "datetime_str"],
            },
        },
        {
            "name": "create_callback_request",
            "description": "Create a callback request for the team to follow up",
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_name": {
                        "type": "string",
                        "description": "Caller's name",
                    },
                    "caller_phone": {
                        "type": "string",
                        "description": "Caller's phone number",
                    },
                    "lo_id": {
                        "type": "string",
                        "description": "Specific LO to call back (optional)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for callback",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "normal", "high", "urgent"],
                        "description": "Urgency level",
                    },
                    "best_time": {
                        "type": "string",
                        "description": "Best time to call back",
                    },
                },
                "required": ["caller_name", "caller_phone"],
            },
        },
        {
            "name": "get_loan_status",
            "description": "Get the status of an existing loan with verification",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_number": {
                        "type": "string",
                        "description": "Loan number",
                    },
                    "borrower_last_name": {
                        "type": "string",
                        "description": "Borrower's last name for verification",
                    },
                    "ssn_last_four": {
                        "type": "string",
                        "description": "Last 4 of SSN for additional verification",
                    },
                },
                "required": ["loan_number", "borrower_last_name"],
            },
        },
        {
            "name": "transfer_call",
            "description": "Transfer the call to a specific person or team",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Target user ID or team",
                    },
                    "transfer_type": {
                        "type": "string",
                        "enum": ["warm", "cold"],
                        "description": "Type of transfer",
                    },
                    "context": {
                        "type": "string",
                        "description": "Context to relay to the recipient",
                    },
                },
                "required": ["target_id"],
            },
        },
        {
            "name": "leave_message",
            "description": "Leave a message for a loan officer",
            "parameters": {
                "type": "object",
                "properties": {
                    "lo_id": {
                        "type": "string",
                        "description": "Loan officer ID",
                    },
                    "caller_name": {
                        "type": "string",
                        "description": "Caller's name",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message content",
                    },
                    "caller_phone": {
                        "type": "string",
                        "description": "Callback number",
                    },
                    "urgent": {
                        "type": "boolean",
                        "description": "Whether the message is urgent",
                    },
                },
                "required": ["lo_id", "caller_name", "message"],
            },
        },
        {
            "name": "get_current_rates",
            "description": "Get current mortgage rate information",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_type": {
                        "type": "string",
                        "enum": ["conventional", "fha", "va", "usda", "jumbo"],
                        "description": "Type of loan",
                    },
                    "loan_amount": {
                        "type": "number",
                        "description": "Estimated loan amount",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "find_available_lo",
            "description": "Find an available loan officer to help the caller",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {
                        "type": "string",
                        "description": "Loan specialty needed (e.g., 'VA', 'jumbo')",
                    },
                    "language": {
                        "type": "string",
                        "description": "Preferred language",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "qualify_lead",
            "description": "Quick lead qualification based on call information",
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_phone": {
                        "type": "string",
                        "description": "Caller's phone number",
                    },
                    "purpose": {
                        "type": "string",
                        "enum": ["purchase", "refinance", "cash_out", "heloc"],
                        "description": "Loan purpose",
                    },
                    "property_type": {
                        "type": "string",
                        "description": "Property type",
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Expected timeframe",
                    },
                },
                "required": ["caller_phone"],
            },
        },
    ]

    def __init__(
        self,
        tool_registry: Any = None,
        db_session_factory: Callable = None,
    ):
        """
        Args:
            tool_registry: The Perennia tool registry from agents/tools
            db_session_factory: Factory function to create DB sessions
        """
        self.tool_registry = tool_registry
        self.db_session_factory = db_session_factory
        self._execution_count = 0
        self._total_execution_time = 0.0

    async def execute(
        self,
        tool_name: str,
        **kwargs,
    ) -> Union[Dict[str, Any], ToolExecutionResult]:
        """
        Execute a tool and return results.

        Handles the mapping from receptionist tool names to actual Perennia tools.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool parameters

        Returns:
            ToolExecutionResult or dict with results
        """
        import time
        start_time = time.time()

        # Map receptionist tools to handler methods
        tool_handlers = {
            "lookup_caller": self._lookup_caller,
            "get_lo_availability": self._get_lo_availability,
            "book_appointment": self._book_appointment,
            "create_callback_request": self._create_callback_request,
            "get_loan_status": self._get_loan_status,
            "transfer_call": self._transfer_call,
            "leave_message": self._leave_message,
            "get_current_rates": self._get_current_rates,
            "find_available_lo": self._find_available_lo,
            "qualify_lead": self._qualify_lead,
        }

        handler = tool_handlers.get(tool_name)

        try:
            if handler:
                result = await handler(**kwargs)
            elif self.tool_registry:
                # Try to execute directly from registry
                result = await self._execute_registry_tool(tool_name, kwargs)
            else:
                result = ToolExecutionResult.fail(f"Unknown tool: {tool_name}")

            # Track metrics
            execution_time = (time.time() - start_time) * 1000
            self._execution_count += 1
            self._total_execution_time += execution_time

            if isinstance(result, ToolExecutionResult):
                result.tool_name = tool_name
                result.execution_time_ms = execution_time

            logger.debug(f"Tool {tool_name} executed in {execution_time:.1f}ms")
            return result

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return ToolExecutionResult.fail(str(e))

    async def _execute_registry_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute a tool from the Perennia registry."""
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return ToolExecutionResult.fail(f"Tool not found: {tool_name}")

        try:
            result = tool(**params)

            # Handle ToolResult from the registry
            if hasattr(result, 'to_dict'):
                data = result.to_dict()
                return ToolExecutionResult(
                    success=data.get("status") == "success",
                    data=data.get("data", {}),
                    message=data.get("message", ""),
                    error=data.get("error"),
                )

            return ToolExecutionResult.ok(
                data=result if isinstance(result, dict) else {"result": result}
            )

        except Exception as e:
            return ToolExecutionResult.fail(str(e))

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get tool definitions for LLM function calling."""
        return self.TOOL_DEFINITIONS

    def get_metrics(self) -> Dict[str, Any]:
        """Get execution metrics."""
        return {
            "total_executions": self._execution_count,
            "total_time_ms": self._total_execution_time,
            "avg_time_ms": (
                self._total_execution_time / self._execution_count
                if self._execution_count > 0 else 0
            ),
        }

    # =========================================================================
    # Tool Implementations
    # =========================================================================

    async def _lookup_caller(self, phone_number: str) -> ToolExecutionResult:
        """Look up caller in CRM by phone number."""
        # Try Perennia tool first
        if self.tool_registry:
            tool = self.tool_registry.get("get_customer_360")
            if tool:
                try:
                    result = tool(phone=phone_number)
                    if hasattr(result, 'status') and result.status == "success":
                        data = result.data
                        return ToolExecutionResult.ok({
                            "found": True,
                            "contact_id": data.get("contact_id"),
                            "first_name": data.get("first_name"),
                            "last_name": data.get("last_name"),
                            "email": data.get("email"),
                            "is_customer": data.get("is_customer", False),
                            "loan_ids": data.get("active_loans", []),
                            "assigned_lo_id": data.get("assigned_lo_id"),
                            "assigned_lo_name": data.get("assigned_lo_name"),
                        })
                except Exception as e:
                    logger.debug(f"Tool lookup failed: {e}")

        # Fallback: direct database lookup
        try:
            from agents.tools.base import execute_single, execute_query

            result = execute_single("""
                SELECT
                    c.id, c.first_name, c.last_name, c.email,
                    c.assigned_to, COALESCE(es.full_name, u.email) as assigned_lo_name,
                    EXISTS(SELECT 1 FROM loans l WHERE l.borrower_id = c.id) as is_customer
                FROM contacts c
                LEFT JOIN users u ON u.id = c.assigned_to
                LEFT JOIN email_signatures es ON es.user_id = u.id
                WHERE c.phone = :phone OR c.mobile = :phone
                LIMIT 1
            """, {"phone": phone_number})

            if result:
                loans = execute_query("""
                    SELECT id FROM loans
                    WHERE borrower_id = :contact_id
                    AND status NOT IN ('funded', 'cancelled', 'denied')
                """, {"contact_id": result["id"]})

                return ToolExecutionResult.ok({
                    "found": True,
                    "contact_id": result["id"],
                    "first_name": result["first_name"],
                    "last_name": result["last_name"],
                    "email": result["email"],
                    "is_customer": result["is_customer"],
                    "loan_ids": [l["id"] for l in loans],
                    "assigned_lo_id": result["assigned_to"],
                    "assigned_lo_name": result["assigned_lo_name"],
                })

        except Exception as e:
            logger.debug(f"Database lookup failed: {e}")

        return ToolExecutionResult.ok(
            {"found": False},
            message="Caller not found in system",
        )

    async def _get_lo_availability(
        self,
        lo_id: Optional[str] = None,
        date: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Get loan officer availability."""
        if self.tool_registry:
            tool = self.tool_registry.get("get_availability")
            if tool:
                try:
                    result = tool(user_id=lo_id, date=date)
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "lo_id": lo_id,
                            "available_slots": result.data.get("slots", []),
                            "next_available": result.data.get("next_available"),
                        })
                except Exception as e:
                    logger.debug(f"Availability lookup failed: {e}")

        # Generate mock availability
        target_date = (
            datetime.strptime(date, "%Y-%m-%d")
            if date else datetime.now()
        )

        # Skip weekends
        while target_date.weekday() >= 5:
            target_date += timedelta(days=1)

        slots = []
        for hour in [9, 10, 11, 13, 14, 15, 16]:
            slot_time = target_date.replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            if slot_time > datetime.now():
                slots.append({
                    "time": slot_time.isoformat(),
                    "display": slot_time.strftime("%I:%M %p"),
                    "available": True,
                })

        return ToolExecutionResult.ok({
            "lo_id": lo_id,
            "date": target_date.strftime("%Y-%m-%d"),
            "available_slots": slots,
            "next_available": slots[0]["time"] if slots else None,
        })

    async def _book_appointment(
        self,
        lo_id: str,
        caller_name: str,
        caller_phone: str,
        datetime_str: str,
        purpose: Optional[str] = None,
        caller_email: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Book an appointment."""
        if self.tool_registry:
            tool = self.tool_registry.get("book_appointment")
            if tool:
                try:
                    result = tool(
                        user_id=lo_id,
                        contact_name=caller_name,
                        contact_phone=caller_phone,
                        contact_email=caller_email,
                        start_time=datetime_str,
                        title=purpose or "Phone Consultation",
                        duration=30,
                    )
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "appointment_id": result.data.get("appointment_id"),
                            "datetime": datetime_str,
                            "confirmation": f"Your appointment is confirmed for {datetime_str}",
                        })
                except Exception as e:
                    logger.debug(f"Booking failed: {e}")

        # Mock confirmation
        appointment_id = str(uuid.uuid4())[:8].upper()

        return ToolExecutionResult.ok({
            "appointment_id": appointment_id,
            "datetime": datetime_str,
            "lo_id": lo_id,
            "caller_name": caller_name,
            "confirmation": f"Appointment scheduled for {datetime_str}",
        })

    async def _create_callback_request(
        self,
        caller_name: str,
        caller_phone: str,
        lo_id: Optional[str] = None,
        reason: Optional[str] = None,
        urgency: str = "normal",
        best_time: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Create callback request."""
        if self.tool_registry:
            tool = self.tool_registry.get("schedule_callback")
            if tool:
                try:
                    result = tool(
                        contact_name=caller_name,
                        contact_phone=caller_phone,
                        assigned_to=lo_id,
                        notes=reason,
                        priority=urgency,
                        preferred_time=best_time,
                    )
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "callback_id": result.data.get("callback_id"),
                            "message": "Callback request created",
                        })
                except Exception as e:
                    logger.debug(f"Callback creation failed: {e}")

        callback_id = str(uuid.uuid4())[:8].upper()
        eta = "as soon as possible" if urgency in ["high", "urgent"] else "within 24 hours"

        return ToolExecutionResult.ok({
            "callback_id": callback_id,
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "urgency": urgency,
            "message": f"We'll call you back {eta}",
        })

    async def _get_loan_status(
        self,
        loan_number: str,
        borrower_last_name: str,
        ssn_last_four: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Get loan status with verification."""
        if self.tool_registry:
            tool = self.tool_registry.get("get_loans_by_status")
            if tool:
                try:
                    result = tool(loan_number=loan_number)
                    if hasattr(result, 'status') and result.status == "success":
                        loan = result.data.get("loan", {})

                        # Verify name matches
                        if borrower_last_name.lower() not in loan.get("borrower_name", "").lower():
                            return ToolExecutionResult.fail(
                                "verification_failed",
                                message="I couldn't verify your information.",
                            )

                        return ToolExecutionResult.ok({
                            "loan_number": loan_number,
                            "status": loan.get("status"),
                            "status_display": self._format_loan_status(loan.get("status")),
                            "next_steps": loan.get("next_steps"),
                            "expected_close": loan.get("expected_close_date"),
                        })
                except Exception as e:
                    logger.debug(f"Loan lookup failed: {e}")

        # Fallback for demo
        return ToolExecutionResult.ok({
            "loan_number": loan_number,
            "status": "processing",
            "status_display": "Your loan is currently being processed",
            "next_steps": "We're waiting on the appraisal to come back",
            "expected_close": "Within the next 2-3 weeks",
        })

    async def _transfer_call(
        self,
        target_id: str,
        transfer_type: str = "warm",
        context: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Set up call transfer."""
        if self.tool_registry:
            tool = self.tool_registry.get("get_lo_availability")
            if tool:
                try:
                    result = tool(user_id=target_id)
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "target_id": target_id,
                            "target_name": result.data.get("user_name"),
                            "target_phone": result.data.get("phone"),
                            "is_available": result.data.get("is_available", False),
                            "transfer_type": transfer_type,
                        })
                except Exception as e:
                    logger.debug(f"Transfer lookup failed: {e}")

        return ToolExecutionResult.ok({
            "target_id": target_id,
            "transfer_type": transfer_type,
            "context": context,
            "ready": True,
        })

    async def _leave_message(
        self,
        lo_id: str,
        caller_name: str,
        message: str,
        caller_phone: Optional[str] = None,
        urgent: bool = False,
    ) -> ToolExecutionResult:
        """Leave a message for loan officer."""
        if self.tool_registry:
            tool = self.tool_registry.get("create_task")
            if tool:
                try:
                    result = tool(
                        assigned_to=lo_id,
                        title=f"Message from {caller_name}",
                        description=message,
                        priority="high" if urgent else "normal",
                        category="callback",
                        metadata={"caller_phone": caller_phone},
                    )
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "message_id": result.data.get("task_id"),
                            "confirmation": "Your message has been delivered",
                        })
                except Exception as e:
                    logger.debug(f"Message creation failed: {e}")

        message_id = str(uuid.uuid4())[:8].upper()

        return ToolExecutionResult.ok({
            "message_id": message_id,
            "lo_id": lo_id,
            "confirmation": "I'll make sure they get your message",
        })

    async def _get_current_rates(
        self,
        loan_type: str = "conventional",
        loan_amount: Optional[float] = None,
    ) -> ToolExecutionResult:
        """Get current rate information."""
        if self.tool_registry:
            tool = self.tool_registry.get("get_current_rates")
            if tool:
                try:
                    result = tool(loan_type=loan_type)
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "rates": result.data.get("rates", []),
                            "as_of": result.data.get("as_of"),
                        })
                except Exception as e:
                    logger.debug(f"Rate lookup failed: {e}")

        # Safe fallback - don't quote specific rates
        return ToolExecutionResult.ok({
            "message": (
                "For the most accurate rate quote, I'd recommend speaking "
                "with one of our loan officers who can look at your specific situation."
            ),
            "general_info": (
                "Rates are changing frequently, but we're seeing competitive "
                "rates across all loan programs."
            ),
            "recommendation": "schedule_consultation",
        })

    async def _find_available_lo(
        self,
        specialty: Optional[str] = None,
        language: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Find an available loan officer."""
        if self.tool_registry:
            tool = self.tool_registry.get("get_lo_pipeline_breakdown")
            if tool:
                try:
                    result = tool()
                    if hasattr(result, 'status') and result.status == "success":
                        los = result.data.get("breakdown", [])
                        if los:
                            return ToolExecutionResult.ok({
                                "lo_id": los[0].get("lo_id"),
                                "lo_name": los[0].get("lo_name"),
                                "is_available": True,
                            })
                except Exception as e:
                    logger.debug(f"LO lookup failed: {e}")

        return ToolExecutionResult.ok({
            "lo_id": "default",
            "lo_name": "the next available loan officer",
            "is_available": True,
        })

    async def _qualify_lead(
        self,
        caller_phone: str,
        purpose: Optional[str] = None,
        property_type: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> ToolExecutionResult:
        """Quick lead qualification."""
        if self.tool_registry:
            tool = self.tool_registry.get("score_lead")
            if tool:
                try:
                    result = tool(
                        phone=caller_phone,
                        loan_purpose=purpose,
                        property_type=property_type,
                        timeframe=timeframe,
                    )
                    if hasattr(result, 'status') and result.status == "success":
                        return ToolExecutionResult.ok({
                            "score": result.data.get("score"),
                            "priority": result.data.get("priority"),
                            "recommended_action": result.data.get("recommended_action"),
                        })
                except Exception as e:
                    logger.debug(f"Lead scoring failed: {e}")

        # Simple qualification based on purpose
        priority = "high" if purpose in ["purchase", "refinance"] else "normal"

        return ToolExecutionResult.ok({
            "priority": priority,
            "recommended_action": "schedule_callback",
        })

    # =========================================================================
    # Helpers
    # =========================================================================

    def _format_loan_status(self, status: str) -> str:
        """Format loan status for spoken output."""
        status_messages = {
            "lead": "We've received your inquiry",
            "application": "Your application has been received and is being reviewed",
            "processing": "Your loan is currently being processed",
            "submitted": "Your loan has been submitted to underwriting",
            "underwriting": "Your loan is being reviewed by our underwriting team",
            "approved": "Great news! Your loan has been approved",
            "clear_to_close": "Your loan is clear to close",
            "docs_out": "Closing documents have been sent out",
            "docs_back": "We've received your signed documents",
            "funded": "Congratulations! Your loan has funded",
            "cancelled": "This loan file has been cancelled",
            "denied": "Unfortunately, this loan was not approved",
        }
        return status_messages.get(status, f"Your loan status is: {status}")


# =============================================================================
# COMPLETE RECEPTIONIST SYSTEM
# =============================================================================

class AIReceptionist:
    """
    Complete AI Receptionist system.

    Integrates all components:
    - Audio Processing (STT/TTS)
    - Call Handling (Telnyx)
    - Tool Execution (CRM operations)

    Usage:
        receptionist = AIReceptionist.create(
            company_name="The Tim Loss Team",
        )

        # Handle incoming call
        greeting = await receptionist.handle_incoming_call(
            call_sid="CA123",
            from_number="+15551234567"
        )

        # Process speech
        response = await receptionist.process_speech(
            call_sid="CA123",
            speech_text="I'd like to schedule an appointment"
        )
    """

    def __init__(
        self,
        audio_processor: Any,
        call_handler: Any,
        tool_executor: ReceptionistToolExecutor,
        config: Dict[str, Any] = None,
    ):
        self.audio = audio_processor
        self.call_handler = call_handler
        self.tools = tool_executor
        self.config = config or {}

        self._active_calls: Dict[str, Dict] = {}

    @classmethod
    def create(
        cls,
        company_name: str = "The Tim Loss Team",
        receptionist_name: str = "Aria",
        tool_registry: Any = None,
        stt_provider: str = "deepgram",
        tts_provider: str = "elevenlabs",
    ) -> "AIReceptionist":
        """Factory method to create a complete receptionist system."""
        from .audio_processor import AudioProcessor, STTConfig, TTSConfig
        from .call_handler import TelnyxStreamHandler

        # Create tool executor
        tool_executor = ReceptionistToolExecutor(tool_registry=tool_registry)

        # Create audio processor
        stt_config = STTConfig(provider=stt_provider)
        tts_config = TTSConfig(provider=tts_provider)
        audio = AudioProcessor(stt_config=stt_config, tts_config=tts_config)

        # Create call handler
        call_handler = TelnyxStreamHandler(audio)

        config = {
            "company_name": company_name,
            "receptionist_name": receptionist_name,
        }

        return cls(
            audio_processor=audio,
            call_handler=call_handler,
            tool_executor=tool_executor,
            config=config,
        )

    async def handle_incoming_call(
        self,
        call_sid: str,
        from_number: str,
        caller_name: Optional[str] = None,
    ) -> str:
        """Handle a new incoming call."""
        # Look up caller
        caller_info = await self.tools.execute(
            "lookup_caller",
            phone_number=from_number,
        )

        # Store call state
        self._active_calls[call_sid] = {
            "from_number": from_number,
            "caller_info": caller_info.data if hasattr(caller_info, 'data') else caller_info,
            "started_at": datetime.now(timezone.utc),
            "messages": [],
        }

        # Generate greeting
        name = self.config.get("receptionist_name", "Aria")
        company = self.config.get("company_name", "The Tim Loss Team")

        if caller_info and caller_info.data.get("found"):
            first_name = caller_info.data.get("first_name", "")
            greeting = (
                f"Hi {first_name}, this is {name} with {company}. "
                "How can I help you today?"
            )
        else:
            greeting = (
                f"Hi, this is {name} with {company}. "
                "How can I help you today?"
            )

        return greeting

    async def process_speech(
        self,
        call_sid: str,
        speech_text: str,
    ) -> str:
        """Process speech input and generate response."""
        call_state = self._active_calls.get(call_sid, {})

        # Add to history
        call_state.setdefault("messages", []).append({
            "role": "user",
            "content": speech_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Simple response logic (would integrate with LLM in production)
        response = await self._generate_response(speech_text, call_state)

        # Add response to history
        call_state["messages"].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return response

    async def process_audio(
        self,
        call_sid: str,
        audio_data: bytes,
    ) -> Optional[bytes]:
        """Process raw audio and return audio response."""
        # Transcribe
        text = await self.audio.transcribe_audio(audio_data)

        if not text or not text.strip():
            return None

        # Get response
        response_text = await self.process_speech(call_sid, text)

        # Synthesize
        return await self.audio.synthesize_for_telephony(response_text)

    async def end_call(
        self,
        call_sid: str,
        reason: str = "completed",
    ) -> Dict[str, Any]:
        """End call and return summary."""
        call_state = self._active_calls.pop(call_sid, {})

        started_at = call_state.get("started_at", datetime.now(timezone.utc))
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()

        return {
            "call_sid": call_sid,
            "duration_seconds": int(duration),
            "messages": call_state.get("messages", []),
            "caller_info": call_state.get("caller_info", {}),
            "reason": reason,
        }

    async def _generate_response(
        self,
        speech_text: str,
        call_state: Dict,
    ) -> str:
        """Generate response to user speech."""
        text_lower = speech_text.lower()

        # Appointment scheduling
        if any(word in text_lower for word in ["appointment", "schedule", "meet"]):
            result = await self.tools.execute("get_lo_availability")
            slots = result.data.get("available_slots", []) if hasattr(result, 'data') else []

            if slots:
                next_slot = slots[0].get("display", "tomorrow")
                return (
                    f"I'd be happy to help you schedule an appointment. "
                    f"Our next available time is {next_slot}. Would that work for you?"
                )
            return "I'd be happy to help you schedule an appointment. What day works best for you?"

        # Rate inquiry
        if any(word in text_lower for word in ["rate", "rates", "interest"]):
            result = await self.tools.execute("get_current_rates")
            message = result.data.get("message", "") if hasattr(result, 'data') else ""

            return (
                message or
                "Great question about rates! For the most accurate quote based on your "
                "situation, I'd recommend speaking with one of our loan officers. "
                "Would you like me to schedule a call?"
            )

        # Loan status
        if any(word in text_lower for word in ["status", "loan", "where", "progress"]):
            return (
                "I can help you check on your loan status. "
                "Could you please provide your loan number?"
            )

        # Refinance
        if any(word in text_lower for word in ["refinance", "refi"]):
            return (
                "I'd be happy to help you explore refinancing options. "
                "Do you know your current interest rate and approximate loan balance?"
            )

        # Transfer request
        if any(word in text_lower for word in ["human", "person", "agent", "transfer", "speak"]):
            return (
                "Of course, let me transfer you to one of our loan officers. "
                "Please hold for just a moment."
            )

        # Goodbye
        if any(word in text_lower for word in ["bye", "goodbye", "thank"]):
            return (
                "Thank you for calling! Have a great day, and don't hesitate "
                "to call back if you have any questions."
            )

        # Default
        return (
            "I understand. Could you tell me a bit more about what you're looking for? "
            "Are you interested in purchasing a home, refinancing, or something else?"
        )

    async def close(self) -> None:
        """Clean up resources."""
        if hasattr(self.audio, 'close'):
            await self.audio.close()


# =============================================================================
# TESTING UTILITIES
# =============================================================================

class ReceptionistTester:
    """Test the receptionist without actual phone calls."""

    def __init__(self, receptionist: Optional[AIReceptionist] = None):
        self.receptionist = receptionist
        self.call_sid = f"TEST-{uuid.uuid4().hex[:8].upper()}"

    async def _ensure_receptionist(self):
        """Create receptionist if not provided."""
        if self.receptionist is None:
            self.receptionist = AIReceptionist.create()

    async def simulate_call(
        self,
        caller_phone: str = "+15551234567",
    ) -> str:
        """Simulate an incoming call."""
        await self._ensure_receptionist()

        print("\n" + "=" * 60)
        print("INCOMING CALL SIMULATION")
        print("=" * 60)

        greeting = await self.receptionist.handle_incoming_call(
            call_sid=self.call_sid,
            from_number=caller_phone,
        )

        name = self.receptionist.config.get("receptionist_name", "AI")
        print(f"\n{name}: {greeting}\n")

        return greeting

    async def say(self, text: str) -> str:
        """Simulate caller speaking."""
        await self._ensure_receptionist()

        print(f"Caller: {text}")

        response = await self.receptionist.process_speech(
            call_sid=self.call_sid,
            speech_text=text,
        )

        name = self.receptionist.config.get("receptionist_name", "AI")
        print(f"{name}: {response}\n")

        return response

    async def end(self) -> Dict[str, Any]:
        """End the simulated call."""
        await self._ensure_receptionist()

        summary = await self.receptionist.end_call(self.call_sid)

        print("=" * 60)
        print("CALL ENDED")
        print("=" * 60)
        print(f"Duration: {summary.get('duration_seconds', 0)} seconds")
        print(f"Messages: {len(summary.get('messages', []))}")

        return summary

    async def run_scenario(self, messages: List[str]) -> Dict[str, Any]:
        """Run a complete call scenario."""
        await self.simulate_call()

        for message in messages:
            await self.say(message)

        return await self.end()


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_receptionist(
    company_name: str = "The Tim Loss Team",
    **kwargs,
) -> AIReceptionist:
    """Quick way to create a receptionist."""
    return AIReceptionist.create(company_name=company_name, **kwargs)


def create_tool_executor(
    tool_registry: Any = None,
) -> ReceptionistToolExecutor:
    """Create a standalone tool executor."""
    return ReceptionistToolExecutor(tool_registry=tool_registry)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

async def _run_demo():
    """Run interactive demo."""
    tester = ReceptionistTester()

    await tester.run_scenario([
        "Hi, I'd like to schedule an appointment with a loan officer",
        "I'm looking to refinance my home",
        "How about tomorrow afternoon?",
        "Yes, that works. My name is John Smith",
        "Perfect, thank you!",
    ])


if __name__ == "__main__":
    import asyncio
    asyncio.run(_run_demo())
