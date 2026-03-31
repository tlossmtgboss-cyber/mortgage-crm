"""
Predictive AI & Proactive Recommendations Service

Provides intelligent predictions and proactive recommendations:
- Lead conversion probability prediction
- Churn risk detection
- Optimal contact time prediction
- Next best action recommendations
- Deal velocity predictions
- Anomaly detection
- Trend forecasting
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import math
import random  # For demo; production would use ML models

from services.workflow_constants import STAGE_SLA_DAYS as _CANONICAL_SLA_DAYS

logger = logging.getLogger(__name__)


class PredictionType(str, Enum):
    """Types of predictions."""
    CONVERSION = "conversion"
    CHURN = "churn"
    CONTACT_TIME = "contact_time"
    DEAL_VELOCITY = "deal_velocity"
    LOAN_APPROVAL = "loan_approval"
    CLOSING_DATE = "closing_date"
    LIFETIME_VALUE = "lifetime_value"


class RecommendationType(str, Enum):
    """Types of recommendations."""
    NEXT_BEST_ACTION = "next_best_action"
    CROSS_SELL = "cross_sell"
    UP_SELL = "up_sell"
    RETENTION = "retention"
    ENGAGEMENT = "engagement"
    PROCESS_OPTIMIZATION = "process_optimization"


class AlertPriority(str, Enum):
    """Priority levels for alerts."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Prediction:
    """A single prediction result."""
    id: str
    prediction_type: PredictionType
    entity_type: str  # lead, loan, user, etc.
    entity_id: str

    # Prediction result
    predicted_value: Any
    confidence: float  # 0.0 to 1.0
    probability: Optional[float] = None  # For classification

    # Factors
    contributing_factors: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    model_version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    # Explanation
    explanation: str = ""


@dataclass
class Recommendation:
    """A proactive recommendation."""
    id: str
    recommendation_type: RecommendationType
    entity_type: str
    entity_id: str

    # Recommendation
    action: str
    title: str
    description: str
    priority: AlertPriority

    # Expected impact
    expected_impact: str = ""
    impact_score: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0

    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    supporting_data: Dict[str, Any] = field(default_factory=dict)

    # Status
    status: str = "pending"  # pending, accepted, dismissed, completed
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    acted_on_at: Optional[datetime] = None


@dataclass
class ProactiveAlert:
    """A proactive alert for the user."""
    id: str
    alert_type: str
    title: str
    message: str
    priority: AlertPriority

    # Related entities
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None

    # Recommendations
    recommendations: List[Recommendation] = field(default_factory=list)

    # Status
    is_read: bool = False
    is_dismissed: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None


