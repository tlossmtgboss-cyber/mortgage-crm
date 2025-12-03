"""
===============================================================================
PERENNIA AI RECEPTIONIST - PART 4: CRM & TOOL INTEGRATION
===============================================================================
Integration with CRM tools and the 160-tool registry.

Features:
- Connection to Perennia tool registry (160 tools)
- Lead management and qualification
- Appointment scheduling
- Call logging and activity tracking
===============================================================================
"""

import os
import sys
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL REGISTRY CONNECTION
# =============================================================================

# Try to import from parent package (when installed as part of mortgage-crm)
try:
    from backend.agents.tools import (
        tool_registry,
        execute_tool,
        ToolResult,
        RECEPTIONIST_TOOLS,
        SCHEDULER_TOOLS,
        LEAD_TOOLS,
    )
    HAS_TOOL_REGISTRY = True
    logger.info(f"Connected to tool registry with {len(tool_registry)} tools")
except ImportError:
    HAS_TOOL_REGISTRY = False
    tool_registry = None
    logger.warning("Tool registry not available - running in standalone mode")


# =============================================================================
# RECEPTIONIST TOOL ACCESS
# =============================================================================

# Tools available to the AI Receptionist
AVAILABLE_TOOLS = [
    # Receptionist-specific tools
    "get_greeting_script",
    "qualify_caller",
    "route_call",
    "create_callback_request",
    "get_lo_availability",
    "get_call_queue_status",
    "handle_inbound_call",
    "log_call_interaction",

    # Scheduling tools
    "get_availability",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",

    # Lead tools
    "get_lead_details",
    "get_engagement_history",
    "score_lead",
]


