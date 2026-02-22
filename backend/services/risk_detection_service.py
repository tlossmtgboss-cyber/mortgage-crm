"""
Risk Detection Service
Detect and flag risk conditions for the Master Manager Platform.

Handles:
- Burnout risk scoring (based on workload patterns)
- Attrition risk scoring (based on tenure, performance trends)
- Single point of failure (SPOF) detection
- Key person dependency identification
- Coverage gap analysis
"""

from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum
import logging

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    BURNOUT_RISK = "burnout_risk"
    ATTRITION_RISK = "attrition_risk"
    SPOF_DETECTED = "spof_detected"
    COVERAGE_GAP = "coverage_gap"
    PERFORMANCE_DECLINE = "performance_decline"
    CAPACITY_OVERLOAD = "capacity_overload"
    NEW_HIRE_AT_RISK = "new_hire_at_risk"


@dataclass
class BurnoutRiskAssessment:
    """Burnout risk assessment for a user."""
    user_id: int
    user_name: str
    role_name: Optional[str]
    overall_risk_score: float  # 0-100
    risk_level: str
    factor_scores: Dict[str, float]
    contributing_factors: List[Dict[str, Any]]
    recommendations: List[str]
    trend: Optional[str] = None  # improving, stable, declining
    assessed_at: Optional[datetime] = None


@dataclass
class AttritionRiskAssessment:
    """Attrition risk assessment for a user."""
    user_id: int
    user_name: str
    role_name: Optional[str]
    overall_risk_score: float  # 0-100
    risk_level: str
    factor_scores: Dict[str, float]
    contributing_factors: List[Dict[str, Any]]
    recommendations: List[str]
    estimated_departure_window: Optional[str] = None
    assessed_at: Optional[datetime] = None


@dataclass
class SPOFRisk:
    """Single point of failure risk."""
    user_id: Optional[int]
    user_name: str
    role_name: str
    criticality_score: float
    risk_level: str
    unique_capabilities: List[str]
    coverage_gap: float
    backup_users: List[Dict[str, Any]]
    knowledge_transfer_status: str
    recommended_actions: List[str]


# =============================================================================
# RISK SCORING WEIGHTS
# =============================================================================

BURNOUT_WEIGHTS = {
    "sustained_high_capacity": 0.30,      # >85% capacity for 2+ weeks
    "capacity_trend": 0.20,                # Increasing workload trend
    "error_rate_increase": 0.15,           # Rising error rates
    "overtime_pattern": 0.15,              # Working outside hours
    "task_overdue_rate": 0.10,             # Overdue tasks %
    "no_vacation_time": 0.10,              # No time off recently
}

ATTRITION_WEIGHTS = {
    "tenure_risk": 0.20,                   # New hires at higher risk
    "performance_decline": 0.25,           # Declining performance
    "engagement_drop": 0.20,               # Reduced activity
    "capacity_overload": 0.15,             # Chronic overload
    "promotion_stagnation": 0.10,          # No growth
    "manager_satisfaction": 0.10,          # Manager relationship
}


def _calculate_risk_level(score: float) -> str:
    """Determine risk level from score."""
    if score >= 80:
        return RiskLevel.CRITICAL.value
    elif score >= 60:
        return RiskLevel.HIGH.value
    elif score >= 40:
        return RiskLevel.MEDIUM.value
    return RiskLevel.LOW.value


