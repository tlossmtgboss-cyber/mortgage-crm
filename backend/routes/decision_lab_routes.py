"""
Mortgage Decision Lab API Routes

Borrower-facing endpoints for:
- Confidence assessment and scoring
- Loan scenario creation and comparison
- Personalized recommendations
- Education content delivery

Based on the Borrower Confidence Manifesto.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from routes.auth_deps import require_auth
from services.confidence_engine_service import (
    ConfidenceEngineService,
    LoanScenarioService,
    get_confidence_engine,
    get_scenario_service
)

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

router = APIRouter(prefix="/api/v1/decision-lab", tags=["Decision Lab"], dependencies=[Depends(require_auth)])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class StartSessionRequest(BaseModel):
    borrower_profile_id: Optional[str] = None
    application_id: Optional[str] = None


class StartSessionResponse(BaseModel):
    session_id: str
    created_at: str


class SubmitResponseRequest(BaseModel):
    question_id: int
    response_value: dict
    confidence_level: int = Field(default=3, ge=1, le=5)
    time_to_answer_ms: int = 0


class CreateScenarioRequest(BaseModel):
    loan_amount: float
    purchase_price: float
    down_payment: float
    property_type: str = "single_family"
    occupancy_type: str = "primary"
    property_state: str = ""
    credit_score: int = 720
    is_baseline: bool = False


class CompareScenarioRequest(BaseModel):
    scenario_ids: List[int]


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@router.post("/sessions", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db)
):
    """
    Start a new Decision Lab session.

    A session tracks a borrower's journey through:
    - Confidence questions and responses
    - Loan scenarios created
    - Recommendations generated
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Log session start
    db.execute(text("""
        INSERT INTO confidence_interactions (
            session_id, borrower_profile_id, event_type, event_data, timestamp
        ) VALUES (
            :session_id, :borrower_profile_id, 'session_start',
            '{"source": "api"}'::jsonb, :timestamp
        )
    """), {
        "session_id": session_id,
        "borrower_profile_id": request.borrower_profile_id,
        "timestamp": now
    })
    db.commit()

    return StartSessionResponse(
        session_id=session_id,
        created_at=now.isoformat()
    )


