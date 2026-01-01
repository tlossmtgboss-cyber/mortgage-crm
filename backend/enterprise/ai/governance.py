"""
AI Governance Framework for Mortgage CRM

Implements responsible AI practices for the AI underwriting system:
- Model monitoring and drift detection
- Fairness and bias analysis
- Explainability and transparency
- Human-in-the-loop controls
- Regulatory compliance (ECOA, Fair Lending)

Key Features:
- Real-time model performance monitoring
- Automated bias detection across protected classes
- Decision explanation generation
- Override tracking and auditing
- Model versioning and rollback
"""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """AI model deployment status."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    SUSPENDED = "suspended"


class RiskLevel(str, Enum):
    """AI decision risk level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BiasCategory(str, Enum):
    """Protected classes for fair lending analysis."""
    RACE = "race"
    ETHNICITY = "ethnicity"
    GENDER = "gender"
    AGE = "age"
    MARITAL_STATUS = "marital_status"
    NATIONAL_ORIGIN = "national_origin"
    DISABILITY = "disability"


@dataclass
class ModelVersion:
    """AI model version information."""
    version_id: str
    model_name: str
    version: str
    status: ModelStatus
    created_at: datetime
    deployed_at: Optional[datetime] = None

    # Model metadata
    description: str = ""
    training_data_hash: str = ""
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)

    # Governance
    approved_by: Optional[str] = None
    approval_date: Optional[datetime] = None
    risk_assessment: Optional[str] = None


@dataclass
class AIDecision:
    """Record of an AI-assisted decision."""
    decision_id: str
    model_version_id: str
    loan_id: str
    tenant_id: str

    # Decision details
    recommendation: str  # approve, deny, review
    confidence_score: float
    risk_score: float
    decision_factors: List[Dict[str, Any]]

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Human review
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    final_decision: Optional[str] = None
    override_reason: Optional[str] = None

    # Outcome tracking
    actual_outcome: Optional[str] = None
    outcome_recorded_at: Optional[datetime] = None


@dataclass
class BiasMetric:
    """Fairness metric for a protected class."""
    category: BiasCategory
    group_name: str
    sample_size: int
    approval_rate: float
    baseline_rate: float
    adverse_impact_ratio: float
    statistical_significance: float
    alert_triggered: bool = False


@dataclass
class ModelAlert:
    """Alert for model governance issues."""
    alert_id: str
    model_version_id: str
    alert_type: str  # drift, bias, performance, error
    severity: RiskLevel
    message: str
    details: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None


