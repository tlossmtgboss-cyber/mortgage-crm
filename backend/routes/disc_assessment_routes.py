"""
DISC + Motivators Assessment API Routes

Endpoints for:
- Session management (start, resume, answer, complete)
- Results retrieval
- PDF report generation
- Admin operations
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from database import engine
from services.disc.scoring_service import DISCScoringService, DISCResult
from services.disc.motivators_service import MotivatorsService, MotivatorResult
from services.disc.wheel_calculator import WheelCalculator, WheelPosition
from services.disc.content_generator import DISCContentGenerator
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/disc", tags=["DISC Assessment"])


# =============================================================================
# SCHEMAS
# =============================================================================

class StartSessionRequest(BaseModel):
    candidate_id: int
    assessment_id: Optional[int] = None


class StartSessionResponse(BaseModel):
    session_id: int
    invite_token: str
    total_questions: int
    instructions: Optional[str] = None


class AnswerRequest(BaseModel):
    question_id: int
    response_value: dict  # {most: "option_id", least: "option_id"} or {value: 1-7}
    response_time_ms: int = 5000


class SessionStatusResponse(BaseModel):
    session_id: int
    status: str
    current_question: int
    total_questions: int
    time_spent_seconds: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class QuestionResponse(BaseModel):
    id: int
    question_order: int
    question_section: str
    question_type: str
    prompt: str
    options: list


class DISCResultResponse(BaseModel):
    adapted_d: int
    adapted_i: int
    adapted_s: int
    adapted_c: int
    adapted_style: str
    natural_d: int
    natural_i: int
    natural_s: int
    natural_c: int
    natural_style: str
    combined_style: str
    wheel_zone: int
    wheel_zone_name: str
    wheel_position: int
    quality_tier: str
    calibration_score: float


class MotivatorResultResponse(BaseModel):
    aesthetic: int
    economic: int
    individualistic: int
    political: int
    altruistic: int
    regulatory: int
    theoretical: int
    top_motivator: str
    second_motivator: str
    lowest_motivator: str
    ranking: dict


class FullResultResponse(BaseModel):
    candidate_id: int
    session_id: int
    completed_at: str
    disc: DISCResultResponse
    motivators: MotivatorResultResponse
    characteristics: Optional[str] = None
    word_sketch: Optional[dict] = None
    communication_tips: Optional[dict] = None
    strengths: Optional[list] = None
    stress_behaviors: Optional[list] = None


# =============================================================================
# SERVICES
# =============================================================================

scoring_service = DISCScoringService()
motivators_service = MotivatorsService()
wheel_calculator = WheelCalculator()
content_generator = DISCContentGenerator()


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@router.post("/sessions/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """Start a new DISC assessment session for a candidate."""
    with engine.connect() as conn:
        # Check for existing active session
        existing = conn.execute(text("""
            SELECT id, status FROM disc_assessment_sessions
            WHERE candidate_id = :candidate_id AND status IN ('not_started', 'in_progress')
            ORDER BY created_at DESC LIMIT 1
        """), {"candidate_id": request.candidate_id}).fetchone()

        if existing:
            # Return existing session
            session_id = existing[0]
            token = conn.execute(text("""
                SELECT invite_token FROM disc_assessment_sessions WHERE id = :id
            """), {"id": session_id}).scalar()
        else:
            # Get default assessment
            assessment_id = request.assessment_id
            if not assessment_id:
                assessment_id = conn.execute(text("""
                    SELECT id FROM disc_assessments WHERE is_active = true ORDER BY id LIMIT 1
                """)).scalar()

            if not assessment_id:
                raise HTTPException(status_code=404, detail="No active assessment found")

            # Create new session
            invite_token = f"disc_{secrets.token_hex(16)}"
            expires_at = datetime.now() + timedelta(days=7)

            result = conn.execute(text("""
                INSERT INTO disc_assessment_sessions
                (candidate_id, assessment_id, status, invite_token, invite_expires_at, created_at)
                VALUES (:candidate_id, :assessment_id, 'not_started', :token, :expires, NOW())
                RETURNING id
            """), {
                "candidate_id": request.candidate_id,
                "assessment_id": assessment_id,
                "token": invite_token,
                "expires": expires_at
            })
            session_id = result.fetchone()[0]
            token = invite_token

        # Get question count and instructions
        info = conn.execute(text("""
            SELECT a.total_disc_questions + a.total_motivator_questions as total,
                   a.instructions
            FROM disc_assessment_sessions s
            JOIN disc_assessments a ON a.id = s.assessment_id
            WHERE s.id = :session_id
        """), {"session_id": session_id}).fetchone()

        conn.commit()

        return StartSessionResponse(
            session_id=session_id,
            invite_token=token,
            total_questions=info[0] if info else 52,
            instructions=info[1] if info else None
        )


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: int):
    """Get status of an assessment session."""
    with engine.connect() as conn:
        session = conn.execute(text("""
            SELECT s.id, s.status, s.current_question, s.time_spent_seconds,
                   s.started_at, s.completed_at,
                   a.total_disc_questions + a.total_motivator_questions as total
            FROM disc_assessment_sessions s
            JOIN disc_assessments a ON a.id = s.assessment_id
            WHERE s.id = :session_id
        """), {"session_id": session_id}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionStatusResponse(
            session_id=session[0],
            status=session[1],
            current_question=session[2] or 0,
            total_questions=session[6],
            time_spent_seconds=session[3] or 0,
            started_at=session[4].isoformat() if session[4] else None,
            completed_at=session[5].isoformat() if session[5] else None
        )


@router.get("/sessions/{session_id}/questions")
async def get_session_questions(session_id: int):
    """Get all questions for a session."""
    with engine.connect() as conn:
        session = conn.execute(text("""
            SELECT assessment_id FROM disc_assessment_sessions WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        questions = conn.execute(text("""
            SELECT id, question_order, question_section, question_type, prompt, options
            FROM disc_questions
            WHERE assessment_id = :assessment_id
            ORDER BY question_order
        """), {"assessment_id": session[0]}).fetchall()

        return [
            QuestionResponse(
                id=q[0],
                question_order=q[1],
                question_section=q[2],
                question_type=q[3],
                prompt=q[4],
                options=q[5]
            )
            for q in questions
        ]


