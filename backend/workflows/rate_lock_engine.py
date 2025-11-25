"""
Rate Lock Intelligence Engine - Pipeline 360
TL Development, LLC

PRD Section 3.4 & Power Play 5 Implementation

This engine provides:
- Rate Lock Eligibility Check
- Lock Score Calculation Algorithm
- Lock Monitoring Subflow (for locked borrowers)
- Float Monitoring Subflow (for floating borrowers)
- Extension Strategy Analysis
- Float-Down Opportunity Detection
- Market Volatility Integration
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES FOR RATE LOCK INTELLIGENCE
# ============================================================================

@dataclass
class MarketSnapshot:
    """Current market conditions from get_market_intelligence"""
    treasury_10yr: float
    treasury_2yr: float
    mortgage_30yr: float
    mbs_price: float
    mbs_change: float  # Daily change in bps
    volatility_score: int  # 0-100
    timestamp: datetime


@dataclass
class LoanContext:
    """Loan-specific context for rate lock decisions"""
    loan_id: int
    loan_number: str
    borrower_name: str
    loan_amount: float
    current_rate: Optional[float]
    closing_date: Optional[datetime]
    lock_date: Optional[datetime]
    lock_expiration_date: Optional[datetime]
    lock_term_days: Optional[int]
    rate_lock_status: str
    borrower_risk_profile: Optional[str]
    property_identified: bool
    loan_structure_complete: bool


@dataclass
class RateLockAnalysis:
    """Complete rate lock analysis result"""
    eligible: bool
    eligibility_reason: str
    lock_score: int  # 0-100
    recommendation: str  # LOCK_NOW, FLOAT_AND_MONITOR, etc.
    recommendation_reason: str
    days_to_close: Optional[int]
    risk_level: str  # CRITICAL, HIGH, MODERATE, LOW, MINIMAL
    market_summary: str
    action_items: List[str]
    scenarios: Dict[str, Any]
    timestamp: datetime


# ============================================================================
# RATE LOCK INTELLIGENCE ENGINE
# ============================================================================

class RateLockIntelligenceEngine:
    """
    Main engine for rate lock decisions per PRD Section 3.4

    Inputs:
    - Market feeds (MBS, treasuries, volatility score)
    - Borrower risk profile
    - Program/product parameters
    - Lock desk policies
    - Closing date / Days-to-close
    - Loan amount
    - Extension cost tables

    Outputs:
    - Lock Now
    - Float & Monitor
    - Extend Lock
    - Explore Float-Down
    - Relock Strategy
    """

    # Days-to-Close Risk Matrix (PRD Section 3 - Lock/Float Decision Framework)
    DAYS_TO_CLOSE_RISK = {
        (0, 7): ("CRITICAL", 30),     # Lock immediately unless massive rally
        (8, 14): ("HIGH", 20),         # Lock on any green day
        (15, 21): ("MODERATE", 10),    # Can float with stop-loss discipline
        (22, 30): ("LOW", 0),          # Float for improvement, set alerts
        (31, 999): ("MINIMAL", -10),   # Float, but monitor weekly
    }

    # Extension cost estimates (bps per 15 days)
    EXTENSION_COSTS = {
        15: 12.5,   # 0.125%
        30: 25.0,   # 0.25%
        45: 37.5,   # 0.375%
    }

    def __init__(self, db_session=None):
        self.db = db_session

    def check_eligibility(self, loan: LoanContext) -> Tuple[bool, str]:
        """
        PRD Step 1: Rate Lock Eligibility Check

        Conditions:
        - Property identified
        - Loan structure complete
        - Closing date present

        Returns (eligible: bool, reason: str)
        """
        reasons = []

        if not loan.property_identified:
            reasons.append("No property identified")

        if not loan.loan_structure_complete:
            reasons.append("Loan structure incomplete")

        if not loan.closing_date:
            reasons.append("No closing date set")

        if reasons:
            return False, f"Not eligible: {', '.join(reasons)}"

        return True, "Eligible for rate lock"

    def calculate_days_to_close(self, closing_date: Optional[datetime]) -> Optional[int]:
        """Calculate days remaining until closing"""
        if not closing_date:
            return None

        now = datetime.now(timezone.utc)
        if closing_date.tzinfo is None:
            closing_date = closing_date.replace(tzinfo=timezone.utc)

        delta = closing_date - now
        return max(0, delta.days)

    def get_risk_level(self, days_to_close: Optional[int]) -> Tuple[str, int]:
        """
        Get risk level and score modifier based on days to close
        Returns (risk_level, score_modifier)
        """
        if days_to_close is None:
            return "UNKNOWN", 0

        for (min_days, max_days), (risk_level, modifier) in self.DAYS_TO_CLOSE_RISK.items():
            if min_days <= days_to_close <= max_days:
                return risk_level, modifier

        return "MINIMAL", -10

    def calculate_lock_score(
        self,
        market: MarketSnapshot,
        loan: LoanContext,
        days_to_close: Optional[int]
    ) -> int:
        """
        PRD Lock Score Calculation Algorithm

        Base Score = 50
        + MBS up > 10 bps today: +15
        + MBS up > 25 bps today: +25
        + 10Y Treasury down > 5 bps: +10
        + Closing in < 15 days: +20
        + Post-FOMC dovish: +15 (not implemented - would need fed calendar)
        - MBS down > 10 bps today: -15
        - MBS down > 25 bps today: -25
        - 10Y Treasury up > 5 bps: -10
        - Pre-CPI/Jobs (unknown): -10 (not implemented - would need econ calendar)
        - High volatility environment: -10

        Score > 70: STRONG LOCK
        Score 55-70: LEAN LOCK
        Score 45-55: NEUTRAL
        Score 30-45: LEAN FLOAT
        Score < 30: STRONG FLOAT
        """
        score = 50  # Base score

        # MBS movement scoring
        if market.mbs_change > 25:
            score += 25
        elif market.mbs_change > 10:
            score += 15
        elif market.mbs_change < -25:
            score -= 25
        elif market.mbs_change < -10:
            score -= 15

        # Days to close scoring
        if days_to_close is not None:
            _, modifier = self.get_risk_level(days_to_close)
            score += modifier

            # Extra urgency for very short closes
            if days_to_close <= 7:
                score += 10

        # Volatility penalty
        if market.volatility_score > 70:
            score -= 10
        elif market.volatility_score > 50:
            score -= 5

        # Borrower risk profile adjustment
        if loan.borrower_risk_profile == "Safety First":
            score += 10  # More likely to recommend locking
        elif loan.borrower_risk_profile == "Aggressive":
            score -= 10  # More tolerance for floating

        # Ensure score is within bounds
        return max(0, min(100, score))

    def get_recommendation(self, score: int, days_to_close: Optional[int], loan: LoanContext) -> Tuple[str, str]:
        """
        Get lock/float recommendation based on score and context
        Returns (recommendation, reason)
        """
        # Check for lock expiration scenarios first
        if loan.rate_lock_status == "Locked" and loan.lock_expiration_date:
            days_to_expiry = self.calculate_days_to_close(loan.lock_expiration_date)
            if days_to_expiry is not None and days_to_expiry <= 7:
                return "EXTEND_LOCK", f"Lock expires in {days_to_expiry} days - extension recommended"

        if loan.rate_lock_status == "Lock Expired":
            return "RELOCK", "Lock has expired - relock strategy needed"

        # Standard scoring-based recommendations
        if score > 70:
            reason = "Strong market position + timeline supports locking"
            if days_to_close and days_to_close <= 14:
                reason = f"Only {days_to_close} days to close - lock to protect"
            return "LOCK_NOW", reason

        elif score >= 55:
            reason = "Market conditions lean favorable for locking"
            return "LOCK_NOW", reason

        elif score >= 45:
            if days_to_close and days_to_close <= 21:
                return "LOCK_NOW", f"Neutral market but {days_to_close} days to close - lock for safety"
            return "FLOAT_AND_MONITOR", "Neutral conditions - monitor for better entry"

        elif score >= 30:
            if days_to_close and days_to_close <= 14:
                return "LOCK_NOW", f"Despite lean-float conditions, only {days_to_close} days to close"
            return "FLOAT_AND_MONITOR", "Market conditions favor floating short-term"

        else:  # score < 30
            if days_to_close and days_to_close <= 7:
                return "LOCK_NOW", "CRITICAL: Lock immediately despite conditions - closing imminent"
            return "FLOAT_AND_MONITOR", "Strong float signal - monitor daily for entry point"

    def check_float_down_opportunity(
        self,
        loan: LoanContext,
        market: MarketSnapshot,
        original_rate: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Check if float-down is available and beneficial

        Threshold: payment reduction >= $75-$100/month or cost/benefit favorable
        """
        if loan.rate_lock_status != "Locked":
            return {"available": False, "reason": "Not currently locked"}

        if not original_rate or not loan.loan_amount:
            return {"available": False, "reason": "Missing rate or loan amount data"}

        # Estimate current market rate
        current_market_rate = market.mortgage_30yr

        # Rate improvement needed for float-down (typically 0.25%+)
        rate_improvement = original_rate - current_market_rate

        if rate_improvement < 0.25:
            return {
                "available": False,
                "reason": f"Rate improvement of {rate_improvement:.3f}% insufficient (need 0.25%+)",
                "current_locked_rate": original_rate,
                "current_market_rate": current_market_rate
            }

        # Calculate monthly payment savings (rough estimate)
        # Per PRD: 0.25% rate change ≈ $15/month per $100,000
        monthly_savings = (rate_improvement / 0.25) * 15 * (loan.loan_amount / 100000)

        return {
            "available": True,
            "reason": f"Market improved {rate_improvement:.3f}% - float-down recommended",
            "current_locked_rate": original_rate,
            "current_market_rate": current_market_rate,
            "rate_improvement": rate_improvement,
            "estimated_monthly_savings": round(monthly_savings, 2),
            "recommendation": "Contact lender to explore float-down option"
        }

    def analyze_extension_strategy(
        self,
        loan: LoanContext,
        expected_delay_days: int = 15
    ) -> Dict[str, Any]:
        """
        Analyze lock extension vs relock strategy

        Factors:
        - Expected delay vs extension cost
        - Risk of relock/reprice
        """
        if loan.rate_lock_status != "Locked":
            return {"needed": False, "reason": "Not currently locked"}

        if not loan.lock_expiration_date:
            return {"needed": False, "reason": "No lock expiration date set"}

        days_to_expiry = self.calculate_days_to_close(loan.lock_expiration_date)

        if days_to_expiry is None or days_to_expiry > 10:
            return {"needed": False, "reason": f"Lock has {days_to_expiry} days remaining - no action needed"}

        # Calculate extension cost
        extension_cost_bps = self.EXTENSION_COSTS.get(expected_delay_days, 25.0)
        extension_cost_dollars = (extension_cost_bps / 100) * (loan.loan_amount or 0) / 100

        return {
            "needed": True,
            "days_to_expiry": days_to_expiry,
            "expected_delay_days": expected_delay_days,
            "extension_cost_bps": extension_cost_bps,
            "extension_cost_dollars": round(extension_cost_dollars, 2),
            "recommendation": "EXTEND_LOCK" if days_to_expiry <= 5 else "MONITOR_CLOSELY",
            "reason": f"Lock expires in {days_to_expiry} days. Extension cost: {extension_cost_bps} bps (${extension_cost_dollars:.2f})"
        }

    def run_full_analysis(
        self,
        loan: LoanContext,
        market: MarketSnapshot
    ) -> RateLockAnalysis:
        """
        PRD Step 2-4: Full Rate Lock Intelligence Analysis

        1. Check eligibility
        2. Calculate lock score
        3. Generate recommendation
        4. Create action items
        """
        # Step 1: Eligibility Check
        eligible, eligibility_reason = self.check_eligibility(loan)

        # Calculate days to close
        days_to_close = self.calculate_days_to_close(loan.closing_date)

        # Get risk level
        risk_level, _ = self.get_risk_level(days_to_close)

        # If not eligible, return early with limited analysis
        if not eligible:
            return RateLockAnalysis(
                eligible=False,
                eligibility_reason=eligibility_reason,
                lock_score=0,
                recommendation="NOT_ELIGIBLE",
                recommendation_reason=eligibility_reason,
                days_to_close=days_to_close,
                risk_level=risk_level,
                market_summary=self._format_market_summary(market),
                action_items=["Complete loan structure", "Identify property", "Set closing date"],
                scenarios={},
                timestamp=datetime.now(timezone.utc)
            )

        # Step 2: Calculate Lock Score
        lock_score = self.calculate_lock_score(market, loan, days_to_close)

        # Step 3: Get Recommendation
        recommendation, recommendation_reason = self.get_recommendation(lock_score, days_to_close, loan)

        # Step 4: Generate Action Items
        action_items = self._generate_action_items(recommendation, loan, days_to_close, market)

        # Generate scenarios
        scenarios = self._generate_scenarios(loan, market, lock_score)

        return RateLockAnalysis(
            eligible=True,
            eligibility_reason=eligibility_reason,
            lock_score=lock_score,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            days_to_close=days_to_close,
            risk_level=risk_level,
            market_summary=self._format_market_summary(market),
            action_items=action_items,
            scenarios=scenarios,
            timestamp=datetime.now(timezone.utc)
        )

    def _format_market_summary(self, market: MarketSnapshot) -> str:
        """Format market conditions for display"""
        mbs_direction = "up" if market.mbs_change > 0 else "down" if market.mbs_change < 0 else "flat"
        mbs_sign = "+" if market.mbs_change > 0 else ""

        return (
            f"MBS 6.0: {market.mbs_price:.2f} ({mbs_sign}{market.mbs_change:.0f} bps {mbs_direction}) | "
            f"10Y: {market.treasury_10yr:.2f}% | "
            f"30Y Rate: {market.mortgage_30yr:.3f}% | "
            f"Volatility: {market.volatility_score}/100"
        )

    def _generate_action_items(
        self,
        recommendation: str,
        loan: LoanContext,
        days_to_close: Optional[int],
        market: MarketSnapshot
    ) -> List[str]:
        """Generate specific action items based on recommendation"""
        actions = []

        if recommendation == "LOCK_NOW":
            actions.append("Contact lock desk to secure rate")
            actions.append(f"Confirm {loan.lock_term_days or 30}-day lock term covers closing date")
            if days_to_close and days_to_close <= 14:
                actions.append("URGENT: Lock today - closing imminent")

        elif recommendation == "FLOAT_AND_MONITOR":
            actions.append("Set rate alert for 0.125% improvement")
            actions.append("Review market conditions tomorrow AM")
            if days_to_close and days_to_close <= 21:
                actions.append(f"CAUTION: Only {days_to_close} days to close - set mental stop-loss")

        elif recommendation == "EXTEND_LOCK":
            actions.append("Contact lock desk about extension options")
            actions.append("Calculate extension cost vs relock risk")
            actions.append("Verify closing timeline with processor")

        elif recommendation == "EXPLORE_FLOAT_DOWN":
            actions.append("Contact lender about float-down eligibility")
            actions.append("Calculate potential savings")
            actions.append("Review float-down terms and costs")

        elif recommendation == "RELOCK":
            actions.append("Get current rate sheet from lender")
            actions.append("Compare relock rate to original")
            actions.append("Discuss options with borrower")

        # Add market-specific actions
        if market.volatility_score > 70:
            actions.append("HIGH VOLATILITY: Expect reprices - act quickly")

        return actions

    def _generate_scenarios(
        self,
        loan: LoanContext,
        market: MarketSnapshot,
        lock_score: int
    ) -> Dict[str, Any]:
        """Generate what-if scenarios"""
        scenarios = {}

        # Scenario 1: Lock today
        if loan.loan_amount:
            # Calculate payment at current rate
            rate = market.mortgage_30yr
            monthly_rate = rate / 100 / 12
            term = 360
            amount = loan.loan_amount

            if monthly_rate > 0:
                payment = amount * (monthly_rate * (1 + monthly_rate)**term) / ((1 + monthly_rate)**term - 1)
                scenarios["lock_today"] = {
                    "rate": rate,
                    "monthly_payment": round(payment, 2),
                    "description": f"Lock at {rate:.3f}% = ${payment:,.2f}/month"
                }

                # Scenario 2: Rate up 0.25%
                rate_up = rate + 0.25
                monthly_rate_up = rate_up / 100 / 12
                payment_up = amount * (monthly_rate_up * (1 + monthly_rate_up)**term) / ((1 + monthly_rate_up)**term - 1)
                scenarios["rate_up_25bps"] = {
                    "rate": rate_up,
                    "monthly_payment": round(payment_up, 2),
                    "payment_increase": round(payment_up - payment, 2),
                    "description": f"If rates rise 0.25% → ${payment_up:,.2f}/month (+${payment_up - payment:,.2f})"
                }

                # Scenario 3: Rate down 0.25%
                rate_down = rate - 0.25
                monthly_rate_down = rate_down / 100 / 12
                payment_down = amount * (monthly_rate_down * (1 + monthly_rate_down)**term) / ((1 + monthly_rate_down)**term - 1)
                scenarios["rate_down_25bps"] = {
                    "rate": rate_down,
                    "monthly_payment": round(payment_down, 2),
                    "payment_decrease": round(payment - payment_down, 2),
                    "description": f"If rates fall 0.25% → ${payment_down:,.2f}/month (-${payment - payment_down:,.2f})"
                }

        return scenarios


