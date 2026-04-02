"""
Production Predictor Service

AI-powered production forecasting and prediction for loan officers, teams, and branches.
Part of the Advanced Analytics module.

Features:
- Historical trend analysis
- Production forecasting (30/60/90 day)
- Goal attainment prediction
- Seasonal adjustment
- Conversion rate analysis
- Risk identification for underperformance
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal
import statistics
import math
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class PredictionConfidence(str, Enum):
    """Confidence levels for predictions."""
    HIGH = "high"        # >80% confidence
    MEDIUM = "medium"    # 60-80% confidence
    LOW = "low"          # <60% confidence


class TrendDirection(str, Enum):
    """Trend direction indicators."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class RiskLevel(str, Enum):
    """Risk level for goal attainment."""
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BEHIND = "behind"
    AHEAD = "ahead"


@dataclass
class ProductionDataPoint:
    """A single production data point."""
    date: date
    units: int
    volume: float
    applications: int = 0
    pull_through_rate: float = 0.0


@dataclass
class ProductionForecast:
    """Production forecast for a future period."""
    period_end: date
    predicted_units: int
    predicted_volume: float
    confidence: PredictionConfidence
    confidence_score: float  # 0-100
    lower_bound_units: int
    upper_bound_units: int
    lower_bound_volume: float
    upper_bound_volume: float
    factors: List[str] = field(default_factory=list)


@dataclass
class GoalAttainment:
    """Goal attainment analysis."""
    goal_units: int
    goal_volume: float
    current_units: int
    current_volume: float
    predicted_final_units: int
    predicted_final_volume: float
    units_progress_pct: float
    volume_progress_pct: float
    units_on_track_pct: float  # % chance to hit goal
    volume_on_track_pct: float
    risk_level: RiskLevel
    days_remaining: int
    units_per_day_needed: float
    volume_per_day_needed: float
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TrendAnalysis:
    """Trend analysis results."""
    direction: TrendDirection
    change_pct: float  # Period-over-period change
    avg_monthly_units: float
    avg_monthly_volume: float
    peak_month: str
    trough_month: str
    volatility_score: float  # 0-100, higher = more volatile
    seasonality_factor: Dict[str, float] = field(default_factory=dict)


