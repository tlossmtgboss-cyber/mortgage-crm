# backend/api/webhooks.py
"""
Webhook endpoints for external system integrations and cache invalidation.
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class CacheInvalidationPayload(BaseModel):
    event: str  # "lead.updated", "loan.status_changed", etc.
    entity_type: str  # "lead", "loan", "contact", "rate"
    entity_id: Optional[int] = None
    user_id: Optional[str] = None


@router.post("/cache-invalidation")
async def handle_cache_invalidation(
    payload: CacheInvalidationPayload,
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")
):
    """
    Webhook endpoint for external systems to trigger cache invalidation.

    This allows CRM actions, database triggers, or external integrations
    to invalidate cached responses when data changes.

    Headers:
        X-Webhook-Secret: Required secret for authentication

    Request body:
    {
        "event": "lead.status_changed",
        "entity_type": "lead",
        "entity_id": 12345,
        "user_id": "user_123"  // Optional - invalidate for specific user
    }

    Events supported:
    - lead.created, lead.updated, lead.status_changed, lead.deleted
    - loan.created, loan.updated, loan.status_changed, loan.funded
    - rate.updated, rate.lock_changed
    - contact.updated
    """
    # Verify webhook secret
    expected_secret = os.getenv("WEBHOOK_SECRET")
    if not expected_secret:
        logger.warning("WEBHOOK_SECRET not configured - webhook disabled")
        raise HTTPException(503, "Webhook not configured")

    if x_webhook_secret != expected_secret:
        logger.warning(f"Invalid webhook secret attempt for event: {payload.event}")
        raise HTTPException(403, "Invalid webhook secret")

    invalidated = {
        "response_cache": [],
        "tool_cache": []
    }

    try:
        # Import caches
        from utils.cache import cache as response_cache
        from core.cache import cache as tool_cache

        # Invalidate based on entity type
        if payload.entity_type == "lead":
            # Response cache invalidations
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"lead_{payload.entity_id}")
                invalidated["response_cache"].append(f"lead_{payload.entity_id}: {count}")

            count = await response_cache.invalidate_by_intent("lead_status")
            invalidated["response_cache"].append(f"lead_status intent: {count}")

            count = await response_cache.invalidate_by_intent("pipeline_query")
            invalidated["response_cache"].append(f"pipeline_query intent: {count}")

            # Tool cache invalidations
            if payload.entity_id:
                await tool_cache.delete(f"perennia:agent:get_lead_details:{payload.entity_id}")
                invalidated["tool_cache"].append(f"get_lead_details:{payload.entity_id}")

            await tool_cache.delete_pattern("perennia:agent:pipeline*")
            invalidated["tool_cache"].append("pipeline patterns")

        elif payload.entity_type == "loan":
            # Response cache invalidations
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"loan_{payload.entity_id}")
                invalidated["response_cache"].append(f"loan_{payload.entity_id}: {count}")

            count = await response_cache.invalidate_by_intent("loan_details")
            invalidated["response_cache"].append(f"loan_details intent: {count}")

            count = await response_cache.invalidate_by_intent("pipeline_query")
            invalidated["response_cache"].append(f"pipeline_query intent: {count}")

            # Tool cache invalidations
            if payload.entity_id:
                await tool_cache.delete(f"perennia:agent:get_loan_details:{payload.entity_id}")
                invalidated["tool_cache"].append(f"get_loan_details:{payload.entity_id}")

            await tool_cache.delete_pattern("perennia:agent:pipeline*")
            invalidated["tool_cache"].append("pipeline patterns")

        elif payload.entity_type == "rate":
            # Rate changes affect lock decisions
            count = await response_cache.invalidate_by_intent("rate_lock")
            invalidated["response_cache"].append(f"rate_lock intent: {count}")

            await tool_cache.delete_pattern("perennia:agent:*rate*")
            invalidated["tool_cache"].append("rate patterns")

            await tool_cache.delete_pattern("perennia:agent:*market*")
            invalidated["tool_cache"].append("market patterns")

        elif payload.entity_type == "contact":
            if payload.entity_id:
                count = await response_cache.invalidate_pattern(f"contact_{payload.entity_id}")
                invalidated["response_cache"].append(f"contact_{payload.entity_id}: {count}")

        elif payload.entity_type == "task":
            count = await response_cache.invalidate_by_intent("tasks")
            invalidated["response_cache"].append(f"tasks intent: {count}")

            await tool_cache.delete_pattern("perennia:agent:*task*")
            invalidated["tool_cache"].append("task patterns")

        # If user_id provided, also invalidate user-specific caches
        if payload.user_id:
            count = await response_cache.invalidate_pattern(payload.user_id)
            invalidated["response_cache"].append(f"user {payload.user_id}: {count}")

        logger.info(f"[WEBHOOK] Cache invalidated for {payload.event}: {invalidated}")

        return {
            "status": "invalidated",
            "event": payload.event,
            "entity_type": payload.entity_type,
            "entity_id": payload.entity_id,
            "invalidated": invalidated
        }

    except ImportError as e:
        logger.warning(f"Cache module not available: {e}")
        return {
            "status": "skipped",
            "reason": "Cache not available",
            "event": payload.event
        }
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}", exc_info=True)
        raise HTTPException(500, f"Cache invalidation failed: {str(e)}")


@router.post("/data-sync")
async def handle_data_sync(
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")
):
    """
    Webhook to trigger full cache clear after bulk data sync.

    Use this after importing data or running migrations that affect
    multiple records.
    """
    expected_secret = os.getenv("WEBHOOK_SECRET")
    if not expected_secret or x_webhook_secret != expected_secret:
        raise HTTPException(403, "Invalid webhook secret")

    try:
        from utils.cache import cache as response_cache
        from core.cache import cache as tool_cache

        response_count = await response_cache.clear_all()
        await tool_cache.delete_pattern("perennia:agent:*")

        logger.info(f"[WEBHOOK] Full cache clear after data sync: {response_count} response cache entries")

        return {
            "status": "cleared",
            "response_cache_cleared": response_count,
            "tool_cache_cleared": True
        }

    except Exception as e:
        logger.error(f"Data sync cache clear failed: {e}")
        raise HTTPException(500, str(e))
