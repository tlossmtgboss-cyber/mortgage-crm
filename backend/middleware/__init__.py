"""
Middleware package for the Perennia CRM backend.

Provides:
- AI Usage Tracking: Track token usage and costs per user
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

__all__ = [
    "AIUsageTracker",
    "log_ai_usage",
    "get_user_daily_cost",
    "get_user_cost_summary",
    "calculate_cost",
    "get_model_pricing",
    "DEFAULT_PRICING"
]
