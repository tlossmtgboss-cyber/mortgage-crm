"""
Core utilities for the mortgage CRM backend.

Provides:
- cache: In-memory and Redis caching utilities
- logging: Structured logging with structlog
"""

from .logging import (
    configure_logging,
    ensure_configured,
    get_logger,
    log_request,
    RequestLoggingMiddleware,
    LoggingContextMiddleware,
    request_id_var,
    user_id_var,
    tenant_id_var,
    get_request_id,
    set_request_id,
    get_user_id,
    set_user_id,
    get_tenant_id,
    set_tenant_id,
    clear_context,
)

__all__ = [
    # Configuration
    "configure_logging",
    "ensure_configured",
    # Logger
    "get_logger",
    # Request logging
    "log_request",
    "RequestLoggingMiddleware",
    "LoggingContextMiddleware",
    # Context variables
    "request_id_var",
    "user_id_var",
    "tenant_id_var",
    # Context getters/setters
    "get_request_id",
    "set_request_id",
    "get_user_id",
    "set_user_id",
    "get_tenant_id",
    "set_tenant_id",
    "clear_context",
]
