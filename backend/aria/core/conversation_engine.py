"""
aria/core/conversation_engine.py
Perennia AI — Aria Conversational Engine

The brain of Aria. This is a LangGraph state machine that manages multi-turn
dialogue: intent recognition, slot filling, confirmation, task execution,
and response generation — all in a human-like conversational flow.

Architecture:
  User message
    → NLU Node (intent + entity extraction)
    → Slot Fill Node (ask clarifying questions if data is missing)
    → Confirmation Node (show user what Aria is about to do)
    → Task Executor Node (run the actual tools)
    → Response Node (generate natural language reply)
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Annotated
from enum import Enum

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from agents.orchestration.llm_circuit_breaker import LLMCircuitBreaker
from agents.orchestration.model_router import get_model_router
from aria.core.intent_registry import IntentRegistry, Intent, SlotSpec, intent_category
from aria.core.context_loader import AriaContextLoader
from aria.core.mode_router import classify_mode, AriaMode
from aria.core.grounding import ground_answer, format_grounded_message, DISCLAIMER
from aria.tasks.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


# ─── Fire-and-forget task safety ───────────────────────────────────────────
def _log_task_error(task: asyncio.Task, label: str = "background"):
    """Callback for fire-and-forget tasks to log exceptions."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.warning(f"Background task '{label}' failed: {exc}")


def _create_tracked_task(coro, label: str = "background"):
    """Create an asyncio task with error logging."""
    task = asyncio.create_task(coro)
    task.add_done_callback(lambda t: _log_task_error(t, label))
    return task


# ─── Circuit Breaker ────────────────────────────────────────────────────────
# Uses the shared LLMCircuitBreaker from agents/orchestration/.
# Prevents cascading failures when Anthropic is down by fast-failing
# instead of letting every Aria message block until timeout.

_circuit_breaker = LLMCircuitBreaker(failure_threshold=5, cooldown_seconds=30.0, name="aria-chat")

# Request timeout for individual LLM calls (seconds)
_LLM_TIMEOUT = 30.0


def _grounding_enabled() -> bool:
    return os.getenv("ARIA_GROUNDING_ENABLED", "false").lower() == "true"


# ─── LLM via shared ModelRouter ─────────────────────────────────────────────

def _get_llm(tier: str = "sonnet"):
    """Return the tier-appropriate LLM client.

    'haiku' for classification/extraction nodes (NLU, slot-fill, slot-answer,
    confirmation), 'sonnet' for the chitchat/response node. Default 'sonnet'
    preserves prior behaviour for any unmodified caller.
    """
    return get_model_router().get(tier)

# ─── State ────────────────────────────────────────────────────────────────────
class DialoguePhase(str, Enum):
    UNDERSTANDING   = "understanding"    # figuring out what user wants
    SLOT_FILLING    = "slot_filling"     # asking for missing info
    CONFIRMING      = "confirming"       # showing user what Aria will do
    EXECUTING       = "executing"        # running tools
    RESPONDING      = "responding"       # generating final reply
    CHITCHAT        = "chitchat"         # general conversation, no task

class AriaState(TypedDict):
    # Conversation history
    messages: Annotated[List, add_messages]

    # Resolved intent and slots
    intent: Optional[str]
    slots: Dict[str, Any]
    missing_slots: List[str]
    current_slot_question: Optional[str]

    # Task tracking
    phase: str
    task_result: Optional[Dict[str, Any]]
    confirmation_preview: Optional[str]

    # User + org context
    user_id: str
    org_id: str
    user_name: str
    user_email: Optional[str]
    user_role: str
    mode: Optional[str]

    # Voice memory preferences (loaded at session start, NOT persisted in session store)
    voice_preferences: Optional[Dict[str, Any]]

    # Operational
    iteration_count: int
    error: Optional[str]

    # Grounding (Phase 2A)
    sources: Optional[List[Dict[str, Any]]]
    citations: Optional[List[Dict[str, Any]]]
    grounded: Optional[bool]
    grounding_answer: Optional[str]
    grounding_disclaimer: Optional[str]