@router.get("/sessions/{session_id}/progress")
async def get_session_progress(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get progress summary for a session."""

    # Count answered questions
    answered = db.execute(text("""
        SELECT COUNT(*) FROM confidence_responses WHERE session_id = :session_id
    """), {"session_id": session_id}).scalar()

    # Count total questions
    total = db.execute(text("""
        SELECT COUNT(*) FROM confidence_questions WHERE is_active = true
    """)).scalar()

    # Get latest score
    score = db.execute(text("""
        SELECT overall_score, readiness_level, calculated_at
        FROM confidence_scores
        WHERE session_id = :session_id
        ORDER BY calculated_at DESC
        LIMIT 1
    """), {"session_id": session_id}).fetchone()

    # Count scenarios
    scenarios = db.execute(text("""
        SELECT COUNT(*) FROM loan_scenarios WHERE session_id = :session_id
    """), {"session_id": session_id}).scalar()

    return {
        "session_id": session_id,
        "questions": {
            "answered": answered or 0,
            "total": total or 0,
            "progress_percent": round((answered / total) * 100, 1) if total > 0 else 0
        },
        "confidence": {
            "score": float(score[0]) if score else None,
            "readiness_level": score[1] if score else None,
            "last_calculated": score[2].isoformat() if score and score[2] else None
        },
        "scenarios_created": scenarios or 0
    }


# =============================================================================
# CONFIDENCE QUESTIONS
# =============================================================================

@router.get("/questions")
async def get_questions(
    session_id: str,
    category: Optional[str] = None,
    include_answered: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get confidence questions for a session.

    Questions are filtered based on:
    - Category (optional)
    - Whether already answered
    - Dependencies on previous answers
    """
    engine = get_confidence_engine(db)
    questions = engine.get_questions_for_session(
        session_id=session_id,
        category=category,
        include_answered=include_answered
    )

    return {
        "session_id": session_id,
        "category": category,
        "count": len(questions),
        "questions": questions
    }


@router.get("/questions/next")
async def get_next_question(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the next unanswered question in the adaptive flow.

    Returns the highest priority question that:
    - Has not been answered
    - Has all dependencies satisfied
    - Is active
    """
    engine = get_confidence_engine(db)
    question = engine.get_next_question(session_id=session_id)

    if not question:
        return {
            "session_id": session_id,
            "question": None,
            "message": "All questions answered",
            "next_step": "Calculate your confidence score"
        }

    # Get education overlay if available
    overlay = None
    if question.get("education_overlay_id"):
        overlay = engine.get_education_overlay(
            f"confidence_question:{question['code']}"
        )

    return {
        "session_id": session_id,
        "question": question,
        "education_overlay": overlay
    }


@router.post("/questions/respond")
async def submit_response(
    session_id: str,
    request: SubmitResponseRequest,
    borrower_profile_id: Optional[str] = None,
    application_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Submit a response to a confidence question.

    The response includes:
    - The answer value
    - Self-reported confidence level (1-5)
    - Time taken to answer (for analytics)
    """
    engine = get_confidence_engine(db)

    result = engine.save_response(
        session_id=session_id,
        question_id=request.question_id,
        response_value=request.response_value,
        confidence_level=request.confidence_level,
        time_to_answer_ms=request.time_to_answer_ms,
        borrower_profile_id=borrower_profile_id,
        application_id=application_id
    )

    # Get next question
    next_question = engine.get_next_question(session_id=session_id)

    return {
        "saved": True,
        "response_id": result["response_id"],
        "next_question": next_question,
        "has_more_questions": next_question is not None
    }


# =============================================================================
# CONFIDENCE SCORING
# =============================================================================

@router.post("/score")
async def calculate_score(
    session_id: str,
    borrower_profile_id: Optional[str] = None,
    application_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Calculate the confidence score based on all responses.

    Returns:
    - Overall score (0-100)
    - Category breakdown
    - Readiness level
    - Personalized recommendations
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        engine = get_confidence_engine(db)

        score = engine.calculate_confidence_score(
            session_id=session_id,
            borrower_profile_id=borrower_profile_id,
            application_id=application_id
        )

        return {
            "session_id": session_id,
            "overall_score": score.overall_score,
            "category_scores": score.category_scores,
            "readiness_level": score.readiness_level.value,
            "key_strengths": score.key_strengths,
            "areas_for_improvement": score.areas_for_improvement,
            "recommended_actions": score.recommended_actions
        }
    except Exception as e:
        logger.error(f"Score calculation error for session {session_id}: {str(e)}")
        # Re-raise with more details for debugging
        raise HTTPException(
            status_code=500,
            detail="Score calculation failed"
        )


@router.get("/score/{session_id}")
async def get_score(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get the most recent confidence score for a session."""

    result = db.execute(text("""
        SELECT overall_score, category_scores, readiness_level,
               key_strengths, areas_for_improvement, recommended_actions,
               calculated_at
        FROM confidence_scores
        WHERE session_id = :session_id
        ORDER BY calculated_at DESC
        LIMIT 1
    """), {"session_id": session_id}).fetchone()

    if not result:
        raise HTTPException(
            status_code=404,
            detail="No score found for this session. Complete the assessment first."
        )

    return {
        "session_id": session_id,
        "overall_score": float(result[0]) if result[0] else 0,
        "category_scores": result[1],
        "readiness_level": result[2],
        "key_strengths": result[3],
        "areas_for_improvement": result[4],
        "recommended_actions": result[5],
        "calculated_at": result[6].isoformat() if result[6] else None
    }


# =============================================================================
# LOAN SCENARIOS
# =============================================================================

@router.post("/scenarios")
async def create_scenario(
    session_id: str,
    request: CreateScenarioRequest,
    borrower_profile_id: Optional[str] = None,
    application_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Create a new loan scenario.

    A scenario represents a potential loan situation with:
    - Property price and down payment
    - Credit profile
    - Property characteristics
    """
    service = get_scenario_service(db)

    scenario = service.create_scenario(
        session_id=session_id,
        loan_amount=Decimal(str(request.loan_amount)),
        purchase_price=Decimal(str(request.purchase_price)),
        down_payment=Decimal(str(request.down_payment)),
        property_type=request.property_type,
        occupancy_type=request.occupancy_type,
        property_state=request.property_state,
        credit_score=request.credit_score,
        borrower_profile_id=borrower_profile_id,
        application_id=application_id,
        is_baseline=request.is_baseline
    )

    return {
        "created": True,
        "scenario": scenario
    }


@router.get("/scenarios")
async def list_scenarios(
    session_id: str,
    db: Session = Depends(get_db)
):
    """List all scenarios for a session."""

    results = db.execute(text("""
        SELECT id, name, scenario_type, loan_amount, purchase_price,
               down_payment, down_payment_percent, property_type,
               credit_score, ltv_ratio, is_baseline, is_favorite,
               created_at
        FROM loan_scenarios
        WHERE session_id = :session_id
        ORDER BY created_at DESC
    """), {"session_id": session_id}).fetchall()

    scenarios = []
    for r in results:
        scenarios.append({
            "id": r[0],
            "scenario_id": r[0],  # Include both for frontend compatibility
            "name": r[1],
            "scenario_type": r[2],
            "loan_amount": float(r[3]) if r[3] else 0,
            "purchase_price": float(r[4]) if r[4] else 0,
            "down_payment": float(r[5]) if r[5] else 0,
            "down_payment_percent": float(r[6]) if r[6] else 0,
            "property_type": r[7],
            "credit_score": r[8],
            "ltv_ratio": float(r[9]) if r[9] else 0,
            "is_baseline": r[10],
            "is_favorite": r[11],
            "created_at": r[12].isoformat() if r[12] else None
        })

    return {
        "session_id": session_id,
        "count": len(scenarios),
        "scenarios": scenarios
    }


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific scenario with its loan options."""

    scenario = db.execute(text("""
        SELECT id, session_id, name, scenario_type, loan_amount, purchase_price,
               down_payment, down_payment_percent, property_type, occupancy_type,
               property_state, credit_score, ltv_ratio, is_baseline, is_favorite,
               created_at
        FROM loan_scenarios
        WHERE id = :scenario_id
    """), {"scenario_id": scenario_id}).fetchone()

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Get loan options
    options = db.execute(text("""
        SELECT id, product_type, product_name, interest_rate, apr, term_months,
               monthly_payment, monthly_pi, monthly_taxes, monthly_insurance,
               monthly_pmi, closing_costs, total_cash_to_close, total_interest_paid,
               pros, cons, rank, is_recommended, recommendation_reasons
        FROM loan_options
        WHERE scenario_id = :scenario_id
        ORDER BY rank ASC
    """), {"scenario_id": scenario_id}).fetchall()

    option_list = []
    for o in options:
        option_list.append({
            "id": o[0],
            "product_type": o[1],
            "product_name": o[2],
            "interest_rate": float(o[3]) if o[3] else 0,
            "apr": float(o[4]) if o[4] else 0,
            "term_months": o[5],
            "monthly_payment": float(o[6]) if o[6] else 0,
            "monthly_pi": float(o[7]) if o[7] else 0,
            "monthly_taxes": float(o[8]) if o[8] else 0,
            "monthly_insurance": float(o[9]) if o[9] else 0,
            "monthly_pmi": float(o[10]) if o[10] else 0,
            "closing_costs": float(o[11]) if o[11] else 0,
            "total_cash_to_close": float(o[12]) if o[12] else 0,
            "total_interest_paid": float(o[13]) if o[13] else 0,
            "pros": o[14],
            "cons": o[15],
            "rank": o[16],
            "is_recommended": o[17],
            "recommendation_reasons": o[18]
        })

    return {
        "scenario": {
            "id": scenario[0],
            "session_id": scenario[1],
            "name": scenario[2],
            "scenario_type": scenario[3],
            "loan_amount": float(scenario[4]) if scenario[4] else 0,
            "purchase_price": float(scenario[5]) if scenario[5] else 0,
            "down_payment": float(scenario[6]) if scenario[6] else 0,
            "down_payment_percent": float(scenario[7]) if scenario[7] else 0,
            "property_type": scenario[8],
            "occupancy_type": scenario[9],
            "property_state": scenario[10],
            "credit_score": scenario[11],
            "ltv_ratio": float(scenario[12]) if scenario[12] else 0,
            "is_baseline": scenario[13],
            "is_favorite": scenario[14],
            "created_at": scenario[15].isoformat() if scenario[15] else None
        },
        "options": option_list
    }


@router.post("/scenarios/{scenario_id}/calculate")
async def calculate_loan_options(
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Calculate available loan options for a scenario.

    Generates multiple loan products with:
    - Payment breakdowns
    - Rate comparisons
    - Pros/cons analysis
    - Recommendations
    """
    service = get_scenario_service(db)
    options = service.calculate_loan_options(scenario_id)

    return {
        "scenario_id": scenario_id,
        "options_count": len(options),
        "options": options
    }


@router.post("/scenarios/compare")
async def compare_scenarios(
    request: CompareScenarioRequest,
    db: Session = Depends(get_db)
):
    """
    Compare multiple scenarios side-by-side.

    Analyzes differences in:
    - Monthly payments
    - Total costs
    - Cash to close
    - Long-term implications
    """
    if len(request.scenario_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 scenarios required for comparison"
        )

    scenarios = []
    for sid in request.scenario_ids:
        result = db.execute(text("""
            SELECT s.id, s.name, s.loan_amount, s.down_payment, s.purchase_price, s.credit_score,
                   o.monthly_payment, o.total_interest_paid, o.total_cash_to_close,
                   o.product_name, o.interest_rate
            FROM loan_scenarios s
            LEFT JOIN loan_options o ON o.scenario_id = s.id AND o.is_recommended = true
            WHERE s.id = :scenario_id
        """), {"scenario_id": sid}).fetchone()

        if result:
            scenarios.append({
                "id": result[0],
                "scenario_id": result[0],  # Include both for frontend compatibility
                "name": result[1] or f"Scenario {result[0]}",
                "loan_amount": float(result[2]) if result[2] else 0,
                "down_payment": float(result[3]) if result[3] else 0,
                "purchase_price": float(result[4]) if result[4] else 0,
                "credit_score": result[5] or 0,
                "monthly_payment": float(result[6]) if result[6] else 0,
                "total_interest": float(result[7]) if result[7] else 0,
                "cash_to_close": float(result[8]) if result[8] else 0,
                "product": result[9],
                "rate": float(result[10]) if result[10] else 0
            })

    # Calculate differences
    if len(scenarios) >= 2:
        base = scenarios[0]
        for s in scenarios[1:]:
            s["payment_diff"] = s["monthly_payment"] - base["monthly_payment"]
            s["interest_diff"] = s["total_interest"] - base["total_interest"]
            s["cash_diff"] = s["cash_to_close"] - base["cash_to_close"]

    # Determine winner
    winner = min(scenarios, key=lambda x: x["monthly_payment"])

    return {
        "scenarios": scenarios,
        "winner": {
            "id": winner["id"],
            "name": winner["name"],
            "reason": "Lowest monthly payment"
        },
        "summary": {
            "payment_range": {
                "min": min(s["monthly_payment"] for s in scenarios),
                "max": max(s["monthly_payment"] for s in scenarios)
            },
            "interest_range": {
                "min": min(s["total_interest"] for s in scenarios),
                "max": max(s["total_interest"] for s in scenarios)
            }
        }
    }


# =============================================================================
# EDUCATION CONTENT
# =============================================================================

@router.get("/education/overlay")
async def get_education_overlay(
    context: str,
    db: Session = Depends(get_db)
):
    """
    Get education overlay for a specific context.

    Overlays provide contextual learning during the journey.
    """
    engine = get_confidence_engine(db)
    overlay = engine.get_education_overlay(trigger_context=context)

    if not overlay:
        return {"overlay": None, "message": "No overlay for this context"}

    return {"overlay": overlay}


@router.get("/education/overlays")
async def list_overlays(
    db: Session = Depends(get_db)
):
    """List all education overlays."""
    results = db.execute(text("""
        SELECT id, title, content, trigger_type, trigger_value, category,
               formula, example, tip, key_takeaway, is_active, display_order,
               created_at, updated_at
        FROM education_overlays
        ORDER BY display_order, id
    """)).fetchall()

    overlays = []
    for r in results:
        overlays.append({
            "id": r[0],
            "title": r[1],
            "content": r[2],
            "trigger_type": r[3],
            "trigger_value": r[4],
            "category": r[5],
            "formula": r[6],
            "example": r[7],
            "tip": r[8],
            "key_takeaway": r[9],
            "is_active": r[10],
            "display_order": r[11],
            "created_at": r[12].isoformat() if r[12] else None,
            "updated_at": r[13].isoformat() if r[13] else None
        })

    return {"overlays": overlays, "count": len(overlays)}


@router.get("/education/overlay/{overlay_id}")
async def get_overlay_by_id(
    overlay_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific education overlay by ID."""
    result = db.execute(text("""
        SELECT id, title, content, trigger_type, trigger_value, category,
               formula, example, tip, key_takeaway, is_active, display_order
        FROM education_overlays
        WHERE id = :overlay_id
    """), {"overlay_id": overlay_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Overlay not found")

    return {
        "id": result[0],
        "title": result[1],
        "content": result[2],
        "trigger_type": result[3],
        "trigger_value": result[4],
        "category": result[5],
        "formula": result[6],
        "example": result[7],
        "tip": result[8],
        "key_takeaway": result[9],
        "is_active": result[10],
        "display_order": result[11]
    }


@router.post("/education/overlay")
async def create_overlay(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new education overlay (admin only)."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    data = await request.json()

    result = db.execute(text("""
        INSERT INTO education_overlays
        (title, content, trigger_type, trigger_value, category, formula,
         example, tip, key_takeaway, is_active, display_order, created_at)
        VALUES
        (:title, :content, :trigger_type, :trigger_value, :category, :formula,
         :example, :tip, :key_takeaway, :is_active, :display_order, NOW())
        RETURNING id
    """), {
        "title": data.get("title"),
        "content": data.get("content"),
        "trigger_type": data.get("trigger_type", "question"),
        "trigger_value": data.get("trigger_value"),
        "category": data.get("category"),
        "formula": data.get("formula"),
        "example": data.get("example"),
        "tip": data.get("tip"),
        "key_takeaway": data.get("key_takeaway"),
        "is_active": data.get("is_active", True),
        "display_order": data.get("display_order", 0)
    })
    db.commit()

    new_id = result.fetchone()[0]
    return {"message": "Overlay created", "id": new_id}


@router.put("/education/overlay/{overlay_id}")
async def update_overlay(
    overlay_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an existing education overlay (admin only)."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    data = await request.json()

    # Check if overlay exists
    existing = db.execute(text(
        "SELECT id FROM education_overlays WHERE id = :id"
    ), {"id": overlay_id}).fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Overlay not found")

    db.execute(text("""
        UPDATE education_overlays SET
            title = :title,
            content = :content,
            trigger_type = :trigger_type,
            trigger_value = :trigger_value,
            category = :category,
            formula = :formula,
            example = :example,
            tip = :tip,
            key_takeaway = :key_takeaway,
            is_active = :is_active,
            display_order = :display_order,
            updated_at = NOW()
        WHERE id = :overlay_id
    """), {
        "overlay_id": overlay_id,
        "title": data.get("title"),
        "content": data.get("content"),
        "trigger_type": data.get("trigger_type"),
        "trigger_value": data.get("trigger_value"),
        "category": data.get("category"),
        "formula": data.get("formula"),
        "example": data.get("example"),
        "tip": data.get("tip"),
        "key_takeaway": data.get("key_takeaway"),
        "is_active": data.get("is_active", True),
        "display_order": data.get("display_order", 0)
    })
    db.commit()

    return {"message": "Overlay updated", "id": overlay_id}


@router.delete("/education/overlay/{overlay_id}")
async def delete_overlay(
    overlay_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Delete an education overlay (admin only)."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)
    # Check if overlay exists
    existing = db.execute(text(
        "SELECT id FROM education_overlays WHERE id = :id"
    ), {"id": overlay_id}).fetchone()

    if not existing:
        raise HTTPException(status_code=404, detail="Overlay not found")

    db.execute(text(
        "DELETE FROM education_overlays WHERE id = :id"
    ), {"id": overlay_id})
    db.commit()

    return {"message": "Overlay deleted", "id": overlay_id}


@router.get("/education/lessons")
async def list_lessons(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List available education lessons."""

    params = {}
    category_filter = ""
    if category:
        category_filter = "WHERE category = :category"
        params["category"] = category

    results = db.execute(text(f"""
        SELECT id, code, category, title, summary,
               difficulty_level, estimated_minutes, display_order
        FROM education_lessons
        WHERE is_active = true
        {category_filter}
        ORDER BY display_order, id
    """), params).fetchall()

    lessons = []
    for r in results:
        lessons.append({
            "id": r[0],
            "code": r[1],
            "category": r[2],
            "title": r[3],
            "summary": r[4],
            "difficulty": r[5],
            "estimated_minutes": r[6]
        })

    return {
        "count": len(lessons),
        "lessons": lessons
    }


@router.get("/education/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific lesson with full content."""

    result = db.execute(text("""
        SELECT id, code, category, title, summary, content,
               difficulty_level, estimated_minutes, prerequisites
        FROM education_lessons
        WHERE id = :lesson_id AND is_active = true
    """), {"lesson_id": lesson_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Get quiz questions
    questions = db.execute(text("""
        SELECT id, question_text, question_type, options, display_order
        FROM education_quiz_questions
        WHERE lesson_id = :lesson_id AND is_active = true
        ORDER BY display_order
    """), {"lesson_id": lesson_id}).fetchall()

    quiz = []
    for q in questions:
        quiz.append({
            "id": q[0],
            "question": q[1],
            "type": q[2],
            "options": q[3],
            "order": q[4]
        })

    return {
        "lesson": {
            "id": result[0],
            "code": result[1],
            "category": result[2],
            "title": result[3],
            "summary": result[4],
            "content": result[5],
            "difficulty": result[6],
            "estimated_minutes": result[7],
            "prerequisites": result[8]
        },
        "quiz": quiz
    }


# =============================================================================
# ANALYTICS & TRACKING
# =============================================================================

# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.post("/admin/seed-questions")
async def seed_questions(
    request: Request,
    db: Session = Depends(get_db)
):
    """Seed initial confidence questions and education content (admin only)."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)

    try:
        from migrations.add_borrower_confidence_engine import seed_initial_data
        seed_initial_data(db)

        # Get counts
        question_count = db.execute(text("SELECT COUNT(*) FROM confidence_questions")).scalar()
        overlay_count = db.execute(text("SELECT COUNT(*) FROM education_overlays")).scalar()

        return {
            "success": True,
            "questions_seeded": question_count,
            "overlays_seeded": overlay_count
        }
    except SQLAlchemyError as e:
        logger.error(f"Seed error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/debug-tables")
async def debug_tables(
    request: Request,
    db: Session = Depends(get_db)
):
    """Debug endpoint to check table state (admin only)."""
    import json
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)

    result = {"errors": []}

    try:
        # Check if table exists and count rows
        questions_count = db.execute(text(
            "SELECT COUNT(*) FROM confidence_questions"
        )).scalar()
        result["questions_count"] = questions_count

        overlays_count = db.execute(text(
            "SELECT COUNT(*) FROM education_overlays"
        )).scalar()
        result["overlays_count"] = overlays_count

        # Get first few questions
        sample_questions = db.execute(text(
            "SELECT id, code, question_text FROM confidence_questions LIMIT 3"
        )).fetchall()
        result["sample_questions"] = [{"id": q[0], "code": q[1], "text": q[2][:50]} for q in sample_questions]

    except SQLAlchemyError as e:
        result["errors"].append(f"Table query error: {str(e)}")

    # Try to insert a test question directly
    try:
        test_options = json.dumps({"min": 1, "max": 5})
        db.execute(text("""
            INSERT INTO confidence_questions (
                code, category, question_text, question_type, options, is_active
            ) VALUES (
                :code, :category, :question_text, :question_type, :options::jsonb, true
            ) ON CONFLICT (code) DO UPDATE SET
                question_text = EXCLUDED.question_text
        """), {
            "code": "TEST_QUESTION",
            "category": "test",
            "question_text": "This is a test question",
            "question_type": "scale",
            "options": test_options
        })
        db.commit()
        result["test_insert"] = "success"

        # Verify it was inserted
        new_count = db.execute(text("SELECT COUNT(*) FROM confidence_questions")).scalar()
        result["new_count"] = new_count

    except SQLAlchemyError as e:
        import traceback
        logger.error(f"Decision lab test insert error: {traceback.format_exc()}")
        result["test_insert_error"] = "Database error"

    return result


@router.post("/admin/run-migration")
async def run_migration(
    request: Request,
    db: Session = Depends(get_db)
):
    """Run the Borrower Confidence Engine migration (admin only)."""
    from auth.dependencies import get_current_user_flexible
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)

    try:
        from migrations.add_borrower_confidence_engine import run_migration as do_migration, seed_initial_data

        # Run migration
        logger.info("Running migration...")
        do_migration(db)
        logger.info("Migration complete, running seed...")

        # Run seeding
        seed_initial_data(db)
        logger.info("Seeding complete")

        # Verify counts
        q_count = db.execute(text("SELECT COUNT(*) FROM confidence_questions")).scalar()
        o_count = db.execute(text("SELECT COUNT(*) FROM education_overlays")).scalar()

        return {
            "success": True,
            "message": "Migration and seeding completed",
            "questions_count": q_count,
            "overlays_count": o_count
        }
    except SQLAlchemyError as e:
        logger.error(f"Migration error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/track")
async def track_interaction(
    session_id: str,
    event_type: str,
    event_data: Optional[dict] = None,
    page_context: Optional[str] = None,
    element_id: Optional[str] = None,
    borrower_profile_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Track a user interaction for analytics."""
    import json

    db.execute(text("""
        INSERT INTO confidence_interactions (
            session_id, borrower_profile_id, event_type,
            event_data, page_context, element_id, timestamp
        ) VALUES (
            :session_id, :borrower_profile_id, :event_type,
            :event_data, :page_context, :element_id, :timestamp
        )
    """), {
        "session_id": session_id,
        "borrower_profile_id": borrower_profile_id,
        "event_type": event_type,
        "event_data": json.dumps(event_data) if event_data else None,
        "page_context": page_context,
        "element_id": element_id,
        "timestamp": datetime.now(timezone.utc)
    })
    db.commit()

    return {"tracked": True}
