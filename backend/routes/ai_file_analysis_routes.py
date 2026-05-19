"""
AI Smart File Analysis Routes

API endpoints for AI-powered loan file analysis:
- Full file analysis with AI insights
- Quick readiness check
- Individual document analysis
- Batch analysis for pipeline review
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Import from main app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai_file_analysis_service import AIFileAnalysisService
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api/v1/ai-file-analysis", tags=["ai-file-analysis"])


# Pydantic models for request/response
class AnalysisResponse(BaseModel):
    loan_id: int
    loan_number: Optional[str]
    loan_type: Optional[str]
    analysis_date: str
    summary: str
    readiness_score: int
    readiness_grade: str
    missing_documents: list
    documents_collected: int
    red_flags: list
    compliance_issues: list
    recommendations: list
    open_conditions: int
    next_steps: list


class QuickCheckResponse(BaseModel):
    loan_id: int
    loan_number: Optional[str]
    readiness_score: int
    readiness_grade: str
    is_ready_to_submit: bool
    missing_documents_count: int
    compliance_issues_count: int
    open_conditions_count: int
    quick_issues: list


class DocumentAnalysisResponse(BaseModel):
    document_id: int
    file_name: Optional[str]
    doc_type: Optional[str]
    status: Optional[str]
    issues: list
    has_issues: bool
    extracted_data: dict


class BatchAnalysisRequest(BaseModel):
    loan_ids: List[int]


class BatchAnalysisItem(BaseModel):
    loan_id: int
    loan_number: Optional[str]
    readiness_score: int
    readiness_grade: str
    critical_issues: int
    is_ready: bool


class BatchAnalysisResponse(BaseModel):
    total_loans: int
    ready_count: int
    needs_attention_count: int
    results: List[BatchAnalysisItem]


# Database dependency - injected from main app
_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set the database and user dependencies from main app."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Database dependency not configured. Call set_dependencies first.")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
@router.get("/analyze/{loan_id}")
async def analyze_loan_file(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Perform comprehensive AI analysis of a loan file.

    Returns detailed analysis including:
    - Missing documents
    - Red flags and potential issues
    - Guideline compliance concerns
    - Recommendations before submission
    - Readiness score (0-100)
    """
    service = AIFileAnalysisService(db)
    result = service.analyze_loan_file(loan_id)

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/quick-check/{loan_id}")
async def quick_file_check(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Quick file readiness check without full AI analysis.
    Faster, rule-based checking for pipeline overview.
    """
    service = AIFileAnalysisService(db)
    result = service.quick_file_check(loan_id)

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/document/{document_id}")
async def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze a specific document for issues.
    Checks for screenshots, expiration, rejection status, etc.
    """
    service = AIFileAnalysisService(db)
    result = service.analyze_document(document_id)

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/batch-check")
async def batch_file_check(
    request: BatchAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Batch file readiness check for multiple loans.
    Useful for pipeline review and prioritization.
    """
    service = AIFileAnalysisService(db)
    results = []
    ready_count = 0

    for loan_id in request.loan_ids[:50]:  # Limit to 50 loans per batch
        check = service.quick_file_check(loan_id)
        if not check.get("error"):
            is_ready = check.get("is_ready_to_submit", False)
            if is_ready:
                ready_count += 1

            results.append({
                "loan_id": loan_id,
                "loan_number": check.get("loan_number"),
                "readiness_score": check.get("readiness_score", 0),
                "readiness_grade": check.get("readiness_grade", "F"),
                "critical_issues": (
                    check.get("missing_documents_count", 0) +
                    check.get("compliance_issues_count", 0)
                ),
                "is_ready": is_ready,
            })

    return {
        "total_loans": len(results),
        "ready_count": ready_count,
        "needs_attention_count": len(results) - ready_count,
        "results": sorted(results, key=lambda x: x["readiness_score"]),
    }


@router.get("/pipeline-readiness")
async def get_pipeline_readiness(
    limit: int = Query(20, le=100),
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get file readiness overview for pipeline loans.
    Shows which loans are ready for submission vs need attention.
    """
    from sqlalchemy import text

    # Get active loans
    filters = ["stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED')"]
    params = {"limit": limit}

    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage

    where_sql = " AND ".join(filters)

    try:
        query_sql = """
            SELECT id, loan_number, stage, loan_type, amount
            FROM loans
            WHERE """ + where_sql + """
            ORDER BY created_at DESC
            LIMIT :limit
        """
        result = db.execute(text(query_sql), params)

        loans = [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching loans for pipeline readiness: {e}")
        loans = []

    # Run quick checks on each loan
    service = AIFileAnalysisService(db)
    pipeline_status = {
        "ready": [],
        "almost_ready": [],
        "needs_work": [],
        "critical": [],
    }

    for loan in loans:
        check = service.quick_file_check(loan["id"])
        loan_info = {
            "loan_id": loan["id"],
            "loan_number": loan.get("loan_number"),
            "stage": loan.get("stage"),
            "loan_type": loan.get("loan_type"),
            "amount": loan.get("amount"),
            "readiness_score": check.get("readiness_score", 0),
            "quick_issues": check.get("quick_issues", []),
        }

        score = check.get("readiness_score", 0)
        if score >= 90:
            pipeline_status["ready"].append(loan_info)
        elif score >= 70:
            pipeline_status["almost_ready"].append(loan_info)
        elif score >= 50:
            pipeline_status["needs_work"].append(loan_info)
        else:
            pipeline_status["critical"].append(loan_info)

    return {
        "summary": {
            "total": len(loans),
            "ready": len(pipeline_status["ready"]),
            "almost_ready": len(pipeline_status["almost_ready"]),
            "needs_work": len(pipeline_status["needs_work"]),
            "critical": len(pipeline_status["critical"]),
        },
        "by_status": pipeline_status,
    }