class ExplainabilityEngine:
    """Generate explanations for AI decisions."""

    # Feature importance labels for consumer-friendly explanations
    FEATURE_EXPLANATIONS = {
        "credit_score": "Credit score assessment",
        "dti_ratio": "Debt-to-income ratio",
        "ltv_ratio": "Loan-to-value ratio",
        "employment_length": "Employment history",
        "income_stability": "Income stability",
        "payment_history": "Payment history",
        "outstanding_debt": "Outstanding debt levels",
        "property_value": "Property valuation",
        "loan_amount": "Requested loan amount",
        "assets": "Available assets",
        "credit_utilization": "Credit utilization",
        "recent_inquiries": "Recent credit inquiries",
    }

    def __init__(self):
        self._feature_weights: Dict[str, float] = {}

    def explain_decision(
        self,
        decision: AIDecision,
        include_technical: bool = False
    ) -> Dict[str, Any]:
        """Generate human-readable explanation for a decision."""
        explanation = {
            "summary": self._generate_summary(decision),
            "key_factors": self._extract_key_factors(decision),
            "recommendation_reasoning": self._explain_recommendation(decision),
        }

        if include_technical:
            explanation["technical_details"] = {
                "model_version": decision.model_version_id,
                "confidence_score": decision.confidence_score,
                "risk_score": decision.risk_score,
                "all_factors": decision.decision_factors,
            }

        return explanation

    def _generate_summary(self, decision: AIDecision) -> str:
        """Generate summary explanation."""
        if decision.recommendation == "approve":
            return (
                f"Based on our analysis, this application demonstrates strong "
                f"creditworthiness with a confidence score of {decision.confidence_score:.0%}."
            )
        elif decision.recommendation == "deny":
            return (
                f"Based on our analysis, this application presents elevated risk "
                f"factors that require additional consideration."
            )
        else:
            return (
                f"This application requires human review due to factors that "
                f"need additional evaluation."
            )

    def _extract_key_factors(
        self,
        decision: AIDecision,
        top_n: int = 4
    ) -> List[Dict[str, Any]]:
        """Extract top contributing factors."""
        sorted_factors = sorted(
            decision.decision_factors,
            key=lambda x: abs(x.get("contribution", 0)),
            reverse=True
        )[:top_n]

        key_factors = []
        for factor in sorted_factors:
            feature = factor.get("feature")
            explanation = self.FEATURE_EXPLANATIONS.get(
                feature,
                feature.replace("_", " ").title()
            )

            key_factors.append({
                "factor": explanation,
                "impact": "positive" if factor.get("contribution", 0) > 0 else "negative",
                "description": self._describe_factor(factor),
            })

        return key_factors

    def _describe_factor(self, factor: Dict[str, Any]) -> str:
        """Generate description for a specific factor."""
        feature = factor.get("feature")
        value = factor.get("value")
        contribution = factor.get("contribution", 0)

        descriptions = {
            "credit_score": lambda v: f"Credit score of {v}" + (
                " exceeds our minimum threshold" if contribution > 0
                else " is below the preferred range"
            ),
            "dti_ratio": lambda v: f"Debt-to-income ratio of {v:.1%}" + (
                " is within acceptable limits" if contribution > 0
                else " exceeds recommended levels"
            ),
            "ltv_ratio": lambda v: f"Loan-to-value ratio of {v:.1%}" + (
                " indicates adequate equity" if contribution > 0
                else " suggests higher loan risk"
            ),
            "employment_length": lambda v: f"Employment tenure of {v} years" + (
                " demonstrates stability" if contribution > 0
                else " is shorter than preferred"
            ),
        }

        if feature in descriptions:
            return descriptions[feature](value)

        return f"{self.FEATURE_EXPLANATIONS.get(feature, feature)}: {value}"

    def _explain_recommendation(self, decision: AIDecision) -> str:
        """Explain the recommendation reasoning."""
        if decision.recommendation == "approve":
            positive_factors = [
                f for f in decision.decision_factors
                if f.get("contribution", 0) > 0
            ]
            return (
                f"The application scored favorably on {len(positive_factors)} "
                f"key underwriting criteria, indicating low default risk."
            )

        elif decision.recommendation == "deny":
            negative_factors = [
                f for f in decision.decision_factors
                if f.get("contribution", 0) < 0
            ]
            return (
                f"The application has {len(negative_factors)} factors that "
                f"do not meet our underwriting standards at this time."
            )

        else:
            return (
                "The application has mixed factors that require manual review "
                "by an underwriter for a final determination."
            )

    def generate_adverse_action_reasons(
        self,
        decision: AIDecision,
        max_reasons: int = 4
    ) -> List[str]:
        """Generate adverse action notice reasons (ECOA compliant)."""
        if decision.recommendation == "approve":
            return []

        # Get top negative factors
        negative_factors = sorted(
            [f for f in decision.decision_factors if f.get("contribution", 0) < 0],
            key=lambda x: x.get("contribution", 0)
        )[:max_reasons]

        # Standard adverse action reasons
        reason_mapping = {
            "credit_score": "Credit score does not meet minimum requirements",
            "dti_ratio": "Debt-to-income ratio exceeds program guidelines",
            "ltv_ratio": "Loan-to-value ratio exceeds program limits",
            "employment_length": "Insufficient length of employment",
            "income_stability": "Insufficient stability of income",
            "payment_history": "Delinquent past or present credit obligations",
            "outstanding_debt": "Excessive obligations in relation to income",
            "assets": "Insufficient cash reserves",
            "credit_utilization": "Proportion of balances to credit limits too high",
            "recent_inquiries": "Too many recent credit inquiries",
        }

        reasons = []
        for factor in negative_factors:
            feature = factor.get("feature")
            reason = reason_mapping.get(feature)
            if reason and reason not in reasons:
                reasons.append(reason)

        return reasons[:max_reasons]


