"""
Production Predictor Routes

API endpoints for production forecasting and prediction.
Part of the Advanced Analytics module.
"""

import logging
from typing import List, Optional
from datetime import datetime, date, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from routes.auth_deps import require_auth
from services.production_predictor_service import (
    ProductionPredictorService,
    get_production_predictor,
    PredictionConfidence,
    TrendDirection,
    RiskLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/production-predictor", tags=["Production Predictor"], dependencies=[Depends(require_auth)])


# =============================================================================
# Request/Response Models
# =============================================================================

class ForecastRequest(BaseModel):
    """Request for production forecast."""
    entity_id: str = Field(..., description="LO ID, team ID, or branch ID")
    entity_type: str = Field(default="lo", description="lo, team, or branch")
    forecast_days: int = Field(default=30, ge=7, le=365)
    include_pipeline: bool = Field(default=True)


class GoalAttainmentRequest(BaseModel):
    """Request for goal attainment prediction."""
    entity_id: Optional[str] = None
    goal_units: int = Field(default=0, ge=0)
    goal_volume: float = Field(default=0, ge=0)
    goal_period_start: Optional[date] = None
    goal_period_end: Optional[date] = None


class TeamForecastRequest(BaseModel):
    """Request for team forecast."""
    team_members: List[str]
    forecast_days: int = Field(default=30, ge=7, le=365)


class ForecastResponse(BaseModel):
    """Production forecast response."""
    entity_id: str
    period_end: date
    predicted_units: int
    predicted_volume: float
    confidence: str
    confidence_score: float
    range: dict
    factors: List[str]


class TrendResponse(BaseModel):
    """Trend analysis response."""
    direction: str
    change_pct: float
    avg_monthly_units: float
    avg_monthly_volume: float
    peak_month: str
    trough_month: str
    volatility_score: float
    seasonality: dict


class GoalAttainmentResponse(BaseModel):
    """Goal attainment prediction response."""
    goal_units: int
    goal_volume: float
    current_units: int
    current_volume: float
    predicted_final_units: int
    predicted_final_volume: float
    units_progress_pct: float
    volume_progress_pct: float
    units_on_track_pct: float
    volume_on_track_pct: float
    risk_level: str
    days_remaining: int
    units_per_day_needed: float
    volume_per_day_needed: float
    recommendations: List[str]


class ConversionAnalysisResponse(BaseModel):
    """Conversion analysis response."""
    period_days: int
    overall_conversion: float
    overall_benchmark: float
    stage_conversions: dict
    weak_spots: List[dict]
    recommendations: List[str]


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/summary/{entity_id}")
async def get_production_summary(
    entity_id: str,
    entity_type: str = Query(default="lo", description="lo, team, or branch"),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive production summary with forecasts.

    Returns current production, trends, and multi-period forecasts.
    """
    try:
        predictor = get_production_predictor(db_session=db)
        summary = predictor.get_production_summary(entity_id, entity_type)
        return summary
    except Exception as e:
        logger.error(f"Error getting production summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/forecast", response_model=ForecastResponse)
async def get_forecast(request: ForecastRequest, db: Session = Depends(get_db)):
    """
    Get production forecast for a specific period.

    Uses historical data, seasonality, and pipeline to predict future production.
    """
    try:
        predictor = get_production_predictor(db_session=db)

        # Get historical data
        history = predictor.get_production_history(
            request.entity_id,
            request.entity_type,
            months=12,
        )

        # Get current pipeline if requested
        pipeline = None
        if request.include_pipeline:
            # In production, fetch from database
            pipeline = {
                "closing_soon": 5,
                "closing_volume": 2000000,
            }

        # Generate forecast
        forecast = predictor.forecast_production(
            history,
            request.forecast_days,
            pipeline,
        )

        return ForecastResponse(
            entity_id=request.entity_id,
            period_end=forecast.period_end,
            predicted_units=forecast.predicted_units,
            predicted_volume=forecast.predicted_volume,
            confidence=forecast.confidence.value,
            confidence_score=forecast.confidence_score,
            range={
                "lower_units": forecast.lower_bound_units,
                "upper_units": forecast.upper_bound_units,
                "lower_volume": forecast.lower_bound_volume,
                "upper_volume": forecast.upper_bound_volume,
            },
            factors=forecast.factors,
        )
    except Exception as e:
        logger.error(f"Error generating forecast: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/trend/{entity_id}", response_model=TrendResponse)
async def get_trend_analysis(
    entity_id: str,
    entity_type: str = Query(default="lo"),
    months: int = Query(default=12, ge=3, le=24),
    db: Session = Depends(get_db),
):
    """
    Get trend analysis for an entity.

    Analyzes historical production patterns, seasonality, and momentum.
    """
    try:
        predictor = get_production_predictor(db_session=db)
        history = predictor.get_production_history(entity_id, entity_type, months)
        trend = predictor.analyze_trend(history)

        return TrendResponse(
            direction=trend.direction.value,
            change_pct=trend.change_pct,
            avg_monthly_units=trend.avg_monthly_units,
            avg_monthly_volume=trend.avg_monthly_volume,
            peak_month=trend.peak_month,
            trough_month=trend.trough_month,
            volatility_score=trend.volatility_score,
            seasonality=trend.seasonality_factor,
        )
    except Exception as e:
        logger.error(f"Error analyzing trend: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/goal-attainment", response_model=GoalAttainmentResponse)
async def predict_goal_attainment(request: GoalAttainmentRequest, db: Session = Depends(get_db)):
    """
    Predict likelihood of achieving production goals.

    Analyzes current progress, forecasts remaining production, and
    provides risk assessment with recommendations.
    """
    # Default response for missing/invalid data
    default_response = GoalAttainmentResponse(
        goal_units=request.goal_units or 0,
        goal_volume=request.goal_volume or 0,
        current_units=0,
        current_volume=0,
        predicted_final_units=0,
        predicted_final_volume=0,
        units_progress_pct=0,
        volume_progress_pct=0,
        units_on_track_pct=0,
        volume_on_track_pct=0,
        risk_level="unknown",
        days_remaining=0,
        units_per_day_needed=0,
        volume_per_day_needed=0,
        recommendations=["Set up your production goals to get personalized predictions"],
    )

    # Return default if required fields are missing
    if not request.entity_id or not request.goal_period_start or not request.goal_period_end:
        return default_response

    try:
        predictor = get_production_predictor(db_session=db)

        attainment = predictor.predict_goal_attainment(
            entity_id=request.entity_id,
            goal_units=request.goal_units,
            goal_volume=request.goal_volume,
            goal_period_start=request.goal_period_start,
            goal_period_end=request.goal_period_end,
        )

        return GoalAttainmentResponse(
            goal_units=attainment.goal_units,
            goal_volume=attainment.goal_volume,
            current_units=attainment.current_units,
            current_volume=attainment.current_volume,
            predicted_final_units=attainment.predicted_final_units,
            predicted_final_volume=attainment.predicted_final_volume,
            units_progress_pct=attainment.units_progress_pct,
            volume_progress_pct=attainment.volume_progress_pct,
            units_on_track_pct=attainment.units_on_track_pct,
            volume_on_track_pct=attainment.volume_on_track_pct,
            risk_level=attainment.risk_level.value,
            days_remaining=attainment.days_remaining,
            units_per_day_needed=attainment.units_per_day_needed,
            volume_per_day_needed=attainment.volume_per_day_needed,
            recommendations=attainment.recommendations,
        )
    except Exception as e:
        logger.error(f"Error predicting goal attainment: {e}")
        return default_response


@router.post("/team-forecast")
async def get_team_forecast(request: TeamForecastRequest, db: Session = Depends(get_db)):
    """
    Get aggregated forecast for a team.

    Includes individual member forecasts and team totals.
    """
    try:
        predictor = get_production_predictor(db_session=db)
        forecast = predictor.get_team_forecast(
            request.team_members,
            request.forecast_days,
        )
        return forecast
    except Exception as e:
        logger.error(f"Error generating team forecast: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/conversions/{entity_id}", response_model=ConversionAnalysisResponse)
async def get_conversion_analysis(
    entity_id: str,
    days: int = Query(default=90, ge=30, le=365),
    db: Session = Depends(get_db),
):
    """
    Analyze conversion rates at each pipeline stage.

    Identifies weak spots and provides recommendations for improvement.
    """
    try:
        predictor = get_production_predictor(db_session=db)
        analysis = predictor.get_conversion_analysis(entity_id, days)

        return ConversionAnalysisResponse(
            period_days=analysis["period_days"],
            overall_conversion=analysis["overall_conversion"],
            overall_benchmark=analysis["overall_benchmark"],
            stage_conversions=analysis["stage_conversions"],
            weak_spots=analysis["weak_spots"],
            recommendations=analysis["recommendations"],
        )
    except Exception as e:
        logger.error(f"Error analyzing conversions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history/{entity_id}")
async def get_production_history(
    entity_id: str,
    entity_type: str = Query(default="lo"),
    months: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """
    Get historical production data.

    Returns monthly production metrics for trend analysis.
    """
    try:
        predictor = get_production_predictor(db_session=db)
        history = predictor.get_production_history(entity_id, entity_type, months)

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "months": months,
            "data": [
                {
                    "date": dp.date.isoformat(),
                    "month": dp.date.strftime("%B %Y"),
                    "units": dp.units,
                    "volume": dp.volume,
                    "applications": dp.applications,
                    "pull_through_rate": round(dp.pull_through_rate * 100, 1),
                }
                for dp in history
            ],
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard")
async def get_production_leaderboard(
    entity_type: str = Query(default="lo", description="lo, team, or branch"),
    period: str = Query(default="mtd", description="mtd, qtd, ytd, or 30d"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Get production leaderboard with rankings.

    Ranks entities by production with forecast comparison.
    """
    try:
        predictor = get_production_predictor(db_session=db)

        # In production, this would query actual data and rank
        # For demo, return sample leaderboard
        leaderboard = []
        for i in range(limit):
            rank = i + 1
            history = predictor.get_production_history(f"lo-{rank}", months=3)
            trend = predictor.analyze_trend(history)
            forecast = predictor.forecast_production(history, 30)

            leaderboard.append({
                "rank": rank,
                "entity_id": f"lo-{rank}",
                "name": f"Loan Officer {rank}",
                "current_units": sum(dp.units for dp in history[-1:]),
                "current_volume": sum(dp.volume for dp in history[-1:]),
                "trend": trend.direction.value,
                "forecast_units": forecast.predicted_units,
                "forecast_volume": forecast.predicted_volume,
            })

        return {
            "period": period,
            "entity_type": entity_type,
            "leaderboard": leaderboard,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def predictor_health():
    """Health check for the production predictor service."""
    return {
        "status": "healthy",
        "service": "production-predictor",
        "timestamp": datetime.now().isoformat(),
    }
