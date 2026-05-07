"""
V2 Developer Documentation Endpoint - Perennia AI

Provides a self-describing API overview for developers integrating
with the Perennia AI platform.

URL prefix: ``/api/v2/docs`` (applied by parent ``api_v2/__init__.py``)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["V2 Developer Docs"])


@router.get(
    "/docs",
    summary="API developer documentation (V2)",
    response_description="API overview, auth guide, rate limits, and versioning policy",
)
async def api_docs_v2(request: Request):
    """Return a self-describing API overview for developers.

    This endpoint provides machine-readable documentation covering:
    - API versioning policy and migration guide
    - Authentication methods
    - Rate limiting rules
    - Available V2 endpoints
    - Response envelope format
    - Error handling conventions
    """
    base_url = str(request.base_url).rstrip("/")

    return JSONResponse(content={
        "api": {
            "name": "Perennia AI API",
            "description": "AI-first operating system for loan officers. RESTful API for CRM data, pipeline management, and AI agent orchestration.",
            "version": "2.0",
            "base_url": f"{base_url}/api/v2",
            "documentation_url": f"{base_url}/api/v2/docs",
            "openapi_url": f"{base_url}/api/v2/openapi.json",
        },
        "versioning": {
            "current_version": "2.0",
            "supported_versions": ["1.0", "2.0"],
            "deprecation_policy": (
                "V1 endpoints are deprecated as of 2026-05-01. "
                "All V1 endpoints include Deprecation and Sunset headers. "
                "V1 will be sunset on 2027-01-01. Migrate to V2 before that date."
            ),
            "version_negotiation": {
                "url_prefix": "Use /api/v2/ path prefix for all V2 endpoints.",
                "accept_header": "Optionally send Accept: application/vnd.perennia.v2+json",
            },
            "migration_guide": {
                "pagination": (
                    "V1 uses offset/limit pagination. V2 uses cursor-based pagination. "
                    "Pass the cursor from meta.cursor to fetch the next page. "
                    "Check meta.has_more to know if more pages exist."
                ),
                "response_format": (
                    "V2 wraps all responses in {data, meta} envelope. "
                    "Errors use RFC 7807 Problem Details format."
                ),
                "dates": "All datetimes in V2 are ISO 8601 with mandatory timezone offsets.",
            },
        },
        "authentication": {
            "type": "Bearer Token (JWT)",
            "header": "Authorization: Bearer <token>",
            "token_endpoint": f"{base_url}/api/v1/token",
            "token_lifetime": "15 minutes (access), 7 days (refresh)",
            "refresh_endpoint": f"{base_url}/api/v1/token/refresh",
            "notes": (
                "Obtain a JWT by posting credentials to the token endpoint. "
                "Include the token in the Authorization header for all API requests. "
                "Use the refresh endpoint to obtain a new access token before expiry."
            ),
        },
        "rate_limits": {
            "default": "100 requests per minute per user",
            "burst": "20 requests per second",
            "headers": {
                "X-RateLimit-Limit": "Maximum requests per window",
                "X-RateLimit-Remaining": "Remaining requests in current window",
                "X-RateLimit-Reset": "UTC epoch seconds when the window resets",
            },
            "exceeded_response": {
                "status": 429,
                "body": "RFC 7807 Problem Details with type 'rate-limit-exceeded'",
            },
        },
        "endpoints": {
            "leads": {
                "list": {
                    "method": "GET",
                    "path": "/api/v2/leads",
                    "description": "List leads with cursor-based pagination",
                    "query_params": ["cursor", "limit", "stage", "source", "owner_id", "q", "fields"],
                },
                "get": {
                    "method": "GET",
                    "path": "/api/v2/leads/{lead_id}",
                    "description": "Get a single lead by ID",
                    "query_params": ["fields"],
                },
            },
            "loans": {
                "list": {
                    "method": "GET",
                    "path": "/api/v2/loans",
                    "description": "List loans with cursor-based pagination",
                    "query_params": ["cursor", "limit", "stage", "loan_type", "loan_officer_id", "q", "fields"],
                },
                "get": {
                    "method": "GET",
                    "path": "/api/v2/loans/{loan_id}",
                    "description": "Get a single loan by ID",
                    "query_params": ["fields"],
                },
            },
            "pipeline": {
                "summary": {
                    "method": "GET",
                    "path": "/api/v2/pipeline/summary",
                    "description": "Organization pipeline overview with stage counts, volumes, and risk metrics",
                    "query_params": ["loan_officer_id"],
                },
            },
            "scheduler": {
                "list": {
                    "method": "GET",
                    "path": "/api/v2/scheduler/appointments",
                    "description": "List appointments with cursor-based pagination",
                    "query_params": ["cursor", "limit", "status", "fields", "include"],
                },
                "get": {
                    "method": "GET",
                    "path": "/api/v2/scheduler/appointments/{id}",
                    "description": "Get a single appointment",
                    "query_params": ["fields", "include"],
                },
                "create": {
                    "method": "POST",
                    "path": "/api/v2/scheduler/appointments",
                    "description": "Create a new appointment",
                },
                "update": {
                    "method": "PATCH",
                    "path": "/api/v2/scheduler/appointments/{id}",
                    "description": "Partially update an appointment",
                },
                "cancel": {
                    "method": "DELETE",
                    "path": "/api/v2/scheduler/appointments/{id}",
                    "description": "Cancel an appointment",
                    "query_params": ["reason"],
                },
                "search": {
                    "method": "GET",
                    "path": "/api/v2/scheduler/appointments/search",
                    "description": "Search appointments with filters",
                    "query_params": ["q", "status", "meeting_type", "start_after", "start_before", "cursor", "limit", "fields", "include"],
                },
            },
        },
        "response_format": {
            "envelope": {
                "data": "The response payload (object or array)",
                "meta": {
                    "api_version": "Always '2.0'",
                    "timestamp": "ISO 8601 response timestamp",
                    "cursor": "Opaque cursor for next page (paginated endpoints only)",
                    "has_more": "Boolean indicating more pages exist",
                    "total": "Total count when available",
                },
                "included": "Related resources when ?include= is used (optional)",
            },
            "error_format": {
                "standard": "RFC 7807 Problem Details",
                "fields": {
                    "type": "URI identifying the problem type",
                    "title": "Short human-readable summary",
                    "status": "HTTP status code",
                    "detail": "Human-readable explanation",
                    "instance": "URI identifying this specific occurrence",
                    "errors": "Field-level validation errors (422 responses)",
                },
                "content_type": "application/problem+json",
            },
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
