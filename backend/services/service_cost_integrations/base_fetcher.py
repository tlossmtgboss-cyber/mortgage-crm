"""
Base class for service cost fetchers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    """Represents a single usage record from a service."""
    usage_date: date
    usage_type: str
    quantity: Decimal
    unit_type: str
    unit_cost: Optional[Decimal] = None
    total_cost: Decimal = Decimal("0")
    metadata: Dict[str, Any] = field(default_factory=dict)
    external_id: Optional[str] = None


@dataclass
class FetchResult:
    """Result of a fetch operation."""
    success: bool
    records: List[UsageRecord] = field(default_factory=list)
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def success_result(cls, records: List[UsageRecord], raw_response: Dict = None):
        return cls(success=True, records=records, raw_response=raw_response)

    @classmethod
    def error_result(cls, error: str):
        return cls(success=False, error=error)


class BaseCostFetcher(ABC):
    """Base class for all service cost fetchers."""

    provider_type: str = "base"
    unit_type: str = "unit"

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    @abstractmethod
    async def fetch_usage(
        self,
        start_date: date,
        end_date: date,
        **kwargs
    ) -> FetchResult:
        """
        Fetch usage data from the service for the given date range.

        Args:
            start_date: Start of the period
            end_date: End of the period
            **kwargs: Additional provider-specific parameters

        Returns:
            FetchResult with usage records
        """
        pass

    @abstractmethod
    def calculate_cost(self, quantity: Decimal, **kwargs) -> Decimal:
        """
        Calculate cost for a given quantity.

        Args:
            quantity: Amount of usage
            **kwargs: Additional pricing parameters

        Returns:
            Calculated cost
        """
        pass

    def validate_credentials(self) -> bool:
        """Validate that credentials are present and valid."""
        return bool(self.api_key)

    def get_api_key_from_env(self, env_var: str) -> Optional[str]:
        """Get API key from environment variable."""
        import os
        return os.getenv(env_var)

    def log_fetch_start(self, start_date: date, end_date: date):
        """Log the start of a fetch operation."""
        logger.info(f"[{self.provider_type}] Fetching usage from {start_date} to {end_date}")

    def log_fetch_complete(self, record_count: int):
        """Log completion of a fetch operation."""
        logger.info(f"[{self.provider_type}] Fetched {record_count} records")

    def log_fetch_error(self, error: str):
        """Log a fetch error."""
        logger.error(f"[{self.provider_type}] Fetch error: {error}")