# ─── System prompt for Aria ───────────────────────────────────────────────────
def build_aria_system_prompt(
    context: Dict[str, Any],
    voice_preferences: Optional[Dict[str, Any]] = None,
) -> str:
    eastern = ZoneInfo("America/New_York")
    now = datetime.now(eastern).strftime("%A, %B %d, %Y at %I:%M %p ET")

    pipeline_summary = context.get("pipeline_summary", "No active loans loaded.")
    recent_contacts  = context.get("recent_contacts", "No recent contacts.")
    kg_context       = context.get("knowledge_graph_context", "")
    memory_context   = context.get("memory_context", "")
    user_name        = context.get("user_name", "the loan officer")
    user_email       = context.get("user_email", "")
    org_name         = context.get("org_name", "your company")

    user_identity = f"You work exclusively with {user_name} at {org_name}."
    if user_email:
        user_identity += f"\nTheir email address is {user_email}."

    # Build voice-preference instructions if available
    style_instructions = ""
    if voice_preferences:
        parts = []
        preferred_name = voice_preferences.get("preferred_name")
        if preferred_name:
            parts.append(f"- Address them as \"{preferred_name}\"")
        response_length = voice_preferences.get("response_length")
        if response_length == "short":
            parts.append("- Keep responses very brief — bullet points over paragraphs")
        elif response_length == "long":
            parts.append("- Give thorough, detailed responses — they prefer depth")
        briefing_depth = voice_preferences.get("briefing_depth")
        if briefing_depth == "concise":
            parts.append("- For pipeline updates, give only top-line numbers")
        elif briefing_depth == "detailed":
            parts.append("- For pipeline updates, include per-loan breakdowns")
        greeting_style = voice_preferences.get("greeting_style")
        if greeting_style == "formal":
            parts.append("- Use formal tone (e.g. 'Good morning' not 'Hey')")
        elif greeting_style == "first_name_only":
            parts.append("- Skip pleasantries — jump straight to business")
        if parts:
            style_instructions = "\n## User style preferences (from past interactions)\n" + "\n".join(parts) + "\n"

    return f"""You are Aria, the AI assistant built into Perennia — a mortgage CRM platform.
{user_identity}

Today is {now}.

## Your personality
- Warm, direct, and professional — like a brilliant colleague who happens to know everything
- You speak in plain English, never mortgage jargon unless the user uses it first
- You are proactive: if you notice something relevant (a missing document, an SLA at risk),
  you mention it naturally without being preachy
- You confirm before doing anything irreversible (sending emails, updating records)
- You ask ONE question at a time when gathering information — never fire a list of questions
{style_instructions}
## Greeting
When starting a new conversation, greet the LO by first name: "Hey {user_name}, what can I help you with?"
If the user name is unknown, use "Hey there" instead.

## What you can do
- Send pre-approval letters, conditional approval letters, LOEs, adverse action notices
- Look up any borrower, loan, contact, or task in the pipeline
- Send SMS and email to borrowers, realtors, title companies, and other parties
- Create and assign tasks, set reminders
- Update loan status, add notes to files
- Run credit, income, and asset analysis on any loan
- Schedule calls, send calendar invites
- Pull mortgage guidelines (FHA/VA/Conventional/USDA) to answer eligibility questions
- Generate reports on pipeline performance

## Current pipeline context
{pipeline_summary}

## Recent contacts
{recent_contacts}

## Key relationships
{kg_context if kg_context else "No relationship data loaded."}

## Relevant past context
{memory_context if memory_context else ""}

## How to handle task requests
When a user asks you to DO something:
1. Identify what's needed (the "slots") — borrower, amount, recipient, etc.
2. If anything is missing or ambiguous, ask ONE clarifying question
3. Before executing, show a brief preview: "Here's what I'll do: ..."
4. After confirmation, execute and confirm completion with specifics
5. Always log the action on the relevant loan file

## Tone calibration
- Short responses for simple questions
- Conversational back-and-forth for task gathering
- Thorough but concise for document previews
- Celebratory but brief for task completion ("Done — sent to Sarah at 2:34 PM ✓")
"""


# ─── Voice Memory write helpers (fire-and-forget) ───────────────────────────

# Compiled once at module level for performance
_PREFERRED_NAME_RE = re.compile(
    r"(?:call me|i go by|my name is|it'?s)\s+([A-Z][a-z]{1,20})",
    re.IGNORECASE,
)
_SHORT_KEYWORDS = {"short", "brief", "concise", "quick", "less"}
_LONG_KEYWORDS = {"detail", "details", "more info", "in depth", "thorough", "elaborate"}
_CONCISE_KEYWORDS = {"just the numbers", "top line", "bottom line", "headlines only"}
_DETAILED_KEYWORDS = {"break it down", "full detail", "walk me through", "deep dive"}
_FORMAL_KEYWORDS = {"more formal", "formal please", "professionally"}
_SKIP_PLEASANTRIES = {"don't need the pleasantries", "skip the small talk", "skip pleasantries", "get to the point", "straight to business"}

_METRIC_KEYWORDS = {
    "pipeline": "pipeline",
    "close rate": "close_rate",
    "closing rate": "close_rate",
    "volume": "volume",
    "pull through": "pull_through",
    "pull-through": "pull_through",
    "lock": "rate_locks",
    "locks": "rate_locks",
    "units": "units",
    "revenue": "revenue",
    "average loan": "avg_loan_size",
    "turn time": "turn_time",
    "cycle time": "cycle_time",
    "funded": "funded",
    "applications": "applications",
}


async def _extract_and_save_preferences(user_id: str, message: str, org_id: str = None) -> None:
    """Scan a user message for preference signals and persist via VoiceMemory.

    Runs as a fire-and-forget task — failures are logged, never raised.
    """
    try:
        from aria.core.voice_memory import VoiceMemory

        prefs_to_save: List[tuple] = []
        msg_lower = message.lower()

        # Preferred name
        m = _PREFERRED_NAME_RE.search(message)
        if m:
            prefs_to_save.append(("preferred_name", m.group(1).strip()))

        # Response length
        if any(kw in msg_lower for kw in _SHORT_KEYWORDS):
            prefs_to_save.append(("response_length", "short"))
        elif any(kw in msg_lower for kw in _LONG_KEYWORDS):
            prefs_to_save.append(("response_length", "long"))

        # Briefing depth
        if any(kw in msg_lower for kw in _CONCISE_KEYWORDS):
            prefs_to_save.append(("briefing_depth", "concise"))
        elif any(kw in msg_lower for kw in _DETAILED_KEYWORDS):
            prefs_to_save.append(("briefing_depth", "detailed"))

        # Greeting style
        if any(kw in msg_lower for kw in _SKIP_PLEASANTRIES):
            prefs_to_save.append(("greeting_style", "first_name_only"))
        elif any(kw in msg_lower for kw in _FORMAL_KEYWORDS):
            prefs_to_save.append(("greeting_style", "formal"))

        if not prefs_to_save:
            return

        vm = VoiceMemory(organization_id=org_id)
        for key, value in prefs_to_save:
            await asyncio.to_thread(vm.remember_preference, user_id, key, value)
            logger.debug("VoiceMemory: saved %s=%s for user %s", key, value, user_id)

    except Exception as e:
        logger.warning("VoiceMemory preference extraction failed: %s", e, exc_info=True)


