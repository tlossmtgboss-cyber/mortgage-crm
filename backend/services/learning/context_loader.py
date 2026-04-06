import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

logger = logging.getLogger(__name__)

async def load_context_scope(scope: str, scope_id: str, db: Session) -> dict:
    """Load learned context for a specific scope from agent_context_store.

    Args:
        scope: 'agent' | 'user' | 'branch' | 'org'
        scope_id: The ID within that scope
        db: Database session

    Returns:
        Merged context dict from all matching records
    """
    try:
        result = db.execute(text("""
            SELECT context_key, context_value, confidence, version
            FROM agent_context_store
            WHERE scope = :scope AND scope_id = :scope_id
            ORDER BY updated_at DESC
        """), {"scope": scope, "scope_id": str(scope_id)})

        context = {}
        for row in result.fetchall():
            key, value, confidence, version = row
            if confidence and confidence >= 0.5:  # Only use high-confidence context
                context[key] = value
        return context
    except Exception as e:
        logger.debug(f"Context load skipped ({scope}/{scope_id}): {e}")
        return {}


async def build_agent_context(agent_id: str, user_id: int, branch_id: int,
                               db: Session) -> dict:
    """Load all three context scopes and merge for agent injection.

    Priority: branch overrides user, user overrides agent base.
    Called at the start of every agent run.
    """
    agent_ctx = await load_context_scope("agent", agent_id, db)
    user_ctx = await load_context_scope("user", str(user_id), db)
    branch_ctx = await load_context_scope("branch", str(branch_id), db)

    # Branch rules override user preferences, user overrides agent defaults
    merged = {**agent_ctx, **user_ctx, **branch_ctx}

    return {
        "agent_context": agent_ctx,
        "user_context": user_ctx,
        "branch_context": branch_ctx,
        "merged_context": merged,
        "context_loaded_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_contexts(base: dict, user: dict, branch: dict) -> dict:
    """Branch overrides user; user overrides agent base."""
    return {**base, **user, **branch}


async def inject_context_into_state(state: dict, agent_id: str, user_id: int,
                                     branch_id: int, db: Session) -> dict:
    """Inject learned context into LangGraph state before agent run."""
    context = await build_agent_context(agent_id, user_id, branch_id, db)
    state["learned_context"] = context
    return state
