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

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from enum import Enum

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from aria.core.intent_registry import IntentRegistry, Intent, SlotSpec
from aria.core.context_loader import AriaContextLoader
from aria.core.mode_router import classify_mode, AriaMode
from aria.tasks.task_executor import TaskExecutor

logger = logging.getLogger(__name__)

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0.3,
    max_tokens=1024,
)

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
    user_role: str
    mode: Optional[str]

    # Operational
    iteration_count: int
    error: Optional[str]


# ─── System prompt for Aria ───────────────────────────────────────────────────
def build_aria_system_prompt(context: Dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")

    pipeline_summary = context.get("pipeline_summary", "No active loans loaded.")
    recent_contacts  = context.get("recent_contacts", "No recent contacts.")
    user_name        = context.get("user_name", "the loan officer")
    org_name         = context.get("org_name", "your company")

    return f"""You are Aria, the AI assistant built into Perennia — a mortgage CRM platform.
You work exclusively with {user_name} at {org_name}.

Today is {now}.

## Your personality
- Warm, direct, and professional — like a brilliant colleague who happens to know everything
- You speak in plain English, never mortgage jargon unless the user uses it first
- You are proactive: if you notice something relevant (a missing document, an SLA at risk),
  you mention it naturally without being preachy
- You confirm before doing anything irreversible (sending emails, updating records)
- You ask ONE question at a time when gathering information — never fire a list of questions

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

    response = await llm.ainvoke([
        SystemMessage(content="You are a precise NLU system. Respond only with the JSON object."),
        HumanMessage(content=extraction_prompt)
    ])

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

    response = await llm.ainvoke([
        SystemMessage(content="You are Aria, a warm and direct AI mortgage assistant."),
        HumanMessage(content=question_prompt)
    ])

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

    response = await llm.ainvoke([
        SystemMessage(content="Extract the slot value. JSON only."),
        HumanMessage(content=extraction_prompt)
    ])

    try:
        parsed = json.loads(response.content.strip())
        value = parsed.get("value")
    except Exception:
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

    response = await llm.ainvoke([
        SystemMessage(content="You are Aria. Write a natural confirmation message."),
        HumanMessage(content=preview_prompt)
    ])

    confirmation = response.content.strip()

    return {
        "phase": DialoguePhase.CONFIRMING,
        "confirmation_preview": confirmation,
        "messages": [AIMessage(content=confirmation)],
    }


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
    if state["phase"] == DialoguePhase.CHITCHAT:
        context_loader = AriaContextLoader()
        context = await context_loader.load_full(state["user_id"])
        system = build_aria_system_prompt(context)

        response = await llm.ainvoke([
            SystemMessage(content=system),
            *state["messages"],
        ])
        return {"messages": [AIMessage(content=response.content)]}

    if state.get("error"):
        error_response = f"I ran into an issue with that: {state['error']}. Want me to try again?"
        return {"messages": [AIMessage(content=error_response)]}

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

    response = await llm.ainvoke([
        SystemMessage(content="You are Aria. Write a natural task completion message."),
        HumanMessage(content=completion_prompt)
    ])

    return {
        "messages": [AIMessage(content=response.content)],
        "phase": DialoguePhase.RESPONDING,
    }


async def query_mode_node(state: AriaState) -> AriaState:
    """Agentic query mode — Claude picks tools, chains queries, synthesizes answer."""
    import json as _json
    import anthropic
    import os

    from aria.tools.crm_query_tools import QUERY_TOOL_DEFINITIONS, execute_query_tool

    question = state["messages"][-1].content if state["messages"] else ""
    org_id = state["org_id"]
    user_id = state["user_id"]

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context_loader = AriaContextLoader()
    context = await context_loader.load_full(user_id)
    system = build_aria_system_prompt(context)

    messages = [{"role": "user", "content": question}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0.3,
        system=system + "\n\nYou have access to CRM query tools. Use them to answer the LO's question. Chain multiple tools if needed. Be specific with numbers and names.",
        messages=messages,
        tools=QUERY_TOOL_DEFINITIONS,
    )

    for _ in range(3):
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            break

        tool_results = []
        for block in tool_blocks:
            result = execute_query_tool(
                block.name, org_id=org_id, user_id=user_id, **block.input
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _json.dumps(result, default=str),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.3,
            system=system,
            messages=messages,
            tools=QUERY_TOOL_DEFINITIONS,
        )

    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
    answer = "\n".join(text_blocks) or "I couldn't find that information."

    return {
        "messages": [AIMessage(content=answer)],
        "phase": DialoguePhase.RESPONDING,
    }


# ─── Entry router nodes ──────────────────────────────────────────────────────

MAX_SLOT_ITERATIONS = 15


async def dispatch_node(state: AriaState) -> dict:
    """Entry point for each turn. Checks iteration limit."""
    count = state.get("iteration_count", 0)
    if count >= MAX_SLOT_ITERATIONS:
        return {
            "phase": DialoguePhase.RESPONDING,
            "error": "I seem to be going in circles. Let me start fresh — what would you like to do?",
        }

    if not state.get("intent") and not state.get("mode"):
        last_message = state["messages"][-1].content if state["messages"] else ""
        mode = await classify_mode(last_message)
        return {"mode": mode.value}

    return {}


async def check_confirm_node(state: AriaState) -> dict:
    """Pass-through node for confirmation check. Routing via should_execute edges."""
    return {}


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
    return "confirmation"


def route_after_slot_answer(state: AriaState) -> str:
    if state["missing_slots"]:
        return "slot_fill"
    return "confirmation"


def route_after_confirmation(state: AriaState) -> str:
    """If no confirmation needed (phase set to EXECUTING), go straight to execute."""
    if state["phase"] == DialoguePhase.EXECUTING:
        return "execute"
    # Confirmation shown — return to user and wait for yes/no
    return END


def should_execute(state: AriaState) -> str:
    """Check if user confirmed or denied the pending action."""
    last_message = next(
        (m.content.lower() for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        ""
    )
    affirmative = any(w in last_message for w in [
        "yes", "yeah", "yep", "do it", "send it", "go ahead", "confirm",
        "sure", "ok", "okay", "correct", "looks good", "that's right", "proceed"
    ])
    negative = any(w in last_message for w in [
        "no", "nope", "cancel", "stop", "don't", "wait", "hold on", "change"
    ])

    if affirmative:
        return "execute"
    if negative:
        return "response"
    # Ambiguous — re-run NLU to understand what they said
    return "nlu"


# ─── Build the graph ─────────────────────────────────────────────────────────

def build_aria_graph() -> StateGraph:
    graph = StateGraph(AriaState)

    # Nodes
    graph.add_node("dispatch",      dispatch_node)
    graph.add_node("nlu",           nlu_node)
    graph.add_node("slot_fill",     slot_fill_node)
    graph.add_node("slot_answer",   slot_answer_node)
    graph.add_node("confirmation",  confirmation_node)
    graph.add_node("check_confirm", check_confirm_node)
    graph.add_node("execute",       execute_node)
    graph.add_node("response",      response_node)
    graph.add_node("query_mode",    query_mode_node)

    # Entry point — dispatch routes based on current dialogue phase
    graph.set_entry_point("dispatch")

    graph.add_conditional_edges("dispatch", route_dispatch, {
        "nlu":           "nlu",
        "slot_answer":   "slot_answer",
        "check_confirm": "check_confirm",
        "response":      "response",
        "query_mode":    "query_mode",
    })

    # NLU routes: chitchat → response, missing slots → slot_fill, ready → confirmation
    graph.add_conditional_edges("nlu", route_after_nlu, {
        "slot_fill":    "slot_fill",
        "confirmation": "confirmation",
        "response":     "response",
    })

    # Slot fill asks question then returns to user (END)
    graph.add_edge("slot_fill", END)

    # Slot answer: more slots needed → slot_fill, all done → confirmation
    graph.add_conditional_edges("slot_answer", route_after_slot_answer, {
        "slot_fill":    "slot_fill",
        "confirmation": "confirmation",
    })

    # Confirmation: no-confirm intents → execute immediately; otherwise wait for user
    graph.add_conditional_edges("confirmation", route_after_confirmation, {
        "execute": "execute",
        END:       END,
    })

    # User's yes/no response: confirmed → execute, denied → response, unclear → nlu
    graph.add_conditional_edges("check_confirm", should_execute, {
        "execute":  "execute",
        "response": "response",
        "nlu":      "nlu",
    })

    # Query mode → END
    graph.add_edge("query_mode", END)

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
