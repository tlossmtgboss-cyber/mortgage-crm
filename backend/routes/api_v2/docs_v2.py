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
                "accept_header": (
                    "Send Accept: application/vnd.perennia.v2+json to request V2 semantics. "
                    "When this header is set on a V1 endpoint with a known V2 successor "
                    "(leads, loans, scheduler), the server responds with a 307 redirect to "
                    "the V2 equivalent. V2 responses include Content-Type: application/vnd.perennia.v2+json."
                ),
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
            "default": "300 requests per minute per authenticated user (30/min unauthenticated)",
            "pipeline_endpoints": "120 requests per minute",
            "headers": {
                "X-RateLimit-Limit": "Maximum requests per window",
                "X-RateLimit-Remaining": "Remaining requests in current window",
                "X-RateLimit-Reset": "Seconds until the rate limit window resets",
            },
            "exceeded_response": {
                "status": 429,
                "body": "RFC 7807 Problem Details with type 'rate-limit-exceeded'",
                "headers": "Retry-After header with seconds to wait",
            },
            "note": "Rate limit headers are included on every V2 response.",
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
            "sparse_fieldsets": {
                "description": (
                    "Use ?fields=id,name,stage to receive only the requested fields. "
                    "Supports dot-notation for nested fields (e.g. ?fields=id,contact.email). "
                    "The id field is always included."
                ),
                "example": "GET /api/v2/leads?fields=id,name,email,stage",
            },
            "link_headers": {
                "description": (
                    "Single-resource responses (GET by ID) include RFC 8288 Link headers "
                    "pointing to related resources. For example, a lead response includes "
                    "links to its associated loans and appointments."
                ),
                "example": '</api/v2/loans?lead_id=42>; rel="loans", </api/v2/scheduler/appointments?lead_id=42>; rel="appointments"',
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
