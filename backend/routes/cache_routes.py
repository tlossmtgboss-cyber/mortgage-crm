"""
Cache Management Routes
Extracted from inline_legacy_routes.py.

Includes:
- Cache status
- Cache metrics
- Cache clear is in api/cache_routes.py (not duplicated here)
- Cache invalidate per user

Lines ~16994-17072 from inline_legacy_routes.py.
"""
from fastapi import Depends, HTTPException
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Import models
from database.models import User


def register_cache_routes(app, get_db, get_current_user, **kwargs):
    """Register cache management routes."""

    @app.get("/api/v1/cache/status")
    async def cache_status():
        """Get cache status and statistics"""
        try:
            from core.cache import cache
            stats = await cache.get_stats()
            return {
                "cache": stats,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except ImportError:
            return {"cache": {"enabled": False}, "timestamp": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"error": "Internal server error", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/v1/cache/metrics")
    async def cache_metrics_endpoint():
        """Get cache performance metrics (hit/miss rates, speedup)"""
        try:
            from agents.tools.metrics import cache_metrics
            return {
                "metrics": cache_metrics.get_stats(),
                "by_tool": cache_metrics.get_stats_by_tool(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except ImportError:
            return {
                "metrics": {"total_queries": 0, "hit_rate": 0},
                "by_tool": {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {"error": "Internal server error", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/v1/cache/ai-stats")
    async def ai_cache_stats():
        """Get AI response cache statistics (embedding cache, Pinecone query cache, LLM cache)"""
        result = {"timestamp": datetime.now(timezone.utc).isoformat()}

        # 1. Embedding cache (in-memory LRU in pinecone_service)
        try:
            from integrations.pinecone_service import vector_memory
            result["embedding_cache"] = vector_memory.get_embedding_cache_stats()
        except Exception:
            result["embedding_cache"] = {"error": "unavailable"}

        # 2. Pinecone query cache (in-memory TTL in ai_memory_service)
        try:
            from ai_memory_service import _pinecone_query_cache
            result["pinecone_query_cache"] = _pinecone_query_cache.stats()
        except Exception:
            result["pinecone_query_cache"] = {"error": "unavailable"}

        # 3. LLM response cache (Redis-backed)
        try:
            from services.llm_cache_service import llm_cache
            result["llm_cache"] = llm_cache.get_stats()
        except Exception:
            result["llm_cache"] = {"error": "unavailable"}

        # 4. Tool execution cache (Redis-backed, in gather node)
        try:
            from core.cache import cache
            stats = await cache.get_stats()
            result["tool_cache"] = stats
        except Exception:
            result["tool_cache"] = {"error": "unavailable"}

        return result

    # Note: POST /api/v1/cache/clear is handled by api/cache_routes.py

    @app.post("/api/v1/cache/invalidate/user/{user_id}")
    async def invalidate_user_cache_endpoint(
        user_id: str,
        current_user: User = Depends(get_current_user)
    ):
        """Invalidate cache for a specific user"""
        # Only allow users to invalidate their own cache (or admins)
        if str(current_user.id) != user_id and current_user.role != 'admin':
            raise HTTPException(status_code=403, detail="Cannot invalidate other user's cache")

        try:
            from core.cache import invalidate_user_cache
            await invalidate_user_cache(user_id)
            return {
                "success": True,
                "message": f"Cache invalidated for user {user_id}"
            }
        except ImportError:
            return {"success": False, "message": "Cache module not available"}
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal server error")
