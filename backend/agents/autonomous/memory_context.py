"""
Memory Context for Autonomous Agents

Provides synchronous memory retrieval so background agents can personalize
decisions based on learned user preferences, directives, and behavioral patterns
— the same AgentMemory table the conversational orchestrator uses.

Two levels of context:
1. Per-LO: preferences, directives, and insights specific to a loan officer
2. Per-org: org-wide directives that apply to all autonomous actions

Results are cached per-execution so the same LO context isn't queried twice
when multiple agents run in the same tick.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Per-tick cache: cleared between agent loop iterations
_lo_cache: Dict[str, Dict[str, Any]] = {}
_org_cache: Dict[int, Dict[str, Any]] = {}


def clear_cache():
    """Clear the per-tick memory cache. Called between scheduler iterations."""
    _lo_cache.clear()
    _org_cache.clear()


def get_lo_memory_context(
    db: Session,
    user_id: int,
    organization_id: int,
) -> Dict[str, Any]:
    """
    Retrieve an LO's preferences, directives, and insights from AgentMemory.

    Returns a dict with:
        - preferences: dict of key->value for PREFERENCE memories
        - directives: list of active directive strings
        - insights: list of agent-derived insights
        - detail_level: 'concise' | 'moderate' | 'detailed' (default: moderate)
        - tone: 'casual' | 'professional' | 'formal' (default: professional)
        - contact_preferences: dict of channel preferences
        - custom_sla_overrides: dict of stage->days overrides
        - raw_memories: list of (key, value, type, confidence) tuples
    """
    cache_key = f"{user_id}:{organization_id}"
    if cache_key in _lo_cache:
        return _lo_cache[cache_key]

    context: Dict[str, Any] = {
        "preferences": {},
        "directives": [],
        "insights": [],
        "detail_level": "moderate",
        "tone": "professional",
        "contact_preferences": {},
        "custom_sla_overrides": {},
        "raw_memories": [],
    }

    try:
        rows = db.execute(text("""
            SELECT key, value, memory_type, confidence
            FROM agent_memories
            WHERE user_id = :user_id
              AND organization_id = :org_id
              AND superseded_by IS NULL
              AND (expires_at IS NULL OR expires_at > :now)
              AND memory_type IN ('preference', 'directive', 'insight', 'context')
            ORDER BY confidence DESC
            LIMIT 50
        """), {
            "user_id": user_id,
            "org_id": organization_id,
            "now": datetime.now(timezone.utc),
        }).fetchall()

        for row in rows:
            key, value, mem_type, confidence = row[0], row[1], row[2], row[3]
            context["raw_memories"].append((key, value, mem_type, confidence))

            if mem_type == "preference":
                context["preferences"][key] = value
                if key == "detail_level" and value in ("concise", "moderate", "detailed"):
                    context["detail_level"] = value
                elif key == "tone" and value in ("casual", "professional", "formal"):
                    context["tone"] = value
                elif key in ("preferred_contact_method", "preferred_channel", "contact_preference"):
                    context["contact_preferences"][key] = value
                elif key.startswith("sla_override_"):
                    stage = key.replace("sla_override_", "").upper()
                    try:
                        context["custom_sla_overrides"][stage] = int(value)
                    except (ValueError, TypeError):
                        pass

            elif mem_type == "directive":
                context["directives"].append(value)

            elif mem_type == "insight":
                context["insights"].append(value)

    except Exception as e:
        logger.warning("memory_context: failed to load LO %s memories: %s", user_id, e)

    _lo_cache[cache_key] = context
    return context


def get_org_directives(
    db: Session,
    organization_id: int,
) -> Dict[str, Any]:
    """
    Retrieve org-wide directives and settings from AgentMemory/AgentContext.

    These are memories where user_id corresponds to an admin or are explicitly
    org-scoped (stored with a well-known admin user_id or via agent_contexts).

    Returns:
        - directives: list of org-level directive strings
        - settings: dict of org-level context key/values
    """
    if organization_id in _org_cache:
        return _org_cache[organization_id]

    result: Dict[str, Any] = {
        "directives": [],
        "settings": {},
    }

    try:
        # Org-wide directives: memories tagged as directives from admin/manager users
        directive_rows = db.execute(text("""
            SELECT DISTINCT am.value
            FROM agent_memories am
            JOIN users u ON u.id = am.user_id
            WHERE am.organization_id = :org_id
              AND am.memory_type = 'directive'
              AND am.superseded_by IS NULL
              AND (am.expires_at IS NULL OR am.expires_at > :now)
              AND u.role IN ('admin', 'manager', 'branch_manager')
              AND am.confidence >= 0.7
            ORDER BY am.value
            LIMIT 20
        """), {
            "org_id": organization_id,
            "now": datetime.now(timezone.utc),
        }).fetchall()

        result["directives"] = [r[0] for r in directive_rows]

        # Org-level context settings
        ctx_rows = db.execute(text("""
            SELECT context_key, context_value
            FROM agent_contexts
            WHERE organization_id = :org_id
              AND context_key LIKE 'org_%'
            LIMIT 30
        """), {"org_id": organization_id}).fetchall()

        result["settings"] = {r[0]: r[1] for r in ctx_rows}

    except Exception as e:
        logger.warning("memory_context: failed to load org %s directives: %s", organization_id, e)

    _org_cache[organization_id] = result
    return result


def get_full_context(
    db: Session,
    user_id: int,
    organization_id: int,
) -> Dict[str, Any]:
    """
    Combined LO + org context in a single call.
    Convenience wrapper used by most autonomous agents.
    """
    lo_ctx = get_lo_memory_context(db, user_id, organization_id)
    org_ctx = get_org_directives(db, organization_id)

    return {
        **lo_ctx,
        "org_directives": org_ctx["directives"],
        "org_settings": org_ctx["settings"],
    }


def should_skip_contact(
    context: Dict[str, Any],
    channel: str,
) -> bool:
    """
    Check if a contact channel is blocked by user preferences or directives.

    Args:
        context: Result from get_lo_memory_context or get_full_context
        channel: 'sms', 'email', 'call', 'push'

    Returns True if the LO has explicitly opted out of this channel for automation.
    """
    prefs = context.get("contact_preferences", {})
    directives = context.get("directives", [])

    # Check explicit channel blocks in preferences
    for key, val in prefs.items():
        val_lower = (val or "").lower()
        if channel in val_lower and ("no" in val_lower or "never" in val_lower or "off" in val_lower):
            return True

    # Check directives for channel blocking
    channel_lower = channel.lower()
    block_phrases = [
        f"no {channel_lower}",
        f"disable {channel_lower}",
        f"stop {channel_lower}",
        f"don't {channel_lower}",
        f"do not {channel_lower}",
    ]
    for directive in directives:
        directive_lower = directive.lower()
        if any(phrase in directive_lower for phrase in block_phrases):
            return True

    return False


def get_sla_target(
    context: Dict[str, Any],
    stage: str,
    default_days: int,
) -> int:
    """
    Get the SLA target for a stage, respecting per-LO overrides.

    Args:
        context: Result from get_lo_memory_context or get_full_context
        stage: Loan stage (e.g., 'UNDERWRITING')
        default_days: Fallback if no override exists

    Returns SLA target in business days.
    """
    overrides = context.get("custom_sla_overrides", {})
    return overrides.get(stage.upper(), default_days)
