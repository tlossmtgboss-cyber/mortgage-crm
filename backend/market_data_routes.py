"""
Market Data Routes

API endpoints for market data from scrapers (Treasury yields, mortgage rates, etc.)
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
import os
import sys

from routes.auth_deps import require_auth

# Add scrapers to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

router = APIRouter(prefix="/api/v1/market", tags=["market-data"], dependencies=[Depends(require_auth)])


@router.get("/data")
async def get_market_data():
    """Get current market data from scrapers."""
    try:
        from scrapers import MarketDataOrchestrator

        orchestrator = MarketDataOrchestrator()
        snapshot = orchestrator.get_market_snapshot()

        if not snapshot:
            # Return mock data if scrapers fail
            return get_fallback_data()

        # Format response for frontend
        return {
            "treasury": {
                "2yr": snapshot.get("treasury", {}).get("2yr"),
                "5yr": snapshot.get("treasury", {}).get("5yr"),
                "10yr": snapshot.get("treasury", {}).get("10yr"),
                "30yr": snapshot.get("treasury", {}).get("30yr"),
                "spread_2s10s": snapshot.get("treasury", {}).get("spread_2s10s")
            },
            "mortgage_rates": {
                "rate_30yr": snapshot.get("mortgage_rates", {}).get("rate_30yr"),
                "rate_15yr": snapshot.get("mortgage_rates", {}).get("rate_15yr"),
                "spread_to_10yr": snapshot.get("mortgage_rates", {}).get("spread_to_10yr")
            },
            "volatility": {
                "vix": snapshot.get("volatility", {}).get("vix"),
                "assessment": snapshot.get("volatility", {}).get("assessment"),
                "score": snapshot.get("volatility", {}).get("score")
            },
            "market_score": snapshot.get("market_score"),
            "recommendation": snapshot.get("recommendation"),
            "timestamp": snapshot.get("timestamp")
        }

    except Exception as e:
        print(f"Error fetching market data: {e}")
        return get_fallback_data()


@router.get("/rate-lock-context")
async def get_rate_lock_context(days: int = 30):
    """Get rate lock recommendation context for a specific lock period."""
    try:
        from scrapers import MarketDataOrchestrator

        orchestrator = MarketDataOrchestrator()
        context = orchestrator.get_rate_lock_context(days)

        return context

    except Exception as e:
        print(f"Error fetching rate lock context: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def get_fallback_data():
    """Return fallback/mock data when scrapers are unavailable."""
    from datetime import datetime

    return {
        "treasury": {
            "2yr": 4.25,
            "5yr": 4.10,
            "10yr": 4.15,
            "30yr": 4.35,
            "spread_2s10s": -0.10
        },
        "mortgage_rates": {
            "rate_30yr": 6.50,
            "rate_15yr": 5.75,
            "spread_to_10yr": 2.35
        },
        "volatility": {
            "vix": 18.5,
            "assessment": "moderate",
            "score": 4
        },
        "market_score": 55,
        "recommendation": "CAUTIOUS",
        "timestamp": datetime.now().isoformat(),
        "is_fallback": True
    }