# ============================================================================
# LOCK MONITORING SUBFLOW (PRD Section 5 - Step 5)
# ============================================================================

class LockMonitoringSubflow:
    """
    Executed when rate_lock_status = LOCKED

    Daily checks:
    - Analyze expiration window
    - Evaluate risk of extension
    - Check for float-down opportunity
    - Create tasks if action required
    """

    def __init__(self, engine: RateLockIntelligenceEngine):
        self.engine = engine

    def run_daily_check(self, loan: LoanContext, market: MarketSnapshot) -> Dict[str, Any]:
        """Run daily lock health check"""
        results = {
            "loan_id": loan.loan_id,
            "loan_number": loan.loan_number,
            "check_date": datetime.now(timezone.utc).isoformat(),
            "alerts": [],
            "tasks": [],
            "status": "healthy"
        }

        # Check 1: Lock expiration window
        if loan.lock_expiration_date:
            days_to_expiry = self.engine.calculate_days_to_close(loan.lock_expiration_date)

            if days_to_expiry is not None:
                if days_to_expiry <= 3:
                    results["alerts"].append({
                        "type": "CRITICAL",
                        "message": f"Lock expires in {days_to_expiry} days!",
                        "action": "Immediate extension decision required"
                    })
                    results["tasks"].append({
                        "title": f"URGENT: Lock extension decision for {loan.borrower_name}",
                        "priority": "urgent",
                        "due_hours": 4
                    })
                    results["status"] = "critical"

                elif days_to_expiry <= 7:
                    results["alerts"].append({
                        "type": "WARNING",
                        "message": f"Lock expires in {days_to_expiry} days",
                        "action": "Review extension strategy"
                    })
                    results["tasks"].append({
                        "title": f"Lock extension review for {loan.borrower_name}",
                        "priority": "high",
                        "due_hours": 24
                    })
                    results["status"] = "warning"

        # Check 2: Float-down opportunity
        if loan.current_rate:
            float_down = self.engine.check_float_down_opportunity(loan, market, loan.current_rate)
            if float_down.get("available"):
                results["alerts"].append({
                    "type": "OPPORTUNITY",
                    "message": f"Float-down available: {float_down['rate_improvement']:.3f}% improvement",
                    "action": "Contact lender for float-down"
                })
                results["tasks"].append({
                    "title": f"Float-down review for {loan.borrower_name} - Save ~${float_down['estimated_monthly_savings']}/month",
                    "priority": "high",
                    "due_hours": 24
                })
                results["float_down_details"] = float_down

        return results


