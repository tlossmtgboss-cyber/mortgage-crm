"""
Pipeline Probability Scores Service

AI-powered loan closing probability prediction for Advanced Analytics.
Uses historical data patterns and loan characteristics to predict:
- Probability of closing
- Risk factors
- Recommended actions to improve close rate
- Expected days to close
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.workflow_constants import STAGE_PROBABILITY_WEIGHTS, STAGE_SLA_DAYS

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level categories."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProbabilityTrend(str, Enum):
    """Probability trend direction."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class RiskFactor:
    """Individual risk factor affecting close probability."""
    factor: str
    description: str
    impact: float  # -1.0 to 0.0 (negative impact on probability)
    category: str  # "timing", "financial", "documentation", "borrower", "market"
    mitigation: Optional[str] = None


@dataclass
class StrengthFactor:
    """Positive factor increasing close probability."""
    factor: str
    description: str
    impact: float  # 0.0 to 1.0 (positive impact on probability)
    category: str


@dataclass
class RecommendedAction:
    """Recommended action to improve close probability."""
    action: str
    priority: str  # "high", "medium", "low"
    expected_impact: float  # Expected probability increase
    effort: str  # "low", "medium", "high"
    deadline_days: Optional[int] = None


@dataclass
class ProbabilityScore:
    """Complete probability score for a loan."""
    loan_id: int
    loan_number: str
    borrower_name: str
    loan_amount: float
    current_status: str

    # Core scores
    close_probability: float  # 0-100
    confidence_level: float  # 0-100
    risk_level: RiskLevel
    trend: ProbabilityTrend

    # Timing predictions
    expected_close_days: int
    expected_close_date: Optional[str]
    lock_expiration_risk: bool

    # Factors
    risk_factors: List[RiskFactor] = field(default_factory=list)
    strength_factors: List[StrengthFactor] = field(default_factory=list)
    recommended_actions: List[RecommendedAction] = field(default_factory=list)

    # Historical comparison
    similar_loans_close_rate: Optional[float] = None
    stage_avg_probability: Optional[float] = None

    # Metadata
    calculated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    model_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result["risk_level"] = self.risk_level.value
        result["trend"] = self.trend.value
        return result


