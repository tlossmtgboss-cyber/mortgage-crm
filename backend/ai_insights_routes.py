"""
FastAPI routes for AI-powered profitability insights.
"""

from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from database import get_db
from routes.auth_deps import require_auth

from services.ai_insights_service import AIInsightsService


router = APIRouter(prefix="/api/v1/profitability/ai", tags=["profitability-ai"], dependencies=[Depends(require_auth)])


# Helper to get organization from tenant context middleware
def get_organization_id(request: Request) -> int:
    """Get organization ID from tenant context middleware."""
    org_id = getattr(request.state, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============ Request/Response Models ============

class NaturalLanguageQuery(BaseModel):
    question: str = Field(..., description="Natural language question about profitability")
    month: Optional[str] = Field(None, description="Month in YYYY-MM format")


class HiringAnalysisRequest(BaseModel):
    role_name: str = Field(..., description="Role to analyze (e.g., 'Loan Officer', 'Processor')")
    salary: float = Field(..., description="Proposed annual salary")
    month: Optional[str] = Field(None, description="Base month for analysis")


class ScenarioCompareRequest(BaseModel):
    scenarios: List[dict] = Field(..., description="List of scenarios to compare")
    month: Optional[str] = Field(None, description="Base month for comparison")


# ============ AI Query Endpoints ============

@router.post("/query")
async def query_profitability(
    request: Request,
    body: NaturalLanguageQuery,
    db: Session = Depends(get_db)
):
    """
    Ask natural language questions about profitability data.

    Examples:
    - "Who are my top 3 loan officers by ROI?"
    - "What's causing our cost per loan to increase?"
    - "Should we hire another processor?"
    - "How does this month compare to last month?"
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    # Parse month
    month = None
    if body.month:
        try:
            month = datetime.strptime(body.month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    try:
        result = service.query_natural_language(body.question, month)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="AI query failed")


@router.get("/recommendations")
async def get_recommendations(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Get AI-powered strategic recommendations based on profitability data."""
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    try:
        recommendations = service.generate_smart_recommendations(month_date)
        return {
            "month": month or date.today().strftime("%Y-%m"),
            "recommendations": recommendations,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")


@router.post("/hiring-analysis")
async def analyze_hiring(
    request: Request,
    body: HiringAnalysisRequest,
    db: Session = Depends(get_db)
):
    """
    Get AI analysis for a hiring decision.

    Analyzes ROI, break-even timeline, and provides a recommendation
    based on current role performance data.
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if body.month:
        try:
            month_date = datetime.strptime(body.month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    try:
        result = service.analyze_hiring_decision(
            body.role_name,
            body.salary,
            month_date
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Hiring analysis failed")


@router.get("/executive-digest")
async def get_executive_digest(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    Generate an executive digest email content with key metrics,
    insights, and recommendations.
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    try:
        digest = service.generate_executive_digest(month_date)
        return digest
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate digest")


@router.get("/anomalies")
async def detect_anomalies(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    Detect anomalies and unusual patterns in profitability data.

    Returns list of detected anomalies with severity and suggested actions.
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    try:
        anomalies = service.detect_anomalies(month_date)
        return {
            "month": month or date.today().strftime("%Y-%m"),
            "anomalies": anomalies,
            "count": len(anomalies),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Anomaly detection failed")


@router.post("/compare-scenarios")
async def compare_scenarios(
    request: Request,
    body: ScenarioCompareRequest,
    db: Session = Depends(get_db)
):
    """
    Compare multiple business scenarios with AI analysis.

    Example scenarios:
    - {"name": "Hire 1 LO", "cost": 8500, "expected_loans": 10}
    - {"name": "Increase marketing 20%", "cost": 2000, "expected_leads": 50}
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if body.month:
        try:
            month_date = datetime.strptime(body.month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    try:
        result = service.compare_scenarios(body.scenarios, month_date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Scenario comparison failed")


# ============ Quick Insights Endpoints ============

@router.get("/quick-insights")
async def get_quick_insights(
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """
    Get quick AI-generated insights without detailed analysis.
    Faster response for dashboard widgets.
    """
    org_id = get_organization_id(request)
    service = AIInsightsService(db, org_id)

    month_date = None
    if month:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format")

    # Get recommendations and anomalies in parallel
    try:
        recommendations = service.generate_smart_recommendations(month_date)
        anomalies = service.detect_anomalies(month_date)

        # Take top items
        top_recommendations = recommendations[:3] if recommendations else []
        critical_anomalies = [a for a in anomalies if a.get("severity") in ["critical", "warning"]][:3]

        return {
            "month": month or date.today().strftime("%Y-%m"),
            "top_recommendations": top_recommendations,
            "alerts": critical_anomalies,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get quick insights")


@router.get("/suggested-questions")
async def get_suggested_questions():
    """Get suggested questions users can ask about profitability."""
    return {
        "questions": [
            {
                "category": "Performance",
                "questions": [
                    "Who are my top 3 loan officers by ROI?",
                    "Which roles have the highest profit contribution?",
                    "How does employee performance compare to last month?"
                ]
            },
            {
                "category": "Costs",
                "questions": [
                    "What's driving our cost per loan?",
                    "Where can we reduce expenses without impacting revenue?",
                    "How do our employee costs compare to industry average?"
                ]
            },
            {
                "category": "Hiring",
                "questions": [
                    "Should we hire another loan officer?",
                    "What would be the ROI of adding a processor?",
                    "Are our current staffing levels optimal?"
                ]
            },
            {
                "category": "Strategy",
                "questions": [
                    "How can we improve profit margin by 5%?",
                    "What's our break-even point?",
                    "Which areas have the biggest growth potential?"
                ]
            }
        ]
    }
