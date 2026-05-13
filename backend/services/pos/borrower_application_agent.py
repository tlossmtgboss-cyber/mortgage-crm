"""
BorrowerApplicationAgent — the borrower-facing AI assistant.

Replaces GuidelinesChatAgent. Uses Claude Sonnet with tool-use to help
borrowers complete their 1003, answer appraisal/title questions, detect
risk, and escalate to LO calls via Smart Calendar.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / (
    "agents/perennia-prompts/core/borrower_application_agent.txt"
)

TOOL_DEFINITIONS = [
    {
        "name": "get_lo_availability",
        "description": "Fetch 3-5 available calendar slots for the assigned LO. Call when the borrower wants to schedule a call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer", "description": "The assigned loan officer's user ID"},
                "organization_id": {"type": "integer"},
                "duration_minutes": {"type": "integer", "default": 30},
                "days_ahead": {"type": "integer", "default": 5},
            },
            "required": ["lo_user_id", "organization_id"],
        },
    },
    {
        "name": "book_lo_meeting",
        "description": "Book a meeting with the assigned LO at a specific time slot the borrower chose.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer"},
                "organization_id": {"type": "integer"},
                "slot_start": {"type": "string", "description": "ISO datetime of the chosen slot"},
                "borrower_name": {"type": "string"},
                "borrower_email": {"type": "string"},
                "borrower_phone": {"type": "string"},
                "duration_minutes": {"type": "integer", "default": 30},
                "topic": {"type": "string", "default": "Application review"},
            },
            "required": ["lo_user_id", "organization_id", "slot_start", "borrower_name"],
        },
    },
    {
        "name": "propose_alternate_window",
        "description": "Search for calendar slots in a different date range if the borrower wants different times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer"},
                "organization_id": {"type": "integer"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "duration_minutes": {"type": "integer", "default": 30},
            },
            "required": ["lo_user_id", "organization_id", "start_date", "end_date"],
        },
    },
    {
        "name": "prompt_document_upload",
        "description": "Direct the borrower to upload a specific document. Returns a structured upload prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "description": "e.g. pay_stubs, w2, tax_returns, bank_statements, gift_letter"},
                "reason": {"type": "string", "description": "Why this document is needed"},
                "application_id": {"type": "string"},
            },
            "required": ["document_type", "reason", "application_id"],
        },
    },
    {
        "name": "emit_crm_event",
        "description": "Publish a CRM event (APPLICATION_ESCALATION, DOCUMENT_SUGGESTED, APPLICATION_STALL).",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "enum": ["APPLICATION_ESCALATION", "DOCUMENT_SUGGESTED", "APPLICATION_STALL"]},
                "organization_id": {"type": "integer"},
                "application_id": {"type": "string"},
                "contact_id": {"type": "integer"},
                "data": {"type": "object", "description": "Event payload (trigger, section, details)"},
            },
            "required": ["event_type", "organization_id", "application_id", "contact_id", "data"],
        },
    },
    {
        "name": "recall_borrower_context",
        "description": "Retrieve prior conversation history for this application (cross-session continuity).",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "organization_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["application_id", "organization_id"],
        },
    },
]


class BorrowerApplicationAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            return PROMPT_PATH.read_text()
        except FileNotFoundError:
            logger.warning("System prompt not found at %s — using fallback", PROMPT_PATH)
            return "You are Aria, the AI assistant in the Perennia borrower portal. Help borrowers complete their mortgage application."

    async def answer(
        self,
        *,
        question: str,
        loan_context: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: str | None = None,
        organization_id: int | None = None,
        contact_id: int | None = None,
        application_id: str | None = None,
    ) -> dict[str, Any]:
        messages = self._build_messages(question, loan_context, history, current_step)

        response = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.2,
            system=self._system_prompt,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )

        tool_results = await self._process_tool_calls(
            response, organization_id, contact_id, application_id
        )

        if tool_results:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0.2,
                system=self._system_prompt,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

        return self._parse_response(response)

    def _build_messages(
        self,
        question: str,
        loan_context: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: str | None,
    ) -> list[dict[str, Any]]:
        borrower_name = loan_context.get('borrower_name') or 'the borrower'
        lo_name = loan_context.get('lo_name') or 'the loan officer'
        context_block = f"""<application_context>
