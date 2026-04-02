"""
Pipeline Probability Routes

API endpoints for AI-powered loan closing probability predictions.
Part of the Advanced Analytics module.
"""

from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from routes.auth_deps import require_auth
from services.pipeline_probability_service import (
    PipelineProbabilityService,
    ProbabilityScore,
    PipelineProbabilitySummary,
    RiskLevel,
    ProbabilityTrend,
)

router = APIRouter(prefix="/api/v1/pipeline-probability", tags=["Pipeline Probability"], dependencies=[Depends(require_auth)])


# =============================================================================
# Request/Response Models
# =============================================================================

class RiskFactorResponse(BaseModel):
    """Risk factor affecting probability."""
    factor: str
    description: str
    impact: float
    category: str
    mitigation: Optional[str] = None


class StrengthFactorResponse(BaseModel):
    """Positive factor for probability."""
    factor: str
    description: str
    impact: float
    category: str


class RecommendedActionResponse(BaseModel):
    """Recommended action to improve probability."""
    action: str
    priority: str
    expected_impact: float
    effort: str
    deadline_days: Optional[int] = None


class ProbabilityScoreResponse(BaseModel):
    """Complete probability score for a loan."""
    loan_id: int
    loan_number: str
    borrower_name: str
    loan_amount: float
    current_status: str

    close_probability: float
    confidence_level: float
    risk_level: str
    trend: str

    expected_close_days: int
    expected_close_date: Optional[str]
    lock_expiration_risk: bool

    risk_factors: List[RiskFactorResponse]
    strength_factors: List[StrengthFactorResponse]
    recommended_actions: List[RecommendedActionResponse]

    similar_loans_close_rate: Optional[float]
    stage_avg_probability: Optional[float]

    calculated_at: str
    model_version: str

    class Config:
        from_attributes = True


class PipelineSummaryResponse(BaseModel):
    """Pipeline probability summary."""
    total_loans: int
    total_volume: float

    low_risk_count: int
    medium_risk_count: int
    high_risk_count: int
    critical_risk_count: int

    high_probability_count: int
    medium_probability_count: int
    low_probability_count: int

    weighted_avg_probability: float
    expected_funded_volume: float
    at_risk_volume: float

    improving_count: int
    declining_count: int

    top_risk_factors: List[dict]


class TrendDataPoint(BaseModel):
    """Single trend data point."""
    date: str
    avg_probability: float
    loan_count: int
    critical_count: int


class TrendsResponse(BaseModel):
    """Probability trends over time."""
    period_days: int
    daily_trends: List[TrendDataPoint]
    trend_direction: str


