"""
Anthropic cost fetcher - fetches Claude API token usage.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class AnthropicCostFetcher(BaseCostFetcher):
    """Fetches Anthropic Claude API usage and costs."""

    provider_type = "anthropic"
    unit_type = "token"

    # Pricing per 1M tokens (as of early 2025)
    PRICING = {
        "claude-opus-4": {"input": Decimal("15.00"), "output": Decimal("75.00")},
        "claude-sonnet-4": {"input": Decimal("3.00"), "output": Decimal("15.00")},
        "claude-3-5-sonnet": {"input": Decimal("3.00"), "output": Decimal("15.00")},
        "claude-3-5-haiku": {"input": Decimal("0.80"), "output": Decimal("4.00")},
        "claude-3-opus": {"input": Decimal("15.00"), "output": Decimal("75.00")},
        "claude-3-sonnet": {"input": Decimal("3.00"), "output": Decimal("15.00")},
        "claude-3-haiku": {"input": Decimal("0.25"), "output": Decimal("1.25")},
    }

    def __init__(self, api_key: str = None):
        super().__init__(api_key or os.getenv("ANTHROPIC_API_KEY"))

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """
        Fetch Anthropic usage for the period.

        Note: Anthropic doesn't have a public usage API as of early 2025.
        Usage must be tracked manually or via webhook/logging.
        """
        if not self.validate_credentials():
            return FetchResult.error_result("Anthropic API key not configured")

        self.log_fetch_start(start_date, end_date)

        # Anthropic doesn't have a usage API - return empty result
        # Users should track usage via logging or manual entry
        return FetchResult.success_result(
            records=[],
            raw_response={"message": "Anthropic usage API not available. Use manual entry."}
        )

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate cost for token usage."""
        model = kwargs.get("model", "claude-3-5-sonnet")
        token_type = kwargs.get("token_type", "input")

        # Normalize model name
        model_key = model.lower().replace("claude-", "claude-")
        for key in self.PRICING:
            if key in model_key or model_key in key:
                pricing = self.PRICING[key]
                break
        else:
            pricing = self.PRICING["claude-3-5-sonnet"]

        rate = pricing.get(token_type, Decimal("3.00"))

        # Cost per 1M tokens
        return (quantity / 1_000_000) * rate