class ProductionPredictorService:
    """
    AI-powered production prediction service.

    Uses statistical analysis and pattern recognition to forecast
    loan officer, team, and branch production.
    """

    # Seasonal adjustment factors (based on mortgage industry patterns)
    SEASONAL_FACTORS = {
        1: 0.85,   # January - slower
        2: 0.90,   # February - picking up
        3: 1.05,   # March - spring buying
        4: 1.10,   # April - peak spring
        5: 1.15,   # May - peak
        6: 1.10,   # June - still strong
        7: 1.00,   # July - moderating
        8: 0.95,   # August - back to school
        9: 0.90,   # September - fall slowdown
        10: 0.95,  # October - moderate
        11: 0.85,  # November - holiday season
        12: 0.75,  # December - slowest
    }

    # Conversion rate benchmarks
    CONVERSION_BENCHMARKS = {
        "lead_to_app": 0.25,
        "app_to_submit": 0.75,
        "submit_to_approve": 0.85,
        "approve_to_fund": 0.90,
        "overall": 0.20,
    }

    def __init__(self, db_session=None):
        self.db = db_session

    def get_production_history(
        self,
        entity_id: str,
        entity_type: str = "lo",  # lo, team, branch, company
        months: int = 12,
    ) -> List[ProductionDataPoint]:
        """
        Get historical production data.

        Queries real loan data from database if available,
        otherwise returns sample data for demonstration.
        """
        today = date.today()
        history = []

        # Try to get real data from database
        if self.db:
            try:
                from sqlalchemy import text

                # Build entity filter based on type
                if entity_type == "lo":
                    entity_filter = "AND l.loan_officer_id = :entity_id"
                elif entity_type == "team":
                    entity_filter = "AND u.team_id = :entity_id"
                elif entity_type == "branch":
                    entity_filter = "AND l.branch_id = :entity_id"
                else:
                    entity_filter = ""  # Company-wide

                # Query monthly aggregations - use correct column names (amount, stage, funded_date)
                sql = """
                    SELECT
                        DATE_TRUNC('month', l.funded_date) as month,
                        COUNT(*) as units,
                        COALESCE(SUM(l.amount), 0) as volume
                    FROM loans l
                    LEFT JOIN users u ON l.loan_officer_id = u.id
                    WHERE l.funded_date >= CURRENT_DATE - INTERVAL ':months months'
                        AND UPPER(l.stage::text) = 'FUNDED'
                """
                if entity_filter:
                    sql += "                        " + entity_filter + "\n"
                sql += """                    GROUP BY DATE_TRUNC('month', l.funded_date)
                    ORDER BY month ASC
                """
                sql = sql.replace(':months', str(months))
                result = self.db.execute(text(sql), {"entity_id": entity_id})

                rows = result.fetchall()

                if rows:
                    for row in rows:
                        month_date = row[0].date() if hasattr(row[0], 'date') else row[0]
                        units = int(row[1] or 0)
                        volume = float(row[2] or 0)
                        # Use units as proxy for applications since we don't track application_date
                        applications = units

                        history.append(ProductionDataPoint(
                            date=month_date,
                            units=units,
                            volume=volume,
                            applications=applications,
                            pull_through_rate=units / applications if applications > 0 else 0,
                        ))

                    logger.info(f"Retrieved {len(history)} months of production data for {entity_type} {entity_id}")
                    return history

            except Exception as e:
                logger.warning(f"Could not fetch production history from database: {e}")

        # No sample/demo data - return empty list when no real CRM data exists
        # The frontend will show an appropriate "no data" state
        logger.info(f"No production data found for {entity_type} {entity_id}")
        return history

    def analyze_trend(
        self,
        history: List[ProductionDataPoint],
    ) -> TrendAnalysis:
        """Analyze production trends from historical data."""
        if len(history) < 3:
            return TrendAnalysis(
                direction=TrendDirection.STABLE,
                change_pct=0,
                avg_monthly_units=0,
                avg_monthly_volume=0,
                peak_month="N/A",
                trough_month="N/A",
                volatility_score=0,
            )

        # Calculate averages
        units = [dp.units for dp in history]
        volumes = [dp.volume for dp in history]

        avg_units = statistics.mean(units)
        avg_volume = statistics.mean(volumes)

        # Calculate trend direction (compare recent 3 months to prior 3)
        recent_avg = statistics.mean(units[-3:]) if len(units) >= 3 else units[-1]
        prior_avg = statistics.mean(units[-6:-3]) if len(units) >= 6 else avg_units

        if prior_avg > 0:
            change_pct = ((recent_avg - prior_avg) / prior_avg) * 100
        else:
            change_pct = 0

        if change_pct > 10:
            direction = TrendDirection.UP
        elif change_pct < -10:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.STABLE

        # Find peak and trough
        max_idx = units.index(max(units))
        min_idx = units.index(min(units))
        peak_month = history[max_idx].date.strftime("%B %Y")
        trough_month = history[min_idx].date.strftime("%B %Y")

        # Calculate volatility (coefficient of variation)
        if avg_units > 0:
            std_dev = statistics.stdev(units) if len(units) > 1 else 0
            volatility = (std_dev / avg_units) * 100
        else:
            volatility = 0

        # Calculate seasonality factors from data
        seasonality = {}
        for dp in history:
            month_name = dp.date.strftime("%B")
            if month_name not in seasonality:
                seasonality[month_name] = []
            seasonality[month_name].append(dp.units / avg_units if avg_units > 0 else 1)

        seasonality_factors = {
            month: statistics.mean(factors)
            for month, factors in seasonality.items()
        }

        return TrendAnalysis(
            direction=direction,
            change_pct=round(change_pct, 1),
            avg_monthly_units=round(avg_units, 1),
            avg_monthly_volume=round(avg_volume, 0),
            peak_month=peak_month,
            trough_month=trough_month,
            volatility_score=min(100, round(volatility, 1)),
            seasonality_factor=seasonality_factors,
        )

    def forecast_production(
        self,
        history: List[ProductionDataPoint],
        forecast_days: int = 30,
        current_pipeline: Optional[Dict] = None,
    ) -> ProductionForecast:
        """
        Forecast future production based on historical patterns.

        Uses:
        - Historical averages
        - Seasonal adjustment
        - Current pipeline (if provided)
        - Trend momentum
        """
        if len(history) < 3:
            # Insufficient data
            return ProductionForecast(
                period_end=date.today() + timedelta(days=forecast_days),
                predicted_units=0,
                predicted_volume=0,
                confidence=PredictionConfidence.LOW,
                confidence_score=30,
                lower_bound_units=0,
                upper_bound_units=0,
                lower_bound_volume=0,
                upper_bound_volume=0,
                factors=["Insufficient historical data for accurate prediction"],
            )

        factors = []

        # Base prediction from recent performance
        recent_months = min(3, len(history))
        recent_units = [dp.units for dp in history[-recent_months:]]
        recent_volumes = [dp.volume for dp in history[-recent_months:]]

        base_monthly_units = statistics.mean(recent_units)
        base_monthly_volume = statistics.mean(recent_volumes)

        # Adjust for forecast period
        months_in_period = forecast_days / 30
        base_units = base_monthly_units * months_in_period
        base_volume = base_monthly_volume * months_in_period

        # Apply seasonal adjustment
        target_month = (date.today() + timedelta(days=forecast_days // 2)).month
        seasonal_factor = self.SEASONAL_FACTORS.get(target_month, 1.0)

        adjusted_units = base_units * seasonal_factor
        adjusted_volume = base_volume * seasonal_factor

        if seasonal_factor != 1.0:
            direction = "increase" if seasonal_factor > 1 else "decrease"
            factors.append(f"Seasonal {direction} expected ({(seasonal_factor-1)*100:+.0f}%)")

        # Apply trend momentum
        trend = self.analyze_trend(history)
        if trend.direction == TrendDirection.UP:
            trend_factor = 1.05
            factors.append("Positive trend momentum")
        elif trend.direction == TrendDirection.DOWN:
            trend_factor = 0.95
            factors.append("Negative trend momentum")
        else:
            trend_factor = 1.0

        adjusted_units *= trend_factor
        adjusted_volume *= trend_factor

        # Incorporate current pipeline if available
        if current_pipeline:
            pipeline_units = current_pipeline.get("closing_soon", 0)
            pipeline_volume = current_pipeline.get("closing_volume", 0)

            # Pipeline contribution (weighted by expected close rate)
            close_rate = 0.85  # Expected close rate for near-term pipeline
            pipeline_contribution_units = pipeline_units * close_rate
            pipeline_contribution_volume = pipeline_volume * close_rate

            # Blend pipeline with forecast
            adjusted_units = (adjusted_units * 0.4) + (pipeline_contribution_units * 0.6)
            adjusted_volume = (adjusted_volume * 0.4) + (pipeline_contribution_volume * 0.6)
            factors.append(f"Pipeline: {pipeline_units} loans closing soon")

        # Calculate confidence
        confidence_score = self._calculate_confidence(history, current_pipeline)

        if confidence_score >= 80:
            confidence = PredictionConfidence.HIGH
        elif confidence_score >= 60:
            confidence = PredictionConfidence.MEDIUM
        else:
            confidence = PredictionConfidence.LOW

        # Calculate bounds based on volatility
        volatility_factor = max(0.1, min(0.5, trend.volatility_score / 100))

        lower_units = adjusted_units * (1 - volatility_factor)
        upper_units = adjusted_units * (1 + volatility_factor)
        lower_volume = adjusted_volume * (1 - volatility_factor)
        upper_volume = adjusted_volume * (1 + volatility_factor)

        return ProductionForecast(
            period_end=date.today() + timedelta(days=forecast_days),
            predicted_units=round(adjusted_units),
            predicted_volume=round(adjusted_volume),
            confidence=confidence,
            confidence_score=confidence_score,
            lower_bound_units=round(lower_units),
            upper_bound_units=round(upper_units),
            lower_bound_volume=round(lower_volume),
            upper_bound_volume=round(upper_volume),
            factors=factors,
        )

    def _calculate_confidence(
        self,
        history: List[ProductionDataPoint],
        current_pipeline: Optional[Dict],
    ) -> float:
        """Calculate prediction confidence score."""
        score = 50  # Base score

        # More history = higher confidence
        if len(history) >= 12:
            score += 20
        elif len(history) >= 6:
            score += 10

        # Lower volatility = higher confidence
        if history:
            units = [dp.units for dp in history]
            if len(units) > 1:
                avg = statistics.mean(units)
                if avg > 0:
                    cv = statistics.stdev(units) / avg
                    if cv < 0.2:
                        score += 15
                    elif cv < 0.4:
                        score += 10

        # Pipeline data = higher confidence
        if current_pipeline:
            score += 15

        return min(100, score)

    def predict_goal_attainment(
        self,
        entity_id: str,
        goal_units: int,
        goal_volume: float,
        goal_period_start: date,
        goal_period_end: date,
    ) -> GoalAttainment:
        """
        Predict likelihood of achieving production goals.
        """
        today = date.today()

        # Get historical data
        history = self.get_production_history(entity_id, months=6)

        # Calculate current progress (simulate for demo)
        days_elapsed = (today - goal_period_start).days
        total_days = (goal_period_end - goal_period_start).days
        days_remaining = (goal_period_end - today).days

        progress_pct = days_elapsed / total_days if total_days > 0 else 0

        # Simulate current production (in production, query actual data)
        current_units = int(goal_units * progress_pct * 0.95)  # Slightly behind pace
        current_volume = goal_volume * progress_pct * 0.95

        units_progress_pct = (current_units / goal_units * 100) if goal_units > 0 else 0
        volume_progress_pct = (current_volume / goal_volume * 100) if goal_volume > 0 else 0

        # Forecast remaining production
        forecast = self.forecast_production(history, forecast_days=days_remaining)

        predicted_final_units = current_units + forecast.predicted_units
        predicted_final_volume = current_volume + forecast.predicted_volume

        # Calculate on-track probability
        units_on_track = min(100, (predicted_final_units / goal_units * 100)) if goal_units > 0 else 0
        volume_on_track = min(100, (predicted_final_volume / goal_volume * 100)) if goal_volume > 0 else 0

        # Determine risk level
        avg_on_track = (units_on_track + volume_on_track) / 2
        if avg_on_track >= 110:
            risk_level = RiskLevel.AHEAD
        elif avg_on_track >= 90:
            risk_level = RiskLevel.ON_TRACK
        elif avg_on_track >= 70:
            risk_level = RiskLevel.AT_RISK
        else:
            risk_level = RiskLevel.BEHIND

        # Calculate required pace
        units_needed = goal_units - current_units
        volume_needed = goal_volume - current_volume

        units_per_day = units_needed / days_remaining if days_remaining > 0 else 0
        volume_per_day = volume_needed / days_remaining if days_remaining > 0 else 0

        # Generate recommendations
        recommendations = []

        if risk_level == RiskLevel.BEHIND:
            recommendations.append("Focus on converting existing pipeline to close faster")
            recommendations.append("Increase lead generation activities")
            if forecast.confidence == PredictionConfidence.LOW:
                recommendations.append("Current trajectory shows significant gap - consider strategy review")
        elif risk_level == RiskLevel.AT_RISK:
            recommendations.append("Maintain current pace but look for quick wins")
            recommendations.append("Review pipeline for any deals that can be accelerated")
        elif risk_level == RiskLevel.AHEAD:
            recommendations.append("On track to exceed goal - consider raising targets")

        return GoalAttainment(
            goal_units=goal_units,
            goal_volume=goal_volume,
            current_units=current_units,
            current_volume=current_volume,
            predicted_final_units=predicted_final_units,
            predicted_final_volume=predicted_final_volume,
            units_progress_pct=round(units_progress_pct, 1),
            volume_progress_pct=round(volume_progress_pct, 1),
            units_on_track_pct=round(units_on_track, 1),
            volume_on_track_pct=round(volume_on_track, 1),
            risk_level=risk_level,
            days_remaining=days_remaining,
            units_per_day_needed=round(units_per_day, 2),
            volume_per_day_needed=round(volume_per_day, 0),
            recommendations=recommendations,
        )

    def get_team_forecast(
        self,
        team_members: List[str],
        forecast_days: int = 30,
    ) -> Dict[str, Any]:
        """Get aggregated forecast for a team."""
        individual_forecasts = []

        for member_id in team_members:
            history = self.get_production_history(member_id, months=6)
            forecast = self.forecast_production(history, forecast_days)
            trend = self.analyze_trend(history)

            individual_forecasts.append({
                "member_id": member_id,
                "forecast": forecast,
                "trend": trend,
            })

        # Aggregate team forecast
        total_predicted_units = sum(f["forecast"].predicted_units for f in individual_forecasts)
        total_predicted_volume = sum(f["forecast"].predicted_volume for f in individual_forecasts)

        # Average confidence
        avg_confidence_score = statistics.mean(
            f["forecast"].confidence_score for f in individual_forecasts
        ) if individual_forecasts else 0

        # Identify top and bottom performers
        sorted_by_units = sorted(
            individual_forecasts,
            key=lambda x: x["forecast"].predicted_units,
            reverse=True,
        )

        return {
            "team_total": {
                "predicted_units": total_predicted_units,
                "predicted_volume": total_predicted_volume,
                "avg_confidence_score": round(avg_confidence_score, 1),
            },
            "individual_forecasts": [
                {
                    "member_id": f["member_id"],
                    "predicted_units": f["forecast"].predicted_units,
                    "predicted_volume": f["forecast"].predicted_volume,
                    "confidence": f["forecast"].confidence.value,
                    "trend": f["trend"].direction.value,
                }
                for f in individual_forecasts
            ],
            "top_performers": [f["member_id"] for f in sorted_by_units[:3]],
            "needs_attention": [
                f["member_id"]
                for f in sorted_by_units[-3:]
                if f["trend"].direction == TrendDirection.DOWN
            ],
        }

    def get_conversion_analysis(
        self,
        entity_id: str,
        days: int = 90,
    ) -> Dict[str, Any]:
        """
        Analyze conversion rates at each pipeline stage.
        """
        # In production, query actual conversion data
        # For demo, return sample analysis

        conversions = {
            "lead_to_app": {
                "rate": 0.28,
                "benchmark": self.CONVERSION_BENCHMARKS["lead_to_app"],
                "total_leads": 150,
                "converted": 42,
            },
            "app_to_submit": {
                "rate": 0.72,
                "benchmark": self.CONVERSION_BENCHMARKS["app_to_submit"],
                "total": 42,
                "converted": 30,
            },
            "submit_to_approve": {
                "rate": 0.90,
                "benchmark": self.CONVERSION_BENCHMARKS["submit_to_approve"],
                "total": 30,
                "converted": 27,
            },
            "approve_to_fund": {
                "rate": 0.92,
                "benchmark": self.CONVERSION_BENCHMARKS["approve_to_fund"],
                "total": 27,
                "converted": 25,
            },
        }

        # Calculate overall and identify weak spots
        overall_rate = 25 / 150  # funded / leads

        weak_spots = []
        for stage, data in conversions.items():
            if data["rate"] < data["benchmark"]:
                gap = (data["benchmark"] - data["rate"]) * 100
                weak_spots.append({
                    "stage": stage,
                    "gap_pct": round(gap, 1),
                    "potential_units": round(data["total"] * gap / 100),
                })

        return {
            "period_days": days,
            "overall_conversion": round(overall_rate * 100, 1),
            "overall_benchmark": self.CONVERSION_BENCHMARKS["overall"] * 100,
            "stage_conversions": conversions,
            "weak_spots": weak_spots,
            "recommendations": self._get_conversion_recommendations(weak_spots),
        }

    def _get_conversion_recommendations(
        self,
        weak_spots: List[Dict],
    ) -> List[str]:
        """Generate recommendations based on conversion weak spots."""
        recommendations = []

        for spot in weak_spots:
            stage = spot["stage"]

            if stage == "lead_to_app":
                recommendations.append("Improve lead follow-up speed - aim for <5 minute response")
                recommendations.append("Enhance lead nurturing sequence")
            elif stage == "app_to_submit":
                recommendations.append("Streamline document collection process")
                recommendations.append("Implement automated follow-ups for missing docs")
            elif stage == "submit_to_approve":
                recommendations.append("Review file quality before submission")
                recommendations.append("Address common UW conditions proactively")
            elif stage == "approve_to_fund":
                recommendations.append("Expedite closing disclosure delivery")
                recommendations.append("Improve coordination with title/escrow")

        return recommendations

    def get_production_summary(
        self,
        entity_id: str,
        entity_type: str = "lo",
    ) -> Dict[str, Any]:
        """
        Get comprehensive production summary with forecasts.
        """
        history = self.get_production_history(entity_id, months=12)
        trend = self.analyze_trend(history)

        # Get forecasts for different periods
        forecast_30 = self.forecast_production(history, 30)
        forecast_60 = self.forecast_production(history, 60)
        forecast_90 = self.forecast_production(history, 90)

        # Current month production
        today = date.today()
        current_month_start = today.replace(day=1)

        # Simulate MTD production
        days_in_month = 30
        days_elapsed = today.day
        mtd_units = int((history[-1].units if history else 0) * days_elapsed / days_in_month)
        mtd_volume = (history[-1].volume if history else 0) * days_elapsed / days_in_month

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "current_month": {
                "mtd_units": mtd_units,
                "mtd_volume": round(mtd_volume),
                "projected_units": history[-1].units if history else 0,
                "projected_volume": round(history[-1].volume if history else 0),
            },
            "trend": {
                "direction": trend.direction.value,
                "change_pct": trend.change_pct,
                "volatility": trend.volatility_score,
            },
            "forecasts": {
                "30_day": {
                    "units": forecast_30.predicted_units,
                    "volume": forecast_30.predicted_volume,
                    "confidence": forecast_30.confidence.value,
                },
                "60_day": {
                    "units": forecast_60.predicted_units,
                    "volume": forecast_60.predicted_volume,
                    "confidence": forecast_60.confidence.value,
                },
                "90_day": {
                    "units": forecast_90.predicted_units,
                    "volume": forecast_90.predicted_volume,
                    "confidence": forecast_90.confidence.value,
                },
            },
            "historical": {
                "avg_monthly_units": trend.avg_monthly_units,
                "avg_monthly_volume": trend.avg_monthly_volume,
                "peak_month": trend.peak_month,
                "trough_month": trend.trough_month,
            },
            "seasonality": trend.seasonality_factor,
        }


# Singleton instance
_predictor_service = None


def get_production_predictor(db_session=None) -> ProductionPredictorService:
    """Get or create the production predictor service instance."""
    global _predictor_service
    if _predictor_service is None:
        _predictor_service = ProductionPredictorService(db_session=db_session)
    elif db_session is not None:
        # Update db session for existing instance
        _predictor_service.db = db_session
    return _predictor_service