def execute_receptionist_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool from the registry.

    Args:
        tool_name: Name of the tool to execute
        **kwargs: Tool arguments

    Returns:
        Tool result as dictionary
    """
    if not HAS_TOOL_REGISTRY:
        logger.warning(f"Tool registry not available, cannot execute {tool_name}")
        return {"status": "error", "error": "Tool registry not available"}

    if tool_name not in AVAILABLE_TOOLS:
        return {"status": "error", "error": f"Tool {tool_name} not available to receptionist"}

    try:
        result = execute_tool(tool_name, **kwargs)
        if hasattr(result, 'to_dict'):
            return result.to_dict()
        return result
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {"status": "error", "error": str(e)}


# =============================================================================
# AI RECEPTIONIST CLASS
# =============================================================================

class AIReceptionist:
    """
    AI Receptionist with full CRM integration.

    Connects voice interactions to the 160-tool registry for:
    - Lead qualification and management
    - Appointment scheduling
    - Call routing and logging
    - LO availability checking
    """

    def __init__(
        self,
        company_name: str = "Perennia Mortgage",
        default_lo_id: Optional[str] = None,
    ):
        self.company_name = company_name
        self.default_lo_id = default_lo_id
        self.has_tools = HAS_TOOL_REGISTRY

        logger.info(f"AI Receptionist initialized for {company_name}")
        logger.info(f"Tool registry: {'connected' if self.has_tools else 'standalone mode'}")

    @classmethod
    def create(
        cls,
        company_name: str = "Perennia Mortgage",
        tool_registry: Any = None,  # Accept but don't require
        default_lo_id: Optional[str] = None,
    ) -> "AIReceptionist":
        """Factory method to create receptionist instance."""
        return cls(
            company_name=company_name,
            default_lo_id=default_lo_id,
        )

    # =========================================================================
    # CALL HANDLING
    # =========================================================================

    def get_greeting(self, caller_phone: Optional[str] = None) -> Dict[str, Any]:
        """Get appropriate greeting for caller."""
        if self.has_tools:
            return execute_receptionist_tool(
                "get_greeting_script",
                caller_phone=caller_phone,
                company_name=self.company_name,
            )

        # Standalone fallback
        return {
            "status": "success",
            "data": {
                "greeting": f"Thank you for calling {self.company_name}. How can I help you today?",
                "caller_known": False,
            }
        }

    def qualify_caller(
        self,
        caller_phone: str,
        intent: str,
        loan_purpose: Optional[str] = None,
        property_type: Optional[str] = None,
        timeframe: Optional[str] = None,
        credit_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Qualify a caller based on their needs."""
        if self.has_tools:
            return execute_receptionist_tool(
                "qualify_caller",
                caller_phone=caller_phone,
                intent=intent,
                loan_purpose=loan_purpose,
                property_type=property_type,
                timeframe=timeframe,
                credit_range=credit_range,
            )

        # Standalone fallback
        return {
            "status": "success",
            "data": {
                "qualified": True,
                "score": 70,
                "recommendation": "schedule_appointment",
                "caller_phone": caller_phone,
                "intent": intent,
            }
        }

    def route_call(
        self,
        caller_phone: str,
        intent: str,
        urgency: str = "normal",
        preferred_lo_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route call to appropriate LO or department."""
        if self.has_tools:
            return execute_receptionist_tool(
                "route_call",
                caller_phone=caller_phone,
                intent=intent,
                urgency=urgency,
                preferred_lo_id=preferred_lo_id or self.default_lo_id,
            )

        # Standalone fallback
        return {
            "status": "success",
            "data": {
                "route_to": "loan_officer",
                "lo_id": self.default_lo_id,
                "reason": intent,
            }
        }

    def log_interaction(
        self,
        call_sid: str,
        caller_phone: str,
        interaction_type: str,
        transcript: Optional[str] = None,
        outcome: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a call interaction to the CRM."""
        if self.has_tools:
            return execute_receptionist_tool(
                "log_call_interaction",
                call_sid=call_sid,
                caller_phone=caller_phone,
                interaction_type=interaction_type,
                transcript=transcript,
                outcome=outcome,
                notes=notes,
            )

        # Standalone fallback
        logger.info(f"Call logged: {call_sid} - {interaction_type} - {outcome}")
        return {
            "status": "success",
            "data": {"logged": True, "call_sid": call_sid}
        }

    # =========================================================================
    # SCHEDULING
    # =========================================================================

    def check_availability(
        self,
        lo_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Check LO availability for appointments."""
        if self.has_tools:
            return execute_receptionist_tool(
                "get_availability",
                user_id=lo_id or self.default_lo_id,
                date_from=date_from,
                date_to=date_to,
                duration_minutes=duration_minutes,
            )

        # Standalone fallback - return mock availability
        from datetime import datetime, timedelta
        slots = []
        current = datetime.now() + timedelta(days=1)

        for i in range(5):
            day = current + timedelta(days=i)
            if day.weekday() < 5:  # Weekdays only
                for hour in [9, 10, 11, 14, 15, 16]:
                    slot_time = day.replace(hour=hour, minute=0, second=0)
                    slots.append({
                        "start": slot_time.isoformat(),
                        "display": slot_time.strftime("%A, %B %d at %I:%M %p"),
                    })

        return {
            "status": "success",
            "data": {
                "slots": slots[:10],
                "total_available": len(slots),
            }
        }

    def book_appointment(
        self,
        caller_phone: str,
        caller_name: Optional[str] = None,
        datetime_str: str = None,
        appointment_type: str = "consultation",
        duration_minutes: int = 30,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Book an appointment for a caller."""
        if self.has_tools:
            # First, find or create lead
            lead_result = self.lookup_caller(caller_phone)
            lead_id = None
            if lead_result.get("status") == "success":
                lead_id = lead_result.get("data", {}).get("id")

            return execute_receptionist_tool(
                "book_appointment",
                contact_id=lead_id or caller_phone,
                contact_type="lead",
                datetime_str=datetime_str,
                appointment_type=appointment_type,
                duration_minutes=duration_minutes,
                user_id=self.default_lo_id,
                notes=notes,
                send_confirmation=True,
            )

        # Standalone fallback
        import uuid
        appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"

        return {
            "status": "success",
            "data": {
                "appointment_id": appt_id,
                "datetime": datetime_str,
                "type": appointment_type,
                "confirmation_sent": True,
            },
            "message": f"Appointment booked for {datetime_str}",
        }

    def create_callback(
        self,
        caller_phone: str,
        caller_name: Optional[str] = None,
        preferred_time: Optional[str] = None,
        reason: Optional[str] = None,
        urgency: str = "normal",
    ) -> Dict[str, Any]:
        """Create a callback request."""
        if self.has_tools:
            return execute_receptionist_tool(
                "create_callback_request",
                caller_phone=caller_phone,
                caller_name=caller_name,
                preferred_time=preferred_time,
                reason=reason,
                urgency=urgency,
                assigned_to=self.default_lo_id,
            )

        # Standalone fallback
        import uuid
        callback_id = f"CB-{str(uuid.uuid4())[:8].upper()}"

        return {
            "status": "success",
            "data": {
                "callback_id": callback_id,
                "caller_phone": caller_phone,
                "preferred_time": preferred_time,
                "status": "pending",
            },
            "message": "Callback request created",
        }

    # =========================================================================
    # LEAD MANAGEMENT
    # =========================================================================

    def lookup_caller(self, phone: str) -> Dict[str, Any]:
        """Look up caller in CRM by phone number."""
        if self.has_tools:
            return execute_receptionist_tool(
                "get_lead_details",
                phone=phone,
            )

        # Standalone fallback
        return {
            "status": "no_data",
            "data": None,
            "message": "Caller not found in CRM",
        }

    def get_caller_history(self, lead_id: str) -> Dict[str, Any]:
        """Get engagement history for a known caller."""
        if self.has_tools:
            return execute_receptionist_tool(
                "get_engagement_history",
                lead_id=lead_id,
            )

        return {"status": "no_data", "data": {"engagements": []}}

    def score_caller(self, lead_id: str) -> Dict[str, Any]:
        """Score a caller/lead."""
        if self.has_tools:
            return execute_receptionist_tool(
                "score_lead",
                lead_id=lead_id,
            )

        return {
            "status": "success",
            "data": {"score": 50, "grade": "C"},
        }

    # =========================================================================
    # QUEUE STATUS
    # =========================================================================

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current call queue status."""
        if self.has_tools:
            return execute_receptionist_tool("get_call_queue_status")

        return {
            "status": "success",
            "data": {
                "calls_waiting": 0,
                "avg_wait_time": 0,
                "available_los": 3,
            }
        }

    def get_lo_status(self, lo_id: Optional[str] = None) -> Dict[str, Any]:
        """Get LO availability status."""
        if self.has_tools:
            return execute_receptionist_tool(
                "get_lo_availability",
                lo_id=lo_id or self.default_lo_id,
            )

        return {
            "status": "success",
            "data": {
                "available": True,
                "next_available": datetime.now().isoformat(),
            }
        }

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_available_tools(self) -> List[str]:
        """Get list of available tools."""
        return AVAILABLE_TOOLS if self.has_tools else []

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute any available tool by name."""
        return execute_receptionist_tool(tool_name, **kwargs)


# =============================================================================
# DATABASE LOGGING (for standalone mode)
# =============================================================================

class StandaloneLogger:
    """
    Simple database logger for standalone mode.
    Uses SQLite when full CRM database isn't available.
    """

    def __init__(self, db_path: str = "receptionist.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT UNIQUE,
                caller_phone TEXT,
                caller_name TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                duration_seconds INTEGER,
                intent TEXT,
                outcome TEXT,
                transcript TEXT,
                notes TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS callback_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caller_phone TEXT,
                caller_name TEXT,
                preferred_time TEXT,
                reason TEXT,
                urgency TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def log_call(
        self,
        call_sid: str,
        caller_phone: str,
        **kwargs
    ):
        """Log a call to the database."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO call_logs
            (call_sid, caller_phone, caller_name, intent, outcome, transcript, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            call_sid,
            caller_phone,
            kwargs.get("caller_name"),
            kwargs.get("intent"),
            kwargs.get("outcome"),
            kwargs.get("transcript"),
            kwargs.get("notes"),
        ))

        conn.commit()
        conn.close()

    def create_callback(
        self,
        caller_phone: str,
        **kwargs
    ) -> int:
        """Create a callback request."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO callback_requests
            (caller_phone, caller_name, preferred_time, reason, urgency)
            VALUES (?, ?, ?, ?, ?)
        """, (
            caller_phone,
            kwargs.get("caller_name"),
            kwargs.get("preferred_time"),
            kwargs.get("reason"),
            kwargs.get("urgency", "normal"),
        ))

        callback_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return callback_id


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_receptionist(
    company_name: str = "Perennia Mortgage",
    default_lo_id: Optional[str] = None,
) -> AIReceptionist:
    """
    Create an AI Receptionist instance.

    Usage:
        from AI_RECEPTIONIST_PART4_INTEGRATION import create_receptionist

        receptionist = create_receptionist(
            company_name="Perennia Mortgage",
            default_lo_id="LO123",
        )

        # Handle incoming call
        greeting = receptionist.get_greeting("+1234567890")

        # Qualify caller
        qualification = receptionist.qualify_caller(
            caller_phone="+1234567890",
            intent="refinance",
        )

        # Book appointment
        appointment = receptionist.book_appointment(
            caller_phone="+1234567890",
            datetime_str="2024-01-15T10:00:00",
        )
    """
    return AIReceptionist(
        company_name=company_name,
        default_lo_id=default_lo_id,
    )


# Global instance
default_receptionist: Optional[AIReceptionist] = None


def get_receptionist() -> AIReceptionist:
    """Get or create the default receptionist instance."""
    global default_receptionist
    if default_receptionist is None:
        default_receptionist = create_receptionist()
    return default_receptionist