class BiasDetector:
    """Detect and analyze bias in AI decisions."""

    # Adverse impact ratio threshold (4/5ths rule)
    ADVERSE_IMPACT_THRESHOLD = 0.80

    def __init__(self):
        self._decision_history: Dict[str, List[AIDecision]] = defaultdict(list)

    def record_decision(
        self,
        decision: AIDecision,
        demographic_data: Dict[BiasCategory, str]
    ) -> None:
        """Record a decision for bias analysis."""
        for category, value in demographic_data.items():
            key = f"{category.value}:{value}"
            self._decision_history[key].append(decision)

    def analyze_bias(
        self,
        model_version_id: str,
        lookback_days: int = 90
    ) -> Dict[BiasCategory, List[BiasMetric]]:
        """Analyze bias across all protected categories."""
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        results = {}
        for category in BiasCategory:
            metrics = self._analyze_category(model_version_id, category, cutoff)
            results[category] = metrics

        return results

    def _analyze_category(
        self,
        model_version_id: str,
        category: BiasCategory,
        cutoff: datetime
    ) -> List[BiasMetric]:
        """Analyze bias for a specific category."""
        # Collect decisions by group
        groups: Dict[str, List[AIDecision]] = defaultdict(list)

        for key, decisions in self._decision_history.items():
            if key.startswith(f"{category.value}:"):
                group_name = key.split(":", 1)[1]
                filtered = [
                    d for d in decisions
                    if d.model_version_id == model_version_id
                    and d.created_at >= cutoff
                ]
                groups[group_name].extend(filtered)

        if not groups:
            return []

        # Calculate approval rates
        approval_rates = {}
        for group, decisions in groups.items():
            if decisions:
                approvals = sum(1 for d in decisions if d.recommendation == "approve")
                approval_rates[group] = approvals / len(decisions)

        if not approval_rates:
            return []

        # Find baseline (highest approval rate group)
        baseline_rate = max(approval_rates.values())

        # Calculate metrics for each group
        metrics = []
        for group, rate in approval_rates.items():
            sample_size = len(groups[group])

            # Adverse impact ratio
            air = rate / baseline_rate if baseline_rate > 0 else 0

            # Statistical significance (simplified z-test)
            significance = self._calculate_significance(
                rate, baseline_rate, sample_size
            )

            metric = BiasMetric(
                category=category,
                group_name=group,
                sample_size=sample_size,
                approval_rate=rate,
                baseline_rate=baseline_rate,
                adverse_impact_ratio=air,
                statistical_significance=significance,
                alert_triggered=air < self.ADVERSE_IMPACT_THRESHOLD and significance < 0.05,
            )
            metrics.append(metric)

        return metrics

    def _calculate_significance(
        self,
        rate: float,
        baseline: float,
        sample_size: int
    ) -> float:
        """Calculate statistical significance of rate difference."""
        if sample_size < 30:
            return 1.0  # Not enough data

        # Simplified z-test for proportions
        pooled = (rate + baseline) / 2
        if pooled == 0 or pooled == 1:
            return 1.0

        se = np.sqrt(pooled * (1 - pooled) * (2 / sample_size))
        if se == 0:
            return 1.0

        z = abs(rate - baseline) / se

        # Convert to p-value (two-tailed)
        from scipy import stats
        p_value = 2 * (1 - stats.norm.cdf(z))

        return p_value