class RiskDetectionService:
    """
    Service for detecting and managing risk conditions.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # BURNOUT RISK DETECTION
    # =========================================================================

    async def calculate_burnout_risk(
        self,
        user_id: int,
        organization_id: Optional[int] = None
    ) -> BurnoutRiskAssessment:
        """
        Calculate burnout risk for a user based on workload patterns.

        Factors:
        - Sustained high capacity (>85% for 2+ weeks)
        - Increasing workload trend
        - Rising error rates
        - Overtime patterns
        - Overdue task rate
        - No recent vacation/time off
        """
        # Get user info
        user_query = text("""
            SELECT u.id, u.full_name, u.organization_id,
                   rd.role_name
            FROM users u
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = u.id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE u.id = :user_id
        """)
        user = self.db.execute(user_query, {"user_id": user_id}).fetchone()

        if not user:
            raise ValueError(f"User {user_id} not found")

        factors = []
        scores = {}

        # Factor 1: Sustained high capacity
        capacity_data = await self._get_capacity_history(user_id, days=14)
        high_capacity_days = sum(1 for c in capacity_data if c.get("capacity_pct", 0) > 85)
        sustained_high = high_capacity_days >= 10  # 10+ days at >85%

        if sustained_high:
            scores["sustained_high_capacity"] = 100
            factors.append({
                "factor": "Sustained High Capacity",
                "description": f"At >85% capacity for {high_capacity_days}/14 days",
                "severity": "high",
                "score": 100
            })
        elif high_capacity_days >= 7:
            scores["sustained_high_capacity"] = 60
            factors.append({
                "factor": "Elevated Capacity",
                "description": f"At >85% capacity for {high_capacity_days}/14 days",
                "severity": "medium",
                "score": 60
            })
        else:
            scores["sustained_high_capacity"] = max(0, high_capacity_days * 8)

        # Factor 2: Capacity trend (increasing workload)
        trend_score = await self._calculate_capacity_trend(user_id)
        scores["capacity_trend"] = trend_score
        if trend_score > 50:
            factors.append({
                "factor": "Increasing Workload",
                "description": "Workload has been steadily increasing",
                "severity": "medium" if trend_score < 75 else "high",
                "score": trend_score
            })

        # Factor 3: Error rate increase
        error_trend = await self._calculate_error_trend(user_id)
        scores["error_rate_increase"] = error_trend
        if error_trend > 40:
            factors.append({
                "factor": "Rising Error Rate",
                "description": "Error rate has increased recently",
                "severity": "medium" if error_trend < 70 else "high",
                "score": error_trend
            })

        # Factor 4: Overtime patterns
        overtime_score = await self._calculate_overtime_pattern(user_id)
        scores["overtime_pattern"] = overtime_score
        if overtime_score > 50:
            factors.append({
                "factor": "Overtime Pattern",
                "description": "Frequently working outside normal hours",
                "severity": "medium" if overtime_score < 75 else "high",
                "score": overtime_score
            })

        # Factor 5: Overdue task rate
        overdue_rate = await self._calculate_overdue_rate(user_id)
        scores["task_overdue_rate"] = overdue_rate
        if overdue_rate > 30:
            factors.append({
                "factor": "High Overdue Rate",
                "description": f"{overdue_rate:.0f}% of tasks are overdue",
                "severity": "medium" if overdue_rate < 50 else "high",
                "score": overdue_rate
            })

        # Factor 6: No vacation time
        vacation_score = await self._calculate_vacation_factor(user_id)
        scores["no_vacation_time"] = vacation_score
        if vacation_score > 60:
            factors.append({
                "factor": "No Recent Time Off",
                "description": "No vacation or time off in extended period",
                "severity": "low" if vacation_score < 80 else "medium",
                "score": vacation_score
            })

        # Calculate weighted overall score
        overall_score = sum(
            scores.get(factor, 0) * weight
            for factor, weight in BURNOUT_WEIGHTS.items()
        )

        risk_level = _calculate_risk_level(overall_score)

        # Generate recommendations
        recommendations = self._generate_burnout_recommendations(factors, overall_score)

        # Update database with new risk score
        await self._update_burnout_risk_score(user_id, overall_score, organization_id)

        return BurnoutRiskAssessment(
            user_id=user_id,
            user_name=user.full_name or "Unknown",
            role_name=user.role_name,
            overall_risk_score=round(overall_score, 1),
            risk_level=risk_level,
            factor_scores=scores,
            contributing_factors=factors,
            recommendations=recommendations,
            trend=None,  # Could be calculated from historical data
            assessed_at=datetime.now(timezone.utc)
        )

    async def _get_capacity_history(
        self,
        user_id: int,
        days: int = 14
    ) -> List[Dict[str, Any]]:
        """Get capacity history for a user."""
        # Try to get from performance records
        query = text("""
            SELECT
                period_start,
                overall_score as capacity_pct
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type = 'daily'
            AND period_start >= CURRENT_DATE - :days
            ORDER BY period_start DESC
        """)

        try:
            results = self.db.execute(query, {
                "user_id": user_id,
                "days": days
            }).fetchall()

            if results:
                return [{"date": r.period_start, "capacity_pct": r.capacity_pct or 0} for r in results]
        except Exception as e:
            logger.exception(f"Failed to query capacity history for user {user_id}: {e}")

        # Fallback to capacity table
        capacity_query = text("""
            SELECT overall_capacity_pct as capacity_pct
            FROM mm_talent_capacity
            WHERE user_id = :user_id
        """)

        try:
            result = self.db.execute(capacity_query, {"user_id": user_id}).fetchone()
            if result:
                # Return current capacity for all days (no history)
                return [{"capacity_pct": result.capacity_pct or 0}] * days
        except Exception as e:
            logger.exception(f"Failed to query fallback capacity for user {user_id}: {e}")

        return []

    async def _calculate_capacity_trend(self, user_id: int) -> float:
        """Calculate if capacity is trending upward (higher = worse)."""
        query = text("""
            SELECT
                period_start,
                overall_score
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type IN ('daily', 'weekly')
            AND period_start >= CURRENT_DATE - 30
            ORDER BY period_start ASC
        """)

        try:
            results = self.db.execute(query, {"user_id": user_id}).fetchall()

            if len(results) < 3:
                return 0

            # Simple linear trend
            scores = [r.overall_score or 0 for r in results]
            first_half_avg = sum(scores[:len(scores)//2]) / max(len(scores)//2, 1)
            second_half_avg = sum(scores[len(scores)//2:]) / max(len(scores) - len(scores)//2, 1)

            if first_half_avg == 0:
                return 0

            # If second half is higher (worse), that's a negative trend
            trend_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100

            # Cap and convert to 0-100 scale
            return min(100, max(0, trend_pct * 2))
        except Exception as e:
            logger.exception(f"Failed to calculate capacity trend for user {user_id}: {e}")
            return 0

    async def _calculate_error_trend(self, user_id: int) -> float:
        """Calculate if error rate is increasing."""
        query = text("""
            SELECT
                period_start,
                error_rate_pct
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type IN ('weekly', 'monthly')
            AND period_start >= CURRENT_DATE - 60
            ORDER BY period_start ASC
        """)

        try:
            results = self.db.execute(query, {"user_id": user_id}).fetchall()

            if len(results) < 2:
                return 0

            rates = [r.error_rate_pct or 0 for r in results]
            first_avg = sum(rates[:len(rates)//2]) / max(len(rates)//2, 1)
            second_avg = sum(rates[len(rates)//2:]) / max(len(rates) - len(rates)//2, 1)

            if second_avg > first_avg:
                increase = (second_avg - first_avg)
                return min(100, increase * 20)  # 5% increase = 100 score

            return 0
        except Exception as e:
            logger.exception(f"Failed to calculate error trend for user {user_id}: {e}")
            return 0

    async def _calculate_overtime_pattern(self, user_id: int) -> float:
        """Calculate overtime work pattern (tasks completed outside business hours)."""
        # This would ideally check task completion timestamps
        # For now, estimate based on task volume
        query = text("""
            SELECT
                COUNT(*) as total_tasks,
                COUNT(CASE WHEN EXTRACT(HOUR FROM completed_at) < 8
                           OR EXTRACT(HOUR FROM completed_at) > 18
                           THEN 1 END) as after_hours
            FROM tasks
            WHERE owner_id = :user_id
            AND completed_at >= CURRENT_DATE - 30
        """)

        try:
            result = self.db.execute(query, {"user_id": user_id}).fetchone()

            if result and result.total_tasks > 0:
                overtime_pct = (result.after_hours or 0) / result.total_tasks * 100
                return min(100, overtime_pct * 2)  # 50% after hours = 100 score
        except Exception as e:
            logger.exception(f"Failed to calculate overtime pattern for user {user_id}: {e}")

        return 0

    async def _calculate_overdue_rate(self, user_id: int) -> float:
        """Calculate percentage of tasks that are overdue."""
        query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status != 'completed' AND due_date < CURRENT_DATE THEN 1 END) as overdue
            FROM tasks
            WHERE owner_id = :user_id
            AND created_at >= CURRENT_DATE - 30
        """)

        try:
            result = self.db.execute(query, {"user_id": user_id}).fetchone()

            if result and result.total > 0:
                return (result.overdue or 0) / result.total * 100
        except Exception as e:
            logger.exception(f"Failed to calculate overdue rate for user {user_id}: {e}")

        return 0

    async def _calculate_vacation_factor(self, user_id: int) -> float:
        """Calculate risk from lack of vacation/time off."""
        # Check if user has had any availability changes indicating time off
        query = text("""
            SELECT
                availability_status,
                return_date,
                updated_at
            FROM mm_talent_capacity
            WHERE user_id = :user_id
        """)

        try:
            result = self.db.execute(query, {"user_id": user_id}).fetchone()

            if result:
                # If currently on leave, no vacation risk
                if result.availability_status == 'on_leave':
                    return 0

                # Check how long since any recorded time off
                # This is a simplified check - ideally would track PTO history
                if result.updated_at:
                    days_active = (datetime.now(timezone.utc) - result.updated_at.replace(tzinfo=timezone.utc)).days
                    if days_active > 90:
                        return 80  # 90+ days without recorded leave
                    elif days_active > 60:
                        return 50
        except Exception as e:
            logger.exception(f"Failed to calculate vacation factor for user {user_id}: {e}")

        return 30  # Default moderate score

    def _generate_burnout_recommendations(
        self,
        factors: List[Dict[str, Any]],
        overall_score: float
    ) -> List[str]:
        """Generate burnout prevention recommendations."""
        recommendations = []

        if overall_score >= 80:
            recommendations.append("URGENT: Schedule immediate workload review with manager")
            recommendations.append("Consider temporary reassignment of non-critical tasks")

        for factor in factors:
            if factor["factor"] == "Sustained High Capacity" and factor["severity"] == "high":
                recommendations.append("Redistribute workload - reassign 20-30% of files")
                recommendations.append("Pause new assignments until capacity drops below 80%")

            if factor["factor"] == "Increasing Workload":
                recommendations.append("Review capacity limits and adjust if needed")
                recommendations.append("Identify bottlenecks causing workload increase")

            if factor["factor"] == "Rising Error Rate":
                recommendations.append("Schedule quality review session")
                recommendations.append("Consider reducing concurrent file count")

            if factor["factor"] == "Overtime Pattern":
                recommendations.append("Enforce work hours boundaries")
                recommendations.append("Review task prioritization")

            if factor["factor"] == "No Recent Time Off":
                recommendations.append("Encourage scheduled PTO within next 30 days")
                recommendations.append("Block time for recovery")

        if not recommendations:
            recommendations.append("Continue monitoring - no immediate action required")

        return recommendations[:5]  # Limit to top 5

    async def _update_burnout_risk_score(
        self,
        user_id: int,
        score: float,
        organization_id: Optional[int]
    ):
        """Update burnout risk score in capacity table."""
        query = text("""
            UPDATE mm_talent_capacity
            SET
                burnout_risk_score = :score,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        try:
            self.db.execute(query, {
                "user_id": user_id,
                "score": score,
                "org_id": organization_id
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"Failed to update burnout score for user {user_id}: {e}")

    # =========================================================================
    # ATTRITION RISK DETECTION
    # =========================================================================

    async def calculate_attrition_risk(
        self,
        user_id: int,
        organization_id: Optional[int] = None
    ) -> AttritionRiskAssessment:
        """
        Calculate attrition risk for a user.

        Factors:
        - Tenure risk (new hires at higher risk)
        - Performance decline
        - Engagement drop (reduced activity)
        - Capacity overload (chronic high capacity)
        - Promotion stagnation
        """
        # Get user info and tenure
        user_query = text("""
            SELECT
                u.id, u.full_name, u.organization_id, u.created_at,
                ts.hire_date, ts.is_new_hire, ts.last_promotion_at,
                ts.has_active_pip, ts.exit_risk_level,
                rd.role_name
            FROM users u
            LEFT JOIN mm_talent_state ts ON ts.user_id = u.id
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = u.id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE u.id = :user_id
        """)
        user = self.db.execute(user_query, {"user_id": user_id}).fetchone()

        if not user:
            raise ValueError(f"User {user_id} not found")

        factors = []
        scores = {}

        # Factor 1: Tenure risk (new hires at higher risk)
        tenure_score = self._calculate_tenure_risk(user)
        scores["tenure_risk"] = tenure_score
        if tenure_score > 50:
            tenure_days = self._get_tenure_days(user)
            factors.append({
                "factor": "New Hire Risk",
                "description": f"Employee tenure: {tenure_days} days",
                "severity": "high" if tenure_score > 70 else "medium",
                "score": tenure_score
            })

        # Factor 2: Performance decline
        perf_decline = await self._calculate_performance_decline(user_id)
        scores["performance_decline"] = perf_decline
        if perf_decline > 30:
            factors.append({
                "factor": "Performance Decline",
                "description": "Performance has declined over recent periods",
                "severity": "high" if perf_decline > 60 else "medium",
                "score": perf_decline
            })

        # Factor 3: Engagement drop
        engagement = await self._calculate_engagement_drop(user_id)
        scores["engagement_drop"] = engagement
        if engagement > 40:
            factors.append({
                "factor": "Reduced Engagement",
                "description": "Activity levels have decreased",
                "severity": "medium" if engagement < 70 else "high",
                "score": engagement
            })

        # Factor 4: Chronic capacity overload
        overload = await self._calculate_chronic_overload(user_id)
        scores["capacity_overload"] = overload
        if overload > 50:
            factors.append({
                "factor": "Chronic Overload",
                "description": "Sustained high capacity may lead to burnout and departure",
                "severity": "medium" if overload < 75 else "high",
                "score": overload
            })

        # Factor 5: Promotion stagnation
        stagnation = self._calculate_promotion_stagnation(user)
        scores["promotion_stagnation"] = stagnation
        if stagnation > 40:
            factors.append({
                "factor": "Promotion Stagnation",
                "description": "No promotion or advancement in extended period",
                "severity": "low" if stagnation < 60 else "medium",
                "score": stagnation
            })

        # Factor 6: PIP status (if on PIP, higher risk)
        if user.has_active_pip:
            scores["manager_satisfaction"] = 80
            factors.append({
                "factor": "Active Performance Plan",
                "description": "Employee is on a Performance Improvement Plan",
                "severity": "high",
                "score": 80
            })
        else:
            scores["manager_satisfaction"] = 0

        # Calculate weighted overall score
        overall_score = sum(
            scores.get(factor, 0) * weight
            for factor, weight in ATTRITION_WEIGHTS.items()
        )

        risk_level = _calculate_risk_level(overall_score)

        # Generate retention actions
        retention_actions = self._generate_retention_actions(factors, overall_score, user)

        # Estimate departure window based on risk level
        estimated_window = None
        if overall_score >= 80:
            estimated_window = "0-3 months"
        elif overall_score >= 60:
            estimated_window = "3-6 months"
        elif overall_score >= 40:
            estimated_window = "6-12 months"

        # Update database with new risk score
        await self._update_attrition_risk_score(user_id, overall_score, organization_id)

        return AttritionRiskAssessment(
            user_id=user_id,
            user_name=user.full_name or "Unknown",
            role_name=user.role_name,
            overall_risk_score=round(overall_score, 1),
            risk_level=risk_level,
            factor_scores=scores,
            contributing_factors=factors,
            recommendations=retention_actions,
            estimated_departure_window=estimated_window,
            assessed_at=datetime.now(timezone.utc)
        )

    def _calculate_tenure_risk(self, user) -> float:
        """Calculate tenure-based risk (new hires have higher attrition)."""
        tenure_days = self._get_tenure_days(user)

        # Highest risk in first 90 days, decreases over time
        if tenure_days < 30:
            return 90
        elif tenure_days < 60:
            return 75
        elif tenure_days < 90:
            return 60
        elif tenure_days < 180:
            return 40
        elif tenure_days < 365:
            return 20
        return 10  # Low risk for tenured employees

    def _get_tenure_days(self, user) -> int:
        """Get tenure in days."""
        hire_date = user.hire_date or user.created_at
        if hire_date:
            if hasattr(hire_date, 'date'):
                hire_date = hire_date.date()
            return (date.today() - hire_date).days
        return 365  # Default to 1 year if unknown

    async def _calculate_performance_decline(self, user_id: int) -> float:
        """Calculate if performance is declining."""
        query = text("""
            SELECT
                period_start,
                overall_score,
                trend_direction
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type = 'monthly'
            AND period_start >= CURRENT_DATE - 90
            ORDER BY period_start DESC
            LIMIT 3
        """)

        try:
            results = self.db.execute(query, {"user_id": user_id}).fetchall()

            if len(results) < 2:
                return 0

            # Check trend
            declining_count = sum(1 for r in results if r.trend_direction == 'declining')
            if declining_count >= 2:
                return 80

            # Check score progression
            scores = [r.overall_score or 0 for r in results]
            if len(scores) >= 2 and scores[0] < scores[-1] - 10:
                # Recent score 10+ points lower than older
                return 60

            return 0
        except Exception as e:
            logger.exception(f"Failed to calculate performance decline for user {user_id}: {e}")
            return 0

    async def _calculate_engagement_drop(self, user_id: int) -> float:
        """Calculate if engagement/activity has dropped."""
        query = text("""
            SELECT
                period_start,
                tasks_completed,
                leads_handled
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type IN ('weekly', 'monthly')
            AND period_start >= CURRENT_DATE - 60
            ORDER BY period_start ASC
        """)

        try:
            results = self.db.execute(query, {"user_id": user_id}).fetchall()

            if len(results) < 2:
                return 0

            # Compare first half to second half
            mid = len(results) // 2
            first_activity = sum((r.tasks_completed or 0) + (r.leads_handled or 0) for r in results[:mid])
            second_activity = sum((r.tasks_completed or 0) + (r.leads_handled or 0) for r in results[mid:])

            if first_activity > 0 and second_activity < first_activity * 0.7:
                # Activity dropped by 30%+
                drop_pct = (first_activity - second_activity) / first_activity * 100
                return min(100, drop_pct)

            return 0
        except Exception as e:
            logger.exception(f"Failed to calculate engagement drop for user {user_id}: {e}")
            return 0

    async def _calculate_chronic_overload(self, user_id: int) -> float:
        """Calculate chronic overload risk."""
        query = text("""
            SELECT
                overall_capacity_pct,
                burnout_risk_score
            FROM mm_talent_capacity
            WHERE user_id = :user_id
        """)

        try:
            result = self.db.execute(query, {"user_id": user_id}).fetchone()

            if result:
                capacity = result.overall_capacity_pct or 0
                burnout = result.burnout_risk_score or 0

                if capacity > 90 and burnout > 60:
                    return 90
                elif capacity > 85 or burnout > 50:
                    return 60
                elif capacity > 75:
                    return 30

            return 0
        except Exception as e:
            logger.exception(f"Failed to calculate chronic overload for user {user_id}: {e}")
            return 0

    def _calculate_promotion_stagnation(self, user) -> float:
        """Calculate stagnation risk from lack of promotion."""
        if user.last_promotion_at:
            days_since = (date.today() - user.last_promotion_at).days
            if days_since > 730:  # 2+ years
                return 70
            elif days_since > 365:  # 1+ year
                return 40
            return 10
        else:
            # No promotion history - check tenure
            tenure = self._get_tenure_days(user)
            if tenure > 730:
                return 60
            elif tenure > 365:
                return 30
            return 0

    def _generate_retention_actions(
        self,
        factors: List[Dict[str, Any]],
        overall_score: float,
        user
    ) -> List[str]:
        """Generate retention action recommendations."""
        actions = []

        if overall_score >= 80:
            actions.append("URGENT: Schedule retention conversation with manager immediately")
            actions.append("Review compensation against market rates")

        for factor in factors:
            if factor["factor"] == "New Hire Risk" and factor["severity"] == "high":
                actions.append("Assign dedicated onboarding buddy")
                actions.append("Schedule weekly 1:1s for first 90 days")
                actions.append("Ensure clear role expectations and success criteria")

            if factor["factor"] == "Performance Decline":
                actions.append("Identify root causes of performance issues")
                actions.append("Provide targeted coaching and support")
                actions.append("Review workload distribution")

            if factor["factor"] == "Reduced Engagement":
                actions.append("Schedule skip-level meeting")
                actions.append("Explore career development opportunities")
                actions.append("Assess team dynamics and work environment")

            if factor["factor"] == "Chronic Overload":
                actions.append("Immediately reduce workload by 20-30%")
                actions.append("Review capacity limits")

            if factor["factor"] == "Promotion Stagnation":
                actions.append("Discuss career progression path")
                actions.append("Identify skill development opportunities")
                actions.append("Consider lateral moves or stretch assignments")

            if factor["factor"] == "Active Performance Plan":
                actions.append("Ensure PIP goals are realistic and measurable")
                actions.append("Provide additional support resources")

        if not actions:
            actions.append("Continue regular check-ins - no immediate action required")

        return actions[:5]

    async def _update_attrition_risk_score(
        self,
        user_id: int,
        score: float,
        organization_id: Optional[int]
    ):
        """Update attrition risk score in capacity table."""
        query = text("""
            UPDATE mm_talent_capacity
            SET
                attrition_risk_score = :score,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        try:
            self.db.execute(query, {
                "user_id": user_id,
                "score": score,
                "org_id": organization_id
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.warning(f"Failed to update attrition score for user {user_id}: {e}")

    # =========================================================================
    # SINGLE POINT OF FAILURE DETECTION
    # =========================================================================

    async def identify_single_points_of_failure(
        self,
        organization_id: Optional[int] = None
    ) -> List[SPOFRisk]:
        """
        Identify roles/people with no coverage (single points of failure).
        """
        # Find roles with only one person
        query = text("""
            SELECT
                rd.role_name,
                rd.replacement_difficulty,
                rd.is_single_point_failure_risk,
                COUNT(tc.user_id) as user_count,
                MIN(tc.user_id) as user_id,
                MIN(u.full_name) as user_name
            FROM mm_role_definitions rd
            LEFT JOIN mm_talent_capacity tc ON tc.role_definition_id = rd.id
                AND tc.is_available = true
            LEFT JOIN users u ON u.id = tc.user_id
            WHERE rd.is_active = true
            AND (:org_id IS NULL OR rd.organization_id = :org_id OR rd.organization_id IS NULL)
            GROUP BY rd.id, rd.role_name, rd.replacement_difficulty, rd.is_single_point_failure_risk
            HAVING COUNT(tc.user_id) <= 1
            ORDER BY rd.replacement_difficulty DESC
        """)

        results = self.db.execute(query, {"org_id": organization_id}).fetchall()

        spof_risks = []

        for r in results:
            difficulty = r.replacement_difficulty or 5
            criticality_score = difficulty * 10  # 0-100 scale

            if r.user_id is None:
                # Empty role - critical coverage gap
                risk_level = "critical"
                criticality_score = 100
                recommendations = [
                    f"URGENT: No one assigned to {r.role_name} role",
                    "Immediately identify candidates or contractors",
                    "Cross-train existing team members"
                ]
            else:
                # Single person in role
                if difficulty >= 8:
                    risk_level = "critical"
                elif difficulty >= 6:
                    risk_level = "high"
                elif difficulty >= 4:
                    risk_level = "medium"
                else:
                    risk_level = "low"

                recommendations = [
                    f"Identify and train backup for {r.role_name}",
                    "Document critical processes and knowledge",
                    "Consider cross-training adjacent roles"
                ]

            # Get backup info from coverage map
            backup_query = text("""
                SELECT backup_user_ids
                FROM mm_coverage_map
                WHERE primary_user_id = :user_id
                AND role_definition_id = (
                    SELECT id FROM mm_role_definitions WHERE role_name = :role_name LIMIT 1
                )
            """)

            backup_users = []
            try:
                backup_result = self.db.execute(backup_query, {
                    "user_id": r.user_id,
                    "role_name": r.role_name
                }).fetchone()

                if backup_result and backup_result.backup_user_ids:
                    backup_users = [{"user_id": uid} for uid in backup_result.backup_user_ids]
            except Exception as e:
                logger.exception(f"Failed to query backup users for role {r.role_name}: {e}")

            spof_risks.append(SPOFRisk(
                user_id=r.user_id,
                user_name=r.user_name or "Unassigned",
                role_name=r.role_name,
                criticality_score=criticality_score,
                risk_level=risk_level,
                unique_capabilities=[r.role_name],
                coverage_gap=100 if len(backup_users) == 0 else 50,
                backup_users=backup_users,
                knowledge_transfer_status="not_started" if len(backup_users) == 0 else "partial",
                recommended_actions=recommendations
            ))

        return spof_risks

    async def get_coverage_gaps(
        self,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Identify coverage gaps in the organization.
        """
        # Find roles with no coverage mapping
        query = text("""
            SELECT
                rd.role_name,
                rd.role_category,
                tc.user_id,
                u.full_name,
                cm.backup_user_ids,
                cm.cross_trained_users,
                cm.is_single_point_failure,
                cm.coverage_score
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            LEFT JOIN mm_coverage_map cm ON cm.primary_user_id = tc.user_id
                AND cm.role_definition_id = tc.role_definition_id
            WHERE tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY cm.coverage_score ASC NULLS FIRST
        """)

        results = self.db.execute(query, {"org_id": organization_id}).fetchall()

        gaps = []

        for r in results:
            backup_count = len(r.backup_user_ids or [])
            cross_trained = len(r.cross_trained_users or [])

            if backup_count == 0:
                gap_type = "no_backup"
                severity = "high"
                message = f"No backup assigned for {r.full_name} ({r.role_name})"
            elif r.is_single_point_failure:
                gap_type = "spof"
                severity = "critical"
                message = f"{r.full_name} is a single point of failure for {r.role_name}"
            elif (r.coverage_score or 0) < 50:
                gap_type = "low_coverage"
                severity = "medium"
                message = f"Low coverage score ({r.coverage_score}%) for {r.full_name}"
            else:
                continue  # No gap

            gaps.append({
                "gap_type": gap_type,
                "severity": severity,
                "message": message,
                "user_id": r.user_id,
                "user_name": r.full_name,
                "role_name": r.role_name,
                "backup_count": backup_count,
                "cross_trained_count": cross_trained,
                "coverage_score": r.coverage_score
            })

        return gaps

    # =========================================================================
    # KEY PERSON DEPENDENCIES
    # =========================================================================

    async def get_key_person_dependencies(
        self,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Identify critical dependencies on specific individuals.
        """
        # Find high-volume, critical individuals
        query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                rd.role_name,
                tc.current_file_count,
                tc.current_lead_count,
                tc.overall_capacity_pct,
                tp.files_funded,
                tp.overall_score
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            LEFT JOIN mm_talent_performance tp ON tp.user_id = tc.user_id
                AND tp.period_type = 'monthly'
                AND tp.period_start = DATE_TRUNC('month', CURRENT_DATE)
            WHERE tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.current_file_count DESC
            LIMIT 20
        """)

        results = self.db.execute(query, {"org_id": organization_id}).fetchall()

        dependencies = []

        for r in results:
            # Calculate dependency score based on workload concentration
            file_count = r.current_file_count or 0
            lead_count = r.current_lead_count or 0
            files_funded = r.files_funded or 0

            # Higher workload = higher dependency risk
            dependency_score = min(100, (file_count * 3) + (lead_count * 0.5) + (files_funded * 5))

            if dependency_score < 30:
                continue  # Not a key dependency

            if dependency_score >= 80:
                risk_level = "critical"
            elif dependency_score >= 60:
                risk_level = "high"
            elif dependency_score >= 40:
                risk_level = "medium"
            else:
                risk_level = "low"

            dependencies.append({
                "user_id": r.user_id,
                "user_name": r.full_name,
                "role_name": r.role_name,
                "dependency_score": round(dependency_score, 1),
                "risk_level": risk_level,
                "metrics": {
                    "current_files": file_count,
                    "current_leads": lead_count,
                    "files_funded_this_month": files_funded,
                    "capacity_pct": r.overall_capacity_pct
                },
                "recommendations": [
                    "Document key processes and institutional knowledge",
                    "Identify and train potential successors",
                    "Consider workload redistribution"
                ] if dependency_score >= 60 else []
            })

        return sorted(dependencies, key=lambda x: x["dependency_score"], reverse=True)

    # =========================================================================
    # BATCH RISK CALCULATIONS
    # =========================================================================

    async def calculate_all_burnout_risks(
        self,
        organization_id: Optional[int] = None
    ) -> int:
        """Calculate burnout risk for all active users."""
        users_query = text("""
            SELECT DISTINCT tc.user_id
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE u.is_active = true
            AND tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
        """)

        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                await self.calculate_burnout_risk(user_row.user_id, organization_id)
                count += 1
            except SQLAlchemyError as e:
                logger.warning(f"Failed to calculate burnout risk for user {user_row.user_id}: {e}")

        return count

    async def calculate_all_attrition_risks(
        self,
        organization_id: Optional[int] = None
    ) -> int:
        """Calculate attrition risk for all active users."""
        users_query = text("""
            SELECT DISTINCT tc.user_id
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE u.is_active = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
        """)

        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                await self.calculate_attrition_risk(user_row.user_id, organization_id)
                count += 1
            except SQLAlchemyError as e:
                logger.warning(f"Failed to calculate attrition risk for user {user_row.user_id}: {e}")

        return count

    async def get_all_burnout_risks(
        self,
        organization_id: Optional[int] = None,
        min_risk_score: float = 0,
        limit: int = 50
    ) -> List[BurnoutRiskAssessment]:
        """Get burnout risk assessments for all users above threshold."""
        users_query = text("""
            SELECT DISTINCT tc.user_id
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE u.is_active = true
            AND tc.is_available = true
            AND (tc.burnout_risk_score >= :min_score OR tc.burnout_risk_score IS NULL)
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.burnout_risk_score DESC NULLS LAST
            LIMIT :limit
        """)

        users = self.db.execute(users_query, {
            "org_id": organization_id,
            "min_score": min_risk_score,
            "limit": limit
        }).fetchall()

        assessments = []
        for user_row in users:
            try:
                assessment = await self.calculate_burnout_risk(user_row.user_id, organization_id)
                if assessment.overall_risk_score >= min_risk_score:
                    assessments.append(assessment)
            except SQLAlchemyError as e:
                logger.warning(f"Failed to get burnout risk for user {user_row.user_id}: {e}")

        return sorted(assessments, key=lambda x: x.overall_risk_score, reverse=True)

    async def get_all_attrition_risks(
        self,
        organization_id: Optional[int] = None,
        min_risk_score: float = 0,
        limit: int = 50
    ) -> List[AttritionRiskAssessment]:
        """Get attrition risk assessments for all users above threshold."""
        users_query = text("""
            SELECT DISTINCT tc.user_id
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE u.is_active = true
            AND (tc.attrition_risk_score >= :min_score OR tc.attrition_risk_score IS NULL)
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.attrition_risk_score DESC NULLS LAST
            LIMIT :limit
        """)

        users = self.db.execute(users_query, {
            "org_id": organization_id,
            "min_score": min_risk_score,
            "limit": limit
        }).fetchall()

        assessments = []
        for user_row in users:
            try:
                assessment = await self.calculate_attrition_risk(user_row.user_id, organization_id)
                if assessment.overall_risk_score >= min_risk_score:
                    assessments.append(assessment)
            except SQLAlchemyError as e:
                logger.warning(f"Failed to get attrition risk for user {user_row.user_id}: {e}")

        return sorted(assessments, key=lambda x: x.overall_risk_score, reverse=True)

    async def calculate_all_risks(
        self,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate all risk scores for all users."""
        burnout_count = await self.calculate_all_burnout_risks(organization_id)
        attrition_count = await self.calculate_all_attrition_risks(organization_id)

        return {
            "message": f"Calculated risks for all users",
            "burnout_users_calculated": burnout_count,
            "attrition_users_calculated": attrition_count,
            "calculated_at": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # RISK DASHBOARD
    # =========================================================================

    async def get_risk_dashboard(
        self,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get comprehensive risk dashboard."""
        # Get burnout risk summary
        burnout_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN burnout_risk_score >= 80 THEN 1 END) as critical,
                COUNT(CASE WHEN burnout_risk_score >= 60 AND burnout_risk_score < 80 THEN 1 END) as high,
                COUNT(CASE WHEN burnout_risk_score >= 40 AND burnout_risk_score < 60 THEN 1 END) as medium,
                COUNT(CASE WHEN burnout_risk_score < 40 OR burnout_risk_score IS NULL THEN 1 END) as low,
                AVG(burnout_risk_score) as avg_score
            FROM mm_talent_capacity
            WHERE is_available = true
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)
        burnout = self.db.execute(burnout_query, {"org_id": organization_id}).fetchone()

        # Get attrition risk summary
        attrition_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN attrition_risk_score >= 80 THEN 1 END) as critical,
                COUNT(CASE WHEN attrition_risk_score >= 60 AND attrition_risk_score < 80 THEN 1 END) as high,
                COUNT(CASE WHEN attrition_risk_score >= 40 AND attrition_risk_score < 60 THEN 1 END) as medium,
                COUNT(CASE WHEN attrition_risk_score < 40 OR attrition_risk_score IS NULL THEN 1 END) as low,
                AVG(attrition_risk_score) as avg_score
            FROM mm_talent_capacity
            WHERE is_available = true
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)
        attrition = self.db.execute(attrition_query, {"org_id": organization_id}).fetchone()

        # Get SPOFs
        spofs = await self.identify_single_points_of_failure(organization_id)
        critical_spofs = [s for s in spofs if s.risk_level == "critical"]
        high_spofs = [s for s in spofs if s.risk_level == "high"]

        # Get coverage gaps
        gaps = await self.get_coverage_gaps(organization_id)

        # Get key person dependencies
        dependencies = await self.get_key_person_dependencies(organization_id)
        critical_deps = [d for d in dependencies if d["risk_level"] == "critical"]

        return {
            "burnout_risk": {
                "total_users": burnout.total or 0,
                "by_level": {
                    "critical": burnout.critical or 0,
                    "high": burnout.high or 0,
                    "medium": burnout.medium or 0,
                    "low": burnout.low or 0
                },
                "avg_score": round(burnout.avg_score or 0, 1)
            },
            "attrition_risk": {
                "total_users": attrition.total or 0,
                "by_level": {
                    "critical": attrition.critical or 0,
                    "high": attrition.high or 0,
                    "medium": attrition.medium or 0,
                    "low": attrition.low or 0
                },
                "avg_score": round(attrition.avg_score or 0, 1)
            },
            "spof_risks": {
                "total": len(spofs),
                "critical": len(critical_spofs),
                "high": len(high_spofs),
                "roles_at_risk": [s.role_name for s in critical_spofs + high_spofs]
            },
            "coverage_gaps": {
                "total": len(gaps),
                "by_severity": {
                    "critical": len([g for g in gaps if g["severity"] == "critical"]),
                    "high": len([g for g in gaps if g["severity"] == "high"]),
                    "medium": len([g for g in gaps if g["severity"] == "medium"])
                }
            },
            "key_dependencies": {
                "total": len(dependencies),
                "critical": len(critical_deps),
                "top_dependencies": dependencies[:5]
            },
            "overall_health": self._calculate_overall_health(
                burnout, attrition, len(critical_spofs), len(gaps)
            )
        }

    def _calculate_overall_health(
        self,
        burnout,
        attrition,
        critical_spofs: int,
        coverage_gaps: int
    ) -> Dict[str, Any]:
        """Calculate overall organizational health score."""
        # Deduct points for risks
        score = 100

        # Burnout impact
        score -= (burnout.critical or 0) * 10
        score -= (burnout.high or 0) * 5

        # Attrition impact
        score -= (attrition.critical or 0) * 10
        score -= (attrition.high or 0) * 5

        # SPOF impact
        score -= critical_spofs * 15

        # Coverage gap impact
        score -= coverage_gaps * 3

        score = max(0, min(100, score))

        if score >= 80:
            status = "healthy"
            color = "green"
        elif score >= 60:
            status = "moderate_risk"
            color = "yellow"
        elif score >= 40:
            status = "at_risk"
            color = "orange"
        else:
            status = "critical"
            color = "red"

        return {
            "score": round(score, 1),
            "status": status,
            "color": color
        }

    # =========================================================================
    # ALERT GENERATION
    # =========================================================================

    async def generate_risk_alerts(
        self,
        organization_id: Optional[int] = None,
        min_severity: str = "warning"
    ) -> List[Dict[str, Any]]:
        """Generate alerts for detected risks."""
        severity_order = {"info": 0, "warning": 1, "high": 2, "critical": 3}
        min_severity_level = severity_order.get(min_severity, 1)

        alerts = []

        # Get high-risk burnout users
        burnout_query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                tc.burnout_risk_score,
                tc.overall_capacity_pct
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE tc.burnout_risk_score >= 60
            AND tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.burnout_risk_score DESC
        """)

        burnout_users = self.db.execute(burnout_query, {"org_id": organization_id}).fetchall()

        for user in burnout_users:
            severity = "critical" if user.burnout_risk_score >= 80 else "warning"
            alerts.append({
                "alert_type": AlertType.BURNOUT_RISK.value,
                "severity": severity,
                "title": f"Burnout Risk: {user.full_name}",
                "description": f"Burnout risk score is {user.burnout_risk_score:.0f}%",
                "user_id": user.user_id,
                "user_name": user.full_name,
                "metrics": {
                    "burnout_score": user.burnout_risk_score,
                    "capacity_pct": user.overall_capacity_pct
                },
                "recommended_actions": [
                    "Review and reduce workload",
                    "Schedule manager check-in",
                    "Consider temporary reassignment"
                ]
            })

        # Get high-risk attrition users
        attrition_query = text("""
            SELECT
                tc.user_id,
                u.full_name,
                tc.attrition_risk_score
            FROM mm_talent_capacity tc
            JOIN users u ON u.id = tc.user_id
            WHERE tc.attrition_risk_score >= 60
            AND tc.is_available = true
            AND (:org_id IS NULL OR tc.organization_id = :org_id)
            ORDER BY tc.attrition_risk_score DESC
        """)

        attrition_users = self.db.execute(attrition_query, {"org_id": organization_id}).fetchall()

        for user in attrition_users:
            severity = "critical" if user.attrition_risk_score >= 80 else "warning"
            alerts.append({
                "alert_type": AlertType.ATTRITION_RISK.value,
                "severity": severity,
                "title": f"Attrition Risk: {user.full_name}",
                "description": f"Attrition risk score is {user.attrition_risk_score:.0f}%",
                "user_id": user.user_id,
                "user_name": user.full_name,
                "metrics": {
                    "attrition_score": user.attrition_risk_score
                },
                "recommended_actions": [
                    "Schedule retention conversation",
                    "Review compensation and growth opportunities",
                    "Address identified risk factors"
                ]
            })

        # Add SPOF alerts
        spofs = await self.identify_single_points_of_failure(organization_id)
        for spof in spofs:
            if spof.risk_level in ["critical", "high"]:
                alerts.append({
                    "alert_type": AlertType.SPOF_DETECTED.value,
                    "severity": spof.risk_level,
                    "title": f"SPOF: {spof.role_name}",
                    "description": f"{spof.user_name} is the only person in {spof.role_name} role",
                    "user_id": spof.user_id,
                    "user_name": spof.user_name,
                    "metrics": {
                        "role": spof.role_name,
                        "backup_count": len(spof.backup_users)
                    },
                    "recommended_actions": spof.recommended_actions
                })

        # Filter by minimum severity
        filtered_alerts = [
            a for a in alerts
            if severity_order.get(a.get("severity", "info"), 0) >= min_severity_level
        ]

        return filtered_alerts


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_risk_detection_service(db: Session) -> RiskDetectionService:
    """Factory function to get RiskDetectionService instance."""
    return RiskDetectionService(db)