async def _record_borrower_context(user_id: str, borrower_name: str, intent: str, slots: Dict[str, Any], org_id: str = None) -> None:
    """Record borrower interaction context after a successful task execution."""
    try:
        from aria.core.voice_memory import VoiceMemory

        context_parts = [f"Executed '{intent}'"]
        # Include relevant slot values for context (exclude borrower_name itself)
        for k, v in slots.items():
            if k not in ("borrower_name", "contact_name") and v is not None:
                context_parts.append(f"{k}: {v}")
        context = "; ".join(context_parts)

        vm = VoiceMemory(organization_id=org_id)
        await asyncio.to_thread(vm.remember_borrower_context, user_id, borrower_name, context)
        logger.debug("VoiceMemory: recorded borrower context for %s (user %s)", borrower_name, user_id)

    except Exception as e:
        logger.warning("VoiceMemory borrower context recording failed: %s", e, exc_info=True)


async def _record_metric_queries(user_id: str, message: str, org_id: str = None) -> None:
    """Detect metric references in a query and record them via VoiceMemory."""
    try:
        from aria.core.voice_memory import VoiceMemory

        msg_lower = message.lower()
        matched_metrics = [
            metric_name
            for keyword, metric_name in _METRIC_KEYWORDS.items()
            if keyword in msg_lower
        ]

        if not matched_metrics:
            return

        vm = VoiceMemory(organization_id=org_id)
        # Deduplicate in case multiple keywords map to the same metric
        for metric in set(matched_metrics):
            await asyncio.to_thread(vm.record_metric_query, user_id, metric)
            logger.debug("VoiceMemory: recorded metric query '%s' for user %s", metric, user_id)

    except Exception as e:
        logger.warning("VoiceMemory metric query recording failed: %s", e, exc_info=True)


# ─── Graph nodes ─────────────────────────────────────────────────────────────

async def nlu_node(state: AriaState) -> AriaState:
    """
    Extract intent and any entities already present in the user's message.
    """
    last_message = state["messages"][-1].content
    registry = IntentRegistry.get()

    intent_specs = {
        i.name: {
            "slots": {s.name: s.extraction_hint or s.description for s in i.required_slots + i.optional_slots}
        }
        for i in registry.intents
    }

    extraction_prompt = f"""Analyze this user message and extract:
1. The primary intent (what they want to accomplish)
2. Any entities/slots already provided in the message — use EXACT slot names from the spec

User message: "{last_message}"

Intent specs (intent name → slot names and hints):
{json.dumps(intent_specs, indent=2)}

Respond ONLY with valid JSON in this exact format:
{{
  "intent": "intent_name_or_null",
  "confidence": 0.0_to_1.0,
  "slots": {{
    "slot_name": "value_or_null"
  }},
  "is_chitchat": true_or_false
}}
"""

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-NLU] Circuit breaker OPEN — skipping NLU extraction")
        return {"phase": DialoguePhase.CHITCHAT, "intent": None, "slots": {}}

    try:
        response = await asyncio.wait_for(
            _get_llm("haiku").ainvoke([
                SystemMessage(content="You are a precise NLU system. Respond only with the JSON object."),
                HumanMessage(content=extraction_prompt)
            ]),
            timeout=_LLM_TIMEOUT,
        )
        _circuit_breaker.record_success()
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error("Aria NLU LLM call failed: %s", e, exc_info=True)
        return {"phase": DialoguePhase.CHITCHAT, "intent": None, "slots": {}}

    try:
        extracted = json.loads(response.content.strip())
    except json.JSONDecodeError:
        extracted = {"intent": None, "confidence": 0.0, "slots": {}, "is_chitchat": True}

    if extracted.get("is_chitchat") or not extracted.get("intent"):
        return {"phase": DialoguePhase.CHITCHAT, "intent": None, "slots": {}}

    intent_name = extracted["intent"]
    intent = registry.get_intent(intent_name)
    if not intent:
        return {"phase": DialoguePhase.CHITCHAT, "intent": None, "slots": {}}

    merged_slots = {**state.get("slots", {})}
    for k, v in extracted.get("slots", {}).items():
        if v is not None:
            merged_slots[k] = v

    missing = [
        slot.name for slot in intent.required_slots
        if slot.name not in merged_slots or merged_slots[slot.name] is None
    ]

    return {
        "intent": intent_name,
        "slots": merged_slots,
        "missing_slots": missing,
        "phase": DialoguePhase.SLOT_FILLING if missing else DialoguePhase.CONFIRMING,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


async def slot_fill_node(state: AriaState) -> AriaState:
    """Ask the user for the next missing slot — one question at a time."""
    intent = IntentRegistry.get().get_intent(state["intent"])
    if not intent or not state["missing_slots"]:
        return {"phase": DialoguePhase.CONFIRMING}

    next_slot_name = state["missing_slots"][0]
    slot_spec = intent.get_slot(next_slot_name)

    context_loader = AriaContextLoader()
    context = await context_loader.load_for_slot(
        user_id=state["user_id"],
        slot=slot_spec,
        slots_so_far=state["slots"],
    )

    question_prompt = f"""You are Aria. The user wants to: {intent.description}

You already know: {json.dumps(state['slots'], indent=2)}

You need to ask about: {slot_spec.name} — {slot_spec.description}

Context from their pipeline: {context}

Ask ONE natural, conversational question to get this information.
If there are obvious choices from the context (e.g. only one matching borrower),
present them as options. Keep it brief and warm.
"""

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-SLOT-FILL] Circuit breaker OPEN — returning degraded response")
        return {
            "phase": DialoguePhase.SLOT_FILLING,
            "current_slot_question": "I need a moment — can you try that again?",
            "messages": [AIMessage(content="I need a moment — can you try that again?")],
        }

    try:
        response = await asyncio.wait_for(
            _get_llm("haiku").ainvoke([
                SystemMessage(content="You are Aria, a warm and direct AI mortgage assistant."),
                HumanMessage(content=question_prompt)
            ]),
            timeout=_LLM_TIMEOUT,
        )
        _circuit_breaker.record_success()
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error("Aria slot-fill LLM call failed: %s", e, exc_info=True)
        return {
            "phase": DialoguePhase.SLOT_FILLING,
            "current_slot_question": "I need a moment — can you try that again?",
            "messages": [AIMessage(content="I need a moment — can you try that again?")],
        }

    question = response.content.strip()

    return {
        "phase": DialoguePhase.SLOT_FILLING,
        "current_slot_question": question,
        "messages": [AIMessage(content=question)],
    }


