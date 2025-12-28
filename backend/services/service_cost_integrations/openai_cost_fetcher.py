"""
OpenAI cost fetcher - fetches token usage.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class OpenAICostFetcher(BaseCostFetcher):
    """Fetches OpenAI API usage and costs."""

    provider_type = "openai"
    unit_type = "token"

    # Pricing per 1K tokens (as of early 2025)
    PRICING = {
        "gpt-4": {"input": Decimal("0.03"), "output": Decimal("0.06")},
        "gpt-4-turbo": {"input": Decimal("0.01"), "output": Decimal("0.03")},
        "gpt-4o": {"input": Decimal("0.005"), "output": Decimal("0.015")},
        "gpt-4o-mini": {"input": Decimal("0.00015"), "output": Decimal("0.0006")},
        "gpt-3.5-turbo": {"input": Decimal("0.0005"), "output": Decimal("0.0015")},
        "text-embedding-3-small": {"input": Decimal("0.00002"), "output": Decimal("0")},
        "text-embedding-3-large": {"input": Decimal("0.00013"), "output": Decimal("0")},
    }

    def __init__(self, api_key: str = None):
        super().__init__(api_key or os.getenv("OPENAI_API_KEY"))

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """Fetch OpenAI usage for the period."""
        if not self.validate_credentials():
            return FetchResult.error_result("OpenAI API key not configured")

        self.log_fetch_start(start_date, end_date)

        try:
            import httpx

            # OpenAI Usage API endpoint
            url = "https://api.openai.com/v1/dashboard/billing/usage"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            params = {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=30)

                if response.status_code != 200:
                    return FetchResult.error_result(f"API error: {response.status_code}")

                data = response.json()

            records = []

            # Parse daily usage
            for daily in data.get("daily_costs", []):
                usage_date = datetime.fromtimestamp(daily.get("timestamp", 0)).date()

                for item in daily.get("line_items", []):
                    model = item.get("name", "unknown")
                    cost = Decimal(str(item.get("cost", 0))) / 100  # Convert from cents

                    record = UsageRecord(
                        usage_date=usage_date,
                        usage_type="api_usage",
                        quantity=Decimal("1"),  # OpenAI doesn't always provide token count in usage API
                        unit_type="request",
                        total_cost=cost,
                        metadata={
                            "model": model,
                        }
                    )
                    records.append(record)

            self.log_fetch_complete(len(records))
            return FetchResult.success_result(records, raw_response=data)

        except ImportError:
            return FetchResult.error_result("httpx package not installed")
        except Exception as e:
            self.log_fetch_error(str(e))
            return FetchResult.error_result(str(e))

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate cost for token usage."""
        model = kwargs.get("model", "gpt-4o-mini")
        token_type = kwargs.get("token_type", "input")  # input or output

        pricing = self.PRICING.get(model, self.PRICING["gpt-4o-mini"])
        rate = pricing.get(token_type, Decimal("0.0001"))

        # Cost per 1K tokens
        return (quantity / 1000) * rate
