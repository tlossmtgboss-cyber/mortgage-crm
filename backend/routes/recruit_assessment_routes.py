"""
Recruiting Assessment API Routes

Endpoints for:
- Quiz management
- Quiz submission
- Score retrieval
- Production calculator
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

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
from auth.dependencies import get_current_user
from database.models import User
from routes.auth_deps import require_auth

router = APIRouter(prefix="/api/v1/recruiting", tags=["Recruiting Assessment"], dependencies=[Depends(require_auth)])


def _verify_candidate_org(db: Session, candidate_id: int, organization_id: int):
    """Verify candidate belongs to the user's organization."""
    row = db.execute(text("""
        SELECT id FROM mm_candidates
        WHERE id = :id AND organization_id = :org_id AND is_active = true
    """), {"id": candidate_id, "org_id": organization_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")


def _require_admin(current_user: User):
    """Require admin role for template management."""
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit quiz responses for a candidate and update their assessment scores.

    The quiz must be completed when changing a candidate's disposition.
    """
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    if not submission.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    try:
        scores = recruit_assessment_service.submit_quiz_responses(
            candidate_id=candidate_id,
            submission=submission,
            responded_by=current_user.id,
            organization_id=current_user.organization_id
        )
        return scores
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/candidates/{candidate_id}/quiz-completed/{disposition}")
async def check_quiz_completed(
    candidate_id: int,
    disposition: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if a quiz has been completed for a specific disposition."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)
    completed = recruit_assessment_service.check_quiz_completed(candidate_id, disposition, organization_id=current_user.organization_id)
    return {"completed": completed, "disposition": disposition}


# =============================================================================
# Score Endpoints
# =============================================================================

@router.get("/candidates/{candidate_id}/scores", response_model=Optional[AssessmentScores])
async def get_candidate_scores(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get assessment scores for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)
    scores = recruit_assessment_service.get_candidate_scores(candidate_id, organization_id=current_user.organization_id)
    if not scores:
        return AssessmentScores(candidate_id=candidate_id)
    return scores


@router.get("/candidates/{candidate_id}/scores/breakdown", response_model=AssessmentScoreBreakdown)
async def get_score_breakdown(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed score breakdown with quiz history and recommendations."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)
    return recruit_assessment_service.get_score_breakdown(candidate_id, organization_id=current_user.organization_id)


@router.post("/candidates/{candidate_id}/scores/recalculate", response_model=AssessmentScores)
async def recalculate_scores(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Force recalculation of assessment scores from all quiz responses."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)
    return recruit_assessment_service.calculate_and_update_scores(candidate_id, organization_id=current_user.organization_id)


# =============================================================================
# Calculator Endpoints
# =============================================================================

@router.get("/calculator/config", response_model=CalculatorConfig)
async def get_calculator_config(current_user: User = Depends(get_current_user)):
    """Get production calculator configuration."""
    return recruit_assessment_service.get_calculator_config(current_user.organization_id)


@router.put("/calculator/config", response_model=CalculatorConfig)
async def update_calculator_config(
    config: CalculatorConfig,
    current_user: User = Depends(get_current_user),
):
    """Update production calculator configuration (admin only)."""
    _require_admin(current_user)
    return recruit_assessment_service.update_calculator_config(config, current_user.organization_id)


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
async def get_all_quiz_templates(current_user: User = Depends(get_current_user)):
    """Get all quiz templates (admin only)."""
    _require_admin(current_user)
    from database import engine

    org_id = current_user.organization_id
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, disposition, question_text, question_type,
                       category, weight, display_order, is_active
                FROM recruit_quiz_templates
                WHERE organization_id = :org_id OR organization_id IS NULL
                ORDER BY disposition, display_order
            """),
            {"org_id": org_id}
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
async def create_quiz_template(template: QuizTemplateCreate, current_user: User = Depends(get_current_user)):
    """Create a new quiz template (admin only)."""
    _require_admin(current_user)
    from database import engine

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO recruit_quiz_templates
                (disposition, question_text, question_type, category, weight, display_order, organization_id)
                VALUES (:disposition, :question_text, :question_type, :category, :weight, :display_order, :org_id)
                RETURNING id
            """),
            {
                "disposition": template.disposition,
                "question_text": template.question_text,
                "question_type": template.question_type,
                "category": template.category,
                "weight": template.weight,
                "display_order": template.display_order,
                "org_id": current_user.organization_id
            }
        )
        row = result.fetchone()
        conn.commit()

    return {"id": row.id, "message": "Template created successfully"}


@router.delete("/quiz/templates/{template_id}")
async def delete_quiz_template(template_id: int, current_user: User = Depends(get_current_user)):
    """Soft delete a quiz template (admin only)."""
    _require_admin(current_user)
    from database import engine

    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE recruit_quiz_templates SET is_active = false WHERE id = :id AND (organization_id = :org_id OR organization_id IS NULL)"),
            {"id": template_id, "org_id": current_user.organization_id}
        )
        conn.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    return {"message": "Template deactivated"}


# =============================================================================
# Migration/admin endpoints removed — use backend/migrations/ scripts instead.
# =============================================================================
