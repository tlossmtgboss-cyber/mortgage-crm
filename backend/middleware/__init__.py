"""
Middleware package for the Perennia CRM backend.

Provides:
- AI Usage Tracking: Track token usage and costs per user
- Middleware Stack: Centralized middleware configuration
- Dynamic CORS: Database-driven CORS configuration
- Tenant Context: Multi-tenant isolation
- Impersonation Enforcement: Read-only mode for impersonation
- Rate Limiting: Per-user/IP rate limiting (Redis-based middleware + in-memory decorator)
- Endpoint Rate Limiter: Decorator-based per-endpoint rate limiting (no Redis)
- AI Cost Tracker: Per-org AI budget enforcement
- Structured Logging: JSON logging for production
- Idempotency: Prevent duplicate webhook operations via X-Idempotency-Key
- PII Response Filter: Scans API responses for PII leaks, auto-masks portal responses
- Request Logging: Per-request structured JSON logging with request_id propagation
- RBAC Enforcement: Defense-in-depth role checks on admin/manager routes
"""

from .ai_usage_middleware import (
    AIUsageTracker,
    log_ai_usage,
    get_user_daily_cost,
    get_user_cost_summary,
    calculate_cost,
    get_model_pricing,
    DEFAULT_PRICING
)

from .stack import (
    configure_middleware,
    configure_production_hardening,
    configure_datadog_monitoring,
)

from .pii_log_filter import PIIRedactionFilter, install_pii_filter

from .idempotency import IdempotencyMiddleware, IdempotencyStore, CachedResponse

from .rate_limiter import (
    RateLimiter,
    get_rate_limiter,
    rate_limit,
    UPLOAD_LIMIT,
    AI_LIMIT,
    READ_LIMIT,
    WRITE_LIMIT,
    AUTH_LIMIT,
    ESIGN_TOKEN_LIMIT,
)

from .ai_cost_tracker import (
    AIBudgetTracker,
    get_ai_budget_tracker,
    OPERATION_COSTS,
)

from .pii_response_filter import PIIResponseFilterMiddleware

from .request_logging import RequestLoggingMiddleware

from .rbac_enforcement import RBACEnforcementMiddleware

__all__ = [
    # AI Usage
    "AIUsageTracker",
    "log_ai_usage",
    "get_user_daily_cost",
    "get_user_cost_summary",
    "calculate_cost",
    "get_model_pricing",
    "DEFAULT_PRICING",
    # Middleware Stack
    "configure_middleware",
    "configure_production_hardening",
    "configure_datadog_monitoring",
    # PII Log Filter
    "PIIRedactionFilter",
    "install_pii_filter",
    # Idempotency
    "IdempotencyMiddleware",
    "IdempotencyStore",
    "CachedResponse",
    # Endpoint Rate Limiter
    "RateLimiter",
    "get_rate_limiter",
    "rate_limit",
    "UPLOAD_LIMIT",
    "AI_LIMIT",
    "READ_LIMIT",
    "WRITE_LIMIT",
    "AUTH_LIMIT",
    "ESIGN_TOKEN_LIMIT",
    # AI Cost Tracker
    "AIBudgetTracker",
    "get_ai_budget_tracker",
    "OPERATION_COSTS",
    # PII Response Filter
    "PIIResponseFilterMiddleware",
    # Request Logging
    "RequestLoggingMiddleware",
    # RBAC Enforcement
    "RBACEnforcementMiddleware",
]
