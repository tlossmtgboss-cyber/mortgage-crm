"""
Recruiting Assessment API Routes

Endpoints for:
- Quiz management
- Quiz submission
- Score retrieval
- Production calculator
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

import os
from database import get_db
from services.recruit_assessment_service import recruit_assessment_service
from sqlalchemy.exc import SQLAlchemyError
from models.recruit_assessment_models import (
    QuizForDisposition,
    QuizSubmission,
    AssessmentScores,
    AssessmentScoreBreakdown,
    CalculatorConfig,
    CalculatorInput,
    CalculatorResult,
)
from routes.auth_deps import require_auth

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

router = APIRouter(prefix="/api/v1/recruiting", tags=["Recruiting Assessment"], dependencies=[Depends(require_auth)])


# =============================================================================
# Quiz Endpoints
# =============================================================================

@router.get("/quiz/{disposition}", response_model=QuizForDisposition)
async def get_quiz_for_disposition(disposition: str):
    """
    Get all quiz questions for a specific disposition stage.

    Disposition stages: screening, phone_screen, interview, assessment, offer
    """
    valid_dispositions = ["screening", "phone_screen", "interview", "assessment", "offer"]
    if disposition not in valid_dispositions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disposition. Must be one of: {', '.join(valid_dispositions)}"
        )

    quiz = recruit_assessment_service.get_quiz_for_disposition(disposition)
    if not quiz.questions:
        raise HTTPException(
            status_code=404,
            detail=f"No quiz questions found for disposition: {disposition}"
        )

    return quiz


@router.post("/candidates/{candidate_id}/quiz", response_model=AssessmentScores)
async def submit_quiz_responses(
    candidate_id: int,
    submission: QuizSubmission,
    responded_by: int = Query(..., description="User ID of the person completing the quiz")
):
    """
    Submit quiz responses for a candidate and update their assessment scores.

    The quiz must be completed when changing a candidate's disposition.
    """
    if not submission.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    try:
        scores = recruit_assessment_service.submit_quiz_responses(
            candidate_id=candidate_id,
            submission=submission,
            responded_by=responded_by
        )
        return scores
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/candidates/{candidate_id}/quiz-completed/{disposition}")
async def check_quiz_completed(candidate_id: int, disposition: str):
    """Check if a quiz has been completed for a specific disposition."""
    completed = recruit_assessment_service.check_quiz_completed(candidate_id, disposition)
    return {"completed": completed, "disposition": disposition}


# =============================================================================
# Score Endpoints
# =============================================================================

@router.get("/candidates/{candidate_id}/scores", response_model=Optional[AssessmentScores])
async def get_candidate_scores(candidate_id: int):
    """Get assessment scores for a candidate."""
    scores = recruit_assessment_service.get_candidate_scores(candidate_id)
    if not scores:
        return AssessmentScores(candidate_id=candidate_id)
    return scores


@router.get("/candidates/{candidate_id}/scores/breakdown", response_model=AssessmentScoreBreakdown)
async def get_score_breakdown(candidate_id: int):
    """Get detailed score breakdown with quiz history and recommendations."""
    return recruit_assessment_service.get_score_breakdown(candidate_id)


@router.post("/candidates/{candidate_id}/scores/recalculate", response_model=AssessmentScores)
async def recalculate_scores(candidate_id: int):
    """Force recalculation of assessment scores from all quiz responses."""
    return recruit_assessment_service.calculate_and_update_scores(candidate_id)


# =============================================================================
# Calculator Endpoints
# =============================================================================

@router.get("/calculator/config", response_model=CalculatorConfig)
async def get_calculator_config(organization_id: int = 1):
    """Get production calculator configuration."""
    return recruit_assessment_service.get_calculator_config(organization_id)


@router.put("/calculator/config", response_model=CalculatorConfig)
async def update_calculator_config(
    config: CalculatorConfig,
    organization_id: int = 1,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Update production calculator configuration (admin only)."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    return recruit_assessment_service.update_calculator_config(config, organization_id)


@router.post("/calculator/calculate", response_model=CalculatorResult)
async def calculate_production_impact(input_data: CalculatorInput):
    """
    Calculate projected production impact for a candidate.

    Input:
    - current_volume: Current annual loan volume ($)
    - current_units: Current annual units closed
    - avg_loan_amount: Optional average loan amount (auto-calculated if not provided)

    Returns projected volume, units, and earnings with our company advantages.
    """
    if input_data.current_volume < 0 or input_data.current_units < 0:
        raise HTTPException(status_code=400, detail="Values cannot be negative")

    return recruit_assessment_service.calculate_production_impact(input_data)


# =============================================================================
# Quiz Template Management (Admin)
# =============================================================================

class QuizTemplateCreate(BaseModel):
    disposition: str
    question_text: str
    question_type: str = "likert"
    category: str
    weight: float = 1.0
    display_order: int = 0


@router.get("/quiz/templates/all")
async def get_all_quiz_templates(request: Request = None, db: Session = Depends(get_db)):
    """Get all quiz templates (admin only)."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    from database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, disposition, question_text, question_type,
                       category, weight, display_order, is_active
                FROM recruit_quiz_templates
                ORDER BY disposition, display_order
            """)
        )
        rows = result.fetchall()

    templates = []
    for row in rows:
        templates.append({
            "id": row.id,
            "disposition": row.disposition,
            "question_text": row.question_text,
            "question_type": row.question_type,
            "category": row.category,
            "weight": float(row.weight),
            "display_order": row.display_order,
            "is_active": row.is_active
        })

    return {"templates": templates, "count": len(templates)}


@router.post("/quiz/templates")
async def create_quiz_template(template: QuizTemplateCreate, request: Request = None, db: Session = Depends(get_db)):
    """Create a new quiz template (admin only)."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    from database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO recruit_quiz_templates
                (disposition, question_text, question_type, category, weight, display_order)
                VALUES (:disposition, :question_text, :question_type, :category, :weight, :display_order)
                RETURNING id
            """),
            {
                "disposition": template.disposition,
                "question_text": template.question_text,
                "question_type": template.question_type,
                "category": template.category,
                "weight": template.weight,
                "display_order": template.display_order
            }
        )
        row = result.fetchone()
        conn.commit()

    return {"id": row.id, "message": "Template created successfully"}


@router.delete("/quiz/templates/{template_id}")
async def delete_quiz_template(template_id: int, request: Request = None, db: Session = Depends(get_db)):
    """Soft delete a quiz template (admin only)."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    from database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(
            text("UPDATE recruit_quiz_templates SET is_active = false WHERE id = :id"),
            {"id": template_id}
        )
        conn.commit()

    return {"message": "Template deactivated"}


# =============================================================================
# Migration Endpoint (Development)
# =============================================================================

@router.post("/admin/run-assessment-migration")
async def run_assessment_migration(request: Request = None, db: Session = Depends(get_db)):
    """Run the assessment tables migration (admin only)."""
    from main import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)

    try:
        from migrations.add_recruit_assessment_tables import run_migration
        run_migration()
        return {"status": "success", "message": "Migration completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
