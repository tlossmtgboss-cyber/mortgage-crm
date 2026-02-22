"""
AI Metrics Routes

Provides endpoints for viewing AI agent performance metrics including
hallucination tracking, response times, tool usage, and quality metrics.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging
from sqlalchemy.exc import SQLAlchemyError

def _get_auth_dep():
    """Get auth dependency at runtime to avoid circular imports."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(dependencies=[Depends(_get_auth_dep())])
logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================

class HallucinationMetricsResponse(BaseModel):
    """Response model for hallucination metrics"""
    avg_faithfulness_score: float
    avg_hallucination_rate: float
    total_responses_analyzed: int
    total_claims_extracted: int
    verified_claims_count: int
    unsupported_claims_count: int
    contradicted_claims_count: int
    verification_rate: float
    hallucination_by_type: Dict[str, float]
    hallucination_by_tool: Dict[str, float]
    responses_with_hallucinations: int
    clean_responses: int
    period_start: datetime
    period_end: datetime


class AgentPerformanceResponse(BaseModel):
    """Response model for agent performance metrics"""
    avg_response_time_ms: float
    p50_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    tool_success_rate: float
    error_rate: float
    errors_by_node: Dict[str, int]
    thumbs_up_count: int
    thumbs_down_count: int
    satisfaction_rate: float
    period_start: datetime
    period_end: datetime


class AIQualityResponse(BaseModel):
    """Response model for AI quality metrics"""
    intent_accuracy: float
    intent_confidence_avg: float
    tool_selection_accuracy: float
    response_quality_avg: float
    followup_click_rate: float
    user_corrections_count: int
    period_start: datetime
    period_end: datetime


class DashboardSummaryResponse(BaseModel):
    """Response model for complete dashboard summary"""
    agent_performance: Dict[str, Any]
    business_metrics: Dict[str, Any]
    ai_quality: Dict[str, Any]
    response_time_breakdown: Dict[str, Any]
    hallucination_metrics: Dict[str, Any]
    generated_at: str


class VerifyResponseRequest(BaseModel):
    """Request model for manual response verification"""
    response_text: str
    source_data: Dict[str, Any]
    tools_used: List[str] = []
    use_llm: bool = False


# =============================================================================
# Dependency Injection
# =============================================================================

# Import get_db from main database module
from database import get_db

# Import authentication dependency
try:
    from auth.dependencies import get_current_user_flexible
except ImportError:
    # Fallback if main not available
    async def get_current_user_flexible():
        return None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/hallucination", response_model=HallucinationMetricsResponse)
async def get_hallucination_metrics(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: Session = Depends(get_db)
):
    """
    Get hallucination metrics for AI responses.

    Returns:
    - Average faithfulness score (0-1, how many claims are verified)
    - Average hallucination rate (0-1, how many claims contradict source data)
    - Breakdown by claim type (numeric, temporal, entity, etc.)
    - Breakdown by tool used
    - Count of responses with hallucinations vs clean responses
    """
    try:
        from agents.metrics.service import AIMetricsService

        metrics = await AIMetricsService.get_hallucination_metrics(
            db=db,
            days=days,
            user_id=user_id
        )

        return HallucinationMetricsResponse(
            avg_faithfulness_score=metrics.avg_faithfulness_score,
            avg_hallucination_rate=metrics.avg_hallucination_rate,
            total_responses_analyzed=metrics.total_responses_analyzed,
            total_claims_extracted=metrics.total_claims_extracted,
            verified_claims_count=metrics.verified_claims_count,
            unsupported_claims_count=metrics.unsupported_claims_count,
            contradicted_claims_count=metrics.contradicted_claims_count,
            verification_rate=metrics.verification_rate,
            hallucination_by_type=metrics.hallucination_by_type,
            hallucination_by_tool=metrics.hallucination_by_tool,
            responses_with_hallucinations=metrics.responses_with_hallucinations,
            clean_responses=metrics.clean_responses,
            period_start=metrics.period_start,
            period_end=metrics.period_end
        )

    except Exception as e:
        logger.error(f"Error getting hallucination metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/performance", response_model=AgentPerformanceResponse)