class ModelMonitor:
    """Monitor model performance and detect issues."""

    def __init__(self):
        self._predictions: List[Dict[str, Any]] = []
        self._baseline_metrics: Dict[str, float] = {}
        self._alerts: List[ModelAlert] = []

    def set_baseline(self, metrics: Dict[str, float]) -> None:
        """Set baseline metrics for drift detection."""
        self._baseline_metrics = metrics.copy()

    def record_prediction(
        self,
        model_version_id: str,
        prediction: Dict[str, Any],
        actual_outcome: Optional[str] = None
    ) -> None:
        """Record a model prediction for monitoring."""
        record = {
            "model_version_id": model_version_id,
            "timestamp": datetime.utcnow(),
            "prediction": prediction,
            "actual_outcome": actual_outcome,
        }
        self._predictions.append(record)

        # Check for real-time alerts
        self._check_realtime_alerts(record)

    def _check_realtime_alerts(self, record: Dict[str, Any]) -> None:
        """Check for immediate alert conditions."""
        prediction = record["prediction"]

        # Check for anomalous confidence
        confidence = prediction.get("confidence_score", 0)
        if confidence < 0.3:
            self._create_alert(
                model_version_id=record["model_version_id"],
                alert_type="low_confidence",
                severity=RiskLevel.MEDIUM,
                message=f"Low confidence prediction: {confidence:.2%}",
                details={"prediction": prediction}
            )

    def calculate_metrics(
        self,
        model_version_id: str,
        lookback_hours: int = 24
    ) -> Dict[str, float]:
        """Calculate current model metrics."""
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

        relevant = [
            p for p in self._predictions
            if p["model_version_id"] == model_version_id
            and p["timestamp"] >= cutoff
            and p.get("actual_outcome") is not None
        ]

        if len(relevant) < 10:
            return {}

        # Calculate metrics
        correct = sum(
            1 for p in relevant
            if p["prediction"].get("recommendation") == p.get("actual_outcome")
        )
        accuracy = correct / len(relevant)

        # Approval rate
        approvals = sum(
            1 for p in relevant
            if p["prediction"].get("recommendation") == "approve"
        )
        approval_rate = approvals / len(relevant)

        # Average confidence
        avg_confidence = statistics.mean(
            p["prediction"].get("confidence_score", 0) for p in relevant
        )

        return {
            "accuracy": accuracy,
            "approval_rate": approval_rate,
            "avg_confidence": avg_confidence,
            "sample_size": len(relevant),
        }

    def detect_drift(
        self,
        model_version_id: str,
        threshold: float = 0.1
    ) -> Dict[str, Any]:
        """Detect model performance drift."""
        current = self.calculate_metrics(model_version_id)

        if not current or not self._baseline_metrics:
            return {"drift_detected": False, "message": "Insufficient data"}

        drift_metrics = {}
        for metric, baseline_value in self._baseline_metrics.items():
            if metric in current:
                current_value = current[metric]
                drift = abs(current_value - baseline_value)
                drift_pct = drift / baseline_value if baseline_value > 0 else 0

                drift_metrics[metric] = {
                    "baseline": baseline_value,
                    "current": current_value,
                    "drift": drift,
                    "drift_pct": drift_pct,
                    "alert": drift_pct > threshold,
                }

        drift_detected = any(m["alert"] for m in drift_metrics.values())

        if drift_detected:
            self._create_alert(
                model_version_id=model_version_id,
                alert_type="drift",
                severity=RiskLevel.HIGH,
                message="Model performance drift detected",
                details={"metrics": drift_metrics}
            )

        return {
            "drift_detected": drift_detected,
            "metrics": drift_metrics,
        }

    def _create_alert(
        self,
        model_version_id: str,
        alert_type: str,
        severity: RiskLevel,
        message: str,
        details: Dict[str, Any]
    ) -> ModelAlert:
        """Create and store an alert."""
        alert = ModelAlert(
            alert_id=str(uuid.uuid4()),
            model_version_id=model_version_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details,
        )
        self._alerts.append(alert)
        logger.warning(f"AI Governance Alert: {alert_type} - {message}")
        return alert

    def get_alerts(
        self,
        model_version_id: str = None,
        unacknowledged_only: bool = True
    ) -> List[ModelAlert]:
        """Get governance alerts."""
        alerts = self._alerts

        if model_version_id:
            alerts = [a for a in alerts if a.model_version_id == model_version_id]

        if unacknowledged_only:
            alerts = [a for a in alerts if a.acknowledged_by is None]

        return sorted(alerts, key=lambda a: a.created_at, reverse=True)