# ============================================================================
# FLOAT MONITORING SUBFLOW (PRD Section 5 - Step 5)
# ============================================================================

class FloatMonitoringSubflow:
    """
    Executed when rate_lock_status = FLOAT_MONITORING

    Daily or event-triggered:
    - Re-run rate intelligence on volatility spikes
    - Alert borrower + LO if risk threshold breached
    - Move to LOCK_RECOMMENDED state when needed
    """

    def __init__(self, engine: RateLockIntelligenceEngine):
        self.engine = engine

    def run_market_check(self, loan: LoanContext, market: MarketSnapshot) -> Dict[str, Any]:
        """Check if market conditions warrant locking"""
        results = {
            "loan_id": loan.loan_id,
            "loan_number": loan.loan_number,
            "check_date": datetime.now(timezone.utc).isoformat(),
            "alerts": [],
            "tasks": [],
            "lock_recommended": False,
            "urgency": "normal"
        }

        # Run full analysis
        analysis = self.engine.run_full_analysis(loan, market)

        # Check for lock trigger conditions
        days_to_close = analysis.days_to_close

        # Condition 1: Days to close dropping below threshold
        if days_to_close is not None and days_to_close <= 15:
            results["alerts"].append({
                "type": "WARNING",
                "message": f"Only {days_to_close} days to close while floating",
                "action": "Strongly consider locking"
            })
            results["urgency"] = "high"

        if days_to_close is not None and days_to_close <= 7:
            results["alerts"].append({
                "type": "CRITICAL",
                "message": f"CRITICAL: {days_to_close} days to close - lock immediately",
                "action": "Lock today"
            })
            results["lock_recommended"] = True
            results["urgency"] = "critical"
            results["tasks"].append({
                "title": f"URGENT: Lock rate for {loan.borrower_name} - closing in {days_to_close} days",
                "priority": "urgent",
                "due_hours": 2
            })

        # Condition 2: Volatility spike
        if market.volatility_score > 75:
            results["alerts"].append({
                "type": "WARNING",
                "message": f"High market volatility ({market.volatility_score}/100)",
                "action": "Consider locking to reduce risk"
            })
            if results["urgency"] == "normal":
                results["urgency"] = "elevated"

        # Condition 3: Significant adverse move
        if market.mbs_change < -20:
            results["alerts"].append({
                "type": "WARNING",
                "message": f"MBS down {abs(market.mbs_change):.0f} bps today",
                "action": "Rates rising - consider locking"
            })
            results["urgency"] = "high"

        # Condition 4: Score indicates lock
        if analysis.lock_score >= 70:
            results["lock_recommended"] = True
            results["alerts"].append({
                "type": "OPPORTUNITY",
                "message": f"Lock score {analysis.lock_score}/100 - favorable conditions",
                "action": "Good opportunity to lock"
            })
            results["tasks"].append({
                "title": f"Rate lock opportunity for {loan.borrower_name}",
                "priority": "high",
                "due_hours": 8
            })

        results["analysis"] = {
            "lock_score": analysis.lock_score,
            "recommendation": analysis.recommendation,
            "market_summary": analysis.market_summary
        }

        return results


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_market_snapshot(market_data: Dict[str, Any]) -> MarketSnapshot:
    """Create MarketSnapshot from market intelligence data"""
    return MarketSnapshot(
        treasury_10yr=market_data.get("treasury_yields", {}).get("10yr", 4.25),
        treasury_2yr=market_data.get("treasury_yields", {}).get("2yr", 4.15),
        mortgage_30yr=market_data.get("mortgage_rates", {}).get("mortgage_30yr", 6.875),
        mbs_price=market_data.get("mbs_prices", {}).get("fnma_6_0", {}).get("price", 100.0),
        mbs_change=market_data.get("mbs_prices", {}).get("fnma_6_0", {}).get("change", 0),
        volatility_score=market_data.get("volatility", {}).get("volatility_score", 50),
        timestamp=datetime.now(timezone.utc)
    )


def create_loan_context(loan) -> LoanContext:
    """Create LoanContext from SQLAlchemy Loan model"""
    # Determine if loan structure is complete
    loan_structure_complete = all([
        loan.amount,
        loan.loan_type or loan.program,
        loan.borrower_name
    ])

    # Determine if property is identified
    property_identified = bool(loan.property_address or (loan.property_city and loan.property_state))

    return LoanContext(
        loan_id=loan.id,
        loan_number=loan.loan_number,
        borrower_name=loan.borrower_name,
        loan_amount=loan.amount,
        current_rate=loan.rate,
        closing_date=loan.closing_date,
        lock_date=loan.lock_date,
        lock_expiration_date=loan.lock_expiration_date,
        lock_term_days=loan.lock_term_days if hasattr(loan, 'lock_term_days') else None,
        rate_lock_status=loan.rate_lock_status.value if hasattr(loan, 'rate_lock_status') and loan.rate_lock_status else "Not Eligible",
        borrower_risk_profile=loan.borrower_risk_profile.value if hasattr(loan, 'borrower_risk_profile') and loan.borrower_risk_profile else None,
        property_identified=property_identified,
        loan_structure_complete=loan_structure_complete
    )
