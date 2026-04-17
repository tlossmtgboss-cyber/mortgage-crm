"""
Circuit-breaker HTTP client for Aria agent -> FastAPI backend tool calls.

All CRM data access goes through this client. The agent process never
imports from db, database.models, or services directly.

3-second timeout. 2 retries with exponential backoff. Graceful degradation.
"""
import os
import logging
from typing import Dict, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("aria.backend_client")

BACKEND_URL = os.environ.get("INTERNAL_BACKEND_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
BACKEND_TIMEOUT = 3.0

GRACEFUL_FALLBACK = (
    "I'm having a little trouble pulling that up right now. "
    "Let me have your loan officer send you an update directly — "
    "I'll flag it for them."
)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=0.3),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
)
async def call_backend_tool(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call a backend internal API endpoint with circuit-breaker retry logic."""
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = INTERNAL_API_KEY
    async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
        resp = await client.post(
            f"{BACKEND_URL}{endpoint}",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def call_backend_tool_safe(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call backend with graceful degradation -- returns fallback on failure."""
    try:
        return await call_backend_tool(endpoint, payload)
    except Exception as e:
        logger.warning(f"Backend tool call failed ({endpoint}): {e}")
        return {"error": True, "spoken_fallback": GRACEFUL_FALLBACK}