class HumanInTheLoop:
    """Human-in-the-loop controls for AI decisions."""

    def __init__(self):
        self._review_queue: List[AIDecision] = []
        self._review_thresholds = {
            "confidence": 0.7,  # Below this requires review
            "risk_score": 0.6,  # Above this requires review
        }

    def set_thresholds(
        self,
        confidence_threshold: float = None,
        risk_threshold: float = None
    ) -> None:
        """Set review thresholds."""
        if confidence_threshold is not None:
            self._review_thresholds["confidence"] = confidence_threshold
        if risk_threshold is not None:
            self._review_thresholds["risk_score"] = risk_threshold

    def evaluate_for_review(self, decision: AIDecision) -> bool:
        """Determine if decision requires human review."""
        # Low confidence check
        if decision.confidence_score < self._review_thresholds["confidence"]:
            return True

        # High risk check
        if decision.risk_score > self._review_thresholds["risk_score"]:
            return True

        # Denial requires review
        if decision.recommendation == "deny":
            return True

        # Large loan amounts require review
        # This would be configured per-tenant
        return False

    def queue_for_review(self, decision: AIDecision) -> str:
        """Add decision to review queue."""
        self._review_queue.append(decision)
        logger.info(f"Decision {decision.decision_id} queued for human review")
        return decision.decision_id

    def get_review_queue(
        self,
        tenant_id: str = None,
        priority: RiskLevel = None
    ) -> List[AIDecision]:
        """Get decisions pending review."""
        queue = self._review_queue

        if tenant_id:
            queue = [d for d in queue if d.tenant_id == tenant_id]

        # Sort by risk score (highest first)
        return sorted(queue, key=lambda d: d.risk_score, reverse=True)

    def record_review(
        self,
        decision_id: str,
        reviewer_id: str,
        final_decision: str,
        override_reason: str = None
    ) -> AIDecision:
        """Record human review of a decision."""
        for decision in self._review_queue:
            if decision.decision_id == decision_id:
                decision.reviewed_by = reviewer_id
                decision.reviewed_at = datetime.utcnow()
                decision.final_decision = final_decision
                decision.override_reason = override_reason

                # Track override
                if final_decision != decision.recommendation:
                    logger.info(
                        f"AI decision overridden: {decision_id} "
                        f"{decision.recommendation} -> {final_decision}"
                    )

                # Remove from queue
                self._review_queue.remove(decision)
                return decision

        raise ValueError(f"Decision not found in review queue: {decision_id}")


