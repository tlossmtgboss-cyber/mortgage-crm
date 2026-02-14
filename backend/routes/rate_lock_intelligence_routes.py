"""
Rate Lock Intelligence Routes

Provides the same API interface as the external rate-lock-intelligence microservice,
allowing the frontend to use the integrated CRM backend instead.

Endpoints:
- POST /v1/recommendations/quick - Get quick rate lock recommendation
- GET /v1/market/snapshot - Get current market snapshot
- GET /health - Health check
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging

from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rate-lock-intelligence", tags=["rate-lock-intelligence"], dependencies=[Depends(require_auth)])


# ============================================================================
# PYDANTIC MODELS - Match the external service interface
# ============================================================================

class LoanScenario(BaseModel):
    """Input scenario for rate lock recommendation"""
    loan_amount: float
    property_value: Optional[float] = None
    ltv: Optional[float] = 80
    fico: Optional[int] = 720
    dti: Optional[float] = 36
    purpose: Optional[str] = "purchase"
    occupancy: Optional[str] = "primary_residence"
    property_type: Optional[str] = "single_family"
    loan_program: Optional[str] = "conventional_30"
    contract_close_date: Optional[str] = None
    estimated_clear_to_close_date: Optional[str] = None
    file_status: Optional[str] = "in_processing"
    conditions_remaining: Optional[int] = 5
    current_rate: Optional[float] = 6.75
    par_rate: Optional[float] = None
    price_at_current_rate: Optional[float] = 100.5
    price_at_par: Optional[float] = 100.0
    rate_sheet_timestamp: Optional[str] = None
    volatility_indicator: Optional[str] = "normal"
    recent_price_changes_bps: Optional[float] = 5
    treasury_10yr_yield: Optional[float] = 4.25
    mbs_current_coupon: Optional[float] = 6.0
    mbs_price: Optional[float] = 100.5
    market_trend: Optional[str] = "stable"
    available_lock_terms: Optional[List[int]] = [15, 30, 45, 60]
    extension_cost_bps_per_15_days: Optional[float] = 19
    relock_policy: Optional[str] = "worse_of_two"
    lock_cutoff_time_local: Optional[str] = "15:00"
    lock_desk_open: Optional[bool] = True
    rate_sensitivity: Optional[str] = "high"
    payment_sensitivity: Optional[str] = "high"
    certainty_preference: Optional[str] = "high"


class QuickRecommendationRequest(BaseModel):
    """Request body for quick recommendation endpoint"""
    scenario: LoanScenario


class RateLockRecommendation(BaseModel):
    """Rate lock recommendation response"""
    action: str  # LOCK_NOW, FLOAT, FLOAT_WITH_CAUTION
    confidence: str  # high, medium, low
    lock_term_recommendation: int
    reasoning: str
    key_factors: List[str]
    risk_assessment: dict
    market_outlook: dict
    scenarios: dict
    timestamp: str


class MarketSnapshot(BaseModel):
    """Market snapshot response"""
    timestamp: str
    treasury_10yr_yield: float
    mbs_current_coupon: float
    mbs_price: float
    volatility_indicator: str
    market_trend: str
    is_mock: bool = False


# ============================================================================
# RATE LOCK INTELLIGENCE LOGIC
# ============================================================================

def calculate_lock_score(scenario: LoanScenario) -> int:
    """
    Calculate lock score (0-100) based on scenario factors.

    Score > 70: LOCK_NOW
    Score 50-70: Consider locking
    Score < 50: FLOAT
    """
    score = 50  # Base score

    # Days to close impact
    if scenario.contract_close_date:
        try:
            close_date = datetime.fromisoformat(scenario.contract_close_date.replace('Z', '+00:00'))
            days_to_close = (close_date - datetime.now()).days

            if days_to_close <= 7:
                score += 30  # Critical - must lock
            elif days_to_close <= 14:
                score += 20  # High urgency
            elif days_to_close <= 21:
                score += 10  # Moderate urgency
            elif days_to_close <= 30:
                score += 5   # Some urgency
            elif days_to_close > 45:
                score -= 10  # Can wait
        except Exception:
            pass

    # Market volatility impact
    if scenario.volatility_indicator == "high":
        score += 15  # Lock to avoid volatility
    elif scenario.volatility_indicator == "low":
        score -= 10  # Can float safely

    # Rate sensitivity - if borrower is rate sensitive, lean toward locking on good days
    if scenario.rate_sensitivity == "high":
        score += 5

    # Certainty preference
    if scenario.certainty_preference == "high":
        score += 10
    elif scenario.certainty_preference == "low":
        score -= 10

    # MBS price movement (positive = rates improving)
    if scenario.recent_price_changes_bps:
        if scenario.recent_price_changes_bps > 20:
            score -= 10  # Rates improving, can wait
        elif scenario.recent_price_changes_bps < -20:
            score += 15  # Rates worsening, lock now

    # Market trend
    if scenario.market_trend == "improving":
        score -= 10  # Wait for better rates
    elif scenario.market_trend == "worsening":
        score += 15  # Lock before rates rise

    # Ensure score stays in bounds
    return max(0, min(100, score))


def determine_recommendation(score: int, scenario: LoanScenario) -> dict:
    """Determine lock/float recommendation based on score and scenario"""

    # Calculate days to close for reasoning
    days_to_close = None
    if scenario.contract_close_date:
        try:
            close_date = datetime.fromisoformat(scenario.contract_close_date.replace('Z', '+00:00'))
            days_to_close = (close_date - datetime.now()).days
        except Exception:
            days_to_close = 30

    # Determine action
    if score >= 70:
        action = "LOCK_NOW"
        confidence = "high"
        reasoning = "Market conditions and timeline strongly favor locking now."
    elif score >= 55:
        action = "LOCK_NOW"
        confidence = "medium"
        reasoning = "Conditions lean toward locking. Consider locking unless you have high risk tolerance."
    elif score >= 45:
        action = "FLOAT_WITH_CAUTION"
        confidence = "medium"
        reasoning = "Neutral conditions. Can float short-term but monitor closely."
    else:
        action = "FLOAT"
        confidence = "medium" if score >= 35 else "high"
        reasoning = "Conditions favor floating to potentially capture better rates."

    # Override for critical timelines
    if days_to_close and days_to_close <= 10:
        action = "LOCK_NOW"
        confidence = "high"
        reasoning = f"With only {days_to_close} days to close, locking is strongly recommended regardless of market conditions."

    # Determine lock term
    if days_to_close:
        if days_to_close <= 15:
            lock_term = 15
        elif days_to_close <= 30:
            lock_term = 30
        elif days_to_close <= 45:
            lock_term = 45
        else:
            lock_term = 60
    else:
        lock_term = 30

    # Build key factors
    key_factors = []
    if days_to_close:
        key_factors.append(f"{days_to_close} days until closing")
    key_factors.append(f"Market volatility: {scenario.volatility_indicator or 'normal'}")
    key_factors.append(f"Market trend: {scenario.market_trend or 'stable'}")
    if scenario.rate_sensitivity:
        key_factors.append(f"Rate sensitivity: {scenario.rate_sensitivity}")

    return {
        "action": action,
        "confidence": confidence,
        "lock_term_recommendation": lock_term,
        "reasoning": reasoning,
        "key_factors": key_factors,
        "score": score
    }


def calculate_payment(loan_amount: float, rate: float, term_years: int = 30) -> float:
    """Calculate monthly payment"""
    monthly_rate = rate / 100 / 12
    num_payments = term_years * 12

    if monthly_rate == 0:
        return loan_amount / num_payments

    payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
    return round(payment, 2)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/v1/recommendations/quick")
async def get_quick_recommendation(request: QuickRecommendationRequest):
    """
    Get a quick rate lock recommendation based on loan scenario.

    This endpoint provides the same interface as the external rate-lock-intelligence
    microservice, allowing seamless migration to the integrated CRM backend.
    """
    try:
        scenario = request.scenario

        # Calculate lock score
        score = calculate_lock_score(scenario)

        # Get recommendation
        rec = determine_recommendation(score, scenario)

        # Calculate payment scenarios
        current_rate = scenario.current_rate or 6.75
        loan_amount = scenario.loan_amount

        current_payment = calculate_payment(loan_amount, current_rate)
        payment_if_up = calculate_payment(loan_amount, current_rate + 0.25)
        payment_if_down = calculate_payment(loan_amount, current_rate - 0.25)

        # Build response
        response = {
            "action": rec["action"],
            "confidence": rec["confidence"],
            "lock_term_recommendation": rec["lock_term_recommendation"],
            "reasoning": rec["reasoning"],
            "key_factors": rec["key_factors"],
            "risk_assessment": {
                "lock_score": score,
                "volatility_risk": scenario.volatility_indicator or "normal",
                "timeline_risk": "high" if rec["lock_term_recommendation"] <= 15 else "moderate",
                "market_risk": scenario.market_trend or "stable"
            },
            "market_outlook": {
                "current_rate": current_rate,
                "treasury_10yr": scenario.treasury_10yr_yield or 4.25,
                "mbs_price": scenario.mbs_price or 100.5,
                "trend": scenario.market_trend or "stable",
                "volatility": scenario.volatility_indicator or "normal"
            },
            "scenarios": {
                "lock_today": {
                    "rate": current_rate,
                    "monthly_payment": current_payment,
                    "description": f"Lock at {current_rate:.3f}% = ${current_payment:,.2f}/month"
                },
                "rate_up_25bps": {
                    "rate": current_rate + 0.25,
                    "monthly_payment": payment_if_up,
                    "payment_increase": round(payment_if_up - current_payment, 2),
                    "description": f"If rates rise 0.25% → ${payment_if_up:,.2f}/month (+${payment_if_up - current_payment:.2f})"
                },
                "rate_down_25bps": {
                    "rate": current_rate - 0.25,
                    "monthly_payment": payment_if_down,
                    "payment_decrease": round(current_payment - payment_if_down, 2),
                    "description": f"If rates fall 0.25% → ${payment_if_down:,.2f}/month (-${current_payment - payment_if_down:.2f})"
                }
            },
            "timestamp": datetime.now().isoformat()
        }

        return response

    except Exception as e:
        logger.error(f"Error generating recommendation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/v1/market/snapshot")
async def get_market_snapshot():
    """
    Get current market snapshot.

    Returns treasury yields, MBS prices, and market indicators.
    """
    try:
        # Try to get real market data from scrapers
        try:
            from scrapers import MarketDataOrchestrator
            orchestrator = MarketDataOrchestrator()
            snapshot = orchestrator.get_market_snapshot()

            if snapshot:
                return {
                    "timestamp": snapshot.get("timestamp", datetime.now().isoformat()),
                    "treasury_10yr_yield": snapshot.get("treasury", {}).get("10yr", 4.25),
                    "mbs_current_coupon": 6.0,
                    "mbs_price": 100.5,
                    "volatility_indicator": snapshot.get("volatility", {}).get("assessment", "normal"),
                    "market_trend": snapshot.get("recommendation", "stable").lower(),
                    "is_mock": False
                }
        except Exception as e:
            logger.warning(f"Could not fetch live market data: {e}")

        # Return mock data as fallback
        return {
            "timestamp": datetime.now().isoformat(),
            "treasury_10yr_yield": 4.25,
            "mbs_current_coupon": 6.0,
            "mbs_price": 100.5,
            "volatility_indicator": "normal",
            "market_trend": "stable",
            "is_mock": True
        }

    except Exception as e:
        logger.error(f"Error fetching market snapshot: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "rate-lock-intelligence",
        "integrated": True,
        "timestamp": datetime.now().isoformat()
    }
