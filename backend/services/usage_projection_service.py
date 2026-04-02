"""
Usage Projection Service

Provides cost projections and pricing recommendations for the Usage Intelligence system.
Uses weighted moving average with trend analysis to predict 30/60/90 day costs.

Usage:
    from services.usage_projection_service import UsageProjectionService

    service = UsageProjectionService(db_session, organization_id=1)

    # Generate projections
    projections = service.generate_projections(scope_type="organization", period_days=30)

    # Get pricing recommendations
    pricing = service.calculate_pricing_recommendation(target_margin_pct=200)
"""

import os
import uuid
import logging
import statistics
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# PROJECTION ALGORITHMS
# =============================================================================

def weighted_moving_average(
    values: List[float],
    weights: Optional[List[float]] = None
) -> float:
    """
    Calculate weighted moving average.
    More recent values have higher weights by default.
    """
    if not values:
        return 0.0

    if weights is None:
        # Exponential weights - recent data weighted higher
        n = len(values)
        weights = [2 ** (i / n) for i in range(n)]

    total_weight = sum(weights)
    weighted_sum = sum(v * w for v, w in zip(values, weights))

    return weighted_sum / total_weight if total_weight > 0 else 0.0


def calculate_linear_trend(values: List[float]) -> Tuple[float, float]:
    """
    Calculate linear trend using simple linear regression.
    Returns (slope, intercept).
    """
    if len(values) < 2:
        return 0.0, values[0] if values else 0.0

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    slope = numerator / denominator if denominator != 0 else 0.0
    intercept = y_mean - slope * x_mean

    return slope, intercept


def calculate_confidence_interval(
    values: List[float],
    confidence_level: float = 0.95
) -> Tuple[float, float]:
    """
    Calculate confidence interval for projection.
    Returns (lower_bound, upper_bound) as multipliers.
    """
    if len(values) < 2:
        return 0.7, 1.3  # Default wide interval

    std_dev = statistics.stdev(values)
    mean = statistics.mean(values)

    # Z-score for 95% confidence
    z_score = 1.96 if confidence_level == 0.95 else 1.645

    # Calculate margin of error as percentage
    margin = (z_score * std_dev / mean) if mean > 0 else 0.3

    return max(0, 1 - margin), 1 + margin


def project_with_trend(
    historical_values: List[float],
    days_to_project: int,
    lookback_days: int = None
) -> Dict[str, Any]:
    """
    Project future costs using weighted moving average with trend adjustment.

    Args:
        historical_values: List of daily cost values (oldest first)
        days_to_project: Number of days to project forward
        lookback_days: Number of days of history used

    Returns:
        Dict with projection, confidence interval, and trend info
    """
    if not historical_values:
        return {
            "projected_cost": 0,
            "confidence_low": 0,
            "confidence_high": 0,
            "trend_direction": "stable",
            "trend_percentage": 0,
            "confidence_score": 0,
            "daily_projections": []
        }

    lookback_days = lookback_days or len(historical_values)

    # Calculate base daily average using weighted moving average
    base_daily_avg = weighted_moving_average(historical_values)

    # Calculate trend
    slope, intercept = calculate_linear_trend(historical_values)

    # Determine trend direction
    daily_change_pct = (slope / base_daily_avg * 100) if base_daily_avg > 0 else 0
    if daily_change_pct > 1:
        trend_direction = "increasing"
    elif daily_change_pct < -1:
        trend_direction = "decreasing"
    else:
        trend_direction = "stable"

    # Project forward with trend
    daily_projections = []
    start_idx = len(historical_values)

    for i in range(days_to_project):
        day_idx = start_idx + i
        projected_value = intercept + slope * day_idx
        # Don't allow negative projections
        projected_value = max(0, projected_value)
        daily_projections.append(projected_value)

    total_projected = sum(daily_projections)

    # Calculate confidence interval
    ci_low, ci_high = calculate_confidence_interval(historical_values)

    # Calculate confidence score based on data availability
    # More data = higher confidence
    data_coverage = min(lookback_days / (days_to_project * 2), 1.0)
    variance_score = 1 - min(statistics.stdev(historical_values) / base_daily_avg, 1) if base_daily_avg > 0 else 0.5
    confidence_score = (data_coverage * 0.6 + variance_score * 0.4) * 100

    return {
        "projected_cost": total_projected,
        "confidence_low": total_projected * ci_low,
        "confidence_high": total_projected * ci_high,
        "trend_direction": trend_direction,
        "trend_percentage": daily_change_pct * days_to_project,
        "confidence_score": round(confidence_score, 1),
        "daily_projections": daily_projections,
        "avg_daily_cost": base_daily_avg
    }


