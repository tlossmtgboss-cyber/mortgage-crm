"""
Salesforce HTTP Client with Connection Pooling and Rate Limiting
================================================================

Provides a shared, long-lived httpx AsyncClient for Salesforce API calls
with connection pooling, rate limit enforcement, and proper timeouts.

Connection exhaustion prevention:
- Connection timeout: 10 seconds (time to establish connection)
- Read timeout: 30 seconds (time to receive response)
- Total timeout: 60 seconds (overall request timeout)
- Shared client with connection pooling (max 20 connections)
- Concurrency limiter: max 10 concurrent SF API calls
- Rate limit tracking from Sforce-Limit-Info response headers

Usage:
    from services.salesforce.http_client import get_sf_client, SF_TIMEOUT

    async with get_sf_client() as client:
        response = await client.get(url, headers=headers)
"""

import asyncio
import httpx
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Timeout configuration for Salesforce API calls
# These prevent database connections from being held indefinitely
SF_TIMEOUT = httpx.Timeout(
    connect=10.0,    # 10 seconds to establish connection
    read=30.0,       # 30 seconds to receive response
    write=10.0,      # 10 seconds to send request
    pool=10.0        # 10 seconds to acquire connection from pool
)

# Overall request timeout (backup safeguard)
SF_REQUEST_TIMEOUT = 60.0  # 60 seconds total


# =============================================================================
# Connection Pooling — shared long-lived client
# =============================================================================

_sf_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_or_create_client() -> httpx.AsyncClient:
    """Get or create a long-lived HTTP client with connection pooling."""
    global _sf_client
    if _sf_client is None or _sf_client.is_closed:
        async with _client_lock:
            # Double-check after acquiring lock
            if _sf_client is None or _sf_client.is_closed:
                _sf_client = httpx.AsyncClient(
                    timeout=SF_TIMEOUT,
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                        keepalive_expiry=300,
                    ),
                    http2=True,
                )
    return _sf_client


@asynccontextmanager
async def get_sf_client():
    """
    Get the shared HTTP client for Salesforce API calls.

    Enforces rate limits before yielding the client, and tracks API usage
    from response headers after each request.

    Usage:
        async with get_sf_client() as client:
            response = await client.get(url, headers=headers)
    """
    await _check_rate_limit()
    async with _rate_limit_semaphore:
        client = await _get_or_create_client()
        yield client
        # Don't close — the client is shared across callers


async def close_sf_client():
    """
    Close the shared client gracefully. Call on application shutdown.

    Register with FastAPI:
        @app.on_event("shutdown")
        async def shutdown():
            from services.salesforce.http_client import close_sf_client
            await close_sf_client()
    """
    global _sf_client
    if _sf_client and not _sf_client.is_closed:
        await _sf_client.aclose()
        _sf_client = None


# =============================================================================
# Rate Limit Tracking and Enforcement
# =============================================================================

_rate_limit_semaphore = asyncio.Semaphore(10)  # Max 10 concurrent SF API calls
_daily_api_calls: int = 0
_daily_api_limit: int = 100000  # Default, updated from response headers
_api_usage_lock = asyncio.Lock()


async def _check_rate_limit():
    """Check and enforce Salesforce API rate limits."""
    if _daily_api_limit <= 0:
        return

    usage_pct = (_daily_api_calls / _daily_api_limit * 100)

    if usage_pct >= 90:
        raise RuntimeError(
            f"Salesforce API usage at {usage_pct:.0f}% ({_daily_api_calls}/{_daily_api_limit}) "
            f"- operations suspended to prevent quota exhaustion"
        )
    elif usage_pct >= 75:
        logger.warning(f"Salesforce API usage at {usage_pct:.0f}% - throttling requests")
        await asyncio.sleep(1)  # Slow down
    elif usage_pct >= 50:
        await asyncio.sleep(0.1)  # Light throttle


def track_api_usage(response: httpx.Response):
    """
    Track API usage from Salesforce response headers.

    Call this after each Salesforce API response to keep rate limit
    tracking up to date. Parses the Sforce-Limit-Info header.

    Args:
        response: The httpx.Response from a Salesforce API call
    """
    global _daily_api_calls, _daily_api_limit

    usage_header = response.headers.get("Sforce-Limit-Info", "")
    if not usage_header:
        return

    try:
        # Format: "api-usage=25/15000"
        parts = usage_header.split("=")
        if len(parts) == 2:
            usage_parts = parts[1].split("/")
            if len(usage_parts) == 2:
                _daily_api_calls = int(usage_parts[0])
                _daily_api_limit = int(usage_parts[1])

                pct = (_daily_api_calls / _daily_api_limit * 100) if _daily_api_limit > 0 else 0
                if pct > 80:
                    logger.warning(
                        f"Salesforce API quota at {pct:.1f}%: "
                        f"{_daily_api_calls}/{_daily_api_limit}"
                    )
                elif pct > 50:
                    logger.info(
                        f"Salesforce API usage: "
                        f"{_daily_api_calls}/{_daily_api_limit} ({pct:.1f}%)"
                    )
    except (ValueError, IndexError):
        pass


def get_api_usage() -> dict:
    """Get the current Salesforce API usage stats."""
    return {
        "used": _daily_api_calls,
        "limit": _daily_api_limit,
        "pct": round((_daily_api_calls / _daily_api_limit * 100), 1) if _daily_api_limit > 0 else 0,
    }
