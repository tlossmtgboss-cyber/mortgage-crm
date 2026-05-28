"""
Centralized Anthropic Client Factory

Provides pre-configured Anthropic (sync) and AsyncAnthropic clients with:
- Connection timeout: 10 seconds
- Operation timeout: 300 seconds (5 minutes) for long-running LLM calls
- Max retries: 3 (SDK uses exponential backoff automatically)

All agent pipeline files should import from here instead of constructing
raw Anthropic() clients.  Peripheral services (routes, one-off scripts)
can adopt this gradually.

Usage:
    from agents.anthropic_client import get_anthropic_client, get_async_anthropic_client

    client = get_anthropic_client()            # sync
    async_client = get_async_anthropic_client() # async
"""

import os
import logging

import httpx
from anthropic import Anthropic, AsyncAnthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeout configuration
# ---------------------------------------------------------------------------
# connect  – TCP + TLS handshake (short, detect network issues fast)
# read     – waiting for first byte of response body
# write    – sending the request body
# pool     – waiting for a connection from the pool
# The overall ceiling is 300s (5 min) which covers the longest Sonnet calls.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = httpx.Timeout(
    300.0,        # total / default for any phase not explicitly set
    connect=10.0, # 10s to establish the connection
)
DEFAULT_MAX_RETRIES = 3  # SDK handles exponential backoff on retryable errors

# ---------------------------------------------------------------------------
# Module-level singletons (created lazily)
# ---------------------------------------------------------------------------
_sync_client: Anthropic | None = None
_async_client: AsyncAnthropic | None = None


def get_anthropic_client(
    *,
    api_key: str | None = None,
    timeout: httpx.Timeout | None = None,
    max_retries: int | None = None,
) -> Anthropic:
    """
    Return a configured synchronous Anthropic client.

    On first call (with default args) the client is cached at module level so
    the entire backend shares one connection pool.  Passing any non-default
    argument bypasses the cache and returns a fresh client -- useful for
    health-check endpoints that need a short timeout.
    """
    global _sync_client

    _api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    _timeout = timeout or DEFAULT_TIMEOUT
    _max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES

    # Return cached singleton when using defaults
    if api_key is None and timeout is None and max_retries is None:
        if _sync_client is None:
            _sync_client = Anthropic(
                api_key=_api_key,
                timeout=_timeout,
                max_retries=_max_retries,
            )
            logger.info(
                "Anthropic sync client initialised "
                "(timeout=%s, max_retries=%d)",
                _timeout,
                _max_retries,
            )
        return _sync_client

    # Non-default args: return a one-off client
    return Anthropic(
        api_key=_api_key,
        timeout=_timeout,
        max_retries=_max_retries,
    )


def get_async_anthropic_client(
    *,
    api_key: str | None = None,
    timeout: httpx.Timeout | None = None,
    max_retries: int | None = None,
) -> AsyncAnthropic:
    """
    Return a configured asynchronous Anthropic client.

    Same caching semantics as the sync variant.
    """
    global _async_client

    _api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    _timeout = timeout or DEFAULT_TIMEOUT
    _max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES

    if api_key is None and timeout is None and max_retries is None:
        if _async_client is None:
            _async_client = AsyncAnthropic(
                api_key=_api_key,
                timeout=_timeout,
                max_retries=_max_retries,
            )
            logger.info(
                "Anthropic async client initialised "
                "(timeout=%s, max_retries=%d)",
                _timeout,
                _max_retries,
            )
        return _async_client

    return AsyncAnthropic(
        api_key=_api_key,
        timeout=_timeout,
        max_retries=_max_retries,
    )


# ---------------------------------------------------------------------------
# Prompt caching helpers
# ---------------------------------------------------------------------------
# Anthropic's prompt caching caches everything from the start of the request
# up to the last content block with a ``cache_control`` marker.  Adding
# ``{"type": "ephemeral"}`` to the system block (and optionally the last
# tool definition) lets subsequent requests with the same prefix reuse the
# cached KV-cache state, reducing input token costs by up to 90 %.
#
# Usage:
#     from agents.anthropic_client import cached_system_block, cache_tool_definitions
#
#     response = client.messages.create(
#         model=model,
#         system=cached_system_block(system_prompt),
#         messages=messages,
#         tools=cache_tool_definitions(tools),
#     )
# ---------------------------------------------------------------------------


def cached_system_block(system_prompt: str) -> list:
    """Wrap a system prompt string with cache_control for Anthropic prompt caching.

    Returns the structured content-block list that the ``system`` parameter
    of ``messages.create()`` / ``messages.stream()`` accepts.
    """
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def cache_tool_definitions(tools: list | None) -> list | None:
    """Add cache_control to the last tool definition.

    This ensures the entire tool list is included in the cached prefix.
    Returns ``None`` unchanged, and never mutates the original list.
    """
    if not tools:
        return tools
    tools = list(tools)  # shallow copy
    last_tool = dict(tools[-1])
    last_tool["cache_control"] = {"type": "ephemeral"}
    tools[-1] = last_tool
    return tools
