"""
09-tools/router.py

Tool router. Given (role, user message, recent context), selects 25-40 tools
to expose to Claude for this turn. The goal is to keep the context window
small without hurting routing accuracy.

Strategy (layered, cheap-to-expensive):
  1. Role filter — hard exclusion. Tools not in user's role are never exposed.
  2. Intent classification — lightweight keyword/regex or small-model classifier
     maps the user's message to 1-3 intent tags.
  3. Domain narrowing — pick tools whose intents overlap + always include
     "always_on" utility tools (get_current_user, format_date, etc.)
  4. Cap at MAX_TOOLS_PER_CALL — if still over, rank by specificity + recent usage.

Drop-in: backend/app/agents/tools/router.py
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.agents.tools.registry import ToolMetadata, registry
from app.agents.tools.usage_tracker import UsageTracker

logger = logging.getLogger(__name__)

MAX_TOOLS_PER_CALL = 40
MIN_TOOLS_PER_CALL = 15  # ensure Claude always has a functional toolbox


@dataclass
class RoutingContext:
    user_role: str
    user_message: str
    recent_tool_calls: list[str]    # last ~10 tool names called this session
    agent_type: str                 # "aria" | "receptionist" | "underwriter_copilot" | ...


# --- Intent classification (stage 2) ----------------------------------------

# Fast, cheap keyword/regex patterns. A small fine-tuned classifier is the
# upgrade path; this is 80% of the value at 1% of the cost.
INTENT_PATTERNS: dict[str, list[re.Pattern]] = {
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
}

# Always-on tools — every call gets these regardless of intent.
# Keep this list small (5-8 tools) or you erode the benefit.
ALWAYS_ON_TOOL_NAMES = {
    "get_current_user",
    "get_current_datetime",
    "get_user_preferences",
    "search_across_all",  # emergency broad-search escape hatch
}


def classify_intents(message: str) -> set[str]:
    hits: set[str] = set()
    for intent, patterns in INTENT_PATTERNS.items():
        if any(p.search(message) for p in patterns):
            hits.add(intent)
    return hits


async def route_tools(
    ctx: RoutingContext,
    *,
    usage: UsageTracker | None = None,
) -> list[ToolMetadata]:
    """Select tools to expose for this turn."""
    # Stage 1: role filter
    candidates = registry.for_role(ctx.user_role)

    # Stage 2: intent classification
    intents = classify_intents(ctx.user_message)

    # Stage 3: narrow by intent overlap
    if intents:
        narrowed = [t for t in candidates if t.intents & intents]
    else:
        # No clear intent — fall back to domain most relevant to agent type
        domain_hint = _agent_to_domains(ctx.agent_type)
        narrowed = [t for t in candidates if t.domains & domain_hint]

    # Always include the always-on set
    always_on = [t for t in candidates if t.name in ALWAYS_ON_TOOL_NAMES]

    selected = {t.name: t for t in always_on}
    for t in narrowed:
        selected[t.name] = t

    # Stage 4: ensure minimum toolbox — if we narrowed too hard, re-broaden
    if len(selected) < MIN_TOOLS_PER_CALL:
        remaining = [t for t in candidates if t.name not in selected]
        # Add by recent session usage, then by popularity
        remaining.sort(
            key=lambda t: (
                -_recent_use_count(t.name, ctx.recent_tool_calls),
                t.specificity,
            ),
        )
        for t in remaining:
            selected[t.name] = t
            if len(selected) >= MIN_TOOLS_PER_CALL:
                break

    # Stage 5: cap at max — rank by relevance if over
    if len(selected) > MAX_TOOLS_PER_CALL:
        ranked = sorted(
            selected.values(),
            key=lambda t: (
                # Always-on never gets dropped
                0 if t.name in ALWAYS_ON_TOOL_NAMES else 1,
                # Intent-matched tools preferred
                0 if t.intents & intents else 1,
                # Recent usage in session preferred
                -_recent_use_count(t.name, ctx.recent_tool_calls),
                # Then by specificity
                t.specificity,
            ),
        )
        selected = {t.name: t for t in ranked[:MAX_TOOLS_PER_CALL]}

    result = list(selected.values())
    logger.debug(
        "Tool router: role=%s intents=%s selected=%d/%d",
        ctx.user_role,
        intents,
        len(result),
        len(candidates),
    )

    if usage:
        await usage.record_routing(
            agent_type=ctx.agent_type,
            role=ctx.user_role,
            intents=intents,
            selected=[t.name for t in result],
        )

    return result


def _agent_to_domains(agent_type: str) -> set[str]:
    mapping = {
        "aria": {"pipeline", "borrower", "communication", "calendar"},
        "receptionist": {"communication", "calendar", "intake"},
        "underwriter_copilot": {"guidelines", "calculation", "documents"},
        "junior_lo": {"pipeline", "borrower", "calculation"},
        "marketing_rep": {"communication", "reporting"},
        "calculator": {"calculation"},
    }
    return mapping.get(agent_type, {"pipeline"})


def _recent_use_count(tool_name: str, recent: list[str]) -> int:
    return sum(1 for n in recent if n == tool_name)
