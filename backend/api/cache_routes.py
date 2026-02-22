# api/cache_routes.py
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from utils.cache import cache


def _get_current_user():
    """Lazy import auth dependency to avoid circular imports."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


router = APIRouter(
    prefix="/cache",
    tags=["cache"],
    dependencies=[Depends(_get_current_user())],
)


class InvalidateRequest(BaseModel):
    pattern: Optional[str] = None
    intent: Optional[str] = None
    query: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/invalidate")
async def invalidate_cache(request: InvalidateRequest):
    """
    Invalidate cached queries

    Examples:
    - {"pattern": "lead_12345"} - Invalidates all queries mentioning lead_12345
    - {"intent": "pipeline_query"} - Invalidates all pipeline queries
    - {"query": "show my pipeline", "user_id": "user_123"} - Invalidates specific query
    """
    if request.query and request.user_id:
        await cache.invalidate(request.query, request.user_id)
        return {"status": "invalidated", "type": "specific_query"}

    if request.pattern:
        count = await cache.invalidate_pattern(request.pattern)
        return {"status": "invalidated", "type": "pattern", "count": count}

    if request.intent:
        count = await cache.invalidate_by_intent(request.intent)
        return {"status": "invalidated", "type": "intent", "count": count}

    raise HTTPException(400, "Must provide pattern, intent, or query+user_id")


@router.get("/stats")
async def get_cache_stats():
    """Get cache performance statistics"""
    return await cache.get_stats()


@router.post("/clear")
async def clear_cache(confirm: bool = False):
    """Clear all cache (requires confirmation)"""
    if not confirm:
        raise HTTPException(400, "Must set confirm=true to clear cache")

    count = await cache.clear_all()
    return {"status": "cleared", "count": count}


# =============================================================================
# CRM CONTEXT CACHE ENDPOINTS
# =============================================================================

@router.get("/crm-context/stats")
async def get_crm_context_cache_stats():
    """
    Get CRM context cache statistics.

    Returns hit rate, miss count, total keys cached, and TTL configuration.
    This is the cache for the expensive 12-query CRM context that runs on every AI chat.
    """
    try:
        from services.crm_context_cache import crm_context_cache
        return await crm_context_cache.get_stats()
    except ImportError:
        return {"enabled": False, "reason": "CRM context cache module not available"}
    except Exception as e:
        raise HTTPException(500, "Error getting cache stats")


@router.post("/crm-context/invalidate")
async def invalidate_crm_context_cache(
    user_id: Optional[int] = None,
    context_type: Optional[str] = None
):
    """
    Invalidate CRM context cache.

    Options:
    - No params: Clears ALL CRM context cache
    - user_id only: Clears all context for specific user
    - context_type only: Clears specific context type for all users
    - Both: Clears specific context type for specific user

    Context types: leads, loans, tasks, mum_clients, pipeline, activities,
                   referral_partners, team_performance, loan_officer_performance,
                   top_referral_borrowers, rate_lock_intelligence, pipeline_efficiency
    """
    try:
        from services.crm_context_cache import crm_context_cache

        if user_id and context_type:
            deleted = await crm_context_cache.invalidate_context_type(context_type, user_id)
            return {"status": "invalidated", "type": "user_context_type", "user_id": user_id, "context_type": context_type, "deleted": deleted}
        elif user_id:
            deleted = await crm_context_cache.invalidate_user_context(user_id)
            return {"status": "invalidated", "type": "user", "user_id": user_id, "deleted": deleted}
        elif context_type:
            deleted = await crm_context_cache.invalidate_context_type(context_type)
            return {"status": "invalidated", "type": "context_type", "context_type": context_type, "deleted": deleted}
        else:
            deleted = await crm_context_cache.invalidate_all()
            return {"status": "invalidated", "type": "all", "deleted": deleted}

    except ImportError:
        raise HTTPException(500, "CRM context cache module not available")
    except Exception as e:
        raise HTTPException(500, "Error invalidating cache")