Borrower name: {borrower_name}
Loan officer name: {lo_name}
Current step: {current_step or 'unknown'}
Completion: {loan_context.get('completion_pct', 0)}%
Sections: {json.dumps(loan_context.get('sections', {}), indent=2)}
Loan: {json.dumps(loan_context.get('loan', {}), indent=2)}
PII flags: {json.dumps(loan_context.get('presence_flags', {}), indent=2)}
</application_context>

IMPORTANT: Address the borrower by their first name ({borrower_name.split()[0] if borrower_name != 'the borrower' else 'there'}). When mentioning the loan officer, use their name ({lo_name})."""

        messages = []
        messages.append({
            "role": "user",
            "content": f"[CONTEXT — do not repeat to borrower]\n{context_block}",
        })
        messages.append({
            "role": "assistant",
            "content": f"Understood. I have {borrower_name}'s application context loaded. Ready to help.",
        })

        for turn in history:
            role = "user" if turn["role"] == "borrower" else "assistant"
            messages.append({"role": role, "content": turn["content"]})

        messages.append({"role": "user", "content": question})
        return messages

    async def _process_tool_calls(
        self,
        response,
        organization_id: int | None,
        contact_id: int | None,
        application_id: str | None,
    ) -> list[dict[str, Any]] | None:
        tool_use_blocks = [
            block for block in response.content
            if block.type == "tool_use"
        ]
        if not tool_use_blocks:
            return None

        results = []
        for block in tool_use_blocks:
            result = await self._execute_tool(
                block.name, block.input,
                organization_id, contact_id, application_id,
            )
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        return results

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        organization_id: int | None,
        contact_id: int | None,
        application_id: str | None,
    ) -> dict[str, Any]:
        import asyncio
        from agents.tools import borrower_application as tools

        tool_input.setdefault("organization_id", organization_id)
        if "application_id" in tool_input or tool_name in ("prompt_document_upload", "emit_crm_event", "recall_borrower_context"):
            tool_input.setdefault("application_id", application_id)
        if "contact_id" in tool_input or tool_name == "emit_crm_event":
            tool_input.setdefault("contact_id", contact_id)

        tool_fn = getattr(tools, tool_name, None)
        if tool_fn is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            if asyncio.iscoroutinefunction(tool_fn):
                return await tool_fn(**tool_input)
            else:
                return await asyncio.to_thread(tool_fn, **tool_input)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
            return {"error": str(e)}

    def _parse_response(self, response) -> dict[str, Any]:
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        full_text = "\n".join(text_blocks)

        structured_output = self._extract_structured_output(full_text)
        content = self._strip_json_block(full_text)

        escalation_reason = None
        if structured_output and structured_output.get("escalate_to_human"):
            escalation_reason = structured_output.get("next_best_action", "Escalation triggered")

        follow_ups = []
        if structured_output:
            intent = structured_output.get("intent", "")
            if intent == "explain_field":
                section = structured_output.get("application_section", "")
                follow_ups = [
                    f"What documents do I need for {section}?",
                    "Can I talk to my loan officer about this?",
                ]
            elif intent == "doc_guidance":
                follow_ups = [
                    "Where do I upload documents?",
                    "What else do I need to provide?",
                ]
            elif intent == "escalation":
                follow_ups = [
                    "When is my loan officer available?",
                    "Can I schedule a call?",
                ]

        meeting_offered = bool(structured_output and structured_output.get("meeting_offered"))

        return {
            "content": content,
            "sources": [],
            "follow_ups": follow_ups[:3],
            "tokens_used": response.usage.output_tokens if response.usage else None,
            "escalation_reason": escalation_reason,
            "structured_output": structured_output,
            "meeting_offered": meeting_offered,
        }

    @staticmethod
    def _extract_structured_output(text: str) -> dict[str, Any] | None:
        pattern = r"```json\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("Failed to parse structured output JSON")
        return None

    @staticmethod
    def _strip_json_block(text: str) -> str:
        return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()