async def slot_answer_node(state: AriaState) -> AriaState:
    """Parse the user's answer to the last slot question and extract the value."""
    if not state.get("current_slot_question") or not state.get("missing_slots"):
        return {}

    last_user_message = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        ""
    )
    slot_name = state["missing_slots"][0]
    intent = IntentRegistry.get().get_intent(state["intent"])
    slot_spec = intent.get_slot(slot_name)

    extraction_prompt = f"""The user was asked: "{state['current_slot_question']}"
They responded: "{last_user_message}"

Extract the value for the slot "{slot_name}" ({slot_spec.description}).
Respond ONLY with JSON: {{"value": "extracted_value_or_null", "confident": true_or_false}}
"""

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-SLOT-ANSWER] Circuit breaker OPEN — cannot extract slot value")
        value = None
    else:
        try:
            response = await asyncio.wait_for(
                _get_llm("haiku").ainvoke([
                    SystemMessage(content="Extract the slot value. JSON only."),
                    HumanMessage(content=extraction_prompt)
                ]),
                timeout=_LLM_TIMEOUT,
            )
            _circuit_breaker.record_success()
            try:
                parsed = json.loads(response.content.strip())
                value = parsed.get("value")
            except json.JSONDecodeError:
                value = None
        except Exception as e:
            _circuit_breaker.record_failure()
            logger.error("Aria slot-answer LLM call failed: %s", e, exc_info=True)
            value = None

    updated_slots = {**state["slots"]}
    if value:
        updated_slots[slot_name] = value

    remaining_missing = [s for s in state["missing_slots"] if s != slot_name]
    if value is None:
        remaining_missing = state["missing_slots"]

    return {
        "slots": updated_slots,
        "missing_slots": remaining_missing,
        "current_slot_question": None,  # Clear so dispatch knows answer was processed
        "phase": DialoguePhase.CONFIRMING if not remaining_missing else DialoguePhase.SLOT_FILLING,
    }


async def confirmation_node(state: AriaState) -> AriaState:
    """Build a preview of what Aria is about to do and present for confirmation."""
    intent = IntentRegistry.get().get_intent(state["intent"])
    if not intent:
        return {"phase": DialoguePhase.EXECUTING}

    if not intent.requires_confirmation:
        return {"phase": DialoguePhase.EXECUTING}

    context_loader = AriaContextLoader()
    preview_context = await context_loader.build_preview_context(
        user_id=state["user_id"],
        intent=intent,
        slots=state["slots"],
    )

    preview_prompt = f"""You are Aria. You're about to execute: {intent.description}

Collected information:
{json.dumps(state['slots'], indent=2)}

Additional context:
{preview_context}

Write a brief, human-like confirmation message that:
1. Shows exactly what you're about to do (be specific: names, amounts, recipients)
2. Asks "Want me to go ahead?" or similar at the end
3. If generating a document, include a brief preview of its key contents
Keep it conversational and under 100 words unless showing a document preview.
"""

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-CONFIRM] Circuit breaker OPEN — returning degraded response")
        fallback = "I'm having trouble connecting right now. Try again in a moment."
        return {
            "phase": DialoguePhase.CONFIRMING,
            "confirmation_preview": fallback,
            "messages": [AIMessage(content=fallback)],
        }

    try:
        response = await asyncio.wait_for(
            _get_llm("haiku").ainvoke([
                SystemMessage(content="You are Aria. Write a natural confirmation message."),
                HumanMessage(content=preview_prompt)
            ]),
            timeout=_LLM_TIMEOUT,
        )
        _circuit_breaker.record_success()
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error("Aria confirmation LLM call failed: %s", e, exc_info=True)
        fallback = "I'm having trouble connecting right now. Try again in a moment."
        return {
            "phase": DialoguePhase.CONFIRMING,
            "confirmation_preview": fallback,
            "messages": [AIMessage(content=fallback)],
        }

    confirmation = response.content.strip()

    return {
        "phase": DialoguePhase.CONFIRMING,
        "confirmation_preview": confirmation,
        "messages": [AIMessage(content=confirmation)],
    }


