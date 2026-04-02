"""
Optimal Blue Rate Service
Fetches mortgage rates from Optimal Blue API with mock data fallback.

Features:
- Real-time rate fetching from Optimal Blue API
- Mock data fallback when no API credentials
- Rate caching (15-minute TTL) to reduce API calls
- Scenario-based pricing (LTV, credit score, loan type)
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import random

import httpx
from sqlalchemy.orm import Session

from models.rate_monitor import OptimalBlueRateCache
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Cache TTL in minutes
RATE_CACHE_TTL_MINUTES = 15


@dataclass
class RateScenario:
    """Loan scenario parameters for rate lookup."""
    loan_type: str = 'conventional'  # conventional, fha, va, usda, jumbo
    loan_term: int = 30  # 15, 20, 30 years
    loan_amount: float = 400000
    ltv: float = 80.0  # Loan-to-value percentage
    credit_score: int = 740
    property_type: str = 'single_family'  # single_family, condo, townhouse, multi_family
    occupancy: str = 'primary'  # primary, second_home, investment
    state: str = 'CA'
    lock_period: int = 30  # Rate lock days

    def to_dict(self) -> Dict[str, Any]:
        return {
            'loan_type': self.loan_type,
            'loan_term': self.loan_term,
            'loan_amount': self.loan_amount,
            'ltv': self.ltv,
            'credit_score': self.credit_score,
            'property_type': self.property_type,
            'occupancy': self.occupancy,
            'state': self.state,
            'lock_period': self.lock_period,
        }

    def generate_cache_key(self) -> str:
        """Generate unique cache key for this scenario."""
        key_string = f"{self.loan_type}_{self.loan_term}_{int(self.loan_amount)}_{int(self.ltv)}_{self.credit_score}_{self.property_type}_{self.occupancy}_{self.state}"
        return hashlib.md5(key_string.encode()).hexdigest()


@dataclass
class RateResult:
    """Rate lookup result."""
    rate: float
    apr: float
    points: float = 0.0
    lender_credits: float = 0.0
    monthly_payment: float = 0.0
    source: str = 'optimal_blue'
    is_mock: bool = False
    fetched_at: datetime = None
    scenario: RateScenario = None
    rate_options: List[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'rate': self.rate,
            'apr': self.apr,
            'points': self.points,
            'lender_credits': self.lender_credits,
            'monthly_payment': self.monthly_payment,
            'source': self.source,
            'is_mock': self.is_mock,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'scenario': self.scenario.to_dict() if self.scenario else None,
            'rate_options': self.rate_options,
        }


class OptimalBlueService:
    """
    Service for fetching mortgage rates from Optimal Blue API.
    Falls back to mock data when API credentials are not available.
    """

    def __init__(self, db: Session = None):
        self.db = db
        self.api_key = os.getenv('OPTIMAL_BLUE_API_KEY')
        self.api_secret = os.getenv('OPTIMAL_BLUE_API_SECRET')
        self.api_url = os.getenv('OPTIMAL_BLUE_API_URL', 'https://api.optimalblue.com/v1')
        self.company_id = os.getenv('OPTIMAL_BLUE_COMPANY_ID')
        self._http_client = None

        # Check if we have valid API credentials
        self.has_credentials = bool(self.api_key and self.api_secret and self.company_id)

        if not self.has_credentials:
            logger.info("Optimal Blue credentials not configured - using mock data")

    async def get_rate(self, scenario: RateScenario) -> RateResult:
        """
        Get mortgage rate for a given scenario.

        Args:
            scenario: Loan scenario parameters

        Returns:
            RateResult with rate information
        """
        # Check cache first
        cached = await self._get_cached_rate(scenario)
        if cached:
            logger.debug(f"Cache hit for scenario: {scenario.generate_cache_key()}")
            return cached

        # Fetch rate (real API or mock)
        if self.has_credentials:
            result = await self._fetch_from_api(scenario)
        else:
            result = await self._generate_mock_rate(scenario)

        # Cache the result
        await self._cache_rate(scenario, result)

        return result

    async def get_current_rates(self, loan_type: str = 'conventional') -> Dict[str, RateResult]:
        """
        Get current rates for common scenarios.

        Returns dict with rates for 15-year and 30-year terms.
        """
        results = {}

        for term in [15, 30]:
            scenario = RateScenario(
                loan_type=loan_type,
                loan_term=term,
                credit_score=740,  # Good credit baseline
                ltv=80.0,
            )
            results[f'{term}_year'] = await self.get_rate(scenario)

        return results

    async def _fetch_from_api(self, scenario: RateScenario) -> RateResult:
        """Fetch rate from Optimal Blue API."""
        try:
            client = await self._get_http_client()

            # Build API request
            payload = {
                'companyId': self.company_id,
                'loanType': scenario.loan_type.upper(),
                'loanTerm': scenario.loan_term,
                'loanAmount': scenario.loan_amount,
                'ltv': scenario.ltv,
                'creditScore': scenario.credit_score,
                'propertyType': scenario.property_type,
                'occupancy': scenario.occupancy,
                'state': scenario.state,
                'lockPeriod': scenario.lock_period,
            }

            response = await client.post(
                f'{self.api_url}/rates/search',
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'X-API-Secret': self.api_secret,
                    'Content-Type': 'application/json',
                }
            )

            if response.status_code == 200:
                data = response.json()

                # Parse best rate from response
                best_rate = data.get('rates', [{}])[0] if data.get('rates') else {}

                result = RateResult(
                    rate=best_rate.get('rate', 0),
                    apr=best_rate.get('apr', 0),
                    points=best_rate.get('points', 0),
                    lender_credits=best_rate.get('lenderCredits', 0),
                    monthly_payment=self._calculate_monthly_payment(
                        scenario.loan_amount,
                        best_rate.get('rate', 0),
                        scenario.loan_term
                    ),
                    source='optimal_blue',
                    is_mock=False,
                    fetched_at=datetime.now(timezone.utc),
                    scenario=scenario,
                    rate_options=data.get('rates', []),
                )

                logger.info(f"Fetched rate from Optimal Blue: {result.rate}%")
                return result

            else:
                logger.error(f"Optimal Blue API error: {response.status_code} - {response.text}")
                # Fall back to mock data on API error
                return await self._generate_mock_rate(scenario)

        except Exception as e:
            logger.error(f"Error fetching from Optimal Blue: {e}")
            return await self._generate_mock_rate(scenario)

    async def _generate_mock_rate(self, scenario: RateScenario) -> RateResult:
        """
        Generate realistic mock rate data.

        Uses current market conditions as baseline with adjustments for:
        - Loan type (FHA/VA slightly higher)
        - Credit score (lower scores = higher rates)
        - LTV (higher LTV = higher rates)
        - Loan term (15-year typically lower than 30-year)
        """
        # Base rates (approximate current market - Jan 2026)
        base_rates = {
            15: 6.25,  # 15-year conventional
            20: 6.50,  # 20-year conventional
            30: 6.75,  # 30-year conventional
        }

        # Get base rate for term
        base_rate = base_rates.get(scenario.loan_term, 6.75)

        # Loan type adjustments
        loan_type_adj = {
            'conventional': 0.0,
            'fha': 0.125,
            'va': -0.125,  # VA often slightly better
            'usda': 0.0,
            'jumbo': 0.25,
        }
        rate = base_rate + loan_type_adj.get(scenario.loan_type.lower(), 0)

        # Credit score adjustments
        if scenario.credit_score >= 760:
            rate -= 0.25
        elif scenario.credit_score >= 740:
            rate -= 0.125
        elif scenario.credit_score >= 720:
            pass  # baseline
        elif scenario.credit_score >= 700:
            rate += 0.125
        elif scenario.credit_score >= 680:
            rate += 0.375
        elif scenario.credit_score >= 660:
            rate += 0.625
        else:
            rate += 1.0

        # LTV adjustments
        if scenario.ltv > 95:
            rate += 0.375
        elif scenario.ltv > 90:
            rate += 0.25
        elif scenario.ltv > 80:
            rate += 0.125
        elif scenario.ltv <= 60:
            rate -= 0.125

        # Property type adjustments
        if scenario.property_type in ['condo', 'townhouse']:
            rate += 0.125
        elif scenario.property_type == 'multi_family':
            rate += 0.25

        # Occupancy adjustments
        if scenario.occupancy == 'second_home':
            rate += 0.125
        elif scenario.occupancy == 'investment':
            rate += 0.375

        # Add small random variation for realism
        rate += random.uniform(-0.05, 0.05)
        rate = round(rate, 3)

        # Calculate APR (slightly higher than rate due to fees)
        apr = round(rate + 0.15, 3)

        # Generate rate options with different point combinations
        rate_options = [
            {'rate': rate, 'points': 0, 'apr': apr},
            {'rate': round(rate - 0.125, 3), 'points': 0.5, 'apr': round(apr - 0.10, 3)},
            {'rate': round(rate - 0.25, 3), 'points': 1.0, 'apr': round(apr - 0.20, 3)},
            {'rate': round(rate + 0.125, 3), 'points': -0.5, 'apr': round(apr + 0.10, 3)},  # Lender credit
        ]

        result = RateResult(
            rate=rate,
            apr=apr,
            points=0.0,
            lender_credits=0.0,
            monthly_payment=self._calculate_monthly_payment(
                scenario.loan_amount,
                rate,
                scenario.loan_term
            ),
            source='mock',
            is_mock=True,
            fetched_at=datetime.now(timezone.utc),
            scenario=scenario,
            rate_options=rate_options,
        )

        logger.debug(f"Generated mock rate: {result.rate}% for {scenario.loan_type} {scenario.loan_term}yr")
        return result

    async def _get_cached_rate(self, scenario: RateScenario) -> Optional[RateResult]:
        """Check cache for existing rate."""
        if not self.db:
            return None

        cache_key = scenario.generate_cache_key()
        now = datetime.now(timezone.utc)

        cached = self.db.query(OptimalBlueRateCache).filter(
            OptimalBlueRateCache.cache_key == cache_key,
            OptimalBlueRateCache.expires_at > now
        ).first()

        if cached:
            return RateResult(
                rate=float(cached.rate),
                apr=float(cached.apr) if cached.apr else float(cached.rate) + 0.15,
                points=float(cached.points) if cached.points else 0,
                lender_credits=float(cached.lender_credits) if cached.lender_credits else 0,
                monthly_payment=self._calculate_monthly_payment(
                    float(cached.loan_amount) if cached.loan_amount else scenario.loan_amount,
                    float(cached.rate),
                    cached.loan_term
                ),
                source=cached.source,
                is_mock=cached.is_mock,
                fetched_at=cached.fetched_at,
                scenario=scenario,
                rate_options=cached.rate_options,
            )

        return None

    async def _cache_rate(self, scenario: RateScenario, result: RateResult) -> None:
        """Cache rate result."""
        if not self.db:
            return

        cache_key = scenario.generate_cache_key()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=RATE_CACHE_TTL_MINUTES)

        # Check if cache entry exists
        existing = self.db.query(OptimalBlueRateCache).filter(
            OptimalBlueRateCache.cache_key == cache_key
        ).first()

        if existing:
            # Update existing cache entry
            existing.rate = Decimal(str(result.rate))
            existing.apr = Decimal(str(result.apr))
            existing.points = Decimal(str(result.points))
            existing.lender_credits = Decimal(str(result.lender_credits))
            existing.rate_options = result.rate_options
            existing.source = result.source
            existing.is_mock = result.is_mock
            existing.fetched_at = result.fetched_at
            existing.expires_at = expires_at
        else:
            # Create new cache entry
            cache_entry = OptimalBlueRateCache(
                cache_key=cache_key,
                loan_type=scenario.loan_type,
                loan_term=scenario.loan_term,
                loan_amount=Decimal(str(scenario.loan_amount)),
                ltv=Decimal(str(scenario.ltv)),
                credit_score=scenario.credit_score,
                property_type=scenario.property_type,
                occupancy=scenario.occupancy,
                state=scenario.state,
                rate=Decimal(str(result.rate)),
                apr=Decimal(str(result.apr)),
                points=Decimal(str(result.points)),
                lender_credits=Decimal(str(result.lender_credits)),
                rate_options=result.rate_options,
                source=result.source,
                is_mock=result.is_mock,
                fetched_at=result.fetched_at,
                expires_at=expires_at,
            )
            self.db.add(cache_entry)

        try:
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error caching rate: {e}")
            self.db.rollback()

    def _calculate_monthly_payment(
        self,
        loan_amount: float,
        annual_rate: float,
        term_years: int
    ) -> float:
        """
        Calculate monthly P&I payment using standard amortization formula.

        M = P * [r(1+r)^n] / [(1+r)^n - 1]

        Where:
        - M = monthly payment
        - P = principal (loan amount)
        - r = monthly interest rate
        - n = number of payments
        """
        if annual_rate <= 0 or loan_amount <= 0 or term_years <= 0:
            return 0.0

        monthly_rate = annual_rate / 100 / 12
        num_payments = term_years * 12

        if monthly_rate == 0:
            return loan_amount / num_payments

        payment = loan_amount * (
            monthly_rate * (1 + monthly_rate) ** num_payments
        ) / (
            (1 + monthly_rate) ** num_payments - 1
        )

        return round(payment, 2)

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries. Returns count of deleted entries."""
        if not self.db:
            return 0

        now = datetime.now(timezone.utc)
        result = self.db.query(OptimalBlueRateCache).filter(
            OptimalBlueRateCache.expires_at < now
        ).delete()

        self.db.commit()
        logger.info(f"Cleaned up {result} expired rate cache entries")
        return result


# Convenience function for quick rate lookup
async def get_current_market_rate(
    db: Session,
    loan_type: str = 'conventional',
    loan_term: int = 30,
    credit_score: int = 740,
    ltv: float = 80.0
) -> float:
    """
    Quick function to get current market rate for comparison.

    Returns the rate as a float (e.g., 6.75 for 6.75%)
    """
    service = OptimalBlueService(db)
    scenario = RateScenario(
        loan_type=loan_type,
        loan_term=loan_term,
        credit_score=credit_score,
        ltv=ltv,
    )
    result = await service.get_rate(scenario)
    return result.rate