@router.get("/sessions/{session_id}/next-question")
async def get_next_question(session_id: int):
    """Get the next unanswered question for a session."""
    with engine.connect() as conn:
        session = conn.execute(text("""
            SELECT assessment_id, current_question, status
            FROM disc_assessment_sessions WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session[2] == "completed":
            return {"completed": True, "message": "Assessment already completed"}

        # Get next question
        next_q = conn.execute(text("""
            SELECT id, question_order, question_section, question_type, prompt, options
            FROM disc_questions
            WHERE assessment_id = :assessment_id
            AND question_order > :current
            ORDER BY question_order
            LIMIT 1
        """), {
            "assessment_id": session[0],
            "current": session[1] or 0
        }).fetchone()

        if not next_q:
            return {"completed": True, "message": "All questions answered"}

        return QuestionResponse(
            id=next_q[0],
            question_order=next_q[1],
            question_section=next_q[2],
            question_type=next_q[3],
            prompt=next_q[4],
            options=next_q[5]
        )


@router.post("/sessions/{session_id}/answer")
async def submit_answer(session_id: int, answer: AnswerRequest):
    """Submit an answer for a question."""
    with engine.connect() as conn:
        # Verify session exists and is active
        session = conn.execute(text("""
            SELECT status, current_question FROM disc_assessment_sessions WHERE id = :id
        """), {"id": session_id}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session[0] == "completed":
            raise HTTPException(status_code=400, detail="Session already completed")

        # Update session status if first answer
        if session[0] == "not_started":
            conn.execute(text("""
                UPDATE disc_assessment_sessions
                SET status = 'in_progress', started_at = NOW()
                WHERE id = :id
            """), {"id": session_id})

        # Get question order
        q_order = conn.execute(text("""
            SELECT question_order FROM disc_questions WHERE id = :qid
        """), {"qid": answer.question_id}).scalar()

        # Save response
        conn.execute(text("""
            INSERT INTO disc_responses (session_id, question_id, response_value, response_time_ms)
            VALUES (:session_id, :question_id, :response_value::jsonb, :response_time_ms)
            ON CONFLICT DO NOTHING
        """), {
            "session_id": session_id,
            "question_id": answer.question_id,
            "response_value": str(answer.response_value).replace("'", '"'),
            "response_time_ms": answer.response_time_ms
        })

        # Update current question and time
        conn.execute(text("""
            UPDATE disc_assessment_sessions
            SET current_question = :current,
                time_spent_seconds = time_spent_seconds + :time_sec,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": session_id,
            "current": q_order or (session[1] or 0) + 1,
            "time_sec": answer.response_time_ms // 1000
        })

        conn.commit()

        return {"success": True, "question_id": answer.question_id}


