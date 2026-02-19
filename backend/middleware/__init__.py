"""
Middleware package for the Perennia CRM backend.

Provides:
- AI Usage Tracking: Track token usage and costs per user
- Middleware Stack: Centralized middleware configuration
- Dynamic CORS: Database-driven CORS configuration
- Tenant Context: Multi-tenant isolation
- Impersonation Enforcement: Read-only mode for impersonation
- Rate Limiting: Per-user/IP rate limiting
- Structured Logging: JSON logging for production
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
]