@dataclass
class PipelineProbabilitySummary:
    """Summary of probability scores across pipeline."""
    total_loans: int
    total_volume: float

    # Risk distribution
    low_risk_count: int
    medium_risk_count: int
    high_risk_count: int
    critical_risk_count: int

    # Probability brackets
    high_probability_count: int  # >80%
    medium_probability_count: int  # 50-80%
    low_probability_count: int  # <50%

    # Weighted metrics
    weighted_avg_probability: float
    expected_funded_volume: float
    at_risk_volume: float

    # Trends
    improving_count: int
    declining_count: int

    # Top concerns
    top_risk_factors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PipelineProbabilityService:
    """Service for calculating and managing pipeline probability scores."""

    # Imported from workflow_constants (canonical source of truth)
    STAGE_WEIGHTS = STAGE_PROBABILITY_WEIGHTS

    # SLA targets derived from canonical STAGE_SLA_DAYS
    # (Previously used lowercase transition-style keys; now uses the flat lookup)
    SLA_TARGETS = STAGE_SLA_DAYS

    def __init__(self, db: Session):
        self.db = db

    async def calculate_probability(self, loan_id: int) -> ProbabilityScore:
        """Calculate closing probability for a single loan."""
        # Get loan details
        loan = await self._get_loan_details(loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Calculate base probability from stage
        base_probability = self._calculate_base_probability(loan)

        # Analyze risk factors
        risk_factors = await self._analyze_risk_factors(loan)

        # Analyze strength factors
        strength_factors = await self._analyze_strength_factors(loan)

        # Calculate adjustments
        risk_adjustment = sum(rf.impact for rf in risk_factors)
        strength_adjustment = sum(sf.impact for sf in strength_factors)

        # Final probability (clamped 0-100)
        final_probability = max(0, min(100,
            (base_probability * 100) + (risk_adjustment * 100) + (strength_adjustment * 100)
        ))

        # Determine risk level
        risk_level = self._determine_risk_level(final_probability, risk_factors)

        # Calculate trend
        trend = await self._calculate_trend(loan_id, final_probability)

        # Predict close timing
        expected_days, expected_date = await self._predict_close_timing(loan)

        # Check lock expiration risk
        lock_risk = self._check_lock_expiration_risk(loan, expected_days)

        # Generate recommendations
        recommendations = self._generate_recommendations(loan, risk_factors, final_probability)

        # Get comparison metrics
        similar_rate = await self._get_similar_loans_close_rate(loan)
        stage_avg = await self._get_stage_avg_probability(loan["status"])

        # Calculate confidence level
        confidence = self._calculate_confidence(loan, risk_factors, strength_factors)

        return ProbabilityScore(
            loan_id=loan_id,
            loan_number=loan["loan_number"],
            borrower_name=loan["borrower_name"],
            loan_amount=float(loan["loan_amount"] or 0),
            current_status=loan["status"],
            close_probability=round(final_probability, 1),
            confidence_level=round(confidence, 1),
            risk_level=risk_level,
            trend=trend,
            expected_close_days=expected_days,
            expected_close_date=expected_date,
            lock_expiration_risk=lock_risk,
            risk_factors=risk_factors,
            strength_factors=strength_factors,
            recommended_actions=recommendations,
            similar_loans_close_rate=similar_rate,
            stage_avg_probability=stage_avg,
        )

    async def calculate_pipeline_scores(
        self,
        lo_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        status_filter: Optional[List[str]] = None,
    ) -> List[ProbabilityScore]:
        """Calculate probability scores for entire pipeline."""
        # Get active loans
        params: Dict[str, Any] = {}
        filters = ["l.status NOT IN ('funded', 'cancelled', 'denied')"]

        if lo_id:
            filters.append("l.loan_officer_id = :lo_id")
            params["lo_id"] = lo_id
        if branch_id:
            filters.append("l.branch_id = :branch_id")
            params["branch_id"] = branch_id
        if status_filter:
            filters.append("l.status = ANY(:statuses)")
            params["statuses"] = status_filter

        where_clause = " AND ".join(filters)

        result = self.db.execute(text(f"""
            SELECT l.id
            FROM loans l
            WHERE {where_clause}
            ORDER BY l.loan_amount DESC
        """), params)

        loan_ids = [row[0] for row in result.fetchall()]

        # Calculate scores for each loan
        scores = []
        for loan_id in loan_ids:
            try:
                score = await self.calculate_probability(loan_id)
                scores.append(score)
            except SQLAlchemyError as e:
                logger.error(f"Failed to calculate probability for loan {loan_id}: {e}")

        # Sort by probability (lowest first - needs attention)
        scores.sort(key=lambda x: x.close_probability)

        return scores

    async def get_pipeline_summary(
        self,
        lo_id: Optional[int] = None,
        branch_id: Optional[int] = None,
    ) -> PipelineProbabilitySummary:
        """Get summary of probability scores across pipeline."""
        scores = await self.calculate_pipeline_scores(lo_id=lo_id, branch_id=branch_id)

        if not scores:
            return PipelineProbabilitySummary(
                total_loans=0,
                total_volume=0,
                low_risk_count=0,
                medium_risk_count=0,
                high_risk_count=0,
                critical_risk_count=0,
                high_probability_count=0,
                medium_probability_count=0,
                low_probability_count=0,
                weighted_avg_probability=0,
                expected_funded_volume=0,
                at_risk_volume=0,
                improving_count=0,
                declining_count=0,
            )

        total_volume = sum(s.loan_amount for s in scores)

        # Risk distribution
        low_risk = len([s for s in scores if s.risk_level == RiskLevel.LOW])
        medium_risk = len([s for s in scores if s.risk_level == RiskLevel.MEDIUM])
        high_risk = len([s for s in scores if s.risk_level == RiskLevel.HIGH])
        critical_risk = len([s for s in scores if s.risk_level == RiskLevel.CRITICAL])

        # Probability brackets
        high_prob = len([s for s in scores if s.close_probability >= 80])
        medium_prob = len([s for s in scores if 50 <= s.close_probability < 80])
        low_prob = len([s for s in scores if s.close_probability < 50])

        # Weighted average
        weighted_sum = sum(s.close_probability * s.loan_amount for s in scores)
        weighted_avg = weighted_sum / total_volume if total_volume > 0 else 0

        # Expected funded volume
        expected_funded = sum(s.loan_amount * (s.close_probability / 100) for s in scores)

        # At-risk volume (high/critical risk)
        at_risk = sum(s.loan_amount for s in scores if s.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL])

        # Trends
        improving = len([s for s in scores if s.trend == ProbabilityTrend.IMPROVING])
        declining = len([s for s in scores if s.trend == ProbabilityTrend.DECLINING])

        # Top risk factors across pipeline
        all_risk_factors: Dict[str, int] = {}
        for score in scores:
            for rf in score.risk_factors:
                all_risk_factors[rf.factor] = all_risk_factors.get(rf.factor, 0) + 1

        top_risks = [
            {"factor": factor, "count": count}
            for factor, count in sorted(all_risk_factors.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        return PipelineProbabilitySummary(
            total_loans=len(scores),
            total_volume=total_volume,
            low_risk_count=low_risk,
            medium_risk_count=medium_risk,
            high_risk_count=high_risk,
            critical_risk_count=critical_risk,
            high_probability_count=high_prob,
            medium_probability_count=medium_prob,
            low_probability_count=low_prob,
            weighted_avg_probability=round(weighted_avg, 1),
            expected_funded_volume=round(expected_funded, 2),
            at_risk_volume=round(at_risk, 2),
            improving_count=improving,
            declining_count=declining,
            top_risk_factors=top_risks,
        )

    async def get_at_risk_loans(
        self,
        threshold: float = 50.0,
        lo_id: Optional[int] = None,
        limit: int = 20,
    ) -> List[ProbabilityScore]:
        """Get loans below probability threshold."""
        scores = await self.calculate_pipeline_scores(lo_id=lo_id)
        at_risk = [s for s in scores if s.close_probability < threshold]
        return at_risk[:limit]

    async def get_probability_trends(
        self,
        lo_id: Optional[int] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get probability trends over time."""
        params: Dict[str, Any] = {"days": days}
        filters = ["ps.calculated_at >= CURRENT_DATE - :days"]

        if lo_id:
            filters.append("l.loan_officer_id = :lo_id")
            params["lo_id"] = lo_id

        where_clause = " AND ".join(filters)

        # Get historical scores
        result = self.db.execute(text(f"""
            SELECT
                DATE(ps.calculated_at) as date,
                AVG(ps.close_probability) as avg_probability,
                COUNT(*) as loan_count,
                SUM(CASE WHEN ps.risk_level = 'critical' THEN 1 ELSE 0 END) as critical_count
            FROM pipeline_probability_scores ps
            JOIN loans l ON l.id = ps.loan_id
            WHERE {where_clause}
            GROUP BY DATE(ps.calculated_at)
            ORDER BY date ASC
        """), params)

        daily_trends = []
        for row in result.fetchall():
            daily_trends.append({
                "date": row[0].isoformat() if row[0] else None,
                "avg_probability": round(float(row[1] or 0), 1),
                "loan_count": row[2],
                "critical_count": row[3],
            })

        return {
            "period_days": days,
            "daily_trends": daily_trends,
            "trend_direction": self._calculate_overall_trend(daily_trends),
        }

    # Private helper methods

    async def _get_loan_details(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Get loan details for probability calculation."""
        result = self.db.execute(text("""
            SELECT
                l.id, l.loan_number, l.status, l.loan_amount, l.loan_type,
                l.borrower_name, l.borrower_credit_score,
                l.property_type, l.occupancy_type, l.ltv, l.dti,
                l.application_date, l.disclosure_sent_at, l.submitted_to_uw_at,
                l.approval_date, l.clear_to_close_at, l.expected_close_date,
                l.lock_expiration_date, l.status_changed_at,
                l.loan_officer_id, l.processor_id,
                u.name as lo_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id})

        row = result.fetchone()
        if not row:
            return None

        columns = result.keys()
        return dict(zip(columns, row))

    def _calculate_base_probability(self, loan: Dict[str, Any]) -> float:
        """Calculate base probability from loan stage."""
        status = loan.get("status", "lead").lower()
        return self.STAGE_WEIGHTS.get(status, 0.1)

    async def _analyze_risk_factors(self, loan: Dict[str, Any]) -> List[RiskFactor]:
        """Analyze risk factors for the loan."""
        factors = []

        # Timing risks
        if loan.get("status_changed_at"):
            days_in_stage = (datetime.now() - loan["status_changed_at"]).days
            if days_in_stage > 14:
                factors.append(RiskFactor(
                    factor="stale_status",
                    description=f"Loan has been in {loan['status']} for {days_in_stage} days",
                    impact=-0.15,
                    category="timing",
                    mitigation="Review for blockers and update status",
                ))
            elif days_in_stage > 7:
                factors.append(RiskFactor(
                    factor="aging_status",
                    description=f"Loan aging in {loan['status']} ({days_in_stage} days)",
                    impact=-0.08,
                    category="timing",
                    mitigation="Check for pending items",
                ))

        # Lock expiration risk
        if loan.get("lock_expiration_date"):
            days_until_expiry = (loan["lock_expiration_date"] - datetime.now().date()).days
            if days_until_expiry < 0:
                factors.append(RiskFactor(
                    factor="lock_expired",
                    description="Rate lock has expired",
                    impact=-0.25,
                    category="timing",
                    mitigation="Extend lock or renegotiate rate",
                ))
            elif days_until_expiry < 7:
                factors.append(RiskFactor(
                    factor="lock_expiring_soon",
                    description=f"Rate lock expires in {days_until_expiry} days",
                    impact=-0.12,
                    category="timing",
                    mitigation="Expedite closing or prepare lock extension",
                ))

        # Credit risk
        credit_score = loan.get("borrower_credit_score")
        if credit_score:
            if credit_score < 620:
                factors.append(RiskFactor(
                    factor="low_credit_score",
                    description=f"Credit score {credit_score} may limit options",
                    impact=-0.20,
                    category="financial",
                    mitigation="Explore FHA or credit repair options",
                ))
            elif credit_score < 680:
                factors.append(RiskFactor(
                    factor="marginal_credit",
                    description=f"Credit score {credit_score} is marginal",
                    impact=-0.08,
                    category="financial",
                ))

        # DTI risk
        dti = loan.get("dti")
        if dti:
            if dti > 50:
                factors.append(RiskFactor(
                    factor="high_dti",
                    description=f"DTI of {dti}% exceeds guidelines",
                    impact=-0.18,
                    category="financial",
                    mitigation="Explore debt payoff or income documentation",
                ))
            elif dti > 43:
                factors.append(RiskFactor(
                    factor="elevated_dti",
                    description=f"DTI of {dti}% is elevated",
                    impact=-0.08,
                    category="financial",
                ))

        # LTV risk
        ltv = loan.get("ltv")
        if ltv:
            if ltv > 97:
                factors.append(RiskFactor(
                    factor="high_ltv",
                    description=f"LTV of {ltv}% is very high",
                    impact=-0.12,
                    category="financial",
                    mitigation="Verify down payment source or consider DPA",
                ))
            elif ltv > 95:
                factors.append(RiskFactor(
                    factor="elevated_ltv",
                    description=f"LTV of {ltv}% requires PMI",
                    impact=-0.05,
                    category="financial",
                ))

        # Document-related risks (check for missing/pending)
        missing_docs = await self._get_missing_documents_count(loan["id"])
        if missing_docs > 5:
            factors.append(RiskFactor(
                factor="many_missing_docs",
                description=f"{missing_docs} documents still needed",
                impact=-0.15,
                category="documentation",
                mitigation="Send borrower document checklist",
            ))
        elif missing_docs > 0:
            factors.append(RiskFactor(
                factor="pending_documents",
                description=f"{missing_docs} documents pending",
                impact=-0.05,
                category="documentation",
            ))

        # Outstanding conditions
        open_conditions = await self._get_open_conditions_count(loan["id"])
        if open_conditions > 10:
            factors.append(RiskFactor(
                factor="many_conditions",
                description=f"{open_conditions} conditions outstanding",
                impact=-0.18,
                category="documentation",
                mitigation="Prioritize critical conditions",
            ))
        elif open_conditions > 5:
            factors.append(RiskFactor(
                factor="conditions_pending",
                description=f"{open_conditions} conditions to clear",
                impact=-0.08,
                category="documentation",
            ))

        return factors

    async def _analyze_strength_factors(self, loan: Dict[str, Any]) -> List[StrengthFactor]:
        """Analyze positive factors for the loan."""
        factors = []

        # Strong credit
        credit_score = loan.get("borrower_credit_score")
        if credit_score:
            if credit_score >= 760:
                factors.append(StrengthFactor(
                    factor="excellent_credit",
                    description=f"Excellent credit score of {credit_score}",
                    impact=0.10,
                    category="financial",
                ))
            elif credit_score >= 720:
                factors.append(StrengthFactor(
                    factor="good_credit",
                    description=f"Good credit score of {credit_score}",
                    impact=0.05,
                    category="financial",
                ))

        # Low DTI
        dti = loan.get("dti")
        if dti and dti < 30:
            factors.append(StrengthFactor(
                factor="low_dti",
                description=f"Strong DTI of {dti}%",
                impact=0.08,
                category="financial",
            ))

        # Low LTV
        ltv = loan.get("ltv")
        if ltv and ltv < 80:
            factors.append(StrengthFactor(
                factor="low_ltv",
                description=f"No PMI required with {ltv}% LTV",
                impact=0.06,
                category="financial",
            ))

        # Primary residence
        if loan.get("occupancy_type") == "primary":
            factors.append(StrengthFactor(
                factor="primary_residence",
                description="Primary residence purchase",
                impact=0.05,
                category="borrower",
            ))

        # Conventional loan (simpler process)
        if loan.get("loan_type") == "conventional":
            factors.append(StrengthFactor(
                factor="conventional_loan",
                description="Conventional loan - streamlined process",
                impact=0.03,
                category="financial",
            ))

        # Advanced stage
        status = loan.get("status", "").lower()
        if status in ["approved", "clear_to_close", "docs_out", "docs_back"]:
            factors.append(StrengthFactor(
                factor="advanced_stage",
                description=f"Loan is in {status} stage",
                impact=0.10,
                category="timing",
            ))

        return factors

    def _determine_risk_level(
        self,
        probability: float,
        risk_factors: List[RiskFactor],
    ) -> RiskLevel:
        """Determine overall risk level."""
        critical_factors = len([rf for rf in risk_factors if rf.impact < -0.15])

        if probability < 30 or critical_factors >= 2:
            return RiskLevel.CRITICAL
        elif probability < 50 or critical_factors >= 1:
            return RiskLevel.HIGH
        elif probability < 70:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    async def _calculate_trend(
        self,
        loan_id: int,
        current_probability: float,
    ) -> ProbabilityTrend:
        """Calculate probability trend based on history."""
        # Get previous score
        result = self.db.execute(text("""
            SELECT close_probability
            FROM pipeline_probability_scores
            WHERE loan_id = :loan_id
            ORDER BY calculated_at DESC
            LIMIT 1 OFFSET 1
        """), {"loan_id": loan_id})

        row = result.fetchone()
        if not row:
            return ProbabilityTrend.STABLE

        previous = float(row[0])
        diff = current_probability - previous

        if diff > 5:
            return ProbabilityTrend.IMPROVING
        elif diff < -5:
            return ProbabilityTrend.DECLINING
        else:
            return ProbabilityTrend.STABLE

    async def _predict_close_timing(
        self,
        loan: Dict[str, Any],
    ) -> tuple[int, Optional[str]]:
        """Predict expected days to close."""
        status = loan.get("status", "lead").lower()

        # Base days from stage
        stage_to_close = {
            "lead": 60,
            "application": 45,
            "processing": 35,
            "submitted": 25,
            "underwriting": 20,
            "conditional_approval": 15,
            "approved": 10,
            "clear_to_close": 7,
            "docs_out": 5,
            "docs_back": 3,
        }

        base_days = stage_to_close.get(status, 45)

        # Adjust based on expected close date if set
        if loan.get("expected_close_date"):
            expected_days = (loan["expected_close_date"] - datetime.now().date()).days
            if expected_days > 0:
                base_days = min(base_days, expected_days)

        expected_date = (datetime.now() + timedelta(days=base_days)).strftime("%Y-%m-%d")

        return base_days, expected_date

    def _check_lock_expiration_risk(
        self,
        loan: Dict[str, Any],
        expected_days: int,
    ) -> bool:
        """Check if lock will expire before expected close."""
        if not loan.get("lock_expiration_date"):
            return False

        days_until_expiry = (loan["lock_expiration_date"] - datetime.now().date()).days
        return days_until_expiry < expected_days

    def _generate_recommendations(
        self,
        loan: Dict[str, Any],
        risk_factors: List[RiskFactor],
        probability: float,
    ) -> List[RecommendedAction]:
        """Generate actionable recommendations."""
        recommendations = []

        # Based on risk factors
        for rf in sorted(risk_factors, key=lambda x: x.impact)[:3]:
            if rf.mitigation:
                recommendations.append(RecommendedAction(
                    action=rf.mitigation,
                    priority="high" if rf.impact < -0.10 else "medium",
                    expected_impact=abs(rf.impact) * 50,  # Estimated improvement
                    effort="medium",
                    deadline_days=3 if rf.impact < -0.15 else 7,
                ))

        # Stage-specific recommendations
        status = loan.get("status", "").lower()
        if status == "processing" and probability < 60:
            recommendations.append(RecommendedAction(
                action="Schedule processor check-in call",
                priority="high",
                expected_impact=10,
                effort="low",
                deadline_days=2,
            ))
        elif status in ["submitted", "underwriting"] and probability < 70:
            recommendations.append(RecommendedAction(
                action="Proactively check underwriter questions",
                priority="medium",
                expected_impact=8,
                effort="low",
                deadline_days=1,
            ))

        return recommendations[:5]  # Top 5 recommendations

    async def _get_similar_loans_close_rate(
        self,
        loan: Dict[str, Any],
    ) -> Optional[float]:
        """Get close rate for similar loans."""
        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'funded' THEN 1 END) as funded
            FROM loans
            WHERE loan_type = :loan_type
                AND loan_amount BETWEEN :min_amt AND :max_amt
                AND created_at >= CURRENT_DATE - 365
                AND status IN ('funded', 'cancelled', 'denied')
        """), {
            "loan_type": loan.get("loan_type"),
            "min_amt": float(loan.get("loan_amount", 0)) * 0.8,
            "max_amt": float(loan.get("loan_amount", 0)) * 1.2,
        })

        row = result.fetchone()
        if not row or row[0] == 0:
            return None

        return round((row[1] / row[0]) * 100, 1)

    async def _get_stage_avg_probability(self, status: str) -> Optional[float]:
        """Get average probability for loans in same stage."""
        result = self.db.execute(text("""
            SELECT AVG(close_probability)
            FROM pipeline_probability_scores ps
            JOIN loans l ON l.id = ps.loan_id
            WHERE l.status = :status
                AND ps.calculated_at >= CURRENT_DATE - 30
        """), {"status": status})

        row = result.fetchone()
        return round(float(row[0]), 1) if row and row[0] else None

    def _calculate_confidence(
        self,
        loan: Dict[str, Any],
        risk_factors: List[RiskFactor],
        strength_factors: List[StrengthFactor],
    ) -> float:
        """Calculate confidence level in the probability score."""
        confidence = 70.0  # Base confidence

        # More data = higher confidence
        if loan.get("borrower_credit_score"):
            confidence += 5
        if loan.get("dti"):
            confidence += 5
        if loan.get("ltv"):
            confidence += 5

        # Advanced stage = higher confidence
        if loan.get("status", "").lower() in ["approved", "clear_to_close", "docs_out", "docs_back"]:
            confidence += 10

        # Many factors identified = higher confidence
        total_factors = len(risk_factors) + len(strength_factors)
        if total_factors >= 5:
            confidence += 5

        return min(95, confidence)

    async def _get_missing_documents_count(self, loan_id: int) -> int:
        """Get count of missing documents."""
        result = self.db.execute(text("""
            SELECT COUNT(*)
            FROM document_requests
            WHERE loan_id = :loan_id AND status = 'pending'
        """), {"loan_id": loan_id})
        row = result.fetchone()
        return row[0] if row else 0

    async def _get_open_conditions_count(self, loan_id: int) -> int:
        """Get count of open conditions."""
        result = self.db.execute(text("""
            SELECT COUNT(*)
            FROM loan_conditions
            WHERE loan_id = :loan_id AND status = 'open'
        """), {"loan_id": loan_id})
        row = result.fetchone()
        return row[0] if row else 0

    def _calculate_overall_trend(self, daily_trends: List[Dict]) -> str:
        """Calculate overall trend direction from daily data."""
        if len(daily_trends) < 2:
            return "stable"

        first_half = daily_trends[:len(daily_trends)//2]
        second_half = daily_trends[len(daily_trends)//2:]

        first_avg = sum(d["avg_probability"] for d in first_half) / len(first_half) if first_half else 0
        second_avg = sum(d["avg_probability"] for d in second_half) / len(second_half) if second_half else 0

        diff = second_avg - first_avg
        if diff > 3:
            return "improving"
        elif diff < -3:
            return "declining"
        else:
            return "stable"

    async def save_score(self, score: ProbabilityScore) -> None:
        """Save probability score to database for historical tracking."""
        self.db.execute(text("""
            INSERT INTO pipeline_probability_scores (
                loan_id, close_probability, confidence_level,
                risk_level, trend, expected_close_days,
                risk_factors, strength_factors, recommended_actions,
                calculated_at, model_version
            ) VALUES (
                :loan_id, :probability, :confidence,
                :risk_level, :trend, :expected_days,
                :risk_factors, :strength_factors, :recommendations,
                CURRENT_TIMESTAMP, :version
            )
        """), {
            "loan_id": score.loan_id,
            "probability": score.close_probability,
            "confidence": score.confidence_level,
            "risk_level": score.risk_level.value,
            "trend": score.trend.value,
            "expected_days": score.expected_close_days,
            "risk_factors": json.dumps([asdict(rf) for rf in score.risk_factors]),
            "strength_factors": json.dumps([asdict(sf) for sf in score.strength_factors]),
            "recommendations": json.dumps([asdict(ra) for ra in score.recommended_actions]),
            "version": score.model_version,
        })
        self.db.commit()