def _detect_execution_failure(result: Any) -> str | None:
    """Inspect a TaskExecutor result for failure signals.

    Several handlers report failure by RETURNING a dict (e.g.
    {"action": "sms_blocked", "error": "..."}) instead of raising. Without
    this check, execute_node treats those as success and response_node
    narrates "Done ✓" over a blocked/failed action — a compliance and trust
    hazard. Returns a human-readable failure message, or None on success.
    """
    if not isinstance(result, dict):
        return None
    # Explicit error string wins.
    err = result.get("error")
    if err:
        return str(err)
    action = str(result.get("action") or "")
    if action.endswith("_blocked") or action.endswith("_failed"):
        return result.get("message") or f"Action did not complete ({action})."
    if result.get("success") is False:
        return result.get("message") or "The action did not complete successfully."
    status = str(result.get("status") or "").lower()
    if status in {"failed", "blocked", "error", "denied"}:
        return result.get("message") or f"The action did not complete ({status})."
    return None


async def execute_node(state: AriaState) -> AriaState:
    """Execute the task using the TaskExecutor."""
    executor = TaskExecutor()
    try:
        result = await executor.execute(
            intent=state["intent"],
            slots=state["slots"],
            user_id=state["user_id"],
            org_id=state["org_id"],
        )

        # Result-integrity gate: handlers that signal failure by returning an
        # error/blocked/failed dict must NOT be narrated as success. Route them
        # to the honest error branch in response_node.
        failure_msg = _detect_execution_failure(result)
        if failure_msg:
            logger.warning(
                "Task '%s' reported failure via result payload: %s",
                state.get("intent"), failure_msg,
            )
            return {
                "task_result": result,
                "phase": DialoguePhase.RESPONDING,
                "error": failure_msg,
            }

        # Fire-and-forget: record borrower context if task involved a borrower
        try:
            borrower_name = state["slots"].get("borrower_name") or state["slots"].get("contact_name")
            if borrower_name and state.get("user_id"):
                _create_tracked_task(
                    _record_borrower_context(
                        state["user_id"],
                        borrower_name,
                        state.get("intent", "unknown"),
                        state["slots"],
                        org_id=state.get("org_id"),
                    ),
                    "borrower_context",
                )
        except Exception:
            pass  # Never break execution flow

        return {
            "task_result": result,
            "phase": DialoguePhase.RESPONDING,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        return {
            "task_result": None,
            "phase": DialoguePhase.RESPONDING,
            "error": str(e),
        }


async def response_node(state: AriaState) -> AriaState:
    """Generate Aria's final response."""
    # Fire-and-forget: extract preference signals from the last user message
    try:
        last_human = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if last_human and state.get("user_id"):
            _create_tracked_task(
                _extract_and_save_preferences(state["user_id"], last_human, org_id=state.get("org_id")),
                "preference_extraction",
            )
    except Exception:
        pass  # Never break response flow

    if state["phase"] == DialoguePhase.CHITCHAT:
        context_loader = AriaContextLoader()
        last_msg = state["messages"][-1].content if state["messages"] else ""
        org_id = int(state["org_id"]) if state.get("org_id") else None
        context = await context_loader.load_with_memory(state["user_id"], query=last_msg, org_id=org_id)
        if state.get("user_email"):
            context["user_email"] = state["user_email"]
        system = build_aria_system_prompt(
            context,
            voice_preferences=state.get("voice_preferences"),
        )

        # Circuit breaker: fast-fail if LLM is unavailable
        if not _circuit_breaker.allow_request():
            logger.warning("[ARIA-RESPONSE] Circuit breaker OPEN — returning degraded chitchat response")
            degraded = "I'm having trouble connecting right now. Try again in a moment."
            return {
                "messages": [AIMessage(content=degraded)],
                "phase": DialoguePhase.RESPONDING,
                "intent": None, "slots": {}, "missing_slots": [],
                "current_slot_question": None, "mode": None,
                "task_result": None, "confirmation_preview": None,
                "error": None, "iteration_count": 0,
            }

        try:
            response = await asyncio.wait_for(
                _get_llm().ainvoke([
                    SystemMessage(content=system),
                    *state["messages"],
                ]),
                timeout=_LLM_TIMEOUT,
            )
            _circuit_breaker.record_success()
        except Exception as e:
            _circuit_breaker.record_failure()
            logger.error("Aria chitchat LLM call failed: %s", e, exc_info=True)
            degraded = "I'm having trouble connecting right now. Try again in a moment."
            return {
                "messages": [AIMessage(content=degraded)],
                "phase": DialoguePhase.RESPONDING,
                "intent": None, "slots": {}, "missing_slots": [],
                "current_slot_question": None, "mode": None,
                "task_result": None, "confirmation_preview": None,
                "error": None, "iteration_count": 0,
            }

        return {
            "messages": [AIMessage(content=response.content)],
            "phase": DialoguePhase.RESPONDING,
            # Reset for next turn
            "intent": None,
            "slots": {},
            "missing_slots": [],
            "current_slot_question": None,
            "mode": None,
            "task_result": None,
            "confirmation_preview": None,
            "error": None,
            "iteration_count": 0,
        }

    if state.get("error"):
        error_response = f"I ran into an issue with that: {state['error']}. Want me to try again?"
        return {
            "messages": [AIMessage(content=error_response)],
            "phase": DialoguePhase.RESPONDING,
            # Reset for next turn
            "intent": None,
            "slots": {},
            "missing_slots": [],
            "current_slot_question": None,
            "mode": None,
            "task_result": None,
            "confirmation_preview": None,
            "error": None,
            "iteration_count": 0,
        }

    result = state.get("task_result", {})
    intent = IntentRegistry.get().get_intent(state["intent"])

    completion_prompt = f"""Task completed: {intent.description if intent else 'task'}
Result: {json.dumps(result, indent=2)}

Write a brief, warm completion message that:
- Confirms exactly what was done (names, times, specifics from the result)
- Mentions any follow-up that was automatically logged
- Stays under 50 words unless there's meaningful additional info to share
- Uses a checkmark or similar natural signal of completion
"""

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-RESPONSE] Circuit breaker OPEN — returning degraded completion response")
        degraded = "I'm having trouble connecting right now. Try again in a moment."
        return {
            "messages": [AIMessage(content=degraded)],
            "phase": DialoguePhase.RESPONDING,
            "intent": None, "slots": {}, "missing_slots": [],
            "current_slot_question": None, "mode": None,
            "task_result": None, "confirmation_preview": None,
            "error": None, "iteration_count": 0,
        }

    try:
        response = await asyncio.wait_for(
            _get_llm().ainvoke([
                SystemMessage(content="You are Aria. Write a natural task completion message."),
                HumanMessage(content=completion_prompt)
            ]),
            timeout=_LLM_TIMEOUT,
        )
        _circuit_breaker.record_success()
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error("Aria completion LLM call failed: %s", e, exc_info=True)
        degraded = "I'm having trouble connecting right now. Try again in a moment."
        return {
            "messages": [AIMessage(content=degraded)],
            "phase": DialoguePhase.RESPONDING,
            "intent": None, "slots": {}, "missing_slots": [],
            "current_slot_question": None, "mode": None,
            "task_result": None, "confirmation_preview": None,
            "error": None, "iteration_count": 0,
        }

    return {
        "messages": [AIMessage(content=response.content)],
        "phase": DialoguePhase.RESPONDING,
        # Reset for next turn
        "intent": None,
        "slots": {},
        "missing_slots": [],
        "current_slot_question": None,
        "mode": None,
        "task_result": None,
        "confirmation_preview": None,
        "error": None,
        "iteration_count": 0,
    }


