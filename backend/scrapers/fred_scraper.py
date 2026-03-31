"""
FRED API Scraper

Fetches mortgage rates, economic indicators, and MBS-related data from FRED.
https://fred.stlouisfed.org/docs/api/fred/
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import httpx

logger = logging.getLogger(__name__)

# FRED API configuration
FRED_API_KEY = os.getenv('FRED_API_KEY', '')
FRED_BASE_URL = 'https://api.stlouisfed.org/fred'

# Key FRED series for mortgage intelligence
FRED_SERIES = {
    # Mortgage Rates (Weekly updates on Thursday)
    'mortgage_30yr': 'MORTGAGE30US',    # 30-Year Fixed Rate
    'mortgage_15yr': 'MORTGAGE15US',    # 15-Year Fixed Rate
    'mortgage_5_1_arm': 'MORTGAGE5US',  # 5/1-Year ARM

    # Economic Indicators
    'cpi': 'CPIAUCSL',                  # Consumer Price Index
    'unemployment': 'UNRATE',           # Unemployment Rate
    'gdp': 'GDP',                       # Gross Domestic Product
    'pce': 'PCEPI',                     # Personal Consumption Expenditures
    'fed_funds': 'FEDFUNDS',            # Federal Funds Rate

    # Housing Market
    'housing_starts': 'HOUST',          # Housing Starts
    'existing_home_sales': 'EXHOSLUSM495S',  # Existing Home Sales
    'case_shiller': 'CSUSHPISA',        # Case-Shiller Home Price Index

    # Financial Conditions
    'vix': 'VIXCLS',                    # VIX Volatility Index
    'sp500': 'SP500',                   # S&P 500 Index
}


class FREDScraper:
    """Scrapes economic and mortgage data from FRED API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FRED_API_KEY
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._cache_duration = timedelta(hours=1)  # Most FRED data updates weekly

    async def get_mortgage_rates(self) -> Dict[str, float]:
        """
        Fetch current mortgage rates.

        Returns:
            Dict with 30yr, 15yr, and ARM rates
        """
        rates = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch each mortgage rate series
            for rate_type in ['mortgage_30yr', 'mortgage_15yr', 'mortgage_5_1_arm']:
                try:
                    value = await self._fetch_series(client, FRED_SERIES[rate_type])
                    if value is not None:
                        rates[rate_type] = value
                except Exception as e:
                    logger.warning(f"Failed to fetch {rate_type}: {e}")

        return rates

    async def get_30yr_mortgage_rate(self) -> Optional[float]:
        """Get current 30-year fixed mortgage rate."""
        rates = await self.get_mortgage_rates()
        return rates.get('mortgage_30yr')

    async def get_15yr_mortgage_rate(self) -> Optional[float]:
        """Get current 15-year fixed mortgage rate."""
        rates = await self.get_mortgage_rates()
        return rates.get('mortgage_15yr')

    async def get_fed_funds_rate(self) -> Optional[float]:
        """Get current Federal Funds Rate."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await self._fetch_series(client, FRED_SERIES['fed_funds'])

    async def get_vix(self) -> Optional[float]:
        """Get current VIX volatility index."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await self._fetch_series(client, FRED_SERIES['vix'])

    async def get_volatility_assessment(self) -> Dict[str, Any]:
        """
        Get market volatility assessment for rate lock decisions.

        Returns:
            Dict with VIX value and interpretation
        """
        vix = await self.get_vix()

        if vix is None:
            return {
                'vix': None,
                'interpretation': 'unknown',
                'volatility_score': 5  # Neutral
            }

        # Interpret VIX levels
        if vix < 12:
            interpretation = 'very_low'
            score = 2
        elif vix < 15:
            interpretation = 'low'
            score = 3
        elif vix < 20:
            interpretation = 'normal'
            score = 5
        elif vix < 25:
            interpretation = 'elevated'
            score = 7
        elif vix < 30:
            interpretation = 'high'
            score = 8
        else:
            interpretation = 'extreme'
            score = 10

        return {
            'vix': vix,
            'interpretation': interpretation,
            'volatility_score': score,
            'timestamp': datetime.now().isoformat()
        }

    async def get_economic_indicators(self) -> Dict[str, float]:
        """
        Fetch key economic indicators.

        Returns:
            Dict with CPI, unemployment, GDP, etc.
        """
        indicators = {}
        indicator_keys = ['cpi', 'unemployment', 'gdp', 'fed_funds']

        async with httpx.AsyncClient(timeout=30.0) as client:
            for key in indicator_keys:
                try:
                    value = await self._fetch_series(client, FRED_SERIES[key])
                    if value is not None:
                        indicators[key] = value
                except Exception as e:
                    logger.warning(f"Failed to fetch {key}: {e}")

        return indicators

    async def get_housing_data(self) -> Dict[str, float]:
        """
        Fetch housing market indicators.

        Returns:
            Dict with housing starts, sales, prices
        """
        housing = {}
        housing_keys = ['housing_starts', 'existing_home_sales', 'case_shiller']

        async with httpx.AsyncClient(timeout=30.0) as client:
            for key in housing_keys:
                try:
                    value = await self._fetch_series(client, FRED_SERIES[key])
                    if value is not None:
                        housing[key] = value
                except Exception as e:
                    logger.warning(f"Failed to fetch {key}: {e}")

        return housing

    async def get_rate_history(self, rate_type: str = 'mortgage_30yr', days: int = 30) -> List[Dict]:
        """
        Fetch historical mortgage rates.

        Args:
            rate_type: 'mortgage_30yr', 'mortgage_15yr', or 'mortgage_5_1_arm'
            days: Number of days of history

        Returns:
            List of {date, value} dicts
        """
        series_id = FRED_SERIES.get(rate_type)
        if not series_id:
            logger.error(f"Unknown rate type: {rate_type}")
            return []

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
                logger.error(f"Failed to fetch rate history: {e}")
                return []

    async def get_rate_trend(self, rate_type: str = 'mortgage_30yr', days: int = 7) -> Dict[str, Any]:
        """
        Analyze rate trend over recent period.

        Returns:
            Dict with trend direction and magnitude
        """
        history = await self.get_rate_history(rate_type, days)

        if len(history) < 2:
            return {
                'trend': 'unknown',
                'change': 0,
                'percent_change': 0
            }

        first_value = history[0]['value']
        last_value = history[-1]['value']

        if first_value is None or last_value is None:
            return {
                'trend': 'unknown',
                'change': 0,
                'percent_change': 0
            }

        change = last_value - first_value
        percent_change = (change / first_value) * 100 if first_value else 0

        if change > 0.05:
            trend = 'rising'
        elif change < -0.05:
            trend = 'falling'
        else:
            trend = 'stable'

        return {
            'trend': trend,
            'change': round(change, 3),
            'percent_change': round(percent_change, 2),
            'start_value': first_value,
            'end_value': last_value,
            'period_days': days
        }

    async def get_complete_market_data(self) -> Dict[str, Any]:
        """
        Fetch all market data in one call.

        Returns:
            Comprehensive market data dict
        """
        # Fetch all data concurrently
        mortgage_rates, volatility, economic, housing = await asyncio.gather(
            self.get_mortgage_rates(),
            self.get_volatility_assessment(),
            self.get_economic_indicators(),
            self.get_housing_data(),
            return_exceptions=True
        )

        return {
            'mortgage_rates': mortgage_rates if isinstance(mortgage_rates, dict) else {},
            'volatility': volatility if isinstance(volatility, dict) else {},
            'economic_indicators': economic if isinstance(economic, dict) else {},
            'housing_market': housing if isinstance(housing, dict) else {},
            'timestamp': datetime.now().isoformat(),
            'source': 'FRED'
        }

    async def _fetch_series(self, client: httpx.AsyncClient, series_id: str) -> Optional[float]:
        """Fetch latest value for a FRED series."""
        # Check cache
        cache_key = series_id
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)

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
                result = float(value)
                # Update cache
                self._cache[cache_key] = result
                self._cache_times[cache_key] = datetime.now()
                return result

            return None
        except Exception as e:
            logger.error(f"Error fetching {series_id}: {e}")
            return None

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache for a specific key is still valid."""
        if key not in self._cache or key not in self._cache_times:
            return False
        return datetime.now() - self._cache_times[key] < self._cache_duration

    def clear_cache(self):
        """Clear all cached data."""
        self._cache = {}
        self._cache_times = {}


# Convenience function for sync contexts
def get_mortgage_rates_sync() -> Dict[str, float]:
    """Synchronous wrapper for getting mortgage rates.

    Safe to call from both sync and async contexts.
    """
    import concurrent.futures

    scraper = FREDScraper()
    coro = scraper.get_mortgage_rates()
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
        scraper = FREDScraper()

        print("Fetching mortgage rates...")
        rates = await scraper.get_mortgage_rates()

        print("\nCurrent Mortgage Rates:")
        print("-" * 40)
        for rate_type, value in rates.items():
            print(f"{rate_type}: {value:.2f}%")

        print("\nVolatility Assessment:")
        vol = await scraper.get_volatility_assessment()
        print(f"VIX: {vol.get('vix')}")
        print(f"Interpretation: {vol.get('interpretation')}")
        print(f"Volatility Score: {vol.get('volatility_score')}/10")

        print("\n30-Year Rate Trend (7 days):")
        trend = await scraper.get_rate_trend()
        print(f"Trend: {trend.get('trend')}")
        print(f"Change: {trend.get('change')}%")

    asyncio.run(main())
