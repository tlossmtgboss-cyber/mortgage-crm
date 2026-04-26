"""
AI Receptionist Tool Integration
================================
Connects the AI Receptionist to the centralized 160-tool registry
for seamless access to CRM, scheduling, and communication tools.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from backend.agents.tools import (
    tool_registry,
    execute_tool,
    RECEPTIONIST_TOOLS,
    SCHEDULER_TOOLS,
    LEAD_TOOLS,
)

logger = logging.getLogger(__name__)


class AIReceptionist:
    """
    AI Receptionist with access to the full tool registry.

    Connects voice/SMS interactions to CRM tools for:
    - Lead qualification and routing
    - Appointment scheduling
    - Call handling and logging
    - LO availability lookup
    """

    def __init__(
        self,
        company_name: str,
        tool_registry: Any,
        default_lo_id: Optional[str] = None,
    ):
        self.company_name = company_name
        self.tool_registry = tool_registry
        self.default_lo_id = default_lo_id

        # Tools available to receptionist
        self.available_tools = (
            RECEPTIONIST_TOOLS +
            SCHEDULER_TOOLS[:4] +  # get_availability, book_appointment, reschedule, cancel
            LEAD_TOOLS[:3]  # get_lead_details, get_engagement_history, score_lead
        )

        logger.info(f"AI Receptionist initialized with {len(self.available_tools)} tools")

    @classmethod
    def create(
        cls,
        company_name: str,
        tool_registry: Any,
        default_lo_id: Optional[str] = None,
    ) -> "AIReceptionist":
        """Factory method to create an AIReceptionist instance."""
        return cls(
            company_name=company_name,
            tool_registry=tool_registry,
            default_lo_id=default_lo_id,
        )

    # =========================================================================
    # Call Handling Tools
    # =========================================================================

    def get_greeting(self, caller_phone: Optional[str] = None) -> Dict[str, Any]:
        """Get appropriate greeting script based on caller."""
        result = execute_tool(
            "get_greeting_script",
            caller_phone=caller_phone,
            company_name=self.company_name,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def qualify_caller(
        self,
        caller_phone: str,
        intent: str,
        loan_purpose: Optional[str] = None,
        property_type: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Qualify a caller based on their stated needs."""
        result = execute_tool(
            "qualify_caller",
            caller_phone=caller_phone,
            intent=intent,
            loan_purpose=loan_purpose,
            property_type=property_type,
            timeframe=timeframe,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def route_call(
        self,
        caller_phone: str,
        intent: str,
        urgency: str = "normal",
        preferred_lo_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route call to appropriate LO or department."""
        result = execute_tool(
            "route_call",
            caller_phone=caller_phone,
            intent=intent,
            urgency=urgency,
            preferred_lo_id=preferred_lo_id or self.default_lo_id,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def handle_inbound_call(
        self,
        call_sid: str,
        caller_phone: str,
        called_number: str,
    ) -> Dict[str, Any]:
        """Handle an inbound call with full context."""
        result = execute_tool(
            "handle_inbound_call",
            call_sid=call_sid,
            caller_phone=caller_phone,
            called_number=called_number,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def log_call_interaction(
        self,
        call_sid: str,
        caller_phone: str,
        interaction_type: str,
        notes: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a call interaction to the CRM."""
        result = execute_tool(
            "log_call_interaction",
            call_sid=call_sid,
            caller_phone=caller_phone,
            interaction_type=interaction_type,
            notes=notes,
            outcome=outcome,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    # =========================================================================
    # Scheduling Tools
    # =========================================================================

    def check_lo_availability(
        self,
        lo_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check LO availability for appointments."""
        result = execute_tool(
            "get_lo_availability",
            lo_id=lo_id or self.default_lo_id,
            date_from=date_from,
            date_to=date_to,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def get_available_slots(
        self,
        user_id: Optional[str] = None,
        duration_minutes: int = 30,
        meeting_type: str = "consultation",
    ) -> Dict[str, Any]:
        """Get available appointment slots."""
        result = execute_tool(
            "get_availability",
            user_id=user_id or self.default_lo_id,
            duration_minutes=duration_minutes,
            meeting_type=meeting_type,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def book_appointment(
        self,
        contact_id: str,
        datetime_str: str,
        appointment_type: str = "consultation",
        contact_type: str = "lead",
        duration_minutes: int = 30,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Book an appointment for a caller."""
        result = execute_tool(
            "book_appointment",
            contact_id=contact_id,
            datetime_str=datetime_str,
            appointment_type=appointment_type,
            contact_type=contact_type,
            duration_minutes=duration_minutes,
            user_id=self.default_lo_id,
            notes=notes,
            send_confirmation=True,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def create_callback_request(
        self,
        caller_phone: str,
        caller_name: Optional[str] = None,
        preferred_time: Optional[str] = None,
        reason: Optional[str] = None,
        urgency: str = "normal",
    ) -> Dict[str, Any]:
        """Create a callback request when LO is unavailable."""
        result = execute_tool(
            "create_callback_request",
            caller_phone=caller_phone,
            caller_name=caller_name,
            preferred_time=preferred_time,
            reason=reason,
            urgency=urgency,
            assigned_to=self.default_lo_id,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    # =========================================================================
    # Lead Management Tools
    # =========================================================================

    def lookup_caller(self, phone: str) -> Dict[str, Any]:
        """Look up caller in CRM by phone number."""
        # First check if they're an existing lead
        result = execute_tool(
            "get_lead_details",
            phone=phone,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def get_caller_history(self, lead_id: str) -> Dict[str, Any]:
        """Get engagement history for a known caller."""
        result = execute_tool(
            "get_engagement_history",
            lead_id=lead_id,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    def score_caller(self, lead_id: str) -> Dict[str, Any]:
        """Score a caller/lead based on their profile and engagement."""
        result = execute_tool(
            "score_lead",
            lead_id=lead_id,
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    # =========================================================================
    # Queue Management
    # =========================================================================

    def get_call_queue_status(self) -> Dict[str, Any]:
        """Get current call queue status."""
        result = execute_tool(
            "get_call_queue_status",
        )
        return result.to_dict() if hasattr(result, 'to_dict') else result

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_available_tools(self) -> List[str]:
        """Get list of tools available to this receptionist."""
        return self.available_tools

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute any available tool by name."""
        if tool_name not in self.available_tools:
            return {
                "status": "error",
                "error": f"Tool '{tool_name}' not available to receptionist",
                "available_tools": self.available_tools,
            }

        result = execute_tool(tool_name, **kwargs)
        return result.to_dict() if hasattr(result, 'to_dict') else result


# =============================================================================
# Factory function for easy instantiation
# =============================================================================

def create_receptionist(
    company_name: str = "The Tim Loss Team",
    default_lo_id: Optional[str] = None,
) -> AIReceptionist:
    """
    Create an AI Receptionist connected to the tool registry.

    Usage:
        from backend.ai_receptionist_tool_integration import create_receptionist

        receptionist = create_receptionist(
            company_name="The Tim Loss Team",
            default_lo_id="LO123",
        )

        # Handle incoming call
        greeting = receptionist.get_greeting("+1234567890")

        # Qualify caller
        qualification = receptionist.qualify_caller(
            caller_phone="+1234567890",
            intent="refinance",
            loan_purpose="cash_out",
            timeframe="30_days",
        )

        # Book appointment
        appointment = receptionist.book_appointment(
            contact_id="LEAD123",
            datetime_str="2024-01-15T10:00:00",
            appointment_type="consultation",
        )
    """
    return AIReceptionist.create(
        company_name=company_name,
        tool_registry=tool_registry,
        default_lo_id=default_lo_id,
    )


# =============================================================================
# Global instance (optional, for convenience)
# =============================================================================

# Create a default receptionist instance
default_receptionist = create_receptionist()
