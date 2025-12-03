# api/cache_routes.py
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils.cache import cache

router = APIRouter(prefix="/cache", tags=["cache"])


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