async def query_mode_node(state: AriaState) -> AriaState:
    """Agentic query mode — Claude picks tools, chains queries, synthesizes answer."""
    import json as _json
    import anthropic

    from aria.tools.crm_query_tools import QUERY_TOOL_DEFINITIONS, execute_query_tool

    question = state["messages"][-1].content if state["messages"] else ""
    org_id = state["org_id"]
    user_id = state["user_id"]

    # Circuit breaker: fast-fail if LLM is unavailable
    if not _circuit_breaker.allow_request():
        logger.warning("[ARIA-QUERY] Circuit breaker OPEN — returning fallback")
        return {
            "messages": [AIMessage(content="I'm having trouble connecting to my reasoning engine right now. Please try again in a moment.")],
            "phase": DialoguePhase.RESPONDING,
        }

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context_loader = AriaContextLoader()
    query_org_id = int(org_id) if org_id else None
    context = await context_loader.load_with_memory(user_id, query=question, org_id=query_org_id)
    if state.get("user_email"):
        context["user_email"] = state["user_email"]
    system = build_aria_system_prompt(
        context,
        voice_preferences=state.get("voice_preferences"),
    )

    messages = [{"role": "user", "content": question}]

    from agents.anthropic_client import cached_system_block, cache_tool_definitions
    cached_query_system = cached_system_block(
        system + "\n\nYou have access to CRM query tools. Use them to answer the LO's question. Chain multiple tools if needed. Be specific with numbers and names."
    )
    cached_query_tools = cache_tool_definitions(QUERY_TOOL_DEFINITIONS)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0.3,
                system=cached_query_system,
                messages=messages,
                tools=cached_query_tools,
            ),
            timeout=_LLM_TIMEOUT,
        )
        _circuit_breaker.record_success()
    except Exception as e:
        _circuit_breaker.record_failure()
        logger.error("[ARIA-QUERY] Initial LLM call failed: %s", e, exc_info=True)
        return {
            "messages": [AIMessage(content="I ran into an issue looking that up. Could you try asking again?")],
            "phase": DialoguePhase.RESPONDING,
        }

    # Cached system for tool-loop follow-ups (same system prompt reused)
    cached_loop_system = cached_system_block(system)

    for _ in range(3):
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            break

        tool_results = []
        for block in tool_blocks:
            result = await asyncio.to_thread(
                execute_query_tool,
                block.name, org_id=org_id, user_id=user_id, **block.input
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _json.dumps(result, default=str),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    temperature=0.3,
                    system=cached_loop_system,
                    messages=messages,
                    tools=cached_query_tools,
                ),
                timeout=_LLM_TIMEOUT,
            )
            _circuit_breaker.record_success()
        except Exception as e:
            _circuit_breaker.record_failure()
            logger.error("[ARIA-QUERY] Tool-loop LLM call failed: %s", e, exc_info=True)
            return {
                "messages": [AIMessage(content="I found some data but lost my connection while analyzing it. Please try again.")],
                "phase": DialoguePhase.RESPONDING,
            }

    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
    answer = "\n".join(text_blocks) or "I couldn't find that information."

    # Fire-and-forget: record which metrics the user asked about
    try:
        if question and state.get("user_id"):
            _create_tracked_task(
                _record_metric_queries(state["user_id"], question, org_id=state.get("org_id")),
                "metric_queries",
            )
    except Exception:
        pass  # Never break query flow

    return {
        "messages": [AIMessage(content=answer)],
        "phase": DialoguePhase.RESPONDING,
    }


