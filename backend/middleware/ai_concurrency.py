"""AI agent concurrency controls.

Prevents any single tenant from monopolizing LLM API capacity.
Global semaphore limits total concurrent AI requests across all tenants.
Per-tenant counter provides fair-share isolation.

Enterprise Readiness Check 6.14
"""
import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import HTTPException

logger = logging.getLogger(__name__)

MAX_CONCURRENT_AI_GLOBAL = int(os.getenv("MAX_CONCURRENT_AI_REQUESTS", "20"))
MAX_CONCURRENT_AI_PER_TENANT = int(os.getenv("MAX_CONCURRENT_AI_PER_TENANT", "5"))

_global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_GLOBAL)
_tenant_counts: dict[int, int] = defaultdict(int)
_tenant_lock = asyncio.Lock()


@asynccontextmanager
async def ai_concurrency_gate(org_id: int):
    """Async context manager that enforces AI concurrency limits.

    Usage:
        async with ai_concurrency_gate(org_id):
            result = await call_llm(...)

    Raises:
        HTTPException 429 if per-tenant limit is reached.
        HTTPException 503 if global capacity is exhausted (30s timeout).
    """
    # --- Per-tenant check ---
    async with _tenant_lock:
        if _tenant_counts[org_id] >= MAX_CONCURRENT_AI_PER_TENANT:
            logger.warning(
                "AI concurrency limit reached for org %d (%d/%d)",
                org_id, _tenant_counts[org_id], MAX_CONCURRENT_AI_PER_TENANT,
            )
            raise HTTPException(
                status_code=429,
                detail="Too many concurrent AI requests. Please wait and retry.",
                headers={"Retry-After": "5"},
            )
        _tenant_counts[org_id] += 1

    # Per-tenant slot reserved. Track whether we've already released it
    # so the finally block doesn't double-decrement.
    tenant_released = False

    try:
        # --- Global semaphore with timeout ---
        try:
            await asyncio.wait_for(_global_semaphore.acquire(), timeout=30.0)
        except asyncio.TimeoutError:
            # Release per-tenant slot and mark released before raising
            async with _tenant_lock:
                _tenant_counts[org_id] = max(0, _tenant_counts[org_id] - 1)
            tenant_released = True
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily at capacity. Please retry.",
                headers={"Retry-After": "10"},
            )

        # Both slots acquired -- yield to caller
        try:
            yield
        finally:
            _global_semaphore.release()
    finally:
        if not tenant_released:
            async with _tenant_lock:
                _tenant_counts[org_id] = max(0, _tenant_counts[org_id] - 1)


def get_ai_concurrency_stats() -> dict:
    """Return current AI concurrency statistics for monitoring."""
    return {
        "global_available": _global_semaphore._value,
        "global_max": MAX_CONCURRENT_AI_GLOBAL,
        "per_tenant_max": MAX_CONCURRENT_AI_PER_TENANT,
        "tenant_counts": dict(_tenant_counts),
    }
