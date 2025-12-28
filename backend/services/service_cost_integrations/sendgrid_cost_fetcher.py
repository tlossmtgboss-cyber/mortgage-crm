"""
SendGrid cost fetcher - fetches email sending stats.
"""

from datetime import date, datetime
from decimal import Decimal
import os

from .base_fetcher import BaseCostFetcher, FetchResult, UsageRecord


class SendGridCostFetcher(BaseCostFetcher):
    """Fetches SendGrid email usage."""

    provider_type = "sendgrid"
    unit_type = "email"

    # Approximate pricing per email (varies by plan)
    COST_PER_EMAIL = Decimal("0.001")  # $1 per 1000 emails

    def __init__(self, api_key: str = None):
        super().__init__(api_key or os.getenv("SENDGRID_API_KEY"))

    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """Fetch SendGrid usage for the period."""
        if not self.validate_credentials():
            return FetchResult.error_result("SendGrid API key not configured")

        self.log_fetch_start(start_date, end_date)

        try:
            import httpx

            url = "https://api.sendgrid.com/v3/stats"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            params = {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "aggregated_by": "day"
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=30)

                if response.status_code != 200:
                    return FetchResult.error_result(f"API error: {response.status_code}")

                data = response.json()

            records = []

            for day_stats in data:
                usage_date = datetime.strptime(day_stats["date"], "%Y-%m-%d").date()

                # Sum up metrics
                total_sent = 0
                for stat in day_stats.get("stats", []):
                    metrics = stat.get("metrics", {})
                    total_sent += metrics.get("requests", 0)

                if total_sent > 0:
                    total_cost = Decimal(str(total_sent)) * self.COST_PER_EMAIL

                    records.append(UsageRecord(
                        usage_date=usage_date,
                        usage_type="email_sent",
                        quantity=Decimal(str(total_sent)),
                        unit_type="email",
                        unit_cost=self.COST_PER_EMAIL,
                        total_cost=total_cost,
                        metadata={
                            "delivered": metrics.get("delivered", 0),
                            "opens": metrics.get("opens", 0),
                            "clicks": metrics.get("clicks", 0),
                            "bounces": metrics.get("bounces", 0),
                        }
                    ))

            self.log_fetch_complete(len(records))
            return FetchResult.success_result(records, raw_response=data)

        except ImportError:
            return FetchResult.error_result("httpx package not installed")
        except Exception as e:
            self.log_fetch_error(str(e))
            return FetchResult.error_result(str(e))

    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """Calculate cost for email sends."""
        return quantity * self.COST_PER_EMAIL