async def ground_node(state: AriaState) -> AriaState:
    """Retrieve grounded guideline context for a factual turn."""
    question = (state.get("slots") or {}).get("question") \
        or (state["messages"][-1].content if state.get("messages") else "")
    result = await ground_answer(question, state["org_id"])
    return {
        "sources": result.sources,
        "citations": result.citations,
        "grounded": result.grounded,
        "grounding_answer": result.answer,
        "grounding_disclaimer": result.disclaimer or DISCLAIMER,
    }


def grounding_check_node(state: AriaState) -> AriaState:
    """Blocking sufficiency gate: emit the cited answer, or a terminal disclaimer."""
    if state.get("grounded"):
        msg = format_grounded_message(state.get("grounding_answer") or "",
                                      state.get("sources") or [])
    else:
        msg = state.get("grounding_disclaimer") or DISCLAIMER
    return {
        "messages": [AIMessage(content=msg)],
        "phase": DialoguePhase.RESPONDING.value,
        "intent": None,
        "missing_slots": [],
        "current_slot_question": None,
        "slots": {},
        "mode": None,
        "task_result": None,
        "confirmation_preview": None,
        "error": None,
        "iteration_count": 0,
    }


# ─── Entry router nodes ──────────────────────────────────────────────────────

MAX_SLOT_ITERATIONS = 6


async def dispatch_node(state: AriaState) -> dict:
    """Entry point for each turn. Checks iteration limit and truncates message history."""
    updates: dict = {}

    # Truncate message history to prevent exceeding LLM context window.
    # Keep the first 2 messages (system context) and the last 20 messages.
    msgs = state.get("messages", [])
    if len(msgs) > 30:
        truncated = msgs[:2] + msgs[-20:]
        updates["messages"] = truncated

    count = state.get("iteration_count", 0)
    if count >= MAX_SLOT_ITERATIONS:
        updates.update({
            "phase": DialoguePhase.RESPONDING,
            "error": "I seem to be going in circles. Let me start fresh — what would you like to do?",
        })
        return updates

    if not state.get("intent") and not state.get("mode"):
        last_message = state["messages"][-1].content if state["messages"] else ""
        mode = await classify_mode(last_message)
        updates["mode"] = mode.value
        return updates

    return updates


async def check_confirm_node(state: AriaState) -> dict:
    """Pass-through node for confirmation check. Routing via should_execute edges."""
    return {}


async def cancel_node(state: AriaState) -> dict:
    """User declined a pending confirmation. Acknowledge and reset — never
    narrate a completion for an action that was cancelled."""
    return {
        "messages": [AIMessage(content="No problem — I've cancelled that. What would you like to do instead?")],
        "phase": DialoguePhase.RESPONDING,
        "intent": None,
        "slots": {},
        "missing_slots": [],
        "current_slot_question": None,
        "mode": None,
        "task_result": None,
        "confirmation_preview": None,
        "error": None,
        "iteration_count": 0,
    }


# ─── Routing logic ────────────────────────────────────────────────────────────

def route_dispatch(state: AriaState) -> str:
    """Route incoming messages based on current dialogue phase."""
    # Hit iteration limit — go straight to error response
    if state.get("error") and state.get("iteration_count", 0) >= MAX_SLOT_ITERATIONS:
        return "response"

    phase = state.get("phase", "")

    # User answered a slot-filling question (current_slot_question is still set)
    if phase == DialoguePhase.SLOT_FILLING and state.get("current_slot_question"):
        return "slot_answer"

    # User responding to confirmation prompt
    if phase == DialoguePhase.CONFIRMING:
        return "check_confirm"

    mode = state.get("mode")
    if mode == AriaMode.QUERY.value:
        return "query_mode"

    # Default: NLU on the new message
    return "nlu"