# =============================================================================
# USAGE PROJECTION SERVICE
# =============================================================================

class UsageProjectionService:
    """
    Service for generating usage projections and pricing recommendations.
    """

    def __init__(self, db: Session, organization_id: int = 1):
        self.db = db
        self.organization_id = organization_id

    def _get_historical_costs(
        self,
        scope_type: str,
        scope_id: Optional[int],
        lookback_days: int
    ) -> Dict[str, List[float]]:
        """
        Get historical daily costs for a given scope.
        Returns dict with 'total' and by-category breakdowns.
        """
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days)

        if scope_type == "user":
            result = self.db.execute(text("""
                SELECT
                    snapshot_date,
                    total_cost,
                    ai_tokens_cost,
                    sms_cost + voice_cost + email_cost as communications_cost,
                    storage_cost,
                    infrastructure_cost
                FROM user_usage_snapshots
                WHERE organization_id = :org_id
                AND user_id = :scope_id
                AND snapshot_date BETWEEN :start_date AND :end_date
                ORDER BY snapshot_date ASC
            """), {
                "org_id": self.organization_id,
                "scope_id": scope_id,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        elif scope_type == "team":
            result = self.db.execute(text("""
                SELECT
                    snapshot_date,
                    total_cost,
                    ai_tokens_cost,
                    communications_cost,
                    storage_cost,
                    infrastructure_cost
                FROM team_usage_snapshots
                WHERE organization_id = :org_id
                AND team_id = :scope_id
                AND snapshot_date BETWEEN :start_date AND :end_date
                ORDER BY snapshot_date ASC
            """), {
                "org_id": self.organization_id,
                "scope_id": scope_id,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        else:  # organization
            result = self.db.execute(text("""
                SELECT
                    snapshot_date,
                    total_cost,
                    ai_tokens_cost,
                    communications_cost,
                    storage_cost,
                    infrastructure_cost
                FROM org_usage_snapshots
                WHERE organization_id = :org_id
                AND snapshot_date BETWEEN :start_date AND :end_date
                ORDER BY snapshot_date ASC
            """), {
                "org_id": self.organization_id,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        # Organize by category
        costs = {
            "total": [],
            "ai_tokens": [],
            "communications": [],
            "storage": [],
            "infrastructure": []
        }

        for row in result:
            costs["total"].append(float(row[1]))
            costs["ai_tokens"].append(float(row[2]))
            costs["communications"].append(float(row[3]))
            costs["storage"].append(float(row[4]))
            costs["infrastructure"].append(float(row[5]))

        return costs

    def generate_projections(
        self,
        scope_type: str = "organization",
        scope_id: Optional[int] = None,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate cost projections for 30/60/90 days.

        Args:
            scope_type: 'user', 'team', or 'organization'
            scope_id: ID of user or team (None for organization)
            period_days: 30, 60, or 90

        Returns:
            Projection results with confidence intervals
        """
        # Get 2x lookback data for better projections
        lookback_days = period_days * 2
        historical = self._get_historical_costs(scope_type, scope_id, lookback_days)

        if not historical["total"]:
            return {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "period_days": period_days,
                "projected_cost": 0,
                "confidence_interval_low": 0,
                "confidence_interval_high": 0,
                "confidence_score": 0,
                "trend_direction": "unknown",
                "trend_percentage": 0,
                "projected_by_category": {},
                "daily_projections": [],
                "alerts": ["Insufficient historical data for projection"]
            }

        # Project total costs
        total_projection = project_with_trend(
            historical["total"],
            period_days,
            lookback_days
        )

        # Project by category
        category_projections = {}
        for category in ["ai_tokens", "communications", "storage", "infrastructure"]:
            cat_proj = project_with_trend(
                historical[category],
                period_days,
                lookback_days
            )
            category_projections[category] = {
                "projected": round(cat_proj["projected_cost"], 2),
                "trend": cat_proj["trend_direction"],
                "pct": round(cat_proj["trend_percentage"], 1)
            }

        # Generate alerts
        alerts = []
        if total_projection["trend_direction"] == "increasing" and total_projection["trend_percentage"] > 20:
            alerts.append(f"Costs projected to increase by {total_projection['trend_percentage']:.1f}%")
        if total_projection["projected_cost"] > 1000:
            alerts.append(f"Projected cost exceeds $1,000 for next {period_days} days")
        if total_projection["confidence_score"] < 50:
            alerts.append("Low confidence projection - limited historical data")

        # Save to database
        self._save_forecast(
            scope_type=scope_type,
            scope_id=scope_id,
            period_days=period_days,
            lookback_days=lookback_days,
            projection=total_projection,
            category_projections=category_projections,
            alerts=alerts
        )

        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "period_days": period_days,
            "lookback_days": lookback_days,
            "projected_cost": round(total_projection["projected_cost"], 2),
            "confidence_interval_low": round(total_projection["confidence_low"], 2),
            "confidence_interval_high": round(total_projection["confidence_high"], 2),
            "confidence_score": total_projection["confidence_score"],
            "trend_direction": total_projection["trend_direction"],
            "trend_percentage": round(total_projection["trend_percentage"], 1),
            "avg_daily_cost": round(total_projection["avg_daily_cost"], 2),
            "projected_by_category": category_projections,
            "daily_projections": [round(d, 2) for d in total_projection["daily_projections"]],
            "alerts": alerts
        }

    def _save_forecast(
        self,
        scope_type: str,
        scope_id: Optional[int],
        period_days: int,
        lookback_days: int,
        projection: Dict,
        category_projections: Dict,
        alerts: List[str]
    ):
        """Save forecast to database."""
        try:
            self.db.execute(text("""
                INSERT INTO usage_forecasts (
                    id, organization_id, scope_type, scope_id,
                    forecast_date, period_days, lookback_days, algorithm,
                    projected_cost, confidence_interval_low, confidence_interval_high,
                    confidence_score, trend_direction, trend_percentage,
                    projected_by_category, daily_projections, alerts
                ) VALUES (
                    :id, :org_id, :scope_type, :scope_id,
                    :forecast_date, :period_days, :lookback_days, :algorithm,
                    :projected_cost, :ci_low, :ci_high,
                    :confidence_score, :trend_direction, :trend_pct,
                    :by_category, :daily, :alerts
                )
            """), {
                "id": str(uuid.uuid4()),
                "org_id": self.organization_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "forecast_date": date.today(),
                "period_days": period_days,
                "lookback_days": lookback_days,
                "algorithm": "weighted_moving_average",
                "projected_cost": str(projection["projected_cost"]),
                "ci_low": str(projection["confidence_low"]),
                "ci_high": str(projection["confidence_high"]),
                "confidence_score": projection["confidence_score"],
                "trend_direction": projection["trend_direction"],
                "trend_pct": projection["trend_percentage"],
                "by_category": category_projections,
                "daily": projection["daily_projections"],
                "alerts": alerts
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to save forecast: {e}")
            self.db.rollback()

    def calculate_pricing_recommendation(
        self,
        target_margin_pct: float = 200,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate pricing recommendations based on actual costs and target margin.

        200% margin means: Price = Cost * 3
        (Price includes 200% profit on top of cost)

        Args:
            target_margin_pct: Target profit margin percentage (default 200)
            period_days: Period to analyze

        Returns:
            Pricing recommendations with breakdown
        """
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=period_days)

        # Get actual costs for period
        costs = self.db.execute(text("""
            SELECT
                COALESCE(SUM(total_cost), 0) as total_cost,
                COALESCE(SUM(ai_tokens_cost), 0) as ai_cost,
                COALESCE(SUM(sms_cost + voice_cost + email_cost), 0) as comm_cost,
                COALESCE(SUM(storage_cost), 0) as storage_cost,
                COALESCE(SUM(infrastructure_cost), 0) as infra_cost
            FROM user_usage_snapshots
            WHERE organization_id = :org_id
            AND snapshot_date BETWEEN :start_date AND :end_date
        """), {
            "org_id": self.organization_id,
            "start_date": start_date,
            "end_date": end_date
        }).fetchone()

        # Get user counts
        users = self.db.execute(text("""
            SELECT
                COUNT(DISTINCT user_id) as total_users,
                COUNT(DISTINCT CASE WHEN total_cost > 0 THEN user_id END) as active_users
            FROM user_usage_snapshots
            WHERE organization_id = :org_id
            AND snapshot_date BETWEEN :start_date AND :end_date
        """), {
            "org_id": self.organization_id,
            "start_date": start_date,
            "end_date": end_date
        }).fetchone()

        total_cost = float(costs[0])
        total_users = users[0] or 1
        active_users = users[1] or 1

        # Calculate per-user metrics
        cost_per_user = total_cost / total_users if total_users > 0 else 0
        cost_per_active_user = total_cost / active_users if active_users > 0 else 0

        # Calculate recommended pricing with target margin
        # 200% margin means Price = Cost * 3
        margin_multiplier = 1 + (target_margin_pct / 100)

        recommended_per_user = cost_per_active_user * margin_multiplier

        # Round to nice numbers
        if recommended_per_user < 50:
            recommended_per_user = round(recommended_per_user / 5) * 5
        elif recommended_per_user < 200:
            recommended_per_user = round(recommended_per_user / 10) * 10
        else:
            recommended_per_user = round(recommended_per_user / 25) * 25

        # Calculate base price (for org-level features)
        base_cost = float(costs[4])  # Infrastructure
        recommended_base = base_cost * margin_multiplier
        recommended_base = round(recommended_base / 50) * 50  # Round to $50

        # Calculate usage fees for overages
        ai_cost_per_token = float(costs[1]) / 1000000 if costs[1] > 0 else 0.00005
        usage_fees = {
            "ai_tokens_per_1k": round(ai_cost_per_token * margin_multiplier * 1000, 4),
            "sms_per_message": round(0.0079 * margin_multiplier, 4),
            "voice_per_minute": round(0.013 * margin_multiplier, 4),
            "email_per_message": round(0.001 * margin_multiplier, 4),
            "storage_per_gb": round(0.023 * margin_multiplier, 2)
        }

        # Calculate recommended allowances (based on average usage)
        avg_ai_per_user = 50000  # tokens
        allowances = {
            "ai_tokens": avg_ai_per_user,
            "sms_messages": 200,
            "voice_minutes": 60,
            "emails": 500,
            "storage_gb": 2
        }

        # Build cost breakdown
        cost_breakdown = {
            "ai_tokens": {
                "total": float(costs[1]),
                "per_user": float(costs[1]) / active_users if active_users > 0 else 0,
                "pct_of_total": (float(costs[1]) / total_cost * 100) if total_cost > 0 else 0
            },
            "communications": {
                "total": float(costs[2]),
                "per_user": float(costs[2]) / active_users if active_users > 0 else 0,
                "pct_of_total": (float(costs[2]) / total_cost * 100) if total_cost > 0 else 0
            },
            "storage": {
                "total": float(costs[3]),
                "per_user": float(costs[3]) / active_users if active_users > 0 else 0,
                "pct_of_total": (float(costs[3]) / total_cost * 100) if total_cost > 0 else 0
            },
            "infrastructure": {
                "total": float(costs[4]),
                "per_user": float(costs[4]) / active_users if active_users > 0 else 0,
                "pct_of_total": (float(costs[4]) / total_cost * 100) if total_cost > 0 else 0
            }
        }

        # Project revenue at recommended prices
        projected_revenue = (recommended_base + recommended_per_user * active_users)
        projected_profit = projected_revenue - total_cost
        actual_margin = ((projected_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

        # Generate recommendations
        recommendations = []
        if actual_margin < target_margin_pct * 0.9:
            recommendations.append("Consider increasing per-user pricing to meet margin target")
        if cost_breakdown["ai_tokens"]["pct_of_total"] > 70:
            recommendations.append("AI token costs dominate - consider usage-based AI pricing tier")
        if active_users < total_users * 0.5:
            recommendations.append("Low active user ratio - focus on engagement before pricing changes")

        result = {
            "period_start": str(start_date),
            "period_end": str(end_date),
            "period_days": period_days,
            "total_actual_cost": round(total_cost, 2),
            "avg_cost_per_user": round(cost_per_user, 2),
            "avg_cost_per_active_user": round(cost_per_active_user, 2),
            "total_users": total_users,
            "active_users": active_users,
            "target_margin_pct": target_margin_pct,
            "margin_multiplier": margin_multiplier,
            "recommended_base_price": recommended_base,
            "recommended_per_user_price": recommended_per_user,
            "recommended_usage_fees": usage_fees,
            "recommended_allowances": allowances,
            "projected_revenue_at_recommended": round(projected_revenue, 2),
            "projected_profit_at_recommended": round(projected_profit, 2),
            "actual_margin_at_recommended": round(actual_margin, 1),
            "cost_breakdown": cost_breakdown,
            "recommendations": recommendations
        }

        # Save recommendation
        self._save_pricing_recommendation(result)

        return result

    def _save_pricing_recommendation(self, result: Dict):
        """Save pricing recommendation to database."""
        try:
            self.db.execute(text("""
                INSERT INTO pricing_recommendations (
                    id, organization_id, calculated_at,
                    period_start, period_end,
                    total_actual_cost, avg_cost_per_user, avg_cost_per_active_user,
                    cost_breakdown, total_users, active_users,
                    target_margin_pct,
                    recommended_base_price, recommended_per_user_price,
                    recommended_usage_fees, recommended_allowances,
                    projected_revenue_at_recommended, projected_profit_at_recommended,
                    recommendations
                ) VALUES (
                    :id, :org_id, :calculated_at,
                    :period_start, :period_end,
                    :total_cost, :cost_per_user, :cost_per_active_user,
                    :cost_breakdown, :total_users, :active_users,
                    :target_margin,
                    :base_price, :per_user_price,
                    :usage_fees, :allowances,
                    :projected_revenue, :projected_profit,
                    :recommendations
                )
            """), {
                "id": str(uuid.uuid4()),
                "org_id": self.organization_id,
                "calculated_at": datetime.now(timezone.utc),
                "period_start": result["period_start"],
                "period_end": result["period_end"],
                "total_cost": str(result["total_actual_cost"]),
                "cost_per_user": str(result["avg_cost_per_user"]),
                "cost_per_active_user": str(result["avg_cost_per_active_user"]),
                "cost_breakdown": result["cost_breakdown"],
                "total_users": result["total_users"],
                "active_users": result["active_users"],
                "target_margin": result["target_margin_pct"],
                "base_price": str(result["recommended_base_price"]),
                "per_user_price": str(result["recommended_per_user_price"]),
                "usage_fees": result["recommended_usage_fees"],
                "allowances": result["recommended_allowances"],
                "projected_revenue": str(result["projected_revenue_at_recommended"]),
                "projected_profit": str(result["projected_profit_at_recommended"]),
                "recommendations": result["recommendations"]
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to save pricing recommendation: {e}")
            self.db.rollback()

    def get_user_cost_ranking(
        self,
        period_days: int = 30,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get users ranked by cost for the period."""
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=period_days)

        result = self.db.execute(text("""
            SELECT
                uus.user_id,
                u.full_name,
                u.email,
                COALESCE(SUM(uus.total_cost), 0) as total_cost,
                COALESCE(SUM(uus.ai_tokens_input + uus.ai_tokens_output), 0) as total_tokens,
                COALESCE(SUM(uus.ai_request_count), 0) as request_count,
                COUNT(DISTINCT uus.snapshot_date) as active_days
            FROM user_usage_snapshots uus
            JOIN users u ON u.id = uus.user_id
            WHERE uus.organization_id = :org_id
            AND uus.snapshot_date BETWEEN :start_date AND :end_date
            GROUP BY uus.user_id, u.full_name, u.email
            ORDER BY total_cost DESC
            LIMIT :limit
        """), {
            "org_id": self.organization_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit
        }).fetchall()

        return [
            {
                "rank": i + 1,
                "user_id": row[0],
                "name": row[1],
                "email": row[2],
                "total_cost": round(float(row[3]), 2),
                "total_tokens": int(row[4]),
                "request_count": int(row[5]),
                "active_days": int(row[6]),
                "avg_daily_cost": round(float(row[3]) / max(int(row[6]), 1), 2)
            }
            for i, row in enumerate(result)
        ]

    def get_cost_trend(
        self,
        scope_type: str = "organization",
        scope_id: Optional[int] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get daily cost trend for charting."""
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days)

        if scope_type == "user":
            table = "user_usage_snapshots"
            filter_col = "user_id"
        elif scope_type == "team":
            table = "team_usage_snapshots"
            filter_col = "team_id"
        else:
            table = "org_usage_snapshots"
            filter_col = None

        if filter_col:
            comm_expr = (
                "sms_cost + voice_cost + email_cost"
                if scope_type == "user" else "communications_cost"
            )
            scoped_query = (
                "SELECT snapshot_date, total_cost, ai_tokens_cost,"
                " " + comm_expr + " as communications_cost,"
                " storage_cost"
                " FROM " + table
                + " WHERE organization_id = :org_id"
                " AND " + filter_col + " = :scope_id"
                " AND snapshot_date BETWEEN :start_date AND :end_date"
                " ORDER BY snapshot_date ASC"
            )
            result = self.db.execute(text(scoped_query), {
                "org_id": self.organization_id,
                "scope_id": scope_id,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()
        else:
            org_query = (
                "SELECT snapshot_date, total_cost, ai_tokens_cost,"
                " communications_cost, storage_cost"
                " FROM " + table
                + " WHERE organization_id = :org_id"
                " AND snapshot_date BETWEEN :start_date AND :end_date"
                " ORDER BY snapshot_date ASC"
            )
            result = self.db.execute(text(org_query), {
                "org_id": self.organization_id,
                "start_date": start_date,
                "end_date": end_date
            }).fetchall()

        return [
            {
                "date": str(row[0]),
                "total_cost": round(float(row[1]), 2),
                "ai_tokens_cost": round(float(row[2]), 2),
                "communications_cost": round(float(row[3]), 2),
                "storage_cost": round(float(row[4]), 2)
            }
            for row in result
        ]
