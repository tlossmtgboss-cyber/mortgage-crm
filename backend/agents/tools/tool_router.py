"""
Tool Router — Intent-Based Tool Selection

Given (role, user message, recent context), selects 25-40 tools to expose
to Claude for this turn. Keeps context window small without hurting routing accuracy.

Strategy (layered, cheap-to-expensive):
  1. Role filter — hard exclusion
  2. Intent classification — keyword/regex maps message to 1-3 intent tags
  3. Domain narrowing — pick tools whose intents overlap + always-on utilities
  4. Cap at MAX_TOOLS_PER_CALL — rank by specificity + recent usage
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_TOOLS_PER_CALL = 40
MIN_TOOLS_PER_CALL = 15


@dataclass
class RoutingContext:
    user_role: str
    user_message: str
    recent_tool_calls: list  # last ~10 tool names called this session
    agent_type: str          # "aria" | "receptionist" | "underwriter_copilot" | ...


# --- Intent classification ---------------------------------------------------

INTENT_PATTERNS = {
    "loan_query": [
        re.compile(r"\b(loan|deal|pipeline|application|1003)\b", re.I),
        re.compile(r"\b(stage|status|approval|underwriting)\b", re.I),
    ],
    "borrower_contact": [
        re.compile(r"\b(call|text|email|sms|reach out|follow up)\b", re.I),
        re.compile(r"\b(borrower|client|applicant)\b", re.I),
    ],
    "document_handling": [
        re.compile(r"\b(upload|download|document|paystub|w-?2|tax return|bank statement)\b", re.I),
        re.compile(r"\b(signature|docusign|esign|disclosure)\b", re.I),
    ],
    "guidelines_lookup": [
        re.compile(r"\b(fannie|freddie|fha|va|usda|jumbo|non-?qm)\b", re.I),
        re.compile(r"\b(guideline|overlay|ltv|dti|reserves|seasoning)\b", re.I),
    ],
    "calculation": [
        re.compile(r"\b(calculate|compute|payment|amortization|dti|ltv|apr)\b", re.I),
        re.compile(r"\$[\d,]+", re.I),
    ],
    "scheduling": [
        re.compile(r"\b(schedule|book|meeting|appointment|calendar)\b", re.I),
    ],
    "pipeline_mgmt": [
        re.compile(r"\b(assign|reassign|transfer|move|advance|stage)\b", re.I),
    ],
    "reporting": [
        re.compile(r"\b(report|metrics|dashboard|kpi|volume|forecast)\b", re.I),
    ],
    "outreach": [
        re.compile(r"\b(outreach|mass|bulk|campaign|broadcast)\b", re.I),
        re.compile(r"\b(mortgage review|annual review|refinance)\b", re.I),
    ],
}

ALWAYS_ON_TOOL_NAMES = {
    "get_current_user",
    "get_current_datetime",
    "search_across_all",
}

AGENT_DOMAIN_MAP = {
    "aria": {"pipeline", "borrower", "communication", "calendar", "outreach"},
    "voice_os": {"pipeline", "borrower", "communication", "calendar", "outreach"},
    "receptionist": {"communication", "calendar", "intake"},
    "underwriter_copilot": {"guidelines", "calculation", "documents"},
    "pipeline_analyst": {"pipeline", "reporting"},
    "compliance_checker": {"compliance", "guidelines"},
    "lead_nurturer": {"borrower", "communication"},
    "document_tracker": {"documents"},
    "rate_monitor": {"calculation", "reporting"},
    "content_creator": {"communication"},
    "scheduler": {"calendar"},
}


def classify_intents(message: str) -> set:
    hits = set()
    for intent, patterns in INTENT_PATTERNS.items():
        if any(p.search(message) for p in patterns):
            hits.add(intent)
    return hits


def route_tools_for_agent(
    agent_type: str,
    user_role: str,
    user_message: str,
    all_tools: list,
    recent_tool_calls: list = None,
) -> list:
    """
    Select tools to expose for this turn.

    Args:
        agent_type: Which agent is handling (e.g. "aria", "pipeline_analyst")
        user_role: User's RBAC role
        user_message: The user's message text
        all_tools: Full list of available tool definitions
        recent_tool_calls: Last ~10 tool names called this session

    Returns:
        Filtered list of tool definitions
    """
    recent = recent_tool_calls or []
    intents = classify_intents(user_message)
    domain_hint = AGENT_DOMAIN_MAP.get(agent_type, {"pipeline"})

    # For now, return all tools — intent-based filtering can be enabled
    # once tool definitions include domain/intent metadata.
    # The infrastructure is ready; flip the switch when ToolDefinition
    # gets .domains and .intents fields.
    if not intents and not domain_hint:
        return all_tools

    logger.debug(
        "Tool router: agent=%s intents=%s domains=%s total_tools=%d",
        agent_type, intents, domain_hint, len(all_tools),
    )

    return all_tools


def _recent_use_count(tool_name: str, recent: list) -> int:
    return sum(1 for n in recent if n == tool_name)
