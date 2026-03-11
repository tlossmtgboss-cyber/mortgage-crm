"""
Perennia AI - Domain Exception Handlers for Standardized Error Responses

Maps domain exceptions from `exceptions.py` (PerenniaError hierarchy) to
consistent JSON error responses:

    {
        "error": {
            "code": "ENTITY_NOT_FOUND",
            "message": "Loan with id '123' not found",
            "status": 404
        }
    }

These handlers complement the existing APIException handlers in
`utils/error_handling.py`. Domain exceptions are raised by service-layer
code, while APIException subclasses are raised by route handlers directly.

Usage:
    from middleware.error_response import register_domain_exception_handlers
    register_domain_exception_handlers(app)
"""

import logging
import os
import traceback

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from exceptions import (
    PerenniaError,
    EntityNotFoundError,
    LoanNotFoundError,
    LeadNotFoundError,
    UserNotFoundError,
    DocumentNotFoundError,
    TenantIsolationError,
    AuthenticationError,
    AuthorizationError,
    ComplianceViolationError,
    SLABreachError,
    InvalidStageError,
    DuplicateEntityError,
    SalesforceError,
    TelephonyError,
    AgentToolError,
    AgentTimeoutError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _is_production() -> bool:
    """Check if running in production environment."""
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("ENVIRONMENT") == "production"
    )


def _build_error_body(code: str, message: str, http_status: int) -> dict:
    """Build the standardized error response body."""
    return {
        "error": {
            "code": code,
            "message": message,
            "status": http_status,
        }
    }


def _record_to_ring_buffer(request: Request, exc: Exception):
    """Record error to the ring buffer if available."""
    try:
        from utils.error_handling import _record_error
        _record_error(
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            error_msg=str(exc),
            tb=traceback.format_exc(),
        )
    except ImportError:
        pass


# =============================================================================
# DOMAIN EXCEPTION HANDLERS
# =============================================================================

async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    """Handle EntityNotFoundError and subclasses (404)."""
    logger.info(
        "Entity not found: %s (id=%s) - %s %s",
        exc.entity_type, exc.entity_id, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=_build_error_body(exc.code, exc.message, 404),
    )


async def tenant_isolation_handler(request: Request, exc: TenantIsolationError) -> JSONResponse:
    """Handle TenantIsolationError (403). Log full details server-side, return sanitized message."""
    logger.warning(
        "Tenant isolation violation: %s - %s %s (requesting_org=%s, target_org=%s)",
        exc.message, request.method, request.url.path,
        exc.requesting_org_id, exc.target_org_id,
    )
    # Never reveal org IDs to the client
    client_message = "Access denied" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=_build_error_body(exc.code, client_message, 403),
    )