def route_after_nlu(state: AriaState) -> str:
    if state["phase"] == DialoguePhase.CHITCHAT:
        return "response"
    if state["missing_slots"]:
        return "slot_fill"
    if _grounding_enabled() and intent_category(state.get("intent")) == "factual":
        return "ground"
    return "confirmation"


def route_after_slot_answer(state: AriaState) -> str:
    if state["missing_slots"]:
        return "slot_fill"
    if _grounding_enabled() and intent_category(state.get("intent")) == "factual":
        return "ground"
    return "confirmation"


def route_after_confirmation(state: AriaState) -> str:
    """If no confirmation needed (phase set to EXECUTING), go straight to execute."""
    if state["phase"] == DialoguePhase.EXECUTING:
        return "execute"
    # Confirmation shown — return to user and wait for yes/no
    return END


def should_execute(state: AriaState) -> str:
    """Check if user confirmed or denied the pending action."""
    import re as _re

    last_message = next(
        (m.content.lower() for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        ""
    )

    def _matches(words: list[str]) -> bool:
        # Word-boundary match so "not correct" doesn't match "correct" and
        # "now"/"know" don't match "no". Phrases match as whole phrases.
        return any(_re.search(r"\b" + _re.escape(w) + r"\b", last_message) for w in words)

    negative = _matches([
        "no", "nope", "cancel", "stop", "don't", "do not", "wait", "hold on",
        "change", "not", "wrong", "incorrect", "nevermind", "never mind",
    ])
    affirmative = _matches([
        "yes", "yeah", "yep", "do it", "send it", "send", "go ahead", "confirm",
        "confirmed", "sure", "ok", "okay", "correct", "looks good",
        "that's right", "proceed", "yup",
    ])

    # Negative wins: an explicit rejection must NEVER execute, even if the
    # reply also contains an affirmative token ("no, don't send it").
    if negative:
        return "cancel"
    if affirmative:
        return "execute"
    # Ambiguous — do NOT execute. Re-run NLU to interpret the reply; the pending
    # action stays unexecuted rather than firing on an unclear answer.
    return "nlu"


# ─── Build the graph ─────────────────────────────────────────────────────────

def build_aria_graph() -> StateGraph:
    graph = StateGraph(AriaState)

    # Nodes
    graph.add_node("dispatch",         dispatch_node)
    graph.add_node("nlu",              nlu_node)
    graph.add_node("slot_fill",        slot_fill_node)
    graph.add_node("slot_answer",      slot_answer_node)
    graph.add_node("confirmation",     confirmation_node)
    graph.add_node("check_confirm",    check_confirm_node)
    graph.add_node("cancel",           cancel_node)
    graph.add_node("execute",          execute_node)
    graph.add_node("response",         response_node)
    graph.add_node("query_mode",       query_mode_node)
    graph.add_node("ground",           ground_node)
    graph.add_node("grounding_check",  grounding_check_node)

    # Entry point — dispatch routes based on current dialogue phase
    graph.set_entry_point("dispatch")

    graph.add_conditional_edges("dispatch", route_dispatch, {
        "nlu":           "nlu",
        "slot_answer":   "slot_answer",
        "check_confirm": "check_confirm",
        "response":      "response",
        "query_mode":    "query_mode",
    })

    # NLU routes: chitchat → response, missing slots → slot_fill, factual → ground, ready → confirmation
    graph.add_conditional_edges("nlu", route_after_nlu, {
        "slot_fill":    "slot_fill",
        "confirmation": "confirmation",
        "response":     "response",
        "ground":       "ground",
    })

    # Slot fill asks question then returns to user (END)
    graph.add_edge("slot_fill", END)

    # Slot answer: more slots needed → slot_fill, factual → ground, all done → confirmation
    graph.add_conditional_edges("slot_answer", route_after_slot_answer, {
        "slot_fill":    "slot_fill",
        "confirmation": "confirmation",
        "ground":       "ground",
    })

    # Confirmation: no-confirm intents → execute immediately; otherwise wait for user
    graph.add_conditional_edges("confirmation", route_after_confirmation, {
        "execute": "execute",
        END:       END,
    })

    # User's yes/no response: confirmed → execute, denied → response, unclear → nlu
    graph.add_conditional_edges("check_confirm", should_execute, {
        "execute":  "execute",
        "cancel":   "cancel",
        "response": "response",
        "nlu":      "nlu",
    })

    # Query mode → END
    graph.add_edge("query_mode", END)

    # Grounding path: ground → grounding_check → END
    graph.add_edge("ground", "grounding_check")
    graph.add_edge("grounding_check", END)

    # Cancelled confirmation → END (acknowledged, nothing executed)
    graph.add_edge("cancel", END)

    # Execute → response → END
    graph.add_edge("execute", "response")
    graph.add_edge("response", END)

    return graph.compile()


# Lazy-build to avoid import-time heavy initialization
_aria_graph = None

def get_aria_graph():
    global _aria_graph
    if _aria_graph is None:
        _aria_graph = build_aria_graph()
    return _aria_graph
