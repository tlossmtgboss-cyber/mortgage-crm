"""
Salesforce HTTP Client with Timeout Configuration
=================================================

Provides a properly configured httpx AsyncClient for Salesforce API calls
with connection and read timeouts to prevent hanging connections.

Connection exhaustion prevention:
- Connection timeout: 10 seconds (time to establish connection)
- Read timeout: 30 seconds (time to receive response)
- Total timeout: 60 seconds (overall request timeout)

Usage:
    from services.salesforce.http_client import get_sf_client, SF_TIMEOUT

    async with get_sf_client() as client:
        response = await client.get(url, headers=headers)
"""

import httpx
import logging

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


def get_sf_client() -> httpx.AsyncClient:
    """
    Get a properly configured httpx AsyncClient for Salesforce API calls.

    Returns:
        httpx.AsyncClient with appropriate timeouts configured

    Usage:
        async with get_sf_client() as client:
            response = await client.get(url, headers=headers)
    """
    return httpx.AsyncClient(
        timeout=SF_TIMEOUT,
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=10,        # Max concurrent connections
            max_keepalive_connections=5,  # Keep-alive connections
            keepalive_expiry=30.0      # Close idle connections after 30s
        )
    )


async def sf_request(
    method: str,
    url: str,
    headers: dict = None,
    params: dict = None,
    json: dict = None,
    timeout: float = None
) -> httpx.Response:
    """
    Make a Salesforce API request with proper timeout handling.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        url: Full URL to request
        headers: Request headers
        params: Query parameters
        json: JSON body for POST/PATCH
        timeout: Override default timeout (seconds)

    Returns:
        httpx.Response object

    Raises:
        httpx.TimeoutException: If request times out
        httpx.HTTPError: For other HTTP errors
    """
    request_timeout = timeout or SF_REQUEST_TIMEOUT

    async with get_sf_client() as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json,
                timeout=request_timeout
            )
            return response
        except httpx.TimeoutException as e:
            logger.error(f"Salesforce API timeout after {request_timeout}s: {method} {url[:100]}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"Salesforce API error: {method} {url[:100]} - {e}")
            raise