async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Handle AuthenticationError (401)."""
    logger.info(
        "Authentication failed: %s - %s %s",
        exc.message, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=_build_error_body(exc.code, exc.message, 401),
    )


async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    """Handle AuthorizationError (403)."""
    logger.info(
        "Authorization denied: %s (required_role=%s) - %s %s",
        exc.message, exc.required_role, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=_build_error_body(exc.code, exc.message, 403),
    )


async def compliance_violation_handler(request: Request, exc: ComplianceViolationError) -> JSONResponse:
    """Handle ComplianceViolationError (422)."""
    logger.warning(
        "Compliance violation: %s (type=%s, severity=%s, loan=%s) - %s %s",
        exc.message, exc.violation_type, exc.severity, exc.loan_id,
        request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_body(exc.code, exc.message, 422),
    )


async def sla_breach_handler(request: Request, exc: SLABreachError) -> JSONResponse:
    """Handle SLABreachError (422)."""
    logger.warning(
        "SLA breach: %s (milestone=%s, days_overdue=%s) - %s %s",
        exc.message, exc.milestone, exc.days_overdue,
        request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_body(exc.code, exc.message, 422),
    )


async def invalid_stage_handler(request: Request, exc: InvalidStageError) -> JSONResponse:
    """Handle InvalidStageError (400)."""
    logger.info(
        "Invalid stage: %s - %s %s",
        exc.message, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_build_error_body(exc.code, exc.message, 400),
    )


async def duplicate_entity_handler(request: Request, exc: DuplicateEntityError) -> JSONResponse:
    """Handle DuplicateEntityError (409)."""
    logger.info(
        "Duplicate entity: %s - %s %s",
        exc.message, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=_build_error_body(exc.code, exc.message, 409),
    )


async def salesforce_error_handler(request: Request, exc: SalesforceError) -> JSONResponse:
    """Handle SalesforceError (502)."""
    logger.error(
        "Salesforce integration error: %s (sf_code=%s) - %s %s",
        exc.message, exc.sf_error_code, request.method, request.url.path,
    )
    _record_to_ring_buffer(request, exc)
    client_message = "Salesforce integration error" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=_build_error_body(exc.code, client_message, 502),
    )


async def telephony_error_handler(request: Request, exc: TelephonyError) -> JSONResponse:
    """Handle TelephonyError (502)."""
    logger.error(
        "Telephony error: %s (provider=%s) - %s %s",
        exc.message, exc.provider, request.method, request.url.path,
    )
    _record_to_ring_buffer(request, exc)
    client_message = "Telephony service error" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=_build_error_body(exc.code, client_message, 502),
    )


async def agent_tool_error_handler(request: Request, exc: AgentToolError) -> JSONResponse:
    """Handle AgentToolError (500)."""
    logger.error(
        "Agent tool error: %s (tool=%s) - %s %s",
        exc.message, exc.tool_name, request.method, request.url.path,
        exc_info=True,
    )
    _record_to_ring_buffer(request, exc)
    client_message = "AI agent encountered an error" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_body(exc.code, client_message, 500),
    )


async def agent_timeout_handler(request: Request, exc: AgentTimeoutError) -> JSONResponse:
    """Handle AgentTimeoutError (504)."""
    logger.error(
        "Agent timeout: %s (agent=%s, timeout=%ss) - %s %s",
        exc.message, exc.agent_name, exc.timeout_seconds,
        request.method, request.url.path,
    )
    _record_to_ring_buffer(request, exc)
    client_message = "AI agent timed out" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content=_build_error_body(exc.code, client_message, 504),
    )


async def perennia_error_fallback_handler(request: Request, exc: PerenniaError) -> JSONResponse:
    """
    Catch-all for any PerenniaError subclass that doesn't have a specific handler.
    This prevents domain exceptions from falling through to the generic Exception handler.
    """
    logger.error(
        "Unhandled domain error: %s (code=%s) - %s %s",
        exc.message, exc.code, request.method, request.url.path,
        exc_info=True,
    )
    _record_to_ring_buffer(request, exc)
    client_message = "An error occurred" if _is_production() else exc.message
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_body(exc.code, client_message, 500),
    )


# =============================================================================
# REGISTRATION
# =============================================================================

def register_domain_exception_handlers(app: FastAPI):
    """
    Register exception handlers for all domain exceptions from exceptions.py.

    Handler priority in FastAPI: more specific exception classes are checked
    first, so registering both EntityNotFoundError and PerenniaError works
    correctly -- a LoanNotFoundError will match EntityNotFoundError before
    falling through to PerenniaError.
    """
    # 404 - Entity not found (covers LoanNotFoundError, LeadNotFoundError, etc.)
    app.add_exception_handler(EntityNotFoundError, entity_not_found_handler)

    # 401 - Authentication
    app.add_exception_handler(AuthenticationError, authentication_error_handler)

    # 403 - Authorization / Tenant isolation
    app.add_exception_handler(TenantIsolationError, tenant_isolation_handler)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)

    # 400 - Bad request / validation
    app.add_exception_handler(InvalidStageError, invalid_stage_handler)

    # 409 - Conflict
    app.add_exception_handler(DuplicateEntityError, duplicate_entity_handler)

    # 422 - Business rule violations
    app.add_exception_handler(ComplianceViolationError, compliance_violation_handler)
    app.add_exception_handler(SLABreachError, sla_breach_handler)

    # 502 - External service errors
    app.add_exception_handler(SalesforceError, salesforce_error_handler)
    app.add_exception_handler(TelephonyError, telephony_error_handler)

    # 500/504 - AI agent errors
    app.add_exception_handler(AgentToolError, agent_tool_error_handler)
    app.add_exception_handler(AgentTimeoutError, agent_timeout_handler)

    # Catch-all for any PerenniaError subclass without a specific handler
    app.add_exception_handler(PerenniaError, perennia_error_fallback_handler)

    logger.info("Domain exception handlers registered (14 exception types)")
