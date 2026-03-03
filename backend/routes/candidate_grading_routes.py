"""
Candidate Grading API Routes
Endpoints for LO candidate assessment and grading operations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from database import get_db
from services.candidate_grading_service import CandidateGradingService
from auth.dependencies import get_current_user
from database.models import User
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recruiting/candidates", tags=["Candidate Grading"])


def _verify_candidate_org(db: Session, candidate_id: int, organization_id: int):
    """Verify candidate belongs to the caller's organization."""
    row = db.execute(text("""
        SELECT id FROM mm_candidates
        WHERE id = :id AND organization_id = :org_id AND is_active = true
    """), {"id": candidate_id, "org_id": organization_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class DISCScoresRequest(BaseModel):
    """DISC personality scores."""
    d_score: int = Field(ge=0, le=100, description="Dominance score 0-100")
    i_score: int = Field(ge=0, le=100, description="Influence score 0-100")
    s_score: int = Field(ge=0, le=100, description="Steadiness score 0-100")
    c_score: int = Field(ge=0, le=100, description="Conscientiousness score 0-100")
    notes: Optional[str] = None
    assessment_source: Optional[str] = "manual"  # manual, ai_inferred, formal_assessment


class CharacterBreakdownRequest(BaseModel):
    """Character assessment breakdown."""
    integrity_score: int = Field(ge=0, le=100)
    coachability_score: int = Field(ge=0, le=100)
    resilience_score: int = Field(ge=0, le=100)
    work_ethic_score: int = Field(ge=0, le=100)
    notes: Optional[str] = None


class SkillsBreakdownRequest(BaseModel):
    """Skills assessment breakdown."""
    technical_score: int = Field(ge=0, le=100)
    product_knowledge_score: int = Field(ge=0, le=100)
    market_expertise_score: int = Field(ge=0, le=100)
    technology_proficiency_score: int = Field(ge=0, le=100)
    identified_skills: Optional[List[str]] = []
    skill_gaps: Optional[List[str]] = []
    notes: Optional[str] = None


class CultureFitBreakdownRequest(BaseModel):
    """Culture fit assessment breakdown."""
    values_alignment_score: int = Field(ge=0, le=100)
    team_compatibility_score: int = Field(ge=0, le=100)
    communication_style_score: int = Field(ge=0, le=100)
    growth_mindset_score: int = Field(ge=0, le=100)
    notes: Optional[str] = None


class ProductionBreakdownRequest(BaseModel):
    """Production data for scoring."""
    annual_volume: Optional[float] = None
    annual_units: Optional[int] = None
    production_history: Optional[Dict] = None


class CreateAssessmentRequest(BaseModel):
    """Request to create a new assessment."""
    # Production
    production_score: Optional[float] = None
    production_breakdown: Optional[ProductionBreakdownRequest] = None

    # DISC
    disc_d_score: Optional[int] = Field(None, ge=0, le=100)
    disc_i_score: Optional[int] = Field(None, ge=0, le=100)
    disc_s_score: Optional[int] = Field(None, ge=0, le=100)
    disc_c_score: Optional[int] = Field(None, ge=0, le=100)
    disc_notes: Optional[str] = None
    disc_assessment_source: Optional[str] = "manual"

    # Character
    character_score: Optional[float] = None
    character_breakdown: Optional[CharacterBreakdownRequest] = None

    # Skills
    skills_score: Optional[float] = None
    skills_breakdown: Optional[SkillsBreakdownRequest] = None

    # Culture Fit
    culture_fit_score: Optional[float] = None
    culture_fit_breakdown: Optional[CultureFitBreakdownRequest] = None

    # Qualitative
    strengths: Optional[List[str]] = []
    weaknesses: Optional[List[str]] = []
    recruiter_notes: Optional[str] = None
    recruiter_recommendation: Optional[str] = None  # strong_hire, hire, maybe, no_hire, strong_no_hire

    # Status
    assessment_status: Optional[str] = "draft"


class UpdateAssessmentRequest(BaseModel):
    """Request to update an existing assessment."""
    # All fields optional for partial updates
    production_score: Optional[float] = None
    production_breakdown: Optional[Dict] = None

    disc_d_score: Optional[int] = Field(None, ge=0, le=100)
    disc_i_score: Optional[int] = Field(None, ge=0, le=100)
    disc_s_score: Optional[int] = Field(None, ge=0, le=100)
    disc_c_score: Optional[int] = Field(None, ge=0, le=100)
    disc_notes: Optional[str] = None

    character_score: Optional[float] = None
    character_breakdown: Optional[Dict] = None

    skills_score: Optional[float] = None
    skills_breakdown: Optional[Dict] = None

    culture_fit_score: Optional[float] = None
    culture_fit_breakdown: Optional[Dict] = None

    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    recruiter_notes: Optional[str] = None
    recruiter_recommendation: Optional[str] = None
    assessment_status: Optional[str] = None


class OverrideRequest(BaseModel):
    """Request to override AI-suggested scores."""
    override_reason: str = Field(..., min_length=10, description="Reason for override (min 10 chars)")
    production_score: Optional[float] = None
    disc_composite_score: Optional[float] = None
    character_score: Optional[float] = None
    skills_score: Optional[float] = None
    culture_fit_score: Optional[float] = None


# =============================================================================
# ASSESSMENT ENDPOINTS
# =============================================================================

@router.get("/{candidate_id}/assessment")
async def get_candidate_assessment(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get the current assessment for a candidate.

    Returns all scoring categories, grades, and breakdown details.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)
        assessment = await service.get_assessment(candidate_id)

        if not assessment:
            return {
                "candidate_id": candidate_id,
                "has_assessment": False,
                "message": "No assessment found for this candidate"
            }

        return {
            "candidate_id": candidate_id,
            "has_assessment": True,
            **assessment
        }

    except Exception as e:
        logger.exception(f"Error getting assessment for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{candidate_id}/assessment")
async def create_candidate_assessment(
    candidate_id: int,
    request: CreateAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a new assessment for a candidate.

    Calculates grades for each category and overall grade based on weights.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        # Convert request to dict, handling nested models
        data = request.model_dump(exclude_none=True)
        if request.production_breakdown:
            data['production_breakdown'] = request.production_breakdown.model_dump()
        if request.character_breakdown:
            data['character_breakdown'] = request.character_breakdown.model_dump()
        if request.skills_breakdown:
            data['skills_breakdown'] = request.skills_breakdown.model_dump()
        if request.culture_fit_breakdown:
            data['culture_fit_breakdown'] = request.culture_fit_breakdown.model_dump()

        result = await service.create_assessment(
            candidate_id=candidate_id,
            organization_id=current_user.organization_id,
            assessed_by=current_user.id,
            data=data
        )

        return result

    except Exception as e:
        logger.exception(f"Error creating assessment for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{candidate_id}/assessment")
async def update_candidate_assessment(
    candidate_id: int,
    request: UpdateAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update an existing assessment.

    Partial updates are supported - only provided fields are updated.
    Grades are recalculated automatically.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        # Get current assessment ID
        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found for this candidate")

        data = request.model_dump(exclude_none=True)

        result = await service.update_assessment(
            assessment_id=current['id'],
            data=data,
            updated_by=current_user.id
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating assessment for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{candidate_id}/assessment/history")
async def get_assessment_history(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get assessment history for a candidate.

    Shows all score changes over time with who made them and why.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)
        history = await service.get_assessment_history(candidate_id)

        return {
            "candidate_id": candidate_id,
            "history": history,
            "count": len(history)
        }

    except Exception as e:
        logger.exception(f"Error getting assessment history for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{candidate_id}/assessment/breakdown")
async def get_assessment_breakdown(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed breakdown of how the overall grade was calculated.

    Shows each category's contribution to the final score.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)
        assessment = await service.get_assessment(candidate_id)

        if not assessment:
            raise HTTPException(status_code=404, detail="No assessment found")

        # Calculate contribution of each category
        production_contribution = (assessment['production']['score'] or 0) * 0.45
        disc_contribution = (assessment['disc']['composite_score'] or 0) * 0.20
        character_contribution = (assessment['character']['score'] or 0) * 0.15
        skills_contribution = (assessment['skills']['score'] or 0) * 0.10
        culture_contribution = (assessment['culture_fit']['score'] or 0) * 0.10

        return {
            "candidate_id": candidate_id,
            "overall_score": assessment['overall']['score'],
            "overall_grade": assessment['overall']['grade'],
            "breakdown": {
                "production": {
                    "score": assessment['production']['score'],
                    "grade": assessment['production']['grade'],
                    "weight": 0.45,
                    "contribution": round(production_contribution, 2),
                    "percentage_of_total": round((production_contribution / (assessment['overall']['score'] or 1)) * 100, 1)
                },
                "disc": {
                    "score": assessment['disc']['composite_score'],
                    "grade": assessment['disc']['grade'],
                    "weight": 0.20,
                    "contribution": round(disc_contribution, 2),
                    "percentage_of_total": round((disc_contribution / (assessment['overall']['score'] or 1)) * 100, 1)
                },
                "character": {
                    "score": assessment['character']['score'],
                    "grade": assessment['character']['grade'],
                    "weight": 0.15,
                    "contribution": round(character_contribution, 2),
                    "percentage_of_total": round((character_contribution / (assessment['overall']['score'] or 1)) * 100, 1)
                },
                "skills": {
                    "score": assessment['skills']['score'],
                    "grade": assessment['skills']['grade'],
                    "weight": 0.10,
                    "contribution": round(skills_contribution, 2),
                    "percentage_of_total": round((skills_contribution / (assessment['overall']['score'] or 1)) * 100, 1)
                },
                "culture_fit": {
                    "score": assessment['culture_fit']['score'],
                    "grade": assessment['culture_fit']['grade'],
                    "weight": 0.10,
                    "contribution": round(culture_contribution, 2),
                    "percentage_of_total": round((culture_contribution / (assessment['overall']['score'] or 1)) * 100, 1)
                }
            },
            "formula": "Overall = (Production × 0.45) + (DISC × 0.20) + (Character × 0.15) + (Skills × 0.10) + (Culture × 0.10)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting assessment breakdown for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CATEGORY-SPECIFIC UPDATE ENDPOINTS
# =============================================================================

@router.put("/{candidate_id}/assessment/disc")
async def update_disc_scores(
    candidate_id: int,
    request: DISCScoresRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update DISC personality scores.

    Recalculates composite score using LO-optimized weights:
    - Influence: 40%
    - Dominance: 30%
    - Steadiness: 15%
    - Conscientiousness: 15%
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found")

        # Calculate new DISC composite
        disc_result = service.calculate_disc_composite(
            request.d_score,
            request.i_score,
            request.s_score,
            request.c_score
        )

        result = await service.update_assessment(
            assessment_id=current['id'],
            data={
                'disc_d_score': request.d_score,
                'disc_i_score': request.i_score,
                'disc_s_score': request.s_score,
                'disc_c_score': request.c_score,
                'disc_primary_style': disc_result.primary_style,
                'disc_secondary_style': disc_result.secondary_style,
                'disc_composite_score': disc_result.composite_score,
                'disc_grade': disc_result.grade,
                'disc_notes': request.notes,
                'disc_assessment_source': request.assessment_source
            },
            updated_by=current_user.id
        )

        return {
            **result,
            "disc": {
                "d_score": request.d_score,
                "i_score": request.i_score,
                "s_score": request.s_score,
                "c_score": request.c_score,
                "composite_score": disc_result.composite_score,
                "grade": disc_result.grade,
                "primary_style": disc_result.primary_style,
                "secondary_style": disc_result.secondary_style
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating DISC scores for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{candidate_id}/assessment/character")
async def update_character_scores(
    candidate_id: int,
    request: CharacterBreakdownRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update character assessment scores.

    Components (equal weight):
    - Integrity
    - Coachability
    - Resilience
    - Work Ethic
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found")

        breakdown = request.model_dump()
        char_result = service.calculate_character_score(breakdown)

        result = await service.update_assessment(
            assessment_id=current['id'],
            data={
                'character_breakdown': breakdown,
                'character_score': char_result.score,
                'character_grade': char_result.grade
            },
            updated_by=current_user.id
        )

        return {
            **result,
            "character": {
                "score": char_result.score,
                "grade": char_result.grade,
                "breakdown": breakdown
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating character scores for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{candidate_id}/assessment/skills")
async def update_skills_scores(
    candidate_id: int,
    request: SkillsBreakdownRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update skills assessment scores.

    Components (equal weight):
    - Technical proficiency
    - Product knowledge
    - Market expertise
    - Technology proficiency
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found")

        breakdown = request.model_dump()
        skills_result = service.calculate_skills_score(breakdown)

        result = await service.update_assessment(
            assessment_id=current['id'],
            data={
                'skills_breakdown': breakdown,
                'skills_score': skills_result.score,
                'skills_grade': skills_result.grade
            },
            updated_by=current_user.id
        )

        return {
            **result,
            "skills": {
                "score": skills_result.score,
                "grade": skills_result.grade,
                "breakdown": breakdown
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating skills scores for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{candidate_id}/assessment/culture-fit")
async def update_culture_fit_scores(
    candidate_id: int,
    request: CultureFitBreakdownRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update culture fit assessment scores.

    Components (equal weight):
    - Values alignment
    - Team compatibility
    - Communication style
    - Growth mindset
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found")

        breakdown = request.model_dump()
        culture_result = service.calculate_culture_fit_score(breakdown)

        result = await service.update_assessment(
            assessment_id=current['id'],
            data={
                'culture_fit_breakdown': breakdown,
                'culture_fit_score': culture_result.score,
                'culture_fit_grade': culture_result.grade
            },
            updated_by=current_user.id
        )

        return {
            **result,
            "culture_fit": {
                "score": culture_result.score,
                "grade": culture_result.grade,
                "breakdown": breakdown
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating culture fit scores for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# OVERRIDE ENDPOINT
# =============================================================================

@router.put("/{candidate_id}/assessment/override")
async def override_assessment_scores(
    candidate_id: int,
    request: OverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Override AI-suggested or calculated scores with manual values.

    Requires a reason for the override (min 10 characters).
    Original scores are preserved in history.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        service = CandidateGradingService(db)

        current = await service.get_assessment(candidate_id)
        if not current:
            raise HTTPException(status_code=404, detail="No assessment found")

        new_scores = {}
        if request.production_score is not None:
            new_scores['production_score'] = request.production_score
        if request.disc_composite_score is not None:
            new_scores['disc_composite_score'] = request.disc_composite_score
        if request.character_score is not None:
            new_scores['character_score'] = request.character_score
        if request.skills_score is not None:
            new_scores['skills_score'] = request.skills_score
        if request.culture_fit_score is not None:
            new_scores['culture_fit_score'] = request.culture_fit_score

        result = await service.override_scores(
            assessment_id=current['id'],
            override_by=current_user.id,
            override_reason=request.override_reason,
            new_scores=new_scores
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error overriding scores for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/grading/weights")
async def get_grading_weights(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get the current grading weights and thresholds.

    Useful for frontend display and documentation.
    """
    return {
        "category_weights": {
            "production": {"weight": 0.45, "description": "Volume, units, consistency, growth trend"},
            "disc": {"weight": 0.20, "description": "DISC personality profile for LO role fit"},
            "character": {"weight": 0.15, "description": "Integrity, coachability, resilience, work ethic"},
            "skills": {"weight": 0.10, "description": "Technical, product knowledge, market expertise"},
            "culture_fit": {"weight": 0.10, "description": "Values alignment, team compatibility"}
        },
        "disc_weights": {
            "D": {"weight": 0.30, "label": "Dominance", "description": "Drive to close deals"},
            "I": {"weight": 0.40, "label": "Influence", "description": "Relationship building (most important for LO)"},
            "S": {"weight": 0.15, "label": "Steadiness", "description": "Process follow-through"},
            "C": {"weight": 0.15, "label": "Conscientiousness", "description": "Compliance and detail orientation"}
        },
        "grade_thresholds": [
            {"min": 95, "grade": "A+", "color": "#10b981"},
            {"min": 90, "grade": "A", "color": "#10b981"},
            {"min": 85, "grade": "A-", "color": "#22c55e"},
            {"min": 80, "grade": "B+", "color": "#84cc16"},
            {"min": 75, "grade": "B", "color": "#84cc16"},
            {"min": 70, "grade": "B-", "color": "#eab308"},
            {"min": 65, "grade": "C+", "color": "#f59e0b"},
            {"min": 60, "grade": "C", "color": "#f59e0b"},
            {"min": 55, "grade": "C-", "color": "#f97316"},
            {"min": 50, "grade": "D", "color": "#ef4444"},
            {"min": 0, "grade": "F", "color": "#dc2626"}
        ],
        "recommendations": [
            {"value": "strong_hire", "label": "Strong Hire", "description": "Exceptional candidate, prioritize"},
            {"value": "hire", "label": "Hire", "description": "Good candidate, recommend proceeding"},
            {"value": "maybe", "label": "Maybe", "description": "Has potential but concerns exist"},
            {"value": "no_hire", "label": "No Hire", "description": "Does not meet requirements"},
            {"value": "strong_no_hire", "label": "Strong No Hire", "description": "Significant concerns, do not proceed"}
        ]
    }


@router.post("/grading/calculate-preview")
async def calculate_grade_preview(
    production_score: Optional[float] = Query(None, ge=0, le=100),
    disc_score: Optional[float] = Query(None, ge=0, le=100),
    character_score: Optional[float] = Query(None, ge=0, le=100),
    skills_score: Optional[float] = Query(None, ge=0, le=100),
    culture_fit_score: Optional[float] = Query(None, ge=0, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Preview what overall grade would result from given scores.

    Useful for "what-if" scenarios when adjusting scores.
    """
    service = CandidateGradingService(db)

    result = service.calculate_overall_grade(
        production_score,
        disc_score,
        character_score,
        skills_score,
        culture_fit_score
    )

    return {
        "inputs": {
            "production": production_score,
            "disc": disc_score,
            "character": character_score,
            "skills": skills_score,
            "culture_fit": culture_fit_score
        },
        "result": {
            "overall_score": result.score,
            "overall_grade": result.grade,
            "color": result.color
        },
        "contributions": {
            "production": round((production_score or 0) * 0.45, 2),
            "disc": round((disc_score or 0) * 0.20, 2),
            "character": round((character_score or 0) * 0.15, 2),
            "skills": round((skills_score or 0) * 0.10, 2),
            "culture_fit": round((culture_fit_score or 0) * 0.10, 2)
        }
    }


# =============================================================================
# ADMIN/MIGRATION ENDPOINT
# =============================================================================

@router.post("/grading/run-migration")
async def run_grading_migration(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Run the candidate grading system migration.

    Creates tables for mm_candidate_assessments and mm_assessment_history.
    Requires admin role.
    """
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from sqlalchemy import text

        migration_sql = """
        -- Check if table exists
        DO $$
        BEGIN
            -- Create mm_candidate_assessments if not exists
            IF NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'mm_candidate_assessments') THEN
                CREATE TABLE mm_candidate_assessments (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    candidate_id INTEGER NOT NULL,
                    assessment_version INTEGER DEFAULT 1,
                    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    assessed_by INTEGER,
                    assessment_status VARCHAR(30) DEFAULT 'draft',

                    -- Production (45% weight)
                    production_score FLOAT,
                    production_grade VARCHAR(2),
                    production_breakdown JSONB DEFAULT '{}'::jsonb,

                    -- DISC (20% weight)
                    disc_d_score INTEGER,
                    disc_i_score INTEGER,
                    disc_s_score INTEGER,
                    disc_c_score INTEGER,
                    disc_primary_style VARCHAR(1),
                    disc_secondary_style VARCHAR(1),
                    disc_composite_score FLOAT,
                    disc_grade VARCHAR(2),
                    disc_notes TEXT,
                    disc_assessment_source VARCHAR(30) DEFAULT 'manual',

                    -- Character (15% weight)
                    character_score FLOAT,
                    character_grade VARCHAR(2),
                    character_breakdown JSONB DEFAULT '{}'::jsonb,

                    -- Skills (10% weight)
                    skills_score FLOAT,
                    skills_grade VARCHAR(2),
                    skills_breakdown JSONB DEFAULT '{}'::jsonb,

                    -- Culture Fit (10% weight)
                    culture_fit_score FLOAT,
                    culture_fit_grade VARCHAR(2),
                    culture_fit_breakdown JSONB DEFAULT '{}'::jsonb,

                    -- Overall
                    overall_score FLOAT,
                    overall_grade VARCHAR(2),

                    -- AI Analysis
                    ai_analysis_run_at TIMESTAMP,
                    ai_confidence_score FLOAT,
                    ai_raw_analysis JSONB,

                    -- Strengths/Weaknesses
                    strengths TEXT[],
                    weaknesses TEXT[],

                    -- Override tracking
                    scores_overridden BOOLEAN DEFAULT FALSE,
                    override_reason TEXT,
                    override_by INTEGER,
                    override_at TIMESTAMP,

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX idx_mm_assessments_candidate ON mm_candidate_assessments(candidate_id);
                CREATE INDEX idx_mm_assessments_org ON mm_candidate_assessments(organization_id);
                CREATE UNIQUE INDEX idx_mm_assessments_candidate_unique ON mm_candidate_assessments(candidate_id);
            END IF;

            -- Add unique constraint if it doesn't exist (for existing tables)
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_mm_assessments_candidate_unique'
            ) THEN
                CREATE UNIQUE INDEX idx_mm_assessments_candidate_unique ON mm_candidate_assessments(candidate_id);
            END IF;

            -- Create mm_assessment_history if not exists
            IF NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'mm_assessment_history') THEN
                CREATE TABLE mm_assessment_history (
                    id SERIAL PRIMARY KEY,
                    assessment_id INTEGER REFERENCES mm_candidate_assessments(id) ON DELETE CASCADE,
                    change_type VARCHAR(30) NOT NULL,
                    changed_by INTEGER,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    previous_scores JSONB,
                    new_scores JSONB,
                    change_reason TEXT
                );

                CREATE INDEX idx_mm_history_assessment ON mm_assessment_history(assessment_id);
            END IF;

            -- Add columns to mm_candidates if they don't exist
            IF NOT EXISTS (SELECT FROM information_schema.columns
                          WHERE table_name = 'mm_candidates' AND column_name = 'current_assessment_id') THEN
                ALTER TABLE mm_candidates ADD COLUMN current_assessment_id INTEGER;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns
                          WHERE table_name = 'mm_candidates' AND column_name = 'current_grade') THEN
                ALTER TABLE mm_candidates ADD COLUMN current_grade VARCHAR(2);
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns
                          WHERE table_name = 'mm_candidates' AND column_name = 'grade_updated_at') THEN
                ALTER TABLE mm_candidates ADD COLUMN grade_updated_at TIMESTAMP;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns
                          WHERE table_name = 'mm_candidates' AND column_name = 'disc_primary_style') THEN
                ALTER TABLE mm_candidates ADD COLUMN disc_primary_style VARCHAR(1);
            END IF;
        END $$;
        """

        db.execute(text(migration_sql))
        db.commit()

        return {
            "success": True,
            "message": "Candidate grading migration completed successfully",
            "tables_created": ["mm_candidate_assessments", "mm_assessment_history"],
            "columns_added": ["current_assessment_id", "current_grade", "grade_updated_at", "disc_primary_style"]
        }

    except SQLAlchemyError as e:
        logger.exception("Error running grading migration")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# AI ANALYSIS ENDPOINTS
# =============================================================================

class AIAnalysisRequest(BaseModel):
    """Request for AI analysis."""
    include_resume: bool = True
    include_social: bool = True
    include_interviews: bool = True
    include_notes: bool = True


class ApplySuggestionsRequest(BaseModel):
    """Request to apply AI suggestions."""
    apply_production: bool = True
    apply_disc: bool = True
    apply_character: bool = True
    apply_skills: bool = True
    apply_culture: bool = True


@router.post("/{candidate_id}/assessment/ai-analyze")
async def run_ai_analysis(
    candidate_id: int,
    request: Optional[AIAnalysisRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Run AI analysis on a candidate.

    Uses Claude to analyze:
    - Resume content
    - Social media profiles and posts
    - Interview notes and feedback
    - Recruiter notes

    Returns suggested scores, DISC inference, strengths/weaknesses,
    and hire recommendation.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        from services.candidate_ai_analyzer import CandidateAIAnalyzer

        analyzer = CandidateAIAnalyzer(db)

        req = request or AIAnalysisRequest()

        analysis = await analyzer.analyze_candidate(
            candidate_id=candidate_id,
            include_resume=req.include_resume,
            include_social=req.include_social,
            include_interviews=req.include_interviews,
            include_notes=req.include_notes,
            triggered_by=current_user.id,
            organization_id=current_user.organization_id
        )

        return {
            "success": True,
            "candidate_id": candidate_id,
            "analyzed_at": analysis.analyzed_at.isoformat(),
            "confidence_score": analysis.confidence_score,

            "suggestions": {
                "production": {
                    "score": analysis.production_suggestion.suggested_score if analysis.production_suggestion else None,
                    "confidence": analysis.production_suggestion.confidence if analysis.production_suggestion else None,
                    "reasoning": analysis.production_suggestion.reasoning if analysis.production_suggestion else None,
                    "evidence": analysis.production_suggestion.evidence if analysis.production_suggestion else []
                },
                "disc": {
                    "d_score": analysis.disc_inference.d_score if analysis.disc_inference else None,
                    "i_score": analysis.disc_inference.i_score if analysis.disc_inference else None,
                    "s_score": analysis.disc_inference.s_score if analysis.disc_inference else None,
                    "c_score": analysis.disc_inference.c_score if analysis.disc_inference else None,
                    "primary_style": analysis.disc_inference.primary_style if analysis.disc_inference else None,
                    "secondary_style": analysis.disc_inference.secondary_style if analysis.disc_inference else None,
                    "confidence": analysis.disc_inference.confidence if analysis.disc_inference else None,
                    "reasoning": analysis.disc_inference.reasoning if analysis.disc_inference else None
                },
                "character": {
                    "score": analysis.character_suggestion.suggested_score if analysis.character_suggestion else None,
                    "confidence": analysis.character_suggestion.confidence if analysis.character_suggestion else None,
                    "reasoning": analysis.character_suggestion.reasoning if analysis.character_suggestion else None
                },
                "skills": {
                    "score": analysis.skills_suggestion.suggested_score if analysis.skills_suggestion else None,
                    "confidence": analysis.skills_suggestion.confidence if analysis.skills_suggestion else None,
                    "reasoning": analysis.skills_suggestion.reasoning if analysis.skills_suggestion else None
                },
                "culture_fit": {
                    "score": analysis.culture_fit_suggestion.suggested_score if analysis.culture_fit_suggestion else None,
                    "confidence": analysis.culture_fit_suggestion.confidence if analysis.culture_fit_suggestion else None,
                    "reasoning": analysis.culture_fit_suggestion.reasoning if analysis.culture_fit_suggestion else None
                }
            },

            "insights": {
                "strengths": [
                    {
                        "trait": s.trait,
                        "category": s.category,
                        "evidence": s.evidence,
                        "impact": s.impact_level
                    }
                    for s in analysis.strengths
                ],
                "weaknesses": [
                    {
                        "trait": w.trait,
                        "category": w.category,
                        "evidence": w.evidence,
                        "impact": w.impact_level
                    }
                    for w in analysis.weaknesses
                ],
                "red_flags": analysis.red_flags,
                "highlights": analysis.highlights
            },

            "recommendation": {
                "decision": analysis.hire_recommendation,
                "reasoning": analysis.recommendation_reasoning
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.exception(f"Error running AI analysis for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{candidate_id}/assessment/ai-apply")
async def apply_ai_suggestions(
    candidate_id: int,
    request: ApplySuggestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Apply AI-suggested scores to the candidate's assessment.

    Allows selecting which categories to apply.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)
        from services.candidate_ai_analyzer import CandidateAIAnalyzer
        import json

        # Get the stored AI analysis
        assessment = db.execute(text("""
            SELECT ai_raw_analysis, ai_confidence_score
            FROM mm_candidate_assessments
            WHERE candidate_id = :candidate_id
        """), {"candidate_id": candidate_id}).fetchone()

        if not assessment or not assessment.ai_raw_analysis:
            raise HTTPException(
                status_code=400,
                detail="No AI analysis found. Run AI analysis first."
            )

        # Parse the stored analysis (don't re-run AI which is slow)
        raw_analysis = assessment.ai_raw_analysis
        if isinstance(raw_analysis, str):
            raw_analysis = json.loads(raw_analysis)

        analyzer = CandidateAIAnalyzer(db)
        analysis = analyzer.rebuild_from_stored(
            candidate_id=candidate_id,
            raw_analysis=raw_analysis,
            confidence_score=assessment.ai_confidence_score or 0
        )

        result = await analyzer.apply_suggestions(
            candidate_id=candidate_id,
            analysis=analysis,
            apply_production=request.apply_production,
            apply_disc=request.apply_disc,
            apply_character=request.apply_character,
            apply_skills=request.apply_skills,
            apply_culture=request.apply_culture,
            applied_by=current_user.id
        )

        return {
            "success": result["applied"],
            "message": "AI suggestions applied successfully" if result["applied"] else result.get("message"),
            "categories_updated": result.get("categories_updated", []),
            "overall_score": result.get("overall_score"),
            "overall_grade": result.get("overall_grade")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error applying AI suggestions for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{candidate_id}/assessment/ai-status")
async def get_ai_analysis_status(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get the status of AI analysis for a candidate.

    Returns when analysis was last run and confidence score.
    """
    try:
        _verify_candidate_org(db, candidate_id, current_user.organization_id)

        result = db.execute(text("""
            SELECT
                ai_analysis_run_at,
                ai_confidence_score,
                ai_raw_analysis,
                strengths,
                weaknesses
            FROM mm_candidate_assessments
            WHERE candidate_id = :candidate_id
        """), {"candidate_id": candidate_id}).fetchone()

        if not result:
            return {
                "has_analysis": False,
                "message": "No assessment found for this candidate"
            }

        return {
            "has_analysis": result.ai_analysis_run_at is not None,
            "last_run_at": result.ai_analysis_run_at.isoformat() if result.ai_analysis_run_at else None,
            "confidence_score": result.ai_confidence_score,
            "strengths_count": len(result.strengths) if result.strengths else 0,
            "weaknesses_count": len(result.weaknesses) if result.weaknesses else 0
        }

    except Exception as e:
        logger.exception(f"Error getting AI analysis status for candidate {candidate_id}")
        raise HTTPException(status_code=500, detail="Internal server error")
