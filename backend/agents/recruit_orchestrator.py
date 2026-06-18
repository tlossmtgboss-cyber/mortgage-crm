"""
Recruiting Chatbot Orchestrator

Lightweight LangGraph orchestrator for the public-facing recruiting chatbot.
Unlike the CRM orchestrator (22 agents, 210+ tools), this is a single
conversational agent scoped to:
  - Answering candidate questions from the org knowledge base
  - Collecting applicant contact information
  - Providing job info and booking links

Flow: retrieve_context → generate_response → check_for_application → END
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

from anthropic import Anthropic
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from .anthropic_client import get_anthropic_client

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class RecruitChatState(TypedDict):
    session_id: str
    org_id: int
    org_name: str
    messages: List[dict]             # OpenAI-format message history
    collected_info: dict             # name, email, phone, nmls captured so far
    kb_context: str                  # retrieved KB chunks injected into system prompt
    tool_results: dict               # results from tool calls
    response: str                    # final response to send
    should_create_application: bool  # signal to create mm_candidates row


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool_use format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the organization's knowledge base for answers about positions, "
            "culture, benefits, compensation, requirements, and other recruiting topics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The candidate's question or search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_open_positions",
        "description": "Get a list of currently open job postings for this organization.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_booking_link",
        "description": (
            "Get a link for candidates to schedule an interview or introductory call "
            "with a recruiter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "collect_applicant_info",
        "description": (
            "Collect applicant contact information to create their application. "
            "Call this when the candidate provides their name, email, or phone number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Candidate's full name"},
                "email": {"type": "string", "description": "Candidate's email address"},
                "phone": {"type": "string", "description": "Candidate's phone number (optional)"},
                "nmls_number": {"type": "string", "description": "Candidate's NMLS license number (optional)"},
            },
            "required": ["name", "email"],
        },
    },
]


# ---------------------------------------------------------------------------
# Node: retrieve_context
# ---------------------------------------------------------------------------

async def retrieve_context(state: RecruitChatState, db: Session) -> RecruitChatState:
    """Embed the latest user message and pull relevant KB chunks."""
    from services.recruit_kb_service import retrieve_relevant_chunks

    messages = state.get("messages", [])
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            user_message = content if isinstance(content, str) else str(content)
            break

    kb_context = ""
    if user_message:
        try:
            chunks = await retrieve_relevant_chunks(
                query=user_message,
                org_id=state["org_id"],
                db=db,
                top_k=5,
            )
            if chunks:
                kb_context = "\n\n---\n\n".join(chunks)
        except Exception as e:
            logger.warning("retrieve_context: KB lookup failed: %s", e)

    return {**state, "kb_context": kb_context}


# ---------------------------------------------------------------------------
# Node: generate_response
# ---------------------------------------------------------------------------

async def generate_response(
    state: RecruitChatState,
    anthropic_client: Anthropic,
    db: Session,
) -> RecruitChatState:
    """Call Claude with full conversation history + KB context. Handle tool use."""
    from services.recruit_kb_service import retrieve_relevant_chunks
    from sqlalchemy import text

    org_name = state.get("org_name", "our organization")
    kb_context = state.get("kb_context", "")
    org_id = state["org_id"]

    system_prompt = (
        f"You are a recruiting assistant for {org_name}. "
        "Help candidates learn about our positions and apply. "
        "If a candidate wants to apply, collect their name, email, and phone number. "
        "Do not ask for SSN, financial information, or any sensitive personal data beyond "
        "name, email, phone, and optionally NMLS license number. "
        "Be warm, concise, and professional."
    )

    if kb_context:
        system_prompt += (
            "\n\nRelevant information from our knowledge base:\n\n"
            f"{kb_context}"
        )

    messages = state.get("messages", [])
    collected_info = state.get("collected_info", {})

    # First Claude call
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
        tools=TOOLS,
    )

    # Handle tool use in a simple loop (max 3 tool rounds to avoid runaway)
    tool_results_accumulated: Dict[str, Any] = {}
    for _ in range(3):
        if response.stop_reason != "tool_use":
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            break

        # Build tool result messages
        tool_result_content = []
        for block in tool_use_blocks:
            tool_name = block.name
            tool_input = block.input

            result_text = ""
            try:
                if tool_name == "search_knowledge_base":
                    chunks = await retrieve_relevant_chunks(
                        query=tool_input.get("query", ""),
                        org_id=org_id,
                        db=db,
                        top_k=5,
                    )
                    result_text = "\n\n".join(chunks) if chunks else "No relevant information found."
                    tool_results_accumulated["kb_search"] = result_text

                elif tool_name == "get_open_positions":
                    try:
                        rows = db.execute(
                            text("""
                                SELECT title, department, location, employment_type
                                FROM mm_job_postings
                                WHERE organization_id = :org_id
                                  AND status = 'active'
                                ORDER BY created_at DESC
                                LIMIT 20
                            """),
                            {"org_id": org_id},
                        ).fetchall()
                        if rows:
                            positions = [
                                f"- {r.title}" +
                                (f" ({r.department})" if r.department else "") +
                                (f" — {r.location}" if getattr(r, 'location', None) else "")
                                for r in rows
                            ]
                            result_text = "Open positions:\n" + "\n".join(positions)
                        else:
                            result_text = "No open positions found at this time."
                    except Exception as e:
                        result_text = "Position information is not available right now."
                        logger.warning("get_open_positions query failed: %s", e)
                    tool_results_accumulated["open_positions"] = result_text

                elif tool_name == "get_booking_link":
                    try:
                        row = db.execute(
                            text(
                                "SELECT booking_slug FROM organizations WHERE id = :org_id"
                            ),
                            {"org_id": org_id},
                        ).fetchone()
                        slug = row.booking_slug if row and row.booking_slug else None
                    except Exception:
                        slug = None
                    if slug:
                        result_text = (
                            f"Candidates can schedule time here: "
                            f"https://app.perenniaai.com/book/{slug}"
                        )
                    else:
                        result_text = (
                            "Please reach out directly via email to schedule an interview. "
                            "Our team will get back to you shortly."
                        )
                    tool_results_accumulated["booking_link"] = result_text

                elif tool_name == "collect_applicant_info":
                    name = tool_input.get("name", "")
                    email = tool_input.get("email", "")
                    phone = tool_input.get("phone", "")
                    nmls = tool_input.get("nmls_number", "")

                    if name:
                        collected_info["name"] = name
                    if email:
                        collected_info["email"] = email
                    if phone:
                        collected_info["phone"] = phone
                    if nmls:
                        collected_info["nmls_number"] = nmls

                    result_text = (
                        f"Information collected: name={name}, email={email}"
                        + (f", phone={phone}" if phone else "")
                        + (f", nmls={nmls}" if nmls else "")
                    )
                    tool_results_accumulated["applicant_info"] = collected_info

                else:
                    result_text = f"Tool {tool_name} is not available."

            except Exception as e:
                logger.error("Tool %s failed: %s", tool_name, e)
                result_text = "Tool execution failed."

            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })

        # Append assistant turn with tool use blocks, then tool results
        assistant_content = [b.model_dump() for b in response.content]
        extended_messages = messages + [
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": tool_result_content},
        ]

        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=extended_messages,
            tools=TOOLS,
        )

    # Extract final text response
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text += block.text

    return {
        **state,
        "response": final_text,
        "collected_info": collected_info,
        "tool_results": tool_results_accumulated,
    }


# ---------------------------------------------------------------------------
# Node: check_for_application
# ---------------------------------------------------------------------------

async def check_for_application(state: RecruitChatState) -> RecruitChatState:
    """Set should_create_application=True when we have name + email."""
    info = state.get("collected_info", {})
    has_name = bool(info.get("name", "").strip())
    has_email = bool(info.get("email", "").strip())
    return {**state, "should_create_application": has_name and has_email}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph(anthropic_client: Anthropic, db: Session) -> Any:
    """Build and compile the recruiting chatbot StateGraph."""

    async def _retrieve_context(state: RecruitChatState) -> RecruitChatState:
        return await retrieve_context(state, db)

    async def _generate_response(state: RecruitChatState) -> RecruitChatState:
        return await generate_response(state, anthropic_client, db)

    async def _check_for_application(state: RecruitChatState) -> RecruitChatState:
        return await check_for_application(state)

    graph = StateGraph(RecruitChatState)
    graph.add_node("retrieve_context", _retrieve_context)
    graph.add_node("generate_response", _generate_response)
    graph.add_node("check_for_application", _check_for_application)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_response")
    graph.add_edge("generate_response", "check_for_application")
    graph.add_edge("check_for_application", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_recruit_chat(
    session_id: str,
    org_id: int,
    org_name: str,
    user_message: str,
    message_history: List[dict],
    db: Session,
    anthropic_client: Optional[Anthropic] = None,
) -> dict:
    """
    Run one turn of the recruiting chatbot.

    Returns:
        {response: str, collected_info: dict, should_create_application: bool}
    """
    if anthropic_client is None:
        anthropic_client = get_anthropic_client()

    # Append the new user message to history
    messages = list(message_history) + [{"role": "user", "content": user_message}]

    initial_state: RecruitChatState = {
        "session_id": session_id,
        "org_id": org_id,
        "org_name": org_name,
        "messages": messages,
        "collected_info": {},
        "kb_context": "",
        "tool_results": {},
        "response": "",
        "should_create_application": False,
    }

    try:
        compiled = _build_graph(anthropic_client, db)
        final_state = await compiled.ainvoke(initial_state)
    except Exception as e:
        logger.exception("run_recruit_chat: orchestrator error for session %s: %s", session_id, e)
        final_state = {
            **initial_state,
            "response": (
                "I'm sorry, I encountered an issue processing your message. "
                "Please try again in a moment."
            ),
        }

    return {
        "response": final_state.get("response", ""),
        "collected_info": final_state.get("collected_info", {}),
        "should_create_application": final_state.get("should_create_application", False),
    }
