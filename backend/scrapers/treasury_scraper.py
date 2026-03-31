"""
Treasury Yield Scraper

Fetches real-time U.S. Treasury yields from Treasury.gov and FRED API.
Provides yield curve data for rate lock intelligence calculations.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import httpx
from functools import lru_cache

logger = logging.getLogger(__name__)

# FRED API configuration
FRED_API_KEY = os.getenv('FRED_API_KEY', '')
FRED_BASE_URL = 'https://api.stlouisfed.org/fred'

# Treasury series IDs in FRED
TREASURY_SERIES = {
    '3_month': 'DGS3MO',
    '6_month': 'DGS6MO',
    '1_year': 'DGS1',
    '2_year': 'DGS2',
    '3_year': 'DGS3',
    '5_year': 'DGS5',
    '7_year': 'DGS7',
    '10_year': 'DGS10',
    '20_year': 'DGS20',
    '30_year': 'DGS30',
}


class TreasuryScraper:
    """Scrapes Treasury yield data from FRED API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FRED_API_KEY
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=15)

    async def get_current_yields(self) -> Dict[str, float]:
        """
        Fetch current Treasury yields for all maturities.

        Returns:
            Dict mapping maturity names to yield values (as percentages)
        """
        # Check cache
        if self._is_cache_valid():
            logger.debug("Returning cached Treasury yields")
            return self._cache.get('yields', {})

        yields = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for maturity, series_id in TREASURY_SERIES.items():
                try:
                    value = await self._fetch_series(client, series_id)
                    if value is not None:
                        yields[maturity] = value
                except Exception as e:
                    logger.warning(f"Failed to fetch {maturity} Treasury: {e}")

        # Update cache
        if yields:
            self._cache['yields'] = yields
            self._cache_time = datetime.now()
            logger.info(f"Fetched Treasury yields: {len(yields)} maturities")

        return yields

    async def get_yield(self, maturity: str) -> Optional[float]:
        """
        Get yield for a specific maturity.

        Args:
            maturity: One of '2_year', '5_year', '10_year', '30_year', etc.

        Returns:
            Yield as percentage or None if not available
        """
        yields = await self.get_current_yields()
        return yields.get(maturity)

    async def get_10_year(self) -> Optional[float]:
        """Get current 10-year Treasury yield."""
        return await self.get_yield('10_year')

    async def get_30_year(self) -> Optional[float]:
        """Get current 30-year Treasury yield."""
        return await self.get_yield('30_year')

    async def get_yield_curve(self) -> Dict[str, float]:
        """
        Get full yield curve data.

        Returns:
            Dict with all available Treasury yields
        """
        return await self.get_current_yields()

    async def get_spread(self, short_maturity: str, long_maturity: str) -> Optional[float]:
        """
        Calculate yield spread between two maturities.

        Args:
            short_maturity: e.g., '2_year'
            long_maturity: e.g., '10_year'

        Returns:
            Spread in basis points (e.g., 50 means 0.50%)
        """
        yields = await self.get_current_yields()
        short_yield = yields.get(short_maturity)
        long_yield = yields.get(long_maturity)

        if short_yield is None or long_yield is None:
            return None

        return round((long_yield - short_yield) * 100, 2)

    async def get_2s10s_spread(self) -> Optional[float]:
        """Get 2-year/10-year Treasury spread (key recession indicator)."""
        return await self.get_spread('2_year', '10_year')

    async def get_history(self, series_id: str, days: int = 30) -> list:
        """
        Fetch historical data for a Treasury series.

        Args:
            series_id: FRED series ID (e.g., 'DGS10')
            days: Number of days of history

        Returns:
            List of {date, value} dicts
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{FRED_BASE_URL}/series/observations",
                    params={
                        'series_id': series_id,
                        'api_key': self.api_key,
                        'file_type': 'json',
                        'observation_start': start_date,
                        'sort_order': 'asc'
                    }
                )
                response.raise_for_status()
                data = response.json()

                if 'observations' not in data:
                    return []

                return [
                    {
                        'date': obs['date'],
                        'value': float(obs['value']) if obs['value'] != '.' else None
                    }
                    for obs in data['observations']
                    if obs['value'] != '.'
                ]
            except Exception as e:
                logger.error(f"Failed to fetch history for {series_id}: {e}")
                return []

    async def _fetch_series(self, client: httpx.AsyncClient, series_id: str) -> Optional[float]:
        """Fetch latest value for a FRED series."""
        try:
            response = await client.get(
                f"{FRED_BASE_URL}/series/observations",
                params={
                    'series_id': series_id,
                    'api_key': self.api_key,
                    'file_type': 'json',
                    'limit': 1,
                    'sort_order': 'desc'
                }
            )
            response.raise_for_status()
            data = response.json()

            if 'observations' not in data or not data['observations']:
                return None

            value = data['observations'][0].get('value')
            if value and value != '.':
                return float(value)

            return None
        except Exception as e:
            logger.error(f"Error fetching {series_id}: {e}")
            return None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_time or 'yields' not in self._cache:
            return False
        return datetime.now() - self._cache_time < self._cache_duration

    def clear_cache(self):
        """Clear the cache to force fresh data fetch."""
        self._cache = {}
        self._cache_time = None

    @staticmethod
    def is_market_open() -> bool:
        """
        Check if Treasury markets are open.

        Markets are open Mon-Fri 8:00 AM - 5:00 PM ET
        """
        now = datetime.now()
        # Check weekday (Mon=0, Fri=4)
        if now.weekday() > 4:
            return False
        # Basic market hours check (simplified)
        hour = now.hour
        return 8 <= hour < 17


# Convenience function for sync contexts
def get_treasury_yields_sync() -> Dict[str, float]:
    """Synchronous wrapper for getting Treasury yields.

    Safe to call from both sync and async contexts.
    """
    import concurrent.futures

    scraper = TreasuryScraper()
    coro = scraper.get_current_yields()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


if __name__ == '__main__':
    # Test the scraper
    logging.basicConfig(level=logging.INFO)

    async def main():
        scraper = TreasuryScraper()

        print("Fetching Treasury yields...")
        yields = await scraper.get_current_yields()

        print("\nCurrent Treasury Yields:")
        print("-" * 40)
        for maturity, value in sorted(yields.items()):
            print(f"{maturity}: {value:.3f}%")

        print("\n2s/10s Spread:")
        spread = await scraper.get_2s10s_spread()
        if spread:
            print(f"{spread:.2f} bps")

        print(f"\nMarket Open: {scraper.is_market_open()}")

    asyncio.run(main())