class AIGovernanceFramework:
    """Main governance framework coordinating all components."""

    def __init__(self):
        self.explainability = ExplainabilityEngine()
        self.bias_detector = BiasDetector()
        self.monitor = ModelMonitor()
        self.human_loop = HumanInTheLoop()
        self._model_versions: Dict[str, ModelVersion] = {}
        self._decisions: Dict[str, AIDecision] = {}

    def register_model(
        self,
        model_name: str,
        version: str,
        metrics: Dict[str, float],
        description: str = "",
    ) -> ModelVersion:
        """Register a new model version."""
        version_id = str(uuid.uuid4())

        model = ModelVersion(
            version_id=version_id,
            model_name=model_name,
            version=version,
            status=ModelStatus.DEVELOPMENT,
            created_at=datetime.utcnow(),
            description=description,
            metrics=metrics,
        )

        self._model_versions[version_id] = model
        return model

    def deploy_model(
        self,
        version_id: str,
        approved_by: str,
        risk_assessment: str = None
    ) -> ModelVersion:
        """Deploy a model to production."""
        model = self._model_versions.get(version_id)
        if not model:
            raise ValueError(f"Model version not found: {version_id}")

        model.status = ModelStatus.PRODUCTION
        model.deployed_at = datetime.utcnow()
        model.approved_by = approved_by
        model.approval_date = datetime.utcnow()
        model.risk_assessment = risk_assessment

        # Set baseline for monitoring
        self.monitor.set_baseline(model.metrics)

        logger.info(f"Model deployed: {model.model_name} v{model.version}")
        return model

    def record_decision(
        self,
        model_version_id: str,
        loan_id: str,
        tenant_id: str,
        recommendation: str,
        confidence_score: float,
        risk_score: float,
        decision_factors: List[Dict[str, Any]],
        demographic_data: Dict[BiasCategory, str] = None
    ) -> AIDecision:
        """Record an AI decision with full governance tracking."""
        decision = AIDecision(
            decision_id=str(uuid.uuid4()),
            model_version_id=model_version_id,
            loan_id=loan_id,
            tenant_id=tenant_id,
            recommendation=recommendation,
            confidence_score=confidence_score,
            risk_score=risk_score,
            decision_factors=decision_factors,
        )

        # Store decision
        self._decisions[decision.decision_id] = decision

        # Record for monitoring
        self.monitor.record_prediction(
            model_version_id,
            {
                "recommendation": recommendation,
                "confidence_score": confidence_score,
                "risk_score": risk_score,
            }
        )

        # Record for bias detection
        if demographic_data:
            self.bias_detector.record_decision(decision, demographic_data)

        # Check if human review required
        if self.human_loop.evaluate_for_review(decision):
            self.human_loop.queue_for_review(decision)
            decision.recommendation = "review"

        return decision

    def get_decision_explanation(
        self,
        decision_id: str,
        include_technical: bool = False
    ) -> Dict[str, Any]:
        """Get explanation for a decision."""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise ValueError(f"Decision not found: {decision_id}")

        return self.explainability.explain_decision(decision, include_technical)

    def get_adverse_action_reasons(self, decision_id: str) -> List[str]:
        """Get adverse action reasons for ECOA compliance."""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise ValueError(f"Decision not found: {decision_id}")

        return self.explainability.generate_adverse_action_reasons(decision)

    def run_bias_analysis(
        self,
        model_version_id: str,
        lookback_days: int = 90
    ) -> Dict[str, Any]:
        """Run comprehensive bias analysis."""
        results = self.bias_detector.analyze_bias(model_version_id, lookback_days)

        # Check for alerts
        alerts_triggered = []
        for category, metrics in results.items():
            for metric in metrics:
                if metric.alert_triggered:
                    alerts_triggered.append({
                        "category": category.value,
                        "group": metric.group_name,
                        "adverse_impact_ratio": metric.adverse_impact_ratio,
                    })

        return {
            "analysis_date": datetime.utcnow().isoformat(),
            "lookback_days": lookback_days,
            "results": {
                cat.value: [
                    {
                        "group": m.group_name,
                        "sample_size": m.sample_size,
                        "approval_rate": m.approval_rate,
                        "baseline_rate": m.baseline_rate,
                        "adverse_impact_ratio": m.adverse_impact_ratio,
                        "alert": m.alert_triggered,
                    }
                    for m in metrics
                ]
                for cat, metrics in results.items()
            },
            "alerts": alerts_triggered,
        }

    def generate_governance_report(
        self,
        model_version_id: str,
        include_bias_analysis: bool = True
    ) -> Dict[str, Any]:
        """Generate comprehensive governance report."""
        model = self._model_versions.get(model_version_id)
        if not model:
            raise ValueError(f"Model not found: {model_version_id}")

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "model": {
                "name": model.model_name,
                "version": model.version,
                "status": model.status.value,
                "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
                "approved_by": model.approved_by,
            },
            "performance": self.monitor.calculate_metrics(model_version_id),
            "drift_analysis": self.monitor.detect_drift(model_version_id),
            "alerts": [
                {
                    "type": a.alert_type,
                    "severity": a.severity.value,
                    "message": a.message,
                    "created_at": a.created_at.isoformat(),
                }
                for a in self.monitor.get_alerts(model_version_id)
            ],
        }

        if include_bias_analysis:
            report["bias_analysis"] = self.run_bias_analysis(model_version_id)

        # Review statistics
        decisions = [
            d for d in self._decisions.values()
            if d.model_version_id == model_version_id
        ]
        reviewed = [d for d in decisions if d.reviewed_by]
        overridden = [d for d in reviewed if d.final_decision != d.recommendation]

        report["human_review"] = {
            "total_decisions": len(decisions),
            "reviewed": len(reviewed),
            "overridden": len(overridden),
            "override_rate": len(overridden) / len(reviewed) if reviewed else 0,
        }

        return report