@router.post("/sessions/{session_id}/complete")
async def complete_session(session_id: int):
    """Mark session as complete and compute results."""
    with engine.connect() as conn:
        # Get session info
        session = conn.execute(text("""
            SELECT s.id, s.candidate_id, s.assessment_id, s.status
            FROM disc_assessment_sessions s
            WHERE s.id = :id
        """), {"id": session_id}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session[3] == "completed":
            raise HTTPException(status_code=400, detail="Session already completed")

        candidate_id = session[1]
        assessment_id = session[2]

        # Get all responses
        responses = conn.execute(text("""
            SELECT r.question_id, r.response_value, r.response_time_ms
            FROM disc_responses r
            WHERE r.session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        responses_list = [
            {"question_id": r[0], "response_value": r[1], "response_time_ms": r[2]}
            for r in responses
        ]

        # Get questions
        questions = conn.execute(text("""
            SELECT id, question_section, question_type, prompt, options, dimension_measured
            FROM disc_questions
            WHERE assessment_id = :assessment_id
        """), {"assessment_id": assessment_id}).fetchall()

        questions_list = [
            {
                "id": q[0],
                "question_section": q[1],
                "question_type": q[2],
                "prompt": q[3],
                "options": q[4],
                "dimension_measured": q[5]
            }
            for q in questions
        ]

        # Score DISC
        disc_result = scoring_service.score_responses(responses_list, questions_list)

        # Score Motivators
        motivator_result = motivators_service.score_responses(responses_list, questions_list)

        # Calculate wheel position
        wheel_pos = wheel_calculator.calculate_position(
            disc_result.adapted.d,
            disc_result.adapted.i,
            disc_result.adapted.s,
            disc_result.adapted.c
        )

        # Save DISC results
        conn.execute(text("""
            INSERT INTO disc_results (
                session_id, candidate_id,
                adapted_d, adapted_i, adapted_s, adapted_c, adapted_style,
                natural_d, natural_i, natural_s, natural_c, natural_style,
                combined_style, wheel_zone, wheel_position, wheel_zone_name,
                calibration_score, consistency_score, response_time_score,
                quality_tier, quality_notes
            ) VALUES (
                :session_id, :candidate_id,
                :ad, :ai, :as, :ac, :a_style,
                :nd, :ni, :ns, :nc, :n_style,
                :combined, :wz, :wp, :wzn,
                :cal, :con, :rts,
                :tier, :notes
            )
        """), {
            "session_id": session_id,
            "candidate_id": candidate_id,
            "ad": disc_result.adapted.d,
            "ai": disc_result.adapted.i,
            "as": disc_result.adapted.s,
            "ac": disc_result.adapted.c,
            "a_style": disc_result.adapted_style,
            "nd": disc_result.natural.d,
            "ni": disc_result.natural.i,
            "ns": disc_result.natural.s,
            "nc": disc_result.natural.c,
            "n_style": disc_result.natural_style,
            "combined": disc_result.combined_style,
            "wz": wheel_pos.zone,
            "wp": wheel_pos.position,
            "wzn": wheel_pos.zone_name,
            "cal": disc_result.calibration_score,
            "con": disc_result.consistency_score,
            "rts": disc_result.response_time_score,
            "tier": disc_result.quality_tier.value,
            "notes": disc_result.quality_notes
        })

        # Save Motivator results
        conn.execute(text("""
            INSERT INTO motivator_results (
                session_id, candidate_id,
                aesthetic, economic, individualistic, political,
                altruistic, regulatory, theoretical,
                ranking, top_motivator, second_motivator, lowest_motivator
            ) VALUES (
                :session_id, :candidate_id,
                :aes, :eco, :ind, :pol, :alt, :reg, :the,
                :ranking::jsonb, :top, :second, :lowest
            )
        """), {
            "session_id": session_id,
            "candidate_id": candidate_id,
            "aes": motivator_result.scores.aesthetic,
            "eco": motivator_result.scores.economic,
            "ind": motivator_result.scores.individualistic,
            "pol": motivator_result.scores.political,
            "alt": motivator_result.scores.altruistic,
            "reg": motivator_result.scores.regulatory,
            "the": motivator_result.scores.theoretical,
            "ranking": str(motivator_result.ranking).replace("'", '"'),
            "top": motivator_result.top_motivator,
            "second": motivator_result.second_motivator,
            "lowest": motivator_result.lowest_motivator
        })

        # Update session status
        conn.execute(text("""
            UPDATE disc_assessment_sessions
            SET status = 'completed', completed_at = NOW()
            WHERE id = :id
        """), {"id": session_id})

        # Update candidate record
        conn.execute(text("""
            UPDATE mm_candidates
            SET disc_session_id = :session_id,
                disc_completed_at = NOW(),
                disc_style = :style,
                top_motivator = :motivator
            WHERE id = :candidate_id
        """), {
            "session_id": session_id,
            "style": disc_result.combined_style,
            "motivator": motivator_result.top_motivator,
            "candidate_id": candidate_id
        })

        conn.commit()

        return {
            "success": True,
            "session_id": session_id,
            "disc_style": disc_result.combined_style,
            "top_motivator": motivator_result.top_motivator,
            "quality_tier": disc_result.quality_tier.value
        }


# =============================================================================
# RESULTS
# =============================================================================

@router.get("/results/{candidate_id}")
async def get_results(candidate_id: int):
    """Get DISC + Motivator results for a candidate."""
    with engine.connect() as conn:
        # Get DISC results
        disc = conn.execute(text("""
            SELECT dr.*, s.completed_at
            FROM disc_results dr
            JOIN disc_assessment_sessions s ON s.id = dr.session_id
            WHERE dr.candidate_id = :candidate_id
            ORDER BY dr.computed_at DESC
            LIMIT 1
        """), {"candidate_id": candidate_id}).fetchone()

        if not disc:
            raise HTTPException(status_code=404, detail="No DISC results found for candidate")

        # Get column names
        disc_cols = ["id", "session_id", "candidate_id",
                     "adapted_d", "adapted_i", "adapted_s", "adapted_c", "adapted_style",
                     "natural_d", "natural_i", "natural_s", "natural_c", "natural_style",
                     "combined_style", "wheel_zone", "wheel_position", "wheel_zone_name",
                     "calibration_score", "consistency_score", "response_time_score",
                     "quality_tier", "quality_notes", "characteristics", "word_sketch",
                     "communication_tips", "wants_and_needs", "strengths", "stress_behaviors",
                     "areas_for_improvement", "integrated_styles", "computed_at",
                     "ai_content_generated_at", "completed_at"]

        disc_dict = dict(zip(disc_cols[:len(disc)], disc))

        # Get Motivator results
        motivator = conn.execute(text("""
            SELECT * FROM motivator_results
            WHERE candidate_id = :candidate_id
            ORDER BY computed_at DESC
            LIMIT 1
        """), {"candidate_id": candidate_id}).fetchone()

        motivator_cols = ["id", "session_id", "candidate_id",
                          "aesthetic", "economic", "individualistic", "political",
                          "altruistic", "regulatory", "theoretical",
                          "ranking", "top_motivator", "second_motivator", "lowest_motivator",
                          "dimension_insights", "overall_summary", "computed_at",
                          "ai_content_generated_at"]

        motivator_dict = dict(zip(motivator_cols[:len(motivator)], motivator)) if motivator else {}

        return {
            "candidate_id": candidate_id,
            "session_id": disc_dict.get("session_id"),
            "completed_at": disc_dict.get("completed_at").isoformat() if disc_dict.get("completed_at") else None,
            "disc": {
                "adapted_d": disc_dict.get("adapted_d"),
                "adapted_i": disc_dict.get("adapted_i"),
                "adapted_s": disc_dict.get("adapted_s"),
                "adapted_c": disc_dict.get("adapted_c"),
                "adapted_style": disc_dict.get("adapted_style"),
                "natural_d": disc_dict.get("natural_d"),
                "natural_i": disc_dict.get("natural_i"),
                "natural_s": disc_dict.get("natural_s"),
                "natural_c": disc_dict.get("natural_c"),
                "natural_style": disc_dict.get("natural_style"),
                "combined_style": disc_dict.get("combined_style"),
                "wheel_zone": disc_dict.get("wheel_zone"),
                "wheel_zone_name": disc_dict.get("wheel_zone_name"),
                "wheel_position": disc_dict.get("wheel_position"),
                "quality_tier": disc_dict.get("quality_tier"),
                "calibration_score": float(disc_dict.get("calibration_score") or 0),
            },
            "motivators": {
                "aesthetic": motivator_dict.get("aesthetic"),
                "economic": motivator_dict.get("economic"),
                "individualistic": motivator_dict.get("individualistic"),
                "political": motivator_dict.get("political"),
                "altruistic": motivator_dict.get("altruistic"),
                "regulatory": motivator_dict.get("regulatory"),
                "theoretical": motivator_dict.get("theoretical"),
                "ranking": motivator_dict.get("ranking"),
                "top_motivator": motivator_dict.get("top_motivator"),
                "second_motivator": motivator_dict.get("second_motivator"),
                "lowest_motivator": motivator_dict.get("lowest_motivator"),
            },
            "characteristics": disc_dict.get("characteristics"),
            "word_sketch": disc_dict.get("word_sketch"),
            "communication_tips": disc_dict.get("communication_tips"),
            "strengths": disc_dict.get("strengths"),
            "stress_behaviors": disc_dict.get("stress_behaviors"),
        }


@router.get("/results/{candidate_id}/summary")
async def get_results_summary(candidate_id: int):
    """Get a brief summary of DISC results for display in cards/lists."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT dr.combined_style, dr.wheel_zone_name, dr.quality_tier,
                   mr.top_motivator, mr.second_motivator,
                   s.completed_at
            FROM disc_results dr
            JOIN disc_assessment_sessions s ON s.id = dr.session_id
            LEFT JOIN motivator_results mr ON mr.session_id = dr.session_id
            WHERE dr.candidate_id = :candidate_id
            ORDER BY dr.computed_at DESC
            LIMIT 1
        """), {"candidate_id": candidate_id}).mappings().fetchone()

        if not result:
            return {"has_results": False}

        return {
            "has_results": True,
            "disc_style": result["combined_style"],
            "wheel_zone": result["wheel_zone_name"],
            "quality_tier": result["quality_tier"],
            "top_motivator": result["top_motivator"],
            "second_motivator": result["second_motivator"],
            "completed_at": result["completed_at"].isoformat() if result["completed_at"] else None
        }


@router.post("/results/{candidate_id}/generate-content")
async def generate_ai_content(candidate_id: int):
    """Generate AI content for a candidate's DISC results."""
    with engine.connect() as conn:
        # Get results
        disc = conn.execute(text("""
            SELECT * FROM disc_results WHERE candidate_id = :id
            ORDER BY computed_at DESC LIMIT 1
        """), {"id": candidate_id}).mappings().fetchone()

        motivator = conn.execute(text("""
            SELECT * FROM motivator_results WHERE candidate_id = :id
            ORDER BY computed_at DESC LIMIT 1
        """), {"id": candidate_id}).mappings().fetchone()

        if not disc or not motivator:
            raise HTTPException(status_code=404, detail="Results not found")

        # Get candidate name
        candidate = conn.execute(text("""
            SELECT first_name, last_name FROM mm_candidates WHERE id = :id
        """), {"id": candidate_id}).mappings().fetchone()

        candidate_name = f"{candidate['first_name']} {candidate['last_name']}" if candidate else "the candidate"

        # Build result objects for content generator
        from services.disc.scoring_service import DISCScores, DISCResult, QualityTier
        from services.disc.motivators_service import MotivatorScores, MotivatorResult

        disc_result = DISCResult(
            adapted=DISCScores(d=disc["adapted_d"], i=disc["adapted_i"], s=disc["adapted_s"], c=disc["adapted_c"]),
            natural=DISCScores(d=disc["natural_d"], i=disc["natural_i"], s=disc["natural_s"], c=disc["natural_c"]),
            adapted_style=disc["adapted_style"],
            natural_style=disc["natural_style"],
            combined_style=disc["combined_style"],
            calibration_score=float(disc["calibration_score"] or 0.5),
            consistency_score=float(disc["consistency_score"] or 0.5),
            response_time_score=float(disc["response_time_score"] or 0.5),
            quality_tier=QualityTier(disc["quality_tier"] or "MEDIUM"),
        )

        motivator_scores = MotivatorScores(
            aesthetic=motivator["aesthetic"],
            economic=motivator["economic"],
            individualistic=motivator["individualistic"],
            political=motivator["political"],
            altruistic=motivator["altruistic"],
            regulatory=motivator["regulatory"],
            theoretical=motivator["theoretical"],
        )

        motivator_result = MotivatorResult(
            scores=motivator_scores,
            ranking=motivator["ranking"] or {},
            top_motivator=motivator["top_motivator"],
            second_motivator=motivator["second_motivator"],
            lowest_motivator=motivator["lowest_motivator"],
        )

        wheel_pos = wheel_calculator.calculate_position(
            disc_result.adapted.d,
            disc_result.adapted.i,
            disc_result.adapted.s,
            disc_result.adapted.c
        )

        # Generate content
        content = await content_generator.generate_all_content(
            disc_result, motivator_result, wheel_pos, candidate_name
        )

        # Save to database
        conn.execute(text("""
            UPDATE disc_results
            SET characteristics = :char,
                word_sketch = :ws::jsonb,
                communication_tips = :ct::jsonb,
                wants_and_needs = :wn::jsonb,
                strengths = :str::jsonb,
                stress_behaviors = :sb::jsonb,
                areas_for_improvement = :afi::jsonb,
                integrated_styles = :is::jsonb,
                ai_content_generated_at = NOW()
            WHERE candidate_id = :candidate_id
            AND computed_at = (SELECT MAX(computed_at) FROM disc_results WHERE candidate_id = :candidate_id)
        """), {
            "candidate_id": candidate_id,
            "char": content.characteristics,
            "ws": str(content.word_sketch).replace("'", '"'),
            "ct": str(content.communication_tips).replace("'", '"'),
            "wn": str(content.wants_and_needs).replace("'", '"'),
            "str": str(content.strengths).replace("'", '"'),
            "sb": str(content.stress_behaviors).replace("'", '"'),
            "afi": str(content.areas_for_improvement).replace("'", '"'),
            "is": str(content.integrated_styles).replace("'", '"'),
        })

        conn.commit()

        return {"success": True, "message": "AI content generated"}


# =============================================================================
# PUBLIC ACCESS (via token)
# =============================================================================

@router.get("/public/session/{token}")
async def get_session_by_token(token: str):
    """Get session info by invite token (for public assessment page)."""
    with engine.connect() as conn:
        session = conn.execute(text("""
            SELECT s.id, s.candidate_id, s.status, s.current_question,
                   s.invite_expires_at, c.first_name,
                   a.total_disc_questions + a.total_motivator_questions as total
            FROM disc_assessment_sessions s
            JOIN mm_candidates c ON c.id = s.candidate_id
            JOIN disc_assessments a ON a.id = s.assessment_id
            WHERE s.invite_token = :token
        """), {"token": token}).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Invalid or expired token")

        if session[4] and session[4] < datetime.now():
            raise HTTPException(status_code=400, detail="Assessment link has expired")

        if session[2] == "completed":
            return {"status": "completed", "message": "Assessment already completed"}

        return {
            "session_id": session[0],
            "candidate_name": session[5],
            "status": session[2],
            "current_question": session[3] or 0,
            "total_questions": session[6]
        }


# =============================================================================
# ADMIN
# =============================================================================

@router.get("/assessments")
async def list_assessments():
    """List all available assessments."""
    with engine.connect() as conn:
        assessments = conn.execute(text("""
            SELECT id, name, version, is_active,
                   total_disc_questions, total_motivator_questions,
                   time_limit_minutes, created_at
            FROM disc_assessments
            ORDER BY created_at DESC
        """)).fetchall()

        return [
            {
                "id": a[0],
                "name": a[1],
                "version": a[2],
                "is_active": a[3],
                "total_disc_questions": a[4],
                "total_motivator_questions": a[5],
                "time_limit_minutes": a[6],
                "created_at": a[7].isoformat() if a[7] else None
            }
            for a in assessments
        ]


@router.post("/admin/run-migration")
async def run_disc_migration(request: Request = None):
    """Run DISC migration (admin only)."""
    from database import get_db as _get_db
    from auth.dependencies import get_current_user_flexible
    db = next(_get_db())
    auth_header = request.headers.get("Authorization", "") if request else ""
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    await get_current_user_flexible(token=token, request=request, db=db)

    try:
        from migrations.add_disc_motivators_assessment import run_migration
        run_migration()
        return {"success": True, "message": "Migration completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PDF REPORT
# =============================================================================

@router.get("/results/{candidate_id}/pdf")
async def download_disc_pdf(candidate_id: int):
    """Generate and download DISC + Motivators PDF report."""
    from fastapi.responses import Response
    from services.disc.report_generator import generate_disc_report

    with engine.connect() as conn:
        # Get candidate name
        candidate = conn.execute(text("""
            SELECT first_name, last_name, name FROM mm_candidates WHERE id = :id
        """), {"id": candidate_id}).mappings().fetchone()

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate_name = f"{candidate['first_name'] or ''} {candidate['last_name'] or ''}".strip() or candidate['name'] or "Unknown"

        # Get DISC results
        disc = conn.execute(text("""
            SELECT adapted_d, adapted_i, adapted_s, adapted_c, adapted_style,
                   natural_d, natural_i, natural_s, natural_c, natural_style,
                   wheel_zone, wheel_position, calibration_score, quality_tier,
                   characteristics, communication_tips, strengths, stress_behaviors,
                   areas_for_improvement
            FROM disc_results
            WHERE candidate_id = :candidate_id
            ORDER BY computed_at DESC LIMIT 1
        """), {"candidate_id": candidate_id}).mappings().fetchone()

        if not disc:
            raise HTTPException(status_code=404, detail="No DISC results found")

        # Get Motivator results
        motivator = conn.execute(text("""
            SELECT aesthetic, economic, individualistic, political,
                   altruistic, regulatory, theoretical, ranking
            FROM motivator_results
            WHERE candidate_id = :candidate_id
            ORDER BY computed_at DESC LIMIT 1
        """), {"candidate_id": candidate_id}).mappings().fetchone()

        if not motivator:
            raise HTTPException(status_code=404, detail="No Motivator results found")

        # Build DISCResult object
        disc_result = DISCResult(
            adapted_d=disc["adapted_d"],
            adapted_i=disc["adapted_i"],
            adapted_s=disc["adapted_s"],
            adapted_c=disc["adapted_c"],
            adapted_style=disc["adapted_style"],
            natural_d=disc["natural_d"],
            natural_i=disc["natural_i"],
            natural_s=disc["natural_s"],
            natural_c=disc["natural_c"],
            natural_style=disc["natural_style"],
            wheel_zone=disc["wheel_zone"],
            wheel_position=disc["wheel_position"],
            calibration_score=float(disc["calibration_score"] or 0.8),
            consistency_score=0.9,
            quality_tier=disc["quality_tier"] or "MEDIUM"
        )

        motivator_scores = {
            'aesthetic': motivator["aesthetic"],
            'economic': motivator["economic"],
            'individualistic': motivator["individualistic"],
            'political': motivator["political"],
            'altruistic': motivator["altruistic"],
            'regulatory': motivator["regulatory"],
            'theoretical': motivator["theoretical"],
        }

        motivator_ranking = motivator["ranking"] if isinstance(motivator["ranking"], dict) else {}

        # Parse generated content if available
        generated_content = {}
        if disc["characteristics"]:
            generated_content['characteristics'] = disc["characteristics"]
        if disc["communication_tips"]:
            import json
            try:
                generated_content['communication_tips'] = json.loads(disc["communication_tips"]) if isinstance(disc["communication_tips"], str) else disc["communication_tips"]
            except Exception as e:
                logger.error(f"Error parsing communication_tips JSON in download_disc_pdf: {e}")
        if disc["strengths"]:
            import json
            try:
                generated_content['strengths'] = json.loads(disc["strengths"]) if isinstance(disc["strengths"], str) else disc["strengths"]
            except Exception as e:
                logger.error(f"Error parsing strengths JSON in download_disc_pdf: {e}")
        if disc["stress_behaviors"]:
            import json
            try:
                generated_content['stress_behaviors'] = json.loads(disc["stress_behaviors"]) if isinstance(disc["stress_behaviors"], str) else disc["stress_behaviors"]
            except Exception as e:
                logger.error(f"Error parsing stress_behaviors JSON in download_disc_pdf: {e}")
        if disc["areas_for_improvement"]:
            import json
            try:
                generated_content['improvements'] = json.loads(disc["areas_for_improvement"]) if isinstance(disc["areas_for_improvement"], str) else disc["areas_for_improvement"]
            except Exception as e:
                logger.error(f"Error parsing improvements JSON in download_disc_pdf: {e}")

        # Generate PDF
        pdf_bytes = await generate_disc_report(
            candidate_name=candidate_name,
            disc_result=disc_result,
            motivator_scores=motivator_scores,
            motivator_ranking=motivator_ranking,
            generated_content=generated_content if generated_content else None
        )

        filename = f"DISC_Report_{candidate_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
