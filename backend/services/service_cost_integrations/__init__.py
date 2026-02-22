"""
Service Cost Integration Fetchers

This module provides API integrations for automatically fetching usage data
from various service providers.

Supported integrations:
- Stripe (payment processing fees)
- OpenAI (token usage)
- Anthropic (token usage)
- Telnyx (SMS/voice usage)
- SendGrid (email stats)
- AWS (S3 storage costs)
"""

from .base_fetcher import BaseCostFetcher, FetchResult
from .stripe_cost_fetcher import StripeCostFetcher
from .openai_cost_fetcher import OpenAICostFetcher
from .anthropic_cost_fetcher import AnthropicCostFetcher
from .sendgrid_cost_fetcher import SendGridCostFetcher
from .aws_cost_fetcher import AWSCostFetcher

__all__ = [
    "BaseCostFetcher",
    "FetchResult",
    "StripeCostFetcher",
    "OpenAICostFetcher",
    "AnthropicCostFetcher",
    "SendGridCostFetcher",
    "AWSCostFetcher",
]

# Registry of fetchers by provider type
FETCHER_REGISTRY = {
    "stripe": StripeCostFetcher,
    "openai": OpenAICostFetcher,
    "anthropic": AnthropicCostFetcher,
    "sendgrid": SendGridCostFetcher,
    "aws_s3": AWSCostFetcher,
}


def get_fetcher(provider_type: str) -> type:
    """Get the appropriate fetcher class for a provider type."""
    return FETCHER_REGISTRY.get(provider_type)
