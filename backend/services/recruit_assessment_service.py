"""
Recruiting Assessment Service

Handles:
- Quiz retrieval by disposition
- Quiz response submission
- Score calculation and updates
- Production calculator
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import text
from database import engine

from models.recruit_assessment_models import (
    QuizTemplate,
    QuizQuestion,
    QuizForDisposition,
    QuizSubmission,
    QuizResponseCreate,
    AssessmentScores,
    AssessmentScoreBreakdown,
    CalculatorConfig,
    CalculatorInput,
    CalculatorResult,
    WEIGHT_PRODUCTION,
    WEIGHT_DISC,
    WEIGHT_CHARACTER,
    WEIGHT_SKILLS,
    WEIGHT_CULTURE_FIT,
    LIKERT_OPTIONS,
    YES_NO_OPTIONS,
    DISPOSITION_LABELS,
)


class RecruitAssessmentService:
    """Service for managing recruiting assessments."""

    def __init__(self):
        pass

    def _verify_candidate_org(self, conn, candidate_id: int, organization_id: int):
        """Verify candidate belongs to the given organization."""
        row = conn.execute(
            text("SELECT id FROM mm_candidates WHERE id = :id AND organization_id = :org_id AND is_active = true"),
            {"id": candidate_id, "org_id": organization_id}
        ).fetchone()
        if not row:
            raise ValueError("Candidate not found")

    # =========================================================================
    # Quiz Management
    # =========================================================================

    def get_quiz_for_disposition(self, disposition: str) -> QuizForDisposition:
        """Get all quiz questions for a specific disposition."""
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, disposition, question_text, question_type,
                           category, weight, display_order
                    FROM recruit_quiz_templates
                    WHERE disposition = :disposition AND is_active = true
                    ORDER BY display_order ASC
                """),
                {"disposition": disposition}
            )
            rows = result.fetchall()

        questions = []
        categories = set()

        for row in rows:
            # Add options based on question type
            if row.question_type == "likert":
                options = LIKERT_OPTIONS
            elif row.question_type == "yes_no":
                options = YES_NO_OPTIONS
            else:
                options = None

            questions.append(QuizQuestion(
                id=row.id,
                question_text=row.question_text,
                question_type=row.question_type,
                category=row.category,
                weight=float(row.weight),
                display_order=row.display_order,
                options=options
            ))
            categories.add(row.category)

        return QuizForDisposition(
            disposition=disposition,
            disposition_label=DISPOSITION_LABELS.get(disposition, disposition.title()),
            questions=questions,
            total_questions=len(questions),
            categories=list(categories)
        )

    def submit_quiz_responses(
        self,
        candidate_id: int,
        submission: QuizSubmission,
        responded_by: int,
        organization_id: Optional[int] = None
    ) -> AssessmentScores:
        """Submit quiz responses and update scores."""
        disposition = submission.disposition

        with engine.connect() as conn:
            # Verify candidate belongs to org
            if organization_id:
                self._verify_candidate_org(conn, candidate_id, organization_id)

            # Insert responses
            for response in submission.responses:
                conn.execute(
                    text("""
                        INSERT INTO recruit_quiz_responses
                        (candidate_id, template_id, disposition, response_value, numeric_score, responded_by)
                        VALUES (:candidate_id, :template_id, :disposition, :response_value, :numeric_score, :responded_by)
                    """),
                    {
                        "candidate_id": candidate_id,
                        "template_id": response.template_id,
                        "disposition": disposition,
                        "response_value": response.response_value,
                        "numeric_score": response.numeric_score,
                        "responded_by": responded_by
                    }
                )

            conn.commit()

        # Recalculate scores
        return self.calculate_and_update_scores(candidate_id, organization_id=organization_id)

    def calculate_and_update_scores(self, candidate_id: int, organization_id: Optional[int] = None) -> AssessmentScores:
        """Calculate scores from all quiz responses and update the scores table."""
        with engine.connect() as conn:
            # Get all responses with their categories and weights
            result = conn.execute(
                text("""
                    SELECT r.numeric_score, r.disposition, t.category, t.weight
                    FROM recruit_quiz_responses r
                    JOIN recruit_quiz_templates t ON t.id = r.template_id
                    WHERE r.candidate_id = :candidate_id
                    ORDER BY r.responded_at DESC
                """),
                {"candidate_id": candidate_id}
            )
            rows = result.fetchall()

        if not rows:
            return AssessmentScores(candidate_id=candidate_id)

        # Calculate weighted averages by category
        category_scores = {
            "production": [],
            "disc": [],
            "character": [],
            "skills": [],
            "culture_fit": []
        }

        dispositions_completed = set()

        for row in rows:
            if row.category in category_scores and row.numeric_score is not None:
                category_scores[row.category].append({
                    "score": float(row.numeric_score),
                    "weight": float(row.weight)
                })
            dispositions_completed.add(row.disposition)

        # Calculate weighted average for each category
        def calc_weighted_avg(scores_list):
            if not scores_list:
                return None
            total_weight = sum(s["weight"] for s in scores_list)
            if total_weight == 0:
                return None
            weighted_sum = sum(s["score"] * s["weight"] for s in scores_list)
            return round(weighted_sum / total_weight, 1)

        production_score = calc_weighted_avg(category_scores["production"])
        disc_score = calc_weighted_avg(category_scores["disc"])
        character_score = calc_weighted_avg(category_scores["character"])
        skills_score = calc_weighted_avg(category_scores["skills"])
        culture_fit_score = calc_weighted_avg(category_scores["culture_fit"])

        # Calculate overall score
        overall_components = []
        if production_score is not None:
            overall_components.append((production_score, WEIGHT_PRODUCTION))
        if disc_score is not None:
            overall_components.append((disc_score, WEIGHT_DISC))
        if character_score is not None:
            overall_components.append((character_score, WEIGHT_CHARACTER))
        if skills_score is not None:
            overall_components.append((skills_score, WEIGHT_SKILLS))
        if culture_fit_score is not None:
            overall_components.append((culture_fit_score, WEIGHT_CULTURE_FIT))

        if overall_components:
            # Normalize weights
            total_weight = sum(w for _, w in overall_components)
            overall_score = sum(s * (w / total_weight) for s, w in overall_components)
            overall_score = round(overall_score, 1)
        else:
            overall_score = None

        # Get last disposition
        last_disposition = rows[0].disposition if rows else None

        # Upsert scores
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO recruit_assessment_scores
                    (candidate_id, production_score, disc_score, character_score,
                     skills_score, culture_fit_score, overall_score,
                     last_quiz_disposition, quiz_count, last_updated)
                    VALUES (:candidate_id, :production_score, :disc_score, :character_score,
                            :skills_score, :culture_fit_score, :overall_score,
                            :last_disposition, :quiz_count, NOW())
                    ON CONFLICT (candidate_id) DO UPDATE SET
                        production_score = EXCLUDED.production_score,
                        disc_score = EXCLUDED.disc_score,
                        character_score = EXCLUDED.character_score,
                        skills_score = EXCLUDED.skills_score,
                        culture_fit_score = EXCLUDED.culture_fit_score,
                        overall_score = EXCLUDED.overall_score,
                        last_quiz_disposition = EXCLUDED.last_quiz_disposition,
                        quiz_count = EXCLUDED.quiz_count,
                        last_updated = NOW()
                """),
                {
                    "candidate_id": candidate_id,
                    "production_score": production_score,
                    "disc_score": disc_score,
                    "character_score": character_score,
                    "skills_score": skills_score,
                    "culture_fit_score": culture_fit_score,
                    "overall_score": overall_score,
                    "last_disposition": last_disposition,
                    "quiz_count": len(dispositions_completed)
                }
            )
            conn.commit()

        return AssessmentScores(
            candidate_id=candidate_id,
            production_score=production_score,
            disc_score=disc_score,
            character_score=character_score,
            skills_score=skills_score,
            culture_fit_score=culture_fit_score,
            overall_score=overall_score,
            last_quiz_disposition=last_disposition,
            quiz_count=len(dispositions_completed),
            last_updated=datetime.now()
        )

    def get_candidate_scores(self, candidate_id: int, organization_id: Optional[int] = None) -> Optional[AssessmentScores]:
        """Get assessment scores for a candidate."""
        with engine.connect() as conn:
            if organization_id:
                self._verify_candidate_org(conn, candidate_id, organization_id)
            result = conn.execute(
                text("""
                    SELECT id, candidate_id, production_score, disc_score,
                           character_score, skills_score, culture_fit_score,
                           overall_score, last_quiz_disposition, quiz_count, last_updated
                    FROM recruit_assessment_scores
                    WHERE candidate_id = :candidate_id
                """),
                {"candidate_id": candidate_id}
            )
            row = result.fetchone()

        if not row:
            return None

        return AssessmentScores(
            id=row.id,
            candidate_id=row.candidate_id,
            production_score=float(row.production_score) if row.production_score else None,
            disc_score=float(row.disc_score) if row.disc_score else None,
            character_score=float(row.character_score) if row.character_score else None,
            skills_score=float(row.skills_score) if row.skills_score else None,
            culture_fit_score=float(row.culture_fit_score) if row.culture_fit_score else None,
            overall_score=float(row.overall_score) if row.overall_score else None,
            last_quiz_disposition=row.last_quiz_disposition,
            quiz_count=row.quiz_count or 0,
            last_updated=row.last_updated
        )

    def get_score_breakdown(self, candidate_id: int, organization_id: Optional[int] = None) -> AssessmentScoreBreakdown:
        """Get detailed score breakdown with quiz history."""
        scores = self.get_candidate_scores(candidate_id, organization_id=organization_id)
        if not scores:
            scores = AssessmentScores(candidate_id=candidate_id)

        # Get quiz history
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT DISTINCT disposition, MIN(responded_at) as completed_at
                    FROM recruit_quiz_responses
                    WHERE candidate_id = :candidate_id
                    GROUP BY disposition
                    ORDER BY MIN(responded_at) ASC
                """),
                {"candidate_id": candidate_id}
            )
            history_rows = result.fetchall()

        quiz_history = [
            {
                "disposition": row.disposition,
                "disposition_label": DISPOSITION_LABELS.get(row.disposition, row.disposition),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None
            }
            for row in history_rows
        ]

        # Generate recommendations
        recommendations = []
        if scores.overall_score:
            if scores.overall_score >= 8:
                recommendations.append("Strong candidate - prioritize for offer")
            elif scores.overall_score >= 6:
                recommendations.append("Good candidate - proceed to next stage")
            elif scores.overall_score >= 4:
                recommendations.append("Average candidate - investigate concerns")
            else:
                recommendations.append("Below average - consider other candidates")

            # Category-specific recommendations
            if scores.production_score and scores.production_score < 6:
                recommendations.append("Production history below average - verify past performance")
            if scores.character_score and scores.character_score < 6:
                recommendations.append("Character concerns - additional reference checks recommended")
            if scores.culture_fit_score and scores.culture_fit_score < 6:
                recommendations.append("Culture fit concerns - consider team dynamics carefully")

        return AssessmentScoreBreakdown(
            candidate_id=candidate_id,
            scores=scores,
            category_details={
                "production": {"weight": WEIGHT_PRODUCTION, "score": scores.production_score},
                "disc": {"weight": WEIGHT_DISC, "score": scores.disc_score},
                "character": {"weight": WEIGHT_CHARACTER, "score": scores.character_score},
                "skills": {"weight": WEIGHT_SKILLS, "score": scores.skills_score},
                "culture_fit": {"weight": WEIGHT_CULTURE_FIT, "score": scores.culture_fit_score},
            },
            quiz_history=quiz_history,
            recommendations=recommendations
        )

    def check_quiz_completed(self, candidate_id: int, disposition: str, organization_id: Optional[int] = None) -> bool:
        """Check if quiz has been completed for a disposition."""
        with engine.connect() as conn:
            if organization_id:
                self._verify_candidate_org(conn, candidate_id, organization_id)
            result = conn.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM recruit_quiz_responses
                    WHERE candidate_id = :candidate_id AND disposition = :disposition
                """),
                {"candidate_id": candidate_id, "disposition": disposition}
            )
            row = result.fetchone()
            return row.count > 0 if row else False

    # =========================================================================
    # Production Calculator
    # =========================================================================

    def get_calculator_config(self, organization_id: int = 1) -> CalculatorConfig:
        """Get calculator configuration for an organization."""
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, organization_id, lead_conversion_lift, avg_deal_size_lift,
                           closing_speed_factor, tech_efficiency_gain, marketing_lead_boost,
                           comp_percentage
                    FROM recruit_calculator_config
                    WHERE organization_id = :org_id OR organization_id IS NULL
                    ORDER BY organization_id DESC NULLS LAST
                    LIMIT 1
                """),
                {"org_id": organization_id}
            )
            row = result.fetchone()

        if not row:
            return CalculatorConfig()

        return CalculatorConfig(
            id=row.id,
            organization_id=row.organization_id,
            lead_conversion_lift=float(row.lead_conversion_lift),
            avg_deal_size_lift=float(row.avg_deal_size_lift),
            closing_speed_factor=float(row.closing_speed_factor),
            tech_efficiency_gain=float(row.tech_efficiency_gain),
            marketing_lead_boost=float(row.marketing_lead_boost),
            comp_percentage=float(row.comp_percentage)
        )

    def update_calculator_config(
        self,
        config: CalculatorConfig,
        organization_id: int = 1
    ) -> CalculatorConfig:
        """Update calculator configuration."""
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO recruit_calculator_config
                    (organization_id, lead_conversion_lift, avg_deal_size_lift,
                     closing_speed_factor, tech_efficiency_gain, marketing_lead_boost,
                     comp_percentage, updated_at)
                    VALUES (:org_id, :lead_lift, :deal_lift, :speed, :efficiency,
                            :marketing, :comp, NOW())
                    ON CONFLICT (organization_id)
                    DO UPDATE SET
                        lead_conversion_lift = EXCLUDED.lead_conversion_lift,
                        avg_deal_size_lift = EXCLUDED.avg_deal_size_lift,
                        closing_speed_factor = EXCLUDED.closing_speed_factor,
                        tech_efficiency_gain = EXCLUDED.tech_efficiency_gain,
                        marketing_lead_boost = EXCLUDED.marketing_lead_boost,
                        comp_percentage = EXCLUDED.comp_percentage,
                        updated_at = NOW()
                """),
                {
                    "org_id": organization_id,
                    "lead_lift": config.lead_conversion_lift,
                    "deal_lift": config.avg_deal_size_lift,
                    "speed": config.closing_speed_factor,
                    "efficiency": config.tech_efficiency_gain,
                    "marketing": config.marketing_lead_boost,
                    "comp": config.comp_percentage
                }
            )
            conn.commit()

        return self.get_calculator_config(organization_id)

    def calculate_production_impact(
        self,
        input_data: CalculatorInput,
        config: Optional[CalculatorConfig] = None
    ) -> CalculatorResult:
        """Calculate projected production impact."""
        if config is None:
            config = self.get_calculator_config()

        current_volume = input_data.current_volume
        current_units = input_data.current_units

        # Calculate average if not provided
        if input_data.avg_loan_amount:
            avg_loan = input_data.avg_loan_amount
        elif current_units > 0:
            avg_loan = current_volume / current_units
        else:
            avg_loan = 350000  # Default average

        # Calculate projections
        # Volume impact: conversion + deal size + marketing
        volume_multiplier = (
            config.lead_conversion_lift *
            config.avg_deal_size_lift *
            config.marketing_lead_boost
        )
        projected_volume = current_volume * volume_multiplier

        # Units impact: conversion + efficiency + marketing
        units_multiplier = (
            config.lead_conversion_lift *
            config.tech_efficiency_gain *
            config.marketing_lead_boost
        )
        projected_units = int(current_units * units_multiplier)

        # Calculate earnings
        current_earnings = current_volume * config.comp_percentage
        potential_earnings = projected_volume * config.comp_percentage

        return CalculatorResult(
            current_volume=current_volume,
            current_units=current_units,
            projected_volume=round(projected_volume, 2),
            projected_units=projected_units,
            volume_increase=round(projected_volume - current_volume, 2),
            volume_increase_pct=round(((projected_volume / current_volume) - 1) * 100, 1) if current_volume > 0 else 0,
            unit_increase=projected_units - current_units,
            unit_increase_pct=round(((projected_units / current_units) - 1) * 100, 1) if current_units > 0 else 0,
            potential_earnings=round(potential_earnings, 2),
            current_earnings=round(current_earnings, 2),
            earnings_increase=round(potential_earnings - current_earnings, 2),
            earnings_increase_pct=round(((potential_earnings / current_earnings) - 1) * 100, 1) if current_earnings > 0 else 0
        )


# Singleton instance
recruit_assessment_service = RecruitAssessmentService()
