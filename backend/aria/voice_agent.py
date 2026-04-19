"""
Perennia AI — Aria LiveKit Voice Agent Worker

Two session types (determined by room metadata):
  - WebRTC (browser/mobile) — LO assistant mode
  - SIP (Telnyx telephony) — inbound receptionist / outbound follow-up

All CRM data access goes through HTTP calls to /internal/aria/* endpoints.
This process NEVER imports from db, database.models, or services directly.

Run:
  python -m aria.voice_agent dev     # development
  python -m aria.voice_agent start   # production
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from livekit import agents, api as livekit_api
from livekit.agents import (
    Agent,
    AgentSession,
    RunContext,
    function_tool,
    AgentServer,
    TurnHandlingOptions,
)
from livekit.plugins import cartesia, deepgram
from livekit.plugins.anthropic import LLM as AnthropicLLM

from agents.aria_backend_client import call_backend_tool_safe
from agents.aria_prompts import get_prompt

logger = logging.getLogger("aria.voice_agent")

# ─── Configuration ───────────────────────────────────────────────────────────

CARTESIA_VOICE_ID = os.getenv(
    "ARIA_CARTESIA_VOICE_ID",
    "a0e99841-438c-4a64-b679-ae501e7d6091",  # Jacqueline
)
CLAUDE_MODEL = os.getenv("ARIA_LLM_MODEL", "claude-sonnet-4-5-20250414")
TELNYX_TRUNK_ID = os.getenv("TELNYX_SIP_TRUNK_ID", "")



TURN_HANDLING: TurnHandlingOptions = {
    "endpointing": {
        "mode": "dynamic",
        "min_delay": 0.5,
        "max_delay": 2.0,
    },
    "interruption": {
        "enabled": True,
        "mode": "adaptive",
        "min_duration": 0.5,
        "min_words": 1,
        "resume_false_interruption": True,
    },
    "preemptive_generation": {
        "enabled": True,
        "preemptive_tts": True,
    },
}


# ─── Aria Agent ──────────────────────────────────────────────────────────────

class AriaVoiceAgent(Agent):
    """Aria — Perennia AI's real-time voice assistant."""

    def __init__(self, mode: str = "lo_assistant", context: dict = None) -> None:
        ctx = context or {}
        prompt = get_prompt(mode, ctx)
        super().__init__(instructions=prompt)
        self._mode = mode
        self._session_data: Dict[str, Any] = {
            "mode": mode,
            "tools_executed": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            **ctx,
        }

    async def on_enter(self) -> None:
        if self._mode == "inbound_receptionist":
            caller_name = self._session_data.get("caller_name", "")
            is_existing = self._session_data.get("is_existing_client", False)
            if is_existing and caller_name:
                first = caller_name.split()[0]
                greeting = (
                    f"Greet the caller by name — you already know who they are. "
                    f"Say something like 'Hi {first}, thanks for calling Perennia, "
                    f"this is Aria. How can I help you today?'"
                )
            else:
                greeting = (
                    "Greet the caller warmly. "
                    "Say 'Thanks for calling Perennia, this is Aria. "
                    "How can I help you today?'"
                )
            await self.session.generate_reply(instructions=greeting)
            return

        greetings = {
            "lo_assistant": (
                "Greet the loan officer briefly. "
                "Say something like 'Hey, Aria here. What can I help you with?'"
            ),
            "outbound_followup": (
                "Introduce yourself briefly using the context in your instructions."
            ),
        }
        await self.session.generate_reply(
            instructions=greetings.get(self._mode, greetings["lo_assistant"])
        )

    # ─── CRM Tools (all via HTTP backend) ─────────────────────────────

    @function_tool()
    async def search_pipeline(self, context: RunContext, query: str):
        """Search the loan pipeline by borrower name, loan number, or stage."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "search_pipeline", "params": {"query": query}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_pipeline_summary(self, context: RunContext):
        """Get a summary of the current loan pipeline — total loans, by stage, SLA alerts."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_pipeline_summary", "params": {}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def search_leads(self, context: RunContext, query: str):
        """Search for leads by name, email, or phone number."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "search_leads", "params": {"query": query}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_lead_details(self, context: RunContext, lead_id: int):
        """Get full details for a specific lead by ID."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_lead_details", "params": {"lead_id": lead_id}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def get_loan_status(self, context: RunContext, lead_id: int):
        """Check the current loan status for a borrower."""
        result = await call_backend_tool_safe(
            "/internal/aria/loan-status",
            {"borrower_id": lead_id},
        )
        if result.get("spoken_summary"):
            return result["spoken_summary"]
        return json.dumps(result, default=str)

    @function_tool()
    async def send_sms(
        self,
        context: RunContext,
        phone_number: str,
        message: str,
    ):
        """Send an SMS text message to a phone number."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "send_sms_message", "params": {
                "to_phone": phone_number,
                "message": message,
            }},
        )
        self._session_data["tools_executed"].append({
            "tool": "send_sms",
            "phone": phone_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def create_task(
        self,
        context: RunContext,
        title: str,
        description: str = "",
        due_date: str = "",
        priority: str = "medium",
    ):
        """Create a task or follow-up item."""
        params = {"title": title, "description": description, "priority": priority}
        if due_date:
            params["due_date"] = due_date
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "create_task", "params": params},
        )
        self._session_data["tools_executed"].append({
            "tool": "create_task",
            "title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def get_sla_alerts(self, context: RunContext):
        """Get current SLA alerts and overdue items."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_sla_alerts", "params": {}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def check_rates(self, context: RunContext, loan_type: str = "conventional"):
        """Check current mortgage rates."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_current_rates", "params": {"loan_type": loan_type}},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def schedule_appointment(
        self,
        context: RunContext,
        contact_id: str = "",
        datetime_str: str = "",
        duration_minutes: int = 30,
        appointment_type: str = "consultation",
        title: str = "",
        notes: str = "",
    ):
        """Schedule a new appointment on the calendar. Use contact_id if known, or provide details in notes."""
        params = {
            "duration_minutes": duration_minutes,
            "appointment_type": appointment_type,
        }
        if contact_id:
            params["contact_id"] = contact_id
        if datetime_str:
            params["datetime_str"] = datetime_str
        if title:
            params["title"] = title
        if notes:
            params["notes"] = notes
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "book_appointment", "params": params},
        )
        self._session_data["tools_executed"].append({
            "tool": "schedule_appointment",
            "title": title or appointment_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def get_daily_briefing(self, context: RunContext):
        """Get a morning briefing with today's tasks, appointments, pipeline updates, and alerts."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_daily_briefing", "params": {}},
        )
        return json.dumps(result, default=str)

    # ─── SMS Conversation Tools ──────────────────────────────────────

    @function_tool()
    async def get_sms_conversation(self, context: RunContext, phone_number: str):
        """Get the SMS conversation history with a phone number. Shows recent messages back and forth."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "get_sms_conversation_history", "params": {
                "phone_number": phone_number,
            }},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def start_scheduling_conversation(
        self,
        context: RunContext,
        phone_number: str,
        borrower_name: str,
        proposed_times: str = "",
        appointment_type: str = "consultation",
    ):
        """Start an SMS conversation with a borrower to schedule an appointment.
        Sends an initial text asking for their availability. They'll text back to confirm."""
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "start_scheduling_sms", "params": {
                "to_phone": phone_number,
                "borrower_name": borrower_name,
                "proposed_times": proposed_times,
                "appointment_type": appointment_type,
            }},
        )
        self._session_data["tools_executed"].append({
            "tool": "start_scheduling_sms",
            "borrower": borrower_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    # ─── Document Generation Tools ───────────────────────────────────

    @function_tool()
    async def generate_pre_approval_letter(
        self,
        context: RunContext,
        lead_id: str,
        approval_amount: str,
        loan_type: str = "Conventional",
        property_address: str = "",
        recipient_email: str = "",
    ):
        """Generate and email a pre-approval letter for a borrower.
        Requires the lead ID and approval amount. The letter is emailed as a PDF."""
        params = {
            "lead_id": lead_id,
            "approval_amount": approval_amount,
            "loan_type": loan_type,
        }
        if property_address:
            params["property_address"] = property_address
        if recipient_email:
            params["recipient_email"] = recipient_email
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "generate_pre_approval_letter", "params": params},
        )
        self._session_data["tools_executed"].append({
            "tool": "generate_pre_approval_letter",
            "lead_id": lead_id,
            "amount": approval_amount,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    # ─── Existing Tools (Inbound/Transfer) ───────────────────────────

    @function_tool()
    async def look_up_caller(self, context: RunContext, phone_number: str):
        """Look up a caller by phone number in the CRM. Use this when receiving an inbound call."""
        result = await call_backend_tool_safe(
            "/internal/aria/lead-lookup",
            {"phone": phone_number},
        )
        lead = result.get("lead")
        if not lead:
            return "I don't have this caller in the system yet — they're a new prospect."
        return json.dumps(lead, default=str)

    @function_tool()
    async def create_lead(
        self,
        context: RunContext,
        first_name: str,
        last_name: str,
        email: str = "",
        loan_purpose: str = "",
        property_type: str = "",
        timeline: str = "",
        notes: str = "",
    ):
        """Create a new lead profile in the CRM for a first-time caller.
        Use this when the caller is new and you've gathered their basic info during the conversation.
        You already have their phone number — never ask for it."""
        from_number = self._session_data.get("from_number", "")
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "create_lead", "params": {
                "first_name": first_name,
                "last_name": last_name,
                "phone": from_number,
                "email": email,
                "source": "inbound_call",
                "loan_purpose": loan_purpose,
                "property_type": property_type,
                "timeline": timeline,
                "notes": f"Created from inbound call. {notes}".strip(),
            }},
        )
        self._session_data["tools_executed"].append({
            "tool": "create_lead",
            "name": f"{first_name} {last_name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return json.dumps(result, default=str)

    @function_tool()
    async def update_lead(
        self,
        context: RunContext,
        lead_id: int,
        notes: str = "",
        email: str = "",
        loan_purpose: str = "",
        property_type: str = "",
    ):
        """Update an existing lead's profile with new information gathered during the call."""
        params: Dict[str, Any] = {"lead_id": lead_id}
        if notes:
            params["notes"] = notes
        if email:
            params["email"] = email
        if loan_purpose:
            params["loan_purpose"] = loan_purpose
        if property_type:
            params["property_type"] = property_type
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": "update_lead", "params": params},
        )
        return json.dumps(result, default=str)

    @function_tool()
    async def warm_transfer_to_lo(self, context: RunContext, reason: str, summary: str):
        """Transfer the caller to their assigned loan officer with a verbal brief.
        Use when the caller needs to speak with their LO directly.
        Reason: ready_to_apply, complex_scenario, or customer_request."""
        room_name = None
        if context.session and context.session.room:
            room_name = context.session.room.name

        if not room_name:
            return "I can't transfer right now — no active call room."

        metadata = {}
        if context.session and context.session.room:
            try:
                metadata = json.loads(context.session.room.metadata or "{}")
            except (json.JSONDecodeError, AttributeError):
                pass

        lead_id = metadata.get("lead_id") or metadata.get("borrower_id")
        if not lead_id:
            return (
                "I don't know which borrower this is — "
                "I can't look up their loan officer without an ID."
            )

        lo = await call_backend_tool_safe(
            "/internal/aria/lo-info", {"lead_id": lead_id}
        )
        if lo.get("error"):
            return f"I couldn't find an assigned loan officer: {lo['error']}"

        borrower = await call_backend_tool_safe(
            "/internal/aria/lead-info", {"lead_id": lead_id}
        )

        # Add LO as SIP participant to the current LiveKit room
        if TELNYX_TRUNK_ID and lo.get("phone"):
            try:
                from livekit.protocol.sip import CreateSIPParticipantRequest

                lk_api = livekit_api.LiveKitAPI()
                await lk_api.sip.create_sip_participant(
                    CreateSIPParticipantRequest(
                        sip_trunk_id=TELNYX_TRUNK_ID,
                        sip_call_to=lo["phone"],
                        room_name=room_name,
                        participant_identity=f"lo_{lo['id']}",
                        participant_name=lo.get("full_name", "Loan Officer"),
                    )
                )
            except Exception as e:
                logger.error(f"SIP transfer failed: {e}")
                return (
                    f"I wasn't able to connect the call — the transfer failed. "
                    f"{lo.get('full_name', 'Your loan officer')} can be reached at "
                    f"{lo.get('phone', 'their direct number')}."
                )

        borrower_name = borrower.get("first_name", "the caller")
        lo_name = lo.get("first_name", "")

        return (
            f"{lo_name}, I have {borrower_name} on the line. "
            f"{summary} "
            f"I'll let you two take it from here."
        )

    # Tools the voice agent is allowed to invoke via the generic executor.
    # All destructive, compliance, or admin tools are excluded.
    _CRM_TOOL_ALLOWLIST = frozenset({
        "search_pipeline", "get_pipeline_summary", "search_leads",
        "get_lead_details", "get_loan_status", "get_loan_details",
        "get_tasks", "get_upcoming_appointments", "get_rate_alerts",
        "get_contact_info", "get_loan_conditions", "get_document_status",
        "get_sla_status", "calculate_income",
    })

    @function_tool()
    async def run_crm_tool(
        self, context: RunContext, tool_name: str, parameters: str = "{}"
    ):
        """Run a read-only CRM tool by name with JSON parameters.
        Fallback for tools without a specific wrapper."""
        if tool_name not in self._CRM_TOOL_ALLOWLIST:
            return json.dumps({"error": f"Tool '{tool_name}' is not available via voice. Use a specific command instead."})
        try:
            params = json.loads(parameters)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON parameters"})
        result = await call_backend_tool_safe(
            "/internal/aria/tool/execute",
            {"tool_name": tool_name, "params": params},
        )
        return json.dumps(result, default=str)


# ─── Agent Server ────────────────────────────────────────────────────────────

server = AgentServer()


def _build_session(mode: str = "lo_assistant", context: dict = None) -> tuple:
    """Build AgentSession + AriaVoiceAgent for a given mode."""
    is_telephony = mode in ("inbound_receptionist", "outbound_followup")

    stt = deepgram.STT(
        model="nova-3",
        language="en",
        smart_format=True,
        punctuate=True,
        filler_words=True,
        no_delay=True,
        endpointing=25 if is_telephony else 50,
    )

    tts = cartesia.TTS(
        model="sonic-3",
        voice=CARTESIA_VOICE_ID,
        speed="normal",
        emotion=["positivity:high", "curiosity"],
    )

    session = AgentSession(
        stt=stt,
        llm=AnthropicLLM(model=CLAUDE_MODEL),
        tts=tts,
        turn_handling=TURN_HANDLING,
        tts_text_transforms=["filter_markdown", "filter_emoji"],
        min_consecutive_speech_delay=0.15,
    )
    agent = AriaVoiceAgent(mode=mode, context=context)
    return session, agent


@server.rtc_session(agent_name="aria-voice")
async def aria_voice_session(ctx: agents.JobContext):
    """Unified session handler for both WebRTC and SIP calls.

    Mode detection (in priority order):
      1. Room metadata {"trigger": "inbound_call"}  -> inbound receptionist
      2. Room metadata {"trigger": "outbound_call"} -> outbound follow-up
      3. Room name starting with "aria-inbound"     -> inbound receptionist (SIP dispatch)
      4. Anything else                              -> LO assistant (WebRTC)
    """
    room_name = ctx.room.name
    logger.info(f"[AriaVoice] Session started: room={room_name}")

    # Parse room metadata to determine session type
    metadata = {}
    try:
        metadata = json.loads(ctx.room.metadata or "{}")
    except (json.JSONDecodeError, AttributeError):
        pass

    trigger = metadata.get("trigger", "")

    # Detect inbound SIP calls from room name when metadata isn't set
    # (LiveKit dispatch rule creates rooms named "aria-inbound_<caller>_<random>")
    if not trigger and room_name.startswith("aria-inbound"):
        trigger = "inbound_call"
        logger.info(f"[AriaVoice] Detected inbound SIP call from room name: {room_name}")

    if trigger == "inbound_call":
        mode = "inbound_receptionist"
        caller_name = metadata.get("caller_name", "")
        is_existing = metadata.get("is_existing_client", False)
        context = {
            "caller_name": caller_name,
            "first_name": caller_name.split()[0] if caller_name else "",
            "from_number": metadata.get("from_number", ""),
            "lead_id": metadata.get("lead_id"),
            "lo_name": metadata.get("lo_name", ""),
            "is_existing_client": is_existing,
            "stage": metadata.get("stage", ""),
            "organization_id": metadata.get("organization_id"),
        }
        logger.info(
            f"[AriaVoice] Inbound receptionist mode: "
            f"from={metadata.get('from_number', 'unknown')} "
            f"caller={caller_name or 'NEW'} existing={is_existing}"
        )
    elif trigger == "outbound_call":
        mode = "outbound_followup"
        context = {
            "first_name": metadata.get("borrower_name", ""),
            "lo_name": metadata.get("lo_name", ""),
            "call_purpose": metadata.get("call_purpose", ""),
            "call_context": metadata.get("call_context", ""),
        }
        logger.info(
            f"[AriaVoice] Outbound follow-up mode: "
            f"lead={metadata.get('lead_id', 'unknown')}"
        )
    else:
        mode = "lo_assistant"
        context = {}
        logger.info("[AriaVoice] LO assistant mode (WebRTC)")

    session, agent = _build_session(mode, context)
    await session.start(room=ctx.room, agent=agent)


# ─── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agents.cli.run_app(server)