class BulkScoreRequest(BaseModel):
    """Request to calculate scores for multiple loans."""
    loan_ids: List[int] = Field(..., max_length=100)


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/loan/{loan_id}", response_model=ProbabilityScoreResponse)
async def get_loan_probability(
    loan_id: int,
    save_history: bool = Query(default=True, description="Save score to history"),
    db: Session = Depends(get_db),
):
    """
    Get closing probability score for a specific loan.

    Returns detailed analysis including:
    - Close probability (0-100%)
    - Risk level (low/medium/high/critical)
    - Risk and strength factors
    - Recommended actions
    - Expected close timing
    """
    service = PipelineProbabilityService(db)

    try:
        score = await service.calculate_probability(loan_id)

        if save_history:
            await service.save_score(score)

        return ProbabilityScoreResponse(**score.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to calculate probability")


@router.get("/pipeline", response_model=List[ProbabilityScoreResponse])
async def get_pipeline_probabilities(
    lo_id: Optional[int] = Query(default=None, description="Filter by loan officer"),
    branch_id: Optional[int] = Query(default=None, description="Filter by branch"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    risk_level: Optional[str] = Query(default=None, description="Filter by risk level"),
    min_probability: Optional[float] = Query(default=None, ge=0, le=100),
    max_probability: Optional[float] = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """
    Get probability scores for the active pipeline.

    Sorted by probability (lowest first) to highlight at-risk loans.
    """
    service = PipelineProbabilityService(db)

    status_filter = [status] if status else None
    scores = await service.calculate_pipeline_scores(
        lo_id=lo_id,
        branch_id=branch_id,
        status_filter=status_filter,
    )

    # Apply additional filters
    if risk_level:
        scores = [s for s in scores if s.risk_level.value == risk_level]
    if min_probability is not None:
        scores = [s for s in scores if s.close_probability >= min_probability]
    if max_probability is not None:
        scores = [s for s in scores if s.close_probability <= max_probability]

    return [ProbabilityScoreResponse(**s.to_dict()) for s in scores[:limit]]


@router.get("/summary", response_model=PipelineSummaryResponse)
async def get_pipeline_summary(
    lo_id: Optional[int] = Query(default=None),
    branch_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Get summary of probability scores across the pipeline.

    Includes:
    - Risk distribution
    - Probability brackets
    - Expected funded volume
    - At-risk volume
    - Top risk factors
    """
    service = PipelineProbabilityService(db)

    summary = await service.get_pipeline_summary(lo_id=lo_id, branch_id=branch_id)

    return PipelineSummaryResponse(**summary.to_dict())


@router.get("/at-risk", response_model=List[ProbabilityScoreResponse])
async def get_at_risk_loans(
    threshold: float = Query(default=50.0, ge=0, le=100, description="Probability threshold"),
    lo_id: Optional[int] = Query(default=None),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    """
    Get loans below the probability threshold (at-risk).

    Default threshold is 50% - loans with less than 50% chance of closing.
    """
    service = PipelineProbabilityService(db)

    at_risk = await service.get_at_risk_loans(
        threshold=threshold,
        lo_id=lo_id,
        limit=limit,
    )

    return [ProbabilityScoreResponse(**s.to_dict()) for s in at_risk]


@router.get("/trends", response_model=TrendsResponse)
async def get_probability_trends(
    lo_id: Optional[int] = Query(default=None),
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """
    Get probability trends over time.

    Shows how pipeline probability has changed over the specified period.
    """
    service = PipelineProbabilityService(db)

    trends = await service.get_probability_trends(lo_id=lo_id, days=days)

    return TrendsResponse(
        period_days=trends["period_days"],
        daily_trends=[TrendDataPoint(**d) for d in trends["daily_trends"]],
        trend_direction=trends["trend_direction"],
    )


@router.post("/bulk", response_model=List[ProbabilityScoreResponse])
async def calculate_bulk_probabilities(
    request: BulkScoreRequest,
    save_history: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """
    Calculate probability scores for multiple loans.

    Maximum 100 loans per request.
    """
    service = PipelineProbabilityService(db)

    scores = []
    for loan_id in request.loan_ids:
        try:
            score = await service.calculate_probability(loan_id)
            if save_history:
                await service.save_score(score)
            scores.append(score)
        except ValueError:
            continue  # Skip not found loans
        except Exception as e:
            continue  # Skip failed calculations

    return [ProbabilityScoreResponse(**s.to_dict()) for s in scores]


@router.get("/leaderboard")
async def get_probability_leaderboard(
    branch_id: Optional[int] = Query(default=None),
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """
    Get leaderboard of LOs by pipeline probability performance.

    Shows which LOs maintain the healthiest pipelines.
    """
    service = PipelineProbabilityService(db)

    # Get scores grouped by LO
    scores = await service.calculate_pipeline_scores(branch_id=branch_id)

    # Group by LO
    lo_scores = {}
    for score in scores:
        # Get LO from the score metadata (would need to add this)
        # For now, aggregate all
        pass

    # For now, return summary metrics
    summary = await service.get_pipeline_summary(branch_id=branch_id)

    return {
        "period_days": days,
        "pipeline_health_score": summary.weighted_avg_probability,
        "total_loans": summary.total_loans,
        "at_risk_percentage": round(
            (summary.high_risk_count + summary.critical_risk_count) / summary.total_loans * 100, 1
        ) if summary.total_loans > 0 else 0,
    }


@router.get("/recommendations/{loan_id}")
async def get_loan_recommendations(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """
    Get prioritized recommendations to improve a loan's close probability.
    """
    service = PipelineProbabilityService(db)

    try:
        score = await service.calculate_probability(loan_id)

        return {
            "loan_id": loan_id,
            "current_probability": score.close_probability,
            "potential_improvement": sum(a.expected_impact for a in score.recommended_actions),
            "recommendations": [
                {
                    "action": a.action,
                    "priority": a.priority,
                    "expected_impact": a.expected_impact,
                    "effort": a.effort,
                    "deadline_days": a.deadline_days,
                }
                for a in score.recommended_actions
            ],
            "risk_factors_to_address": [
                {
                    "factor": rf.factor,
                    "description": rf.description,
                    "mitigation": rf.mitigation,
                }
                for rf in score.risk_factors if rf.mitigation
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/distribution")
async def get_probability_distribution(
    lo_id: Optional[int] = Query(default=None),
    branch_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Get distribution of probabilities across the pipeline.

    Returns counts in probability brackets for visualization.
    """
    service = PipelineProbabilityService(db)

    scores = await service.calculate_pipeline_scores(lo_id=lo_id, branch_id=branch_id)

    # Create distribution buckets
    distribution = {
        "0-20": {"count": 0, "volume": 0},
        "20-40": {"count": 0, "volume": 0},
        "40-60": {"count": 0, "volume": 0},
        "60-80": {"count": 0, "volume": 0},
        "80-100": {"count": 0, "volume": 0},
    }

    for score in scores:
        prob = score.close_probability
        if prob < 20:
            bucket = "0-20"
        elif prob < 40:
            bucket = "20-40"
        elif prob < 60:
            bucket = "40-60"
        elif prob < 80:
            bucket = "60-80"
        else:
            bucket = "80-100"

        distribution[bucket]["count"] += 1
        distribution[bucket]["volume"] += score.loan_amount

    return {
        "total_loans": len(scores),
        "distribution": distribution,
        "buckets": ["0-20", "20-40", "40-60", "60-80", "80-100"],
    }


@router.get("/health")
async def probability_health_check():
    """Health check for the probability service."""
    return {
        "status": "healthy",
        "service": "pipeline-probability",
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
