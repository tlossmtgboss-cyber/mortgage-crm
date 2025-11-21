"""
Market Data Orchestrator

Coordinates all market data scrapers and provides a unified interface
for the Rate Lock Intelligence system.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from .treasury_scraper import TreasuryScraper
from .fred_scraper import FREDScraper

logger = logging.getLogger(__name__)


class MarketDataOrchestrator:
    """
    Orchestrates market data collection from multiple sources.

    Provides unified access to:
    - Treasury yields
    - Mortgage rates
    - Volatility indicators
    - Economic data
    """

    def __init__(self):
        self.treasury = TreasuryScraper()
        self.fred = FREDScraper()
        self._full_cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)

    async def get_market_snapshot(self) -> Dict[str, Any]:
        """
        Get a comprehensive market snapshot for rate lock decisions.

        Returns:
            Dict containing all market data needed for recommendations
        """
        # Check cache first
        if self._is_cache_valid():
            logger.debug("Returning cached market snapshot")
            return self._full_cache

        # Fetch all data concurrently
        treasury_yields, mortgage_rates, volatility, rate_trend = await asyncio.gather(
            self.treasury.get_current_yields(),
            self.fred.get_mortgage_rates(),
            self.fred.get_volatility_assessment(),
            self.fred.get_rate_trend(),
            return_exceptions=True
        )

        # Get 2s/10s spread
        spread_2s10s = await self.treasury.get_2s10s_spread()

        snapshot = {
            'treasury_yields': treasury_yields if isinstance(treasury_yields, dict) else {},
            'mortgage_rates': mortgage_rates if isinstance(mortgage_rates, dict) else {},
            'volatility': volatility if isinstance(volatility, dict) else {},
            'rate_trend': rate_trend if isinstance(rate_trend, dict) else {},
            'spreads': {
                '2s10s': spread_2s10s
            },
            'market_status': {
                'is_open': self.treasury.is_market_open(),
                'timestamp': datetime.now().isoformat()
            },
            'source': 'pipeline360_scrapers'
        }

        # Calculate derived metrics
        snapshot['market_score'] = self._calculate_market_score(snapshot)
        snapshot['recommendation_factors'] = self._extract_recommendation_factors(snapshot)

        # Update cache
        self._full_cache = snapshot
        self._cache_time = datetime.now()

        logger.info("Market snapshot updated successfully")
        return snapshot

    async def get_volatility(self) -> Dict[str, Any]:
        """Get current market volatility assessment."""
        return await self.fred.get_volatility_assessment()

    async def get_rate_lock_context(self) -> Dict[str, Any]:
        """
        Get context specifically needed for rate lock recommendations.

        Returns:
            Dict with volatility score, trend, and key indicators
        """
        snapshot = await self.get_market_snapshot()

        return {
            'volatility_score': snapshot.get('volatility', {}).get('volatility_score', 5),
            'vix': snapshot.get('volatility', {}).get('vix'),
            'rate_trend': snapshot.get('rate_trend', {}).get('trend', 'unknown'),
            'rate_change': snapshot.get('rate_trend', {}).get('change', 0),
            'ten_year_treasury': snapshot.get('treasury_yields', {}).get('10_year'),
            'thirty_year_mortgage': snapshot.get('mortgage_rates', {}).get('mortgage_30yr'),
            'market_score': snapshot.get('market_score', 50),
            'timestamp': snapshot.get('market_status', {}).get('timestamp')
        }

    async def should_lock(self, loan_days_to_close: int) -> Dict[str, Any]:
        """
        Quick assessment of whether to lock based on market conditions.

        Args:
            loan_days_to_close: Days until loan closing

        Returns:
            Dict with recommendation and reasoning
        """
        context = await self.get_rate_lock_context()

        volatility_score = context.get('volatility_score', 5)
        rate_trend = context.get('rate_trend', 'unknown')
        market_score = context.get('market_score', 50)

        # Decision logic
        reasons = []
        lock_score = 50  # Start neutral

        # Factor 1: Volatility (up to ±20 points)
        if volatility_score >= 8:
            lock_score += 20
            reasons.append("High market volatility favors locking")
        elif volatility_score <= 3:
            lock_score -= 15
            reasons.append("Low volatility allows floating")
        else:
            lock_score += (volatility_score - 5) * 3

        # Factor 2: Rate trend (up to ±20 points)
        if rate_trend == 'rising':
            lock_score += 15
            reasons.append("Rates are trending up")
        elif rate_trend == 'falling':
            lock_score -= 15
            reasons.append("Rates are trending down")

        # Factor 3: Time pressure (up to ±10 points)
        if loan_days_to_close <= 15:
            lock_score += 10
            reasons.append("Close date approaching")
        elif loan_days_to_close >= 45:
            lock_score -= 5
            reasons.append("Ample time before closing")

        # Determine recommendation
        if lock_score >= 65:
            recommendation = 'lock_now'
            urgency = 'high'
        elif lock_score >= 50:
            recommendation = 'cautious_lock'
            urgency = 'moderate'
        elif lock_score >= 35:
            recommendation = 'cautious_float'
            urgency = 'low'
        else:
            recommendation = 'float'
            urgency = 'low'

        return {
            'recommendation': recommendation,
            'urgency': urgency,
            'lock_score': lock_score,
            'reasons': reasons,
            'market_context': context
        }

    def _calculate_market_score(self, snapshot: Dict) -> int:
        """
        Calculate overall market score (0-100).

        Higher score = more reason to lock
        Lower score = more reason to float
        """
        score = 50  # Start neutral

        # Volatility impact
        vol_score = snapshot.get('volatility', {}).get('volatility_score', 5)
        score += (vol_score - 5) * 4  # ±20 points

        # Rate trend impact
        trend = snapshot.get('rate_trend', {}).get('trend', 'stable')
        if trend == 'rising':
            score += 15
        elif trend == 'falling':
            score -= 15

        # Spread impact (inverted yield curve = uncertainty)
        spread = snapshot.get('spreads', {}).get('2s10s')
        if spread is not None:
            if spread < 0:
                score += 10  # Inverted curve = lock
            elif spread > 100:
                score -= 5  # Normal steep curve

        return max(0, min(100, int(score)))

    def _extract_recommendation_factors(self, snapshot: Dict) -> Dict[str, Any]:
        """Extract key factors for rate lock recommendation."""
        return {
            'volatility_level': snapshot.get('volatility', {}).get('interpretation', 'normal'),
            'rate_direction': snapshot.get('rate_trend', {}).get('trend', 'stable'),
            'yield_curve': 'inverted' if (snapshot.get('spreads', {}).get('2s10s', 0) or 0) < 0 else 'normal',
            'market_timing': 'favorable' if snapshot.get('market_score', 50) < 45 else 'unfavorable'
        }

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_time or not self._full_cache:
            return False
        return datetime.now() - self._cache_time < self._cache_duration

    def clear_cache(self):
        """Clear all caches."""
        self._full_cache = {}
        self._cache_time = None
        self.treasury.clear_cache()
        self.fred.clear_cache()


# Singleton instance for easy access
_orchestrator: Optional[MarketDataOrchestrator] = None


def get_orchestrator() -> MarketDataOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MarketDataOrchestrator()
    return _orchestrator


# Convenience functions
async def get_market_snapshot() -> Dict[str, Any]:
    """Get current market snapshot."""
    return await get_orchestrator().get_market_snapshot()


async def get_rate_lock_context() -> Dict[str, Any]:
    """Get context for rate lock decisions."""
    return await get_orchestrator().get_rate_lock_context()


if __name__ == '__main__':
    # Test the orchestrator
    logging.basicConfig(level=logging.INFO)

    async def main():
        orchestrator = MarketDataOrchestrator()

        print("Fetching market snapshot...")
        print("=" * 60)

        snapshot = await orchestrator.get_market_snapshot()

        print("\nTreasury Yields:")
        for maturity, value in snapshot.get('treasury_yields', {}).items():
            print(f"  {maturity}: {value:.3f}%")

        print("\nMortgage Rates:")
        for rate_type, value in snapshot.get('mortgage_rates', {}).items():
            print(f"  {rate_type}: {value:.2f}%")

        print("\nVolatility:")
        vol = snapshot.get('volatility', {})
        print(f"  VIX: {vol.get('vix')}")
        print(f"  Level: {vol.get('interpretation')}")
        print(f"  Score: {vol.get('volatility_score')}/10")

        print("\nRate Trend (7 days):")
        trend = snapshot.get('rate_trend', {})
        print(f"  Direction: {trend.get('trend')}")
        print(f"  Change: {trend.get('change')}%")

        print(f"\nMarket Score: {snapshot.get('market_score')}/100")
        print(f"2s/10s Spread: {snapshot.get('spreads', {}).get('2s10s')} bps")

        # Test lock recommendation
        print("\n" + "=" * 60)
        print("Lock Recommendation (30 days to close):")
        rec = await orchestrator.should_lock(30)
        print(f"  Recommendation: {rec.get('recommendation')}")
        print(f"  Urgency: {rec.get('urgency')}")
        print(f"  Score: {rec.get('lock_score')}")
        print("  Reasons:")
        for reason in rec.get('reasons', []):
            print(f"    - {reason}")

    asyncio.run(main())