async def get_agent_performance(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    user_id: Optional[int] = Query(None, description="Filter by specific user"),
    db: Session = Depends(get_db)
):
    """
    Get agent performance metrics.

    Returns:
    - Response time statistics (avg, p50, p95, p99)
    - Tool success rate
    - Error rate and breakdown by node
    - User satisfaction metrics (thumbs up/down)
    """
    try:
        from agents.metrics.service import AIMetricsService

        metrics = await AIMetricsService.get_agent_performance(
            db=db,
            days=days,
            user_id=user_id
        )

        return AgentPerformanceResponse(**metrics.model_dump())

    except Exception as e:
        logger.error(f"Error getting agent performance metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/quality", response_model=AIQualityResponse)
async def get_ai_quality_metrics(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get AI quality metrics.

    Returns:
    - Intent classification accuracy
    - Tool selection accuracy
    - Response quality score
    - Follow-up click rate
    - User corrections count
    """
    try:
        from agents.metrics.service import AIMetricsService

        metrics = await AIMetricsService.get_ai_quality_metrics(
            db=db,
            days=days
        )

        return AIQualityResponse(**metrics.model_dump())

    except Exception as e:
        logger.error(f"Error getting AI quality metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboard", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive dashboard summary of all AI metrics.

    Returns all metrics in a single response:
    - Agent performance
    - Business metrics
    - AI quality
    - Response time breakdown
    - Hallucination metrics
    """
    try:
        from agents.metrics.service import AIMetricsService

        summary = await AIMetricsService.get_dashboard_summary(
            db=db,
            days=days
        )

        return DashboardSummaryResponse(**summary)

    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/response-time")
async def get_response_time_breakdown(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    query_type: Optional[str] = Query(None, description="Filter by query type"),
    db: Session = Depends(get_db)
):
    """
    Get detailed response time breakdown by query type.

    Returns average time spent in each phase:
    - analyze, gather, reason, execute, respond
    """
    try:
        from agents.metrics.service import AIMetricsService

        breakdown = await AIMetricsService.get_response_time_breakdown(
            db=db,
            days=days,
            query_type=query_type
        )

        return breakdown

    except Exception as e:
        logger.error(f"Error getting response time breakdown: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/business")
async def get_business_metrics(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get business-level AI metrics.

    Returns:
    - Total queries and unique users
    - Most common query types
    - Tool usage ranking
    - Actions executed
    - Engagement metrics
    """
    try:
        from agents.metrics.service import AIMetricsService

        metrics = await AIMetricsService.get_business_metrics(
            db=db,
            days=days
        )

        return metrics.model_dump()

    except Exception as e:
        logger.error(f"Error getting business metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.post("/verify-response")
async def manually_verify_response(
    request: VerifyResponseRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Manually trigger hallucination verification on a response.

    This endpoint is useful for testing or retroactive analysis.
    """
    try:
        from agents.hallucination_verifier import get_hallucination_verifier
        from agents.metrics.service import AIMetricsService
        import uuid

        verifier = get_hallucination_verifier()

        # Generate proper UUID for session tracking
        session_uuid = str(uuid.uuid4())

        report = await verifier.generate_report(
            session_id=session_uuid,
            message_id=f"manual_{uuid.uuid4().hex[:8]}",
            response_text=request.response_text,
            source_data=request.source_data,
            tools_used=request.tools_used,
            use_llm=request.use_llm
        )

        # Record to database for metrics tracking
        user_id = current_user.id if current_user and hasattr(current_user, 'id') else 1
        await AIMetricsService.record_hallucination_report(
            db=db,
            user_id=user_id,
            report=report
        )

        return {
            "faithfulness_score": report.faithfulness_score,
            "hallucination_rate": report.hallucination_rate,
            "total_claims": report.total_claims,
            "verified_claims": report.verified_claims,
            "unsupported_claims": report.unsupported_claims,
            "contradicted_claims": report.contradicted_claims,
            "confidence": report.confidence,
            "analysis_time_ms": report.analysis_time_ms,
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "claim_text": c.claim_text,
                    "claim_type": c.claim_type.value,
                    "extracted_value": c.extracted_value,
                }
                for c in report.claims
            ],
            "verification_results": [
                {
                    "claim_id": r.claim_id,
                    "status": r.status.value,
                    "expected_value": r.expected_value,
                    "claimed_value": r.claimed_value,
                    "discrepancy": r.discrepancy,
                    "confidence": r.confidence,
                }
                for r in report.verification_results
            ]
        }

    except Exception as e:
        logger.error(f"Error verifying response: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