class PredictiveAIService:
    """
    Predictive AI service for proactive recommendations.

    Features:
    - Lead scoring and conversion prediction
    - Churn risk detection and prevention
    - Optimal contact timing
    - Next best action recommendations
    - Deal velocity and closing predictions
    - Anomaly detection for early warning
    - Trend analysis and forecasting
    """

    def __init__(self, db_session=None):
        self.db = db_session

        # Cache for predictions
        self._prediction_cache: Dict[str, Prediction] = {}
        self._recommendation_cache: Dict[str, List[Recommendation]] = {}
        self._alert_cache: Dict[str, List[ProactiveAlert]] = {}

        # Model configurations
        self._model_configs = {
            PredictionType.CONVERSION: {
                "features": ["engagement_score", "lead_score", "days_since_contact",
                           "email_opens", "website_visits", "call_count"],
                "threshold": 0.6
            },
            PredictionType.CHURN: {
                "features": ["days_inactive", "support_tickets", "usage_decline",
                           "payment_issues", "satisfaction_score"],
                "threshold": 0.7
            },
            PredictionType.LOAN_APPROVAL: {
                "features": ["credit_score", "dti_ratio", "ltv_ratio",
                           "employment_stability", "reserves"],
                "threshold": 0.8
            }
        }

        logger.info("PredictiveAIService initialized")

    # =========================================================================
    # Prediction Methods
    # =========================================================================

    def predict_conversion(
        self,
        lead_id: str,
        lead_data: Dict[str, Any]
    ) -> Prediction:
        """Predict lead conversion probability."""
        import uuid
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Feature extraction
        features = self._extract_conversion_features(lead_data)

        # Calculate prediction (simplified model - production would use ML)
        base_score = 0.0

        # Engagement factors
        if features.get("email_opens", 0) > 3:
            base_score += 0.15
        if features.get("website_visits", 0) > 5:
            base_score += 0.12
        if features.get("call_responded", False):
            base_score += 0.20

        # Lead quality factors
        lead_score = features.get("lead_score", 50) / 100
        base_score += lead_score * 0.25

        # Recency factors
        days_since_contact = features.get("days_since_contact", 30)
        if days_since_contact < 3:
            base_score += 0.15
        elif days_since_contact < 7:
            base_score += 0.08

        # Source quality
        high_quality_sources = ["referral", "website_application", "rate_quote"]
        if features.get("source") in high_quality_sources:
            base_score += 0.13

        # Normalize probability
        probability = min(max(base_score, 0.05), 0.95)

        # Contributing factors
        contributing_factors = []
        if features.get("email_opens", 0) > 3:
            contributing_factors.append({
                "factor": "email_engagement",
                "impact": "positive",
                "description": f"Opened {features.get('email_opens')} emails"
            })
        if days_since_contact > 14:
            contributing_factors.append({
                "factor": "contact_recency",
                "impact": "negative",
                "description": f"No contact in {days_since_contact} days"
            })
        if lead_score > 70:
            contributing_factors.append({
                "factor": "lead_score",
                "impact": "positive",
                "description": f"High lead score: {int(lead_score * 100)}"
            })

        prediction = Prediction(
            id=prediction_id,
            prediction_type=PredictionType.CONVERSION,
            entity_type="lead",
            entity_id=lead_id,
            predicted_value="convert" if probability > 0.5 else "no_convert",
            probability=probability,
            confidence=0.75 + (0.2 * len(contributing_factors) / 5),
            contributing_factors=contributing_factors,
            explanation=self._generate_conversion_explanation(probability, contributing_factors)
        )

        self._prediction_cache[prediction_id] = prediction
        return prediction

    def predict_churn_risk(
        self,
        customer_id: str,
        customer_data: Dict[str, Any]
    ) -> Prediction:
        """Predict customer churn risk."""
        import uuid
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Feature extraction
        features = self._extract_churn_features(customer_data)

        # Calculate churn risk
        risk_score = 0.0

        # Inactivity
        days_inactive = features.get("days_inactive", 0)
        if days_inactive > 30:
            risk_score += 0.25
        elif days_inactive > 14:
            risk_score += 0.10

        # Support issues
        open_tickets = features.get("open_tickets", 0)
        if open_tickets > 2:
            risk_score += 0.20
        elif open_tickets > 0:
            risk_score += 0.08

        # Satisfaction
        satisfaction = features.get("satisfaction_score", 5) / 10
        risk_score += (1 - satisfaction) * 0.25

        # Usage decline
        usage_decline = features.get("usage_decline_pct", 0)
        if usage_decline > 50:
            risk_score += 0.20
        elif usage_decline > 25:
            risk_score += 0.10

        # Payment issues
        if features.get("payment_issues", False):
            risk_score += 0.15

        probability = min(max(risk_score, 0.05), 0.95)

        # Contributing factors
        contributing_factors = []
        if days_inactive > 14:
            contributing_factors.append({
                "factor": "inactivity",
                "impact": "negative",
                "weight": 0.25,
                "description": f"Inactive for {days_inactive} days"
            })
        if open_tickets > 0:
            contributing_factors.append({
                "factor": "support_issues",
                "impact": "negative",
                "weight": 0.20,
                "description": f"{open_tickets} open support tickets"
            })
        if usage_decline > 25:
            contributing_factors.append({
                "factor": "usage_decline",
                "impact": "negative",
                "weight": 0.15,
                "description": f"Usage declined {usage_decline}%"
            })

        risk_level = "high" if probability > 0.7 else "medium" if probability > 0.4 else "low"

        prediction = Prediction(
            id=prediction_id,
            prediction_type=PredictionType.CHURN,
            entity_type="customer",
            entity_id=customer_id,
            predicted_value=risk_level,
            probability=probability,
            confidence=0.70 + (0.15 * len(contributing_factors) / 4),
            contributing_factors=contributing_factors,
            explanation=f"Churn risk is {risk_level} ({probability:.0%}). "
                       f"{len(contributing_factors)} risk factors identified."
        )

        self._prediction_cache[prediction_id] = prediction
        return prediction

    def predict_optimal_contact_time(
        self,
        lead_id: str,
        lead_data: Dict[str, Any]
    ) -> Prediction:
        """Predict optimal time to contact a lead."""
        import uuid
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Analyze past engagement patterns
        engagement_history = lead_data.get("engagement_history", [])

        # Default optimal times by day
        optimal_times = {
            0: "10:00",  # Monday
            1: "10:00",
            2: "14:00",
            3: "14:00",
            4: "10:00",
            5: None,     # Saturday
            6: None      # Sunday
        }

        # Analyze engagement patterns if available
        response_hours = []
        response_days = []

        for engagement in engagement_history:
            if engagement.get("response"):
                timestamp = engagement.get("timestamp")
                if timestamp:
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp)
                    response_hours.append(timestamp.hour)
                    response_days.append(timestamp.weekday())

        # Calculate best time based on history
        if response_hours:
            avg_hour = sum(response_hours) / len(response_hours)
            best_hour = round(avg_hour)
            confidence = min(0.5 + (len(response_hours) * 0.1), 0.95)
        else:
            best_hour = 10
            confidence = 0.5

        # Calculate best day
        if response_days:
            from collections import Counter
            day_counts = Counter(response_days)
            best_day = day_counts.most_common(1)[0][0]
        else:
            best_day = 1  # Tuesday default

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        prediction = Prediction(
            id=prediction_id,
            prediction_type=PredictionType.CONTACT_TIME,
            entity_type="lead",
            entity_id=lead_id,
            predicted_value={
                "best_day": day_names[best_day],
                "best_hour": best_hour,
                "best_time": f"{best_hour:02d}:00",
                "timezone": lead_data.get("timezone", "America/New_York")
            },
            confidence=confidence,
            contributing_factors=[
                {
                    "factor": "engagement_history",
                    "data_points": len(response_hours),
                    "description": f"Based on {len(response_hours)} past responses"
                }
            ],
            explanation=f"Best time to contact: {day_names[best_day]} at {best_hour:02d}:00. "
                       f"Based on {len(response_hours)} past engagement patterns."
        )

        self._prediction_cache[prediction_id] = prediction
        return prediction

    def predict_deal_velocity(
        self,
        loan_id: str,
        loan_data: Dict[str, Any]
    ) -> Prediction:
        """Predict deal velocity and closing timeline."""
        import uuid
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Current stage
        stage = loan_data.get("stage", "application")
        days_in_stage = loan_data.get("days_in_stage", 0)

        # Historical averages (would come from database)
        stage_benchmarks = {
            "application": 5,
            "processing": 7,
            "underwriting": 5,
            "approved": 3,
            "clear_to_close": 5,
            "closing": 2
        }

        stage_order = ["application", "processing", "underwriting", "approved", "clear_to_close", "closing"]

        # Calculate remaining days
        remaining_stages = stage_order[stage_order.index(stage):] if stage in stage_order else stage_order
        predicted_days = sum(stage_benchmarks.get(s, 5) for s in remaining_stages)

        # Adjust for current progress
        predicted_days -= min(days_in_stage, stage_benchmarks.get(stage, 5))

        # Risk factors that may delay
        delay_risk = 0.0
        risk_factors = []

        if loan_data.get("missing_documents", 0) > 0:
            delay_risk += 0.2
            risk_factors.append({
                "factor": "missing_documents",
                "impact": "+3-5 days",
                "description": f"{loan_data.get('missing_documents')} documents missing"
            })

        if loan_data.get("conditions_count", 0) > 5:
            delay_risk += 0.15
            risk_factors.append({
                "factor": "many_conditions",
                "impact": "+2-4 days",
                "description": f"{loan_data.get('conditions_count')} conditions to clear"
            })

        if loan_data.get("appraisal_pending", False):
            delay_risk += 0.25
            risk_factors.append({
                "factor": "appraisal_pending",
                "impact": "+5-7 days",
                "description": "Appraisal not yet completed"
            })

        # Adjust prediction for delays
        delay_days = int(predicted_days * delay_risk)
        predicted_days += delay_days

        predicted_close = datetime.utcnow() + timedelta(days=predicted_days)

        velocity = "on_track" if days_in_stage <= stage_benchmarks.get(stage, 5) else "behind"

        prediction = Prediction(
            id=prediction_id,
            prediction_type=PredictionType.DEAL_VELOCITY,
            entity_type="loan",
            entity_id=loan_id,
            predicted_value={
                "predicted_close_date": predicted_close.strftime("%Y-%m-%d"),
                "predicted_days_remaining": predicted_days,
                "velocity": velocity,
                "delay_risk": delay_risk
            },
            confidence=0.70 - (delay_risk * 0.3),
            contributing_factors=risk_factors,
            explanation=f"Predicted close: {predicted_close.strftime('%B %d, %Y')} "
                       f"({predicted_days} days). Status: {velocity}. "
                       f"{len(risk_factors)} risk factors identified."
        )

        self._prediction_cache[prediction_id] = prediction
        return prediction

    def predict_loan_approval(
        self,
        loan_id: str,
        loan_data: Dict[str, Any]
    ) -> Prediction:
        """Predict loan approval probability."""
        import uuid
        prediction_id = f"pred_{uuid.uuid4().hex[:12]}"

        # Extract factors
        credit_score = loan_data.get("credit_score", 700)
        dti_ratio = loan_data.get("dti_ratio", 35)
        ltv_ratio = loan_data.get("ltv_ratio", 80)
        employment_months = loan_data.get("employment_months", 24)
        reserves_months = loan_data.get("reserves_months", 3)

        # Calculate approval probability
        probability = 0.5

        # Credit score impact
        if credit_score >= 760:
            probability += 0.20
        elif credit_score >= 720:
            probability += 0.15
        elif credit_score >= 680:
            probability += 0.08
        elif credit_score >= 620:
            probability += 0.0
        else:
            probability -= 0.20

        # DTI impact
        if dti_ratio <= 36:
            probability += 0.15
        elif dti_ratio <= 43:
            probability += 0.08
        elif dti_ratio <= 50:
            probability += 0.0
        else:
            probability -= 0.15

        # LTV impact
        if ltv_ratio <= 80:
            probability += 0.12
        elif ltv_ratio <= 90:
            probability += 0.05
        elif ltv_ratio <= 95:
            probability += 0.0
        else:
            probability -= 0.10

        # Employment stability
        if employment_months >= 24:
            probability += 0.08
        elif employment_months >= 12:
            probability += 0.03

        # Reserves
        if reserves_months >= 6:
            probability += 0.08
        elif reserves_months >= 3:
            probability += 0.04

        probability = min(max(probability, 0.05), 0.98)

        # Contributing factors
        factors = []
        if credit_score >= 720:
            factors.append({"factor": "credit_score", "impact": "positive",
                          "description": f"Strong credit: {credit_score}"})
        elif credit_score < 640:
            factors.append({"factor": "credit_score", "impact": "negative",
                          "description": f"Low credit: {credit_score}"})

        if dti_ratio > 43:
            factors.append({"factor": "dti_ratio", "impact": "negative",
                          "description": f"High DTI: {dti_ratio}%"})

        if ltv_ratio > 90:
            factors.append({"factor": "ltv_ratio", "impact": "negative",
                          "description": f"High LTV: {ltv_ratio}%"})

        approval_likelihood = "likely" if probability > 0.75 else "possible" if probability > 0.5 else "unlikely"

        prediction = Prediction(
            id=prediction_id,
            prediction_type=PredictionType.LOAN_APPROVAL,
            entity_type="loan",
            entity_id=loan_id,
            predicted_value=approval_likelihood,
            probability=probability,
            confidence=0.80,
            contributing_factors=factors,
            explanation=f"Approval {approval_likelihood} ({probability:.0%}). "
                       f"Key factors: Credit {credit_score}, DTI {dti_ratio}%, LTV {ltv_ratio}%."
        )

        self._prediction_cache[prediction_id] = prediction
        return prediction

    # =========================================================================
    # Recommendation Methods
    # =========================================================================

    def get_next_best_action(
        self,
        entity_type: str,
        entity_id: str,
        entity_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """Get next best action recommendations."""
        import uuid
        recommendations = []

        if entity_type == "lead":
            recommendations = self._get_lead_recommendations(entity_id, entity_data)
        elif entity_type == "loan":
            recommendations = self._get_loan_recommendations(entity_id, entity_data)
        elif entity_type == "customer":
            recommendations = self._get_customer_recommendations(entity_id, entity_data)

        # Sort by impact score
        recommendations.sort(key=lambda r: r.impact_score, reverse=True)

        # Cache recommendations
        cache_key = f"{entity_type}_{entity_id}"
        self._recommendation_cache[cache_key] = recommendations

        return recommendations[:5]  # Top 5 recommendations

    def _get_lead_recommendations(
        self,
        lead_id: str,
        lead_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """Get recommendations for a lead."""
        import uuid
        recommendations = []

        # Check contact recency
        days_since_contact = lead_data.get("days_since_contact", 0)
        if days_since_contact > 3:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.NEXT_BEST_ACTION,
                entity_type="lead",
                entity_id=lead_id,
                action="contact_lead",
                title="Follow up with lead",
                description=f"No contact in {days_since_contact} days. "
                           f"Recommend calling or emailing to maintain engagement.",
                priority=AlertPriority.HIGH if days_since_contact > 7 else AlertPriority.MEDIUM,
                expected_impact="Increase response rate by 40%",
                impact_score=0.8 if days_since_contact > 7 else 0.6,
                confidence=0.85
            ))

        # Check for missing info
        if not lead_data.get("phone"):
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.ENGAGEMENT,
                entity_type="lead",
                entity_id=lead_id,
                action="request_phone",
                title="Get phone number",
                description="Lead is missing phone number. Request via email.",
                priority=AlertPriority.MEDIUM,
                expected_impact="Enable phone outreach",
                impact_score=0.5,
                confidence=0.75
            ))

        # Check lead score for nurturing
        lead_score = lead_data.get("lead_score", 50)
        if lead_score < 40:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.ENGAGEMENT,
                entity_type="lead",
                entity_id=lead_id,
                action="add_to_nurture",
                title="Add to nurture campaign",
                description="Low lead score. Add to educational nurture sequence.",
                priority=AlertPriority.LOW,
                expected_impact="Gradual score improvement",
                impact_score=0.3,
                confidence=0.70
            ))
        elif lead_score > 80:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.NEXT_BEST_ACTION,
                entity_type="lead",
                entity_id=lead_id,
                action="schedule_consultation",
                title="Schedule consultation",
                description="High-score lead ready for consultation.",
                priority=AlertPriority.HIGH,
                expected_impact="High conversion potential",
                impact_score=0.9,
                confidence=0.80
            ))

        return recommendations

    def _get_loan_recommendations(
        self,
        loan_id: str,
        loan_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """Get recommendations for a loan."""
        import uuid
        recommendations = []

        # Check for missing documents
        missing_docs = loan_data.get("missing_documents", [])
        if missing_docs:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.NEXT_BEST_ACTION,
                entity_type="loan",
                entity_id=loan_id,
                action="request_documents",
                title="Request missing documents",
                description=f"Request {len(missing_docs)} missing documents: "
                           f"{', '.join(missing_docs[:3])}{'...' if len(missing_docs) > 3 else ''}",
                priority=AlertPriority.HIGH,
                expected_impact="Unblock loan processing",
                impact_score=0.9,
                confidence=0.95,
                context={"documents": missing_docs}
            ))

        # Check stage duration
        days_in_stage = loan_data.get("days_in_stage", 0)
        stage = loan_data.get("stage", "")
        # Canonical SLA days with lowercase keys for compatibility
        stage_sla = {k.lower(): v for k, v in _CANONICAL_SLA_DAYS.items()}

        if stage in stage_sla and days_in_stage > stage_sla[stage]:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.PROCESS_OPTIMIZATION,
                entity_type="loan",
                entity_id=loan_id,
                action="escalate_delay",
                title=f"Escalate {stage} delay",
                description=f"Loan stuck in {stage} for {days_in_stage} days "
                           f"(SLA: {stage_sla[stage]} days).",
                priority=AlertPriority.HIGH,
                expected_impact="Reduce cycle time",
                impact_score=0.85,
                confidence=0.90
            ))

        # Lock expiration warning
        lock_expires = loan_data.get("lock_expiration_date")
        if lock_expires:
            if isinstance(lock_expires, str):
                lock_expires = datetime.fromisoformat(lock_expires)
            days_until_expiry = (lock_expires - datetime.utcnow()).days

            if days_until_expiry <= 7:
                recommendations.append(Recommendation(
                    id=f"rec_{uuid.uuid4().hex[:8]}",
                    recommendation_type=RecommendationType.NEXT_BEST_ACTION,
                    entity_type="loan",
                    entity_id=loan_id,
                    action="extend_lock",
                    title="Rate lock expiring soon",
                    description=f"Rate lock expires in {days_until_expiry} days. "
                               f"Consider extension or rush to close.",
                    priority=AlertPriority.CRITICAL if days_until_expiry <= 3 else AlertPriority.HIGH,
                    expected_impact="Prevent rate lock expiry",
                    impact_score=0.95,
                    confidence=1.0
                ))

        return recommendations

    def _get_customer_recommendations(
        self,
        customer_id: str,
        customer_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """Get recommendations for a customer."""
        import uuid
        recommendations = []

        # Check for refinance opportunity
        current_rate = customer_data.get("current_rate", 0)
        market_rate = customer_data.get("market_rate", current_rate)

        if current_rate - market_rate >= 0.5:
            monthly_savings = customer_data.get("loan_amount", 300000) * 0.005 / 12

            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.UP_SELL,
                entity_type="customer",
                entity_id=customer_id,
                action="offer_refinance",
                title="Refinance opportunity",
                description=f"Current rate {current_rate}% vs market {market_rate}%. "
                           f"Potential savings: ${monthly_savings:.0f}/month.",
                priority=AlertPriority.HIGH,
                expected_impact=f"Save customer ${monthly_savings * 12:.0f}/year",
                impact_score=0.85,
                confidence=0.80
            ))

        # Check for cross-sell (HELOC)
        equity_pct = customer_data.get("equity_percentage", 0)
        if equity_pct > 30:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.CROSS_SELL,
                entity_type="customer",
                entity_id=customer_id,
                action="offer_heloc",
                title="HELOC opportunity",
                description=f"Customer has {equity_pct}% equity. Ideal HELOC candidate.",
                priority=AlertPriority.MEDIUM,
                expected_impact="Additional revenue opportunity",
                impact_score=0.6,
                confidence=0.70
            ))

        # Retention for at-risk customers
        if customer_data.get("churn_risk", 0) > 0.6:
            recommendations.append(Recommendation(
                id=f"rec_{uuid.uuid4().hex[:8]}",
                recommendation_type=RecommendationType.RETENTION,
                entity_type="customer",
                entity_id=customer_id,
                action="retention_outreach",
                title="Retention outreach needed",
                description="Customer shows churn risk. Proactive outreach recommended.",
                priority=AlertPriority.HIGH,
                expected_impact="Reduce churn probability",
                impact_score=0.9,
                confidence=0.75
            ))

        return recommendations

    # =========================================================================
    # Proactive Alerts
    # =========================================================================

    def generate_proactive_alerts(
        self,
        user_id: int,
        portfolio_data: Dict[str, Any]
    ) -> List[ProactiveAlert]:
        """Generate proactive alerts for a user's portfolio."""
        import uuid
        alerts = []

        # Pipeline alerts
        pipeline = portfolio_data.get("pipeline", [])
        for loan in pipeline:
            # Lock expiration
            lock_expires = loan.get("lock_expiration_date")
            if lock_expires:
                if isinstance(lock_expires, str):
                    lock_expires = datetime.fromisoformat(lock_expires)
                days_until_expiry = (lock_expires - datetime.utcnow()).days

                if days_until_expiry <= 5:
                    alerts.append(ProactiveAlert(
                        id=f"alert_{uuid.uuid4().hex[:8]}",
                        alert_type="lock_expiring",
                        title="Rate Lock Expiring",
                        message=f"Loan {loan.get('loan_number')} rate lock expires in {days_until_expiry} days.",
                        priority=AlertPriority.CRITICAL if days_until_expiry <= 2 else AlertPriority.HIGH,
                        entity_type="loan",
                        entity_id=loan.get("id")
                    ))

            # Stalled deals
            days_in_stage = loan.get("days_in_stage", 0)
            if days_in_stage > 10:
                alerts.append(ProactiveAlert(
                    id=f"alert_{uuid.uuid4().hex[:8]}",
                    alert_type="stalled_deal",
                    title="Stalled Loan",
                    message=f"Loan {loan.get('loan_number')} has been in "
                           f"{loan.get('stage')} for {days_in_stage} days.",
                    priority=AlertPriority.HIGH,
                    entity_type="loan",
                    entity_id=loan.get("id")
                ))

        # Lead alerts
        leads = portfolio_data.get("leads", [])
        hot_leads_no_contact = [
            l for l in leads
            if l.get("lead_score", 0) > 70 and l.get("days_since_contact", 0) > 2
        ]

        if hot_leads_no_contact:
            alerts.append(ProactiveAlert(
                id=f"alert_{uuid.uuid4().hex[:8]}",
                alert_type="hot_leads_neglected",
                title="Hot Leads Need Attention",
                message=f"{len(hot_leads_no_contact)} high-score leads haven't been contacted recently.",
                priority=AlertPriority.HIGH,
                entity_type="leads",
                entity_id=",".join(str(l.get("id")) for l in hot_leads_no_contact[:5])
            ))

        # Anomaly detection
        if portfolio_data.get("conversion_rate_change", 0) < -0.2:
            alerts.append(ProactiveAlert(
                id=f"alert_{uuid.uuid4().hex[:8]}",
                alert_type="performance_anomaly",
                title="Conversion Rate Drop",
                message="Conversion rate dropped 20%+ compared to last period.",
                priority=AlertPriority.MEDIUM
            ))

        # Cache alerts
        self._alert_cache[str(user_id)] = alerts

        return alerts

    def get_alerts(self, user_id: int) -> List[ProactiveAlert]:
        """Get cached alerts for a user."""
        return self._alert_cache.get(str(user_id), [])

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss an alert."""
        for alerts in self._alert_cache.values():
            for alert in alerts:
                if alert.id == alert_id:
                    alert.is_dismissed = True
                    return True
        return False

    def mark_alert_read(self, alert_id: str) -> bool:
        """Mark an alert as read."""
        for alerts in self._alert_cache.values():
            for alert in alerts:
                if alert.id == alert_id:
                    alert.is_read = True
                    alert.read_at = datetime.utcnow()
                    return True
        return False

    # =========================================================================
    # Trend Analysis
    # =========================================================================

    def analyze_trends(
        self,
        entity_type: str,
        data_points: List[Dict[str, Any]],
        metric: str
    ) -> Dict[str, Any]:
        """Analyze trends in historical data."""
        if not data_points:
            return {"trend": "unknown", "data_points": 0}

        # Extract values
        values = [d.get(metric, 0) for d in data_points if metric in d]
        if not values:
            return {"trend": "unknown", "data_points": 0}

        # Calculate basic stats
        avg_value = sum(values) / len(values)
        min_value = min(values)
        max_value = max(values)

        # Determine trend
        if len(values) >= 3:
            first_third = sum(values[:len(values)//3]) / (len(values)//3)
            last_third = sum(values[-len(values)//3:]) / (len(values)//3)

            change_pct = ((last_third - first_third) / first_third * 100) if first_third != 0 else 0

            if change_pct > 10:
                trend = "increasing"
            elif change_pct < -10:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
            change_pct = 0

        return {
            "entity_type": entity_type,
            "metric": metric,
            "trend": trend,
            "change_percent": round(change_pct, 1),
            "average": round(avg_value, 2),
            "min": round(min_value, 2),
            "max": round(max_value, 2),
            "data_points": len(values)
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_conversion_features(self, lead_data: Dict) -> Dict[str, Any]:
        """Extract features for conversion prediction."""
        return {
            "lead_score": lead_data.get("lead_score", 50),
            "email_opens": lead_data.get("email_opens", 0),
            "website_visits": lead_data.get("website_visits", 0),
            "call_responded": lead_data.get("call_responded", False),
            "days_since_contact": lead_data.get("days_since_contact", 0),
            "source": lead_data.get("source", "unknown")
        }

    def _extract_churn_features(self, customer_data: Dict) -> Dict[str, Any]:
        """Extract features for churn prediction."""
        return {
            "days_inactive": customer_data.get("days_inactive", 0),
            "open_tickets": customer_data.get("open_tickets", 0),
            "satisfaction_score": customer_data.get("satisfaction_score", 5),
            "usage_decline_pct": customer_data.get("usage_decline_pct", 0),
            "payment_issues": customer_data.get("payment_issues", False)
        }

    def _generate_conversion_explanation(
        self,
        probability: float,
        factors: List[Dict]
    ) -> str:
        """Generate human-readable conversion explanation."""
        likelihood = "high" if probability > 0.7 else "moderate" if probability > 0.4 else "low"

        positive_factors = [f for f in factors if f.get("impact") == "positive"]
        negative_factors = [f for f in factors if f.get("impact") == "negative"]

        explanation = f"Conversion likelihood is {likelihood} ({probability:.0%}). "

        if positive_factors:
            explanation += f"Positive factors: {', '.join(f['factor'] for f in positive_factors)}. "

        if negative_factors:
            explanation += f"Risk factors: {', '.join(f['factor'] for f in negative_factors)}."

        return explanation

    def get_prediction(self, prediction_id: str) -> Optional[Prediction]:
        """Get a cached prediction."""
        return self._prediction_cache.get(prediction_id)

    def accept_recommendation(self, recommendation_id: str) -> bool:
        """Mark a recommendation as accepted."""
        for recs in self._recommendation_cache.values():
            for rec in recs:
                if rec.id == recommendation_id:
                    rec.status = "accepted"
                    rec.acted_on_at = datetime.utcnow()
                    return True
        return False

    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        """Mark a recommendation as dismissed."""
        for recs in self._recommendation_cache.values():
            for rec in recs:
                if rec.id == recommendation_id:
                    rec.status = "dismissed"
                    return True
        return False
